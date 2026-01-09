from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from arq.connections import RedisSettings

from app.domain.memory.queue import MemoryQueueConfig, MemoryQueueService


@pytest.mark.anyio
async def test_enqueue_memory_update_success(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(ai=SimpleNamespace(MEMORY_ENABLED=True, MEMORY_QUEUE_ENABLED=True))
    monkeypatch.setattr("app.domain.memory.queue.get_settings", lambda: settings)

    class StubRedis:
        async def enqueue_job(self, *args: object, **kwargs: object) -> object:
            return SimpleNamespace(job_id="job-1")

    async def fake_create_pool(*args: object, **kwargs: object) -> StubRedis:
        return StubRedis()

    monkeypatch.setattr("app.domain.memory.queue.create_pool", fake_create_pool)

    config = MemoryQueueConfig(
        redis_settings=RedisSettings(),
        queue_name="memory_updates",
        max_retries=3,
        job_timeout=120,
    )
    service = MemoryQueueService(config=config)

    ok = await service.enqueue_memory_update(
        UUID("12345678-1234-5678-1234-567812345678"),
        "Hello",
        "World",
    )

    assert ok is True


@pytest.mark.anyio
async def test_enqueue_memory_update_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(ai=SimpleNamespace(MEMORY_ENABLED=True, MEMORY_QUEUE_ENABLED=False))
    monkeypatch.setattr("app.domain.memory.queue.get_settings", lambda: settings)

    async def fake_create_pool(*args: object, **kwargs: object) -> object:
        raise AssertionError("create_pool should not be called when queue is disabled")

    monkeypatch.setattr("app.domain.memory.queue.create_pool", fake_create_pool)

    config = MemoryQueueConfig(
        redis_settings=RedisSettings(),
        queue_name="memory_updates",
        max_retries=3,
        job_timeout=120,
    )
    service = MemoryQueueService(config=config)

    ok = await service.enqueue_memory_update(
        UUID("12345678-1234-5678-1234-567812345678"),
        "Hello",
        "World",
    )

    assert ok is False
