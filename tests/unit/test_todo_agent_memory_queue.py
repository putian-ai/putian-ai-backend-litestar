from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from app.domain.todo_agents.services import TodoAgentService


class StubMemoryAgentService:
    def __init__(self) -> None:
        self.updated: list[tuple[Any, str, str]] = []

    async def update_memory_after_response(self, user_id: Any, user_message: str, agent_response: str) -> None:
        self.updated.append((user_id, user_message, agent_response))


class StubMemoryQueueService:
    def __init__(self, result: bool) -> None:
        self.result = result
        self.calls: list[tuple[Any, str, str]] = []

    async def enqueue_memory_update(self, user_id: Any, user_message: str, agent_response: str) -> bool:
        self.calls.append((user_id, user_message, agent_response))
        return self.result


@pytest.mark.anyio
async def test_memory_update_uses_queue_when_available(tmp_path: Any) -> None:
    memory_agent_service = StubMemoryAgentService()
    memory_queue_service = StubMemoryQueueService(result=True)

    service = TodoAgentService(
        todo_service=SimpleNamespace(),
        tag_service=SimpleNamespace(),
        rate_limit_service=SimpleNamespace(),
        quota_service=SimpleNamespace(),
        memory_agent_service=memory_agent_service,
        memory_queue_service=memory_queue_service,
        session_db_path=str(tmp_path / "conversations.db"),
    )

    await service._update_memory_after_response(
        UUID("12345678-1234-5678-1234-567812345678"),
        "User message",
        "Agent response",
    )

    assert len(memory_queue_service.calls) == 1
    assert memory_agent_service.updated == []


@pytest.mark.anyio
async def test_memory_update_falls_back_when_queue_fails(tmp_path: Any) -> None:
    memory_agent_service = StubMemoryAgentService()
    memory_queue_service = StubMemoryQueueService(result=False)

    service = TodoAgentService(
        todo_service=SimpleNamespace(),
        tag_service=SimpleNamespace(),
        rate_limit_service=SimpleNamespace(),
        quota_service=SimpleNamespace(),
        memory_agent_service=memory_agent_service,
        memory_queue_service=memory_queue_service,
        session_db_path=str(tmp_path / "conversations.db"),
    )

    await service._update_memory_after_response(
        UUID("12345678-1234-5678-1234-567812345678"),
        "User message",
        "Agent response",
    )

    assert len(memory_queue_service.calls) == 1
    assert len(memory_agent_service.updated) == 1
