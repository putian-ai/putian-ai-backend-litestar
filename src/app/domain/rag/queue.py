"""Redis-backed queue for RAG indexing jobs."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.worker import Worker, create_worker
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.domain.rag.lightrag_client import create_light_rag_client
from app.domain.rag.services import RagDocumentService

if TYPE_CHECKING:
    from litestar import Litestar

logger = structlog.get_logger()


@dataclass(frozen=True)
class RagQueueConfig:
    redis_settings: RedisSettings
    queue_name: str
    max_retries: int
    job_timeout: int


class RagQueueService:
    """Enqueue RAG indexing jobs into Redis via ARQ."""

    def __init__(self, config: RagQueueConfig) -> None:
        self._config = config
        self._redis: ArqRedis | None = None
        self._lock = asyncio.Lock()

    async def enqueue_document_index(self, *, user_id: UUID, document_id: UUID) -> bool:
        """Queue indexing after a successful upload."""
        return await self._enqueue_job(
            user_id=user_id,
            document_id=document_id,
            reason="upload",
        )

    async def enqueue_user_rebuild(self, *, user_id: UUID) -> bool:
        """Queue full rebuild after deletion."""
        return await self._enqueue_job(
            user_id=user_id,
            document_id=None,
            reason="rebuild",
        )

    async def close(self) -> None:
        if self._redis is None:
            return
        await self._redis.close(close_connection_pool=True)
        self._redis = None

    def get_unavailable_reason(self) -> str | None:
        settings = get_settings()

        if not settings.ai.RAG_ENABLED:
            return "RAG is disabled"
        if not settings.ai.RAG_QUEUE_ENABLED:
            return "RAG queue is disabled"

        missing_credentials: list[str] = []
        if not settings.ai.DEEPSEEK_API_KEY:
            missing_credentials.append("DEEPSEEK_API_KEY")
        if not settings.ai.SILICON_FLOW_API_KEY:
            missing_credentials.append("SILICON_FLOW_API_KEY")

        if missing_credentials:
            joined = ", ".join(missing_credentials)
            return f"Missing RAG provider credentials: {joined}"

        return None

    async def _enqueue_job(
        self,
        *,
        user_id: UUID,
        document_id: UUID | None,
        reason: str,
    ) -> bool:
        unavailable_reason = self.get_unavailable_reason()
        if unavailable_reason is not None:
            logger.warning(
                "RAG indexing skipped due to unmet prerequisites",
                user_id=str(user_id),
                reason=unavailable_reason,
            )
            return False

        try:
            redis = await self._get_pool()
            job = await redis.enqueue_job(
                "process_rag_index_job",
                str(user_id),
                str(document_id) if document_id else None,
                reason,
                _queue_name=self._config.queue_name,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("RAG indexing enqueue failed", error=str(exc), user_id=str(user_id))
            return False

        if job is None:
            logger.warning("RAG indexing enqueue deduplicated", user_id=str(user_id), reason=reason)
            return False

        logger.info("RAG indexing enqueued", user_id=str(user_id), reason=reason, job_id=job.job_id)
        return True

    async def _get_pool(self) -> ArqRedis:
        if self._redis is not None:
            return self._redis
        async with self._lock:
            if self._redis is None:
                self._redis = await create_pool(
                    self._config.redis_settings,
                    default_queue_name=self._config.queue_name,
                )
        return self._redis


def _build_queue_config() -> RagQueueConfig:
    settings = get_settings()
    return RagQueueConfig(
        redis_settings=RedisSettings.from_dsn(settings.ai.RAG_QUEUE_URL),
        queue_name=settings.ai.RAG_QUEUE_NAME,
        max_retries=settings.ai.RAG_QUEUE_MAX_RETRIES,
        job_timeout=settings.ai.RAG_QUEUE_JOB_TIMEOUT,
    )


@lru_cache(maxsize=1)
def get_rag_queue_service() -> RagQueueService:
    return RagQueueService(config=_build_queue_config())


def _build_worker_settings() -> dict[str, Any]:
    config = _build_queue_config()
    return {
        "functions": [process_rag_index_job],
        "redis_settings": config.redis_settings,
        "queue_name": config.queue_name,
        "max_tries": config.max_retries,
        "job_timeout": config.job_timeout,
        "handle_signals": False,
        "max_jobs": 1,
    }


async def process_rag_index_job(
    _: dict[str, Any],
    user_id: str,
    document_id: str | None,
    reason: str,
) -> None:
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        logger.warning("RAG index job received invalid user_id", user_id=user_id)
        return

    settings = get_settings()
    session_factory = async_sessionmaker(settings.db.get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        service = RagDocumentService(session=session)
        client = create_light_rag_client()
        await service.process_index_job(user_id=user_uuid, client=client)


async def start_rag_worker(app: Litestar | None = None) -> Worker | None:
    settings = get_settings()
    if not settings.ai.RAG_ENABLED or not settings.ai.RAG_QUEUE_ENABLED or not settings.ai.RAG_QUEUE_WORKER_ENABLED:
        return None
    if not settings.ai.DEEPSEEK_API_KEY or not settings.ai.SILICON_FLOW_API_KEY:
        logger.info("RAG queue worker skipped due to missing provider credentials")
        return None

    worker = create_worker(_build_worker_settings())
    task = asyncio.create_task(worker.async_run())

    def _log_worker_exit(done_task: asyncio.Task[None]) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            exc = done_task.exception()
            if exc:
                logger.error("RAG queue worker stopped", error=str(exc))

    task.add_done_callback(_log_worker_exit)

    if app is not None:
        app.state.rag_queue_worker = worker
        app.state.rag_queue_worker_task = task

    logger.info("RAG queue worker started")
    return worker


async def stop_rag_worker(app: Litestar | None = None) -> None:
    worker: Worker | None = None
    task: asyncio.Task[None] | None = None

    if app is not None:
        worker = getattr(app.state, "rag_queue_worker", None)
        task = getattr(app.state, "rag_queue_worker_task", None)

    if worker is not None:
        await worker.close()

    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    await close_rag_queue_service()
    logger.info("RAG queue worker stopped")


async def close_rag_queue_service() -> None:
    service = get_rag_queue_service()
    await service.close()
