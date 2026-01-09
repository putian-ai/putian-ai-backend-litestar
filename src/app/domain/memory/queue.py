"""Redis-backed queue for memory updates."""

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
from app.domain.memory.agent_service import MemoryAgentService
from app.domain.memory.services import MemoryService

if TYPE_CHECKING:
    from litestar import Litestar

logger = structlog.get_logger()


@dataclass(frozen=True)
class MemoryQueueConfig:
    redis_settings: RedisSettings
    queue_name: str
    max_retries: int
    job_timeout: int


class MemoryQueueService:
    """Enqueue memory updates into Redis via ARQ."""

    def __init__(self, config: MemoryQueueConfig) -> None:
        self._config = config
        self._redis: ArqRedis | None = None
        self._lock = asyncio.Lock()

    async def enqueue_memory_update(
        self,
        user_id: UUID,
        user_message: str,
        agent_response: str,
    ) -> bool:
        settings = get_settings()
        if not settings.ai.MEMORY_ENABLED or not settings.ai.MEMORY_QUEUE_ENABLED:
            return False

        try:
            redis = await self._get_pool()
            job = await redis.enqueue_job(
                "process_memory_update",
                str(user_id),
                user_message,
                agent_response,
                _queue_name=self._config.queue_name,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Memory update enqueue failed", error=str(exc))
            return False

        if job is None:
            logger.warning("Memory update enqueue deduplicated", user_id=str(user_id))
            return False

        logger.info("Memory update enqueued", user_id=str(user_id), job_id=job.job_id)
        return True

    async def close(self) -> None:
        if self._redis is None:
            return
        await self._redis.close(close_connection_pool=True)
        self._redis = None

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


def _build_queue_config() -> MemoryQueueConfig:
    settings = get_settings()
    return MemoryQueueConfig(
        redis_settings=RedisSettings.from_dsn(settings.ai.MEMORY_QUEUE_URL),
        queue_name=settings.ai.MEMORY_QUEUE_NAME,
        max_retries=settings.ai.MEMORY_QUEUE_MAX_RETRIES,
        job_timeout=settings.ai.MEMORY_QUEUE_JOB_TIMEOUT,
    )


@lru_cache(maxsize=1)
def get_memory_queue_service() -> MemoryQueueService:
    return MemoryQueueService(config=_build_queue_config())


def _build_worker_settings() -> dict[str, Any]:
    config = _build_queue_config()
    return {
        "functions": [process_memory_update],
        "redis_settings": config.redis_settings,
        "queue_name": config.queue_name,
        "max_tries": config.max_retries,
        "job_timeout": config.job_timeout,
        "handle_signals": False,
    }


async def process_memory_update(
    _: dict[str, Any],
    user_id: str,
    user_message: str,
    agent_response: str,
) -> None:
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        logger.warning("Memory update job received invalid user id", user_id=user_id)
        return

    settings = get_settings()
    session_factory = async_sessionmaker(settings.db.get_engine(), expire_on_commit=False)

    async with session_factory() as session:
        memory_service = MemoryService(session=session)
        agent_service = MemoryAgentService(memory_service=memory_service)
        await agent_service.update_memory_after_response(user_uuid, user_message, agent_response)


async def start_memory_worker(app: Litestar | None = None) -> Worker | None:
    settings = get_settings()
    if (
        not settings.ai.MEMORY_ENABLED
        or not settings.ai.MEMORY_QUEUE_ENABLED
        or not settings.ai.MEMORY_QUEUE_WORKER_ENABLED
    ):
        return None

    worker = create_worker(_build_worker_settings())
    task = asyncio.create_task(worker.async_run())

    def _log_worker_exit(done_task: asyncio.Task[None]) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            exc = done_task.exception()
            if exc:
                logger.error("Memory queue worker stopped", error=str(exc))

    task.add_done_callback(_log_worker_exit)

    if app is not None:
        app.state.memory_queue_worker = worker
        app.state.memory_queue_worker_task = task

    logger.info("Memory queue worker started")
    return worker


async def stop_memory_worker(app: Litestar | None = None) -> None:
    worker: Worker | None = None
    task: asyncio.Task[None] | None = None

    if app is not None:
        worker = getattr(app.state, "memory_queue_worker", None)
        task = getattr(app.state, "memory_queue_worker_task", None)

    if worker is not None:
        await worker.close()

    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    await close_memory_queue_service()
    logger.info("Memory queue worker stopped")


async def close_memory_queue_service() -> None:
    service = get_memory_queue_service()
    await service.close()
