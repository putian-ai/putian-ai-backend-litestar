from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.domain.memory.schemas import MemoryContextResult
from app.domain.todo_agents.services import TodoAgentService


class StubRateLimitService:
    async def check_and_increment_usage(self, user_id: Any, quota_service: Any) -> None:
        return None


class StubMemoryAgentService:
    def __init__(self) -> None:
        self.updated: list[tuple[Any, str, str]] = []

    async def build_memory_context(self, user_id: Any, user_message: str) -> MemoryContextResult:
        return MemoryContextResult(context="Prefer morning", selected_ids=[])

    async def update_memory_after_response(self, user_id: Any, user_message: str, agent_response: str) -> None:
        self.updated.append((user_id, user_message, agent_response))


class StubAgent:
    def __init__(self) -> None:
        self.instructions = "BASE"
        self.cloned_with: str | None = None

    def clone(self, instructions: str) -> "StubAgent":
        cloned = StubAgent()
        cloned.instructions = instructions
        self.cloned_with = instructions
        return cloned


@pytest.mark.anyio
async def test_memory_context_injected(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    agent = StubAgent()

    async def fake_run(run_agent: Any, input_payload: Any, session: Any, max_turns: int = 20) -> Any:
        return SimpleNamespace(final_output="ok")

    monkeypatch.setattr("app.domain.todo_agents.services.get_agent_by_name", lambda _: agent)
    monkeypatch.setattr("app.domain.todo_agents.services.Runner.run", fake_run)

    memory_agent_service = StubMemoryAgentService()
    service = TodoAgentService(
        todo_service=SimpleNamespace(),
        tag_service=SimpleNamespace(),
        rate_limit_service=StubRateLimitService(),
        quota_service=SimpleNamespace(),
        memory_agent_service=memory_agent_service,
        session_db_path=str(tmp_path / "conversations.db"),
    )

    response = await service.chat_with_agent(
        user_id="12345678-1234-5678-1234-567812345678",
        message="Schedule a workout",
        session_id="user_123_session",
        agent_name="TodoAssistant",
    )

    assert response == "ok"
    assert agent.cloned_with is not None
    assert "MEMORY CONTEXT:" in agent.cloned_with
    assert len(memory_agent_service.updated) == 1
