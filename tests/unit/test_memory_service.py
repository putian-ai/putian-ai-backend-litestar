from __future__ import annotations

import pytest
from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import models as m
from app.domain.memory.schemas import MemoryDelta, MemoryDeltaAction, MemoryScope
from app.domain.memory.services import MemoryService


@pytest.fixture(name="sessionmaker")
async def fx_sessionmaker() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(UUIDAuditBase.registry.metadata.create_all)

    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.anyio
async def test_apply_memory_deltas_add_user(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with MemoryService.new(sessionmaker()) as service:
        user = m.User(email="user@example.com")
        service.repository.session.add(user)
        await service.repository.session.commit()
        await service.repository.session.refresh(user)

        deltas = [
            MemoryDelta(
                action=MemoryDeltaAction.ADD,
                scope=MemoryScope.USER,
                section="preferences",
                content="Prefer morning workouts",
                metadata={"source": "summary"},
            )
        ]

        await service.apply_memory_deltas(deltas, user.id)
        memories = await service.list_user_memory(user.id)

        assert len(memories) == 1
        assert memories[0].content == "Prefer morning workouts"
        assert memories[0].user_id == user.id


@pytest.mark.anyio
async def test_apply_memory_deltas_tag_update(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with MemoryService.new(sessionmaker()) as service:
        user = m.User(email="user2@example.com")
        service.repository.session.add(user)
        await service.repository.session.commit()
        await service.repository.session.refresh(user)

        memory = await service.create(
            {
                "is_global": False,
                "user_id": user.id,
                "content": "Avoid late meetings",
                "section": "preferences",
                "metadata_json": {"source": "summary"},
            }
        )

        deltas = [
            MemoryDelta(
                action=MemoryDeltaAction.TAG,
                scope=MemoryScope.USER,
                target_id=str(memory.id),
                helpful_delta=2,
            )
        ]

        await service.apply_memory_deltas(deltas, user.id)
        updated = await service.get(memory.id)

        assert updated.helpful_count == 2
