from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.domain.memory.agent_service import MemoryAgentService
from app.domain.memory.schemas import MemoryContextResult, MemoryDelta, MemoryDeltaAction, MemoryScope, MemoryUpdateResult


class StubMemoryService:
    def __init__(self, bullets: list[Any]) -> None:
        self.bullets = bullets
        self.applied: list[MemoryDelta] = []

    async def list_effective_memory(self, user_id: Any, limit: int | None = None) -> list[Any]:
        return self.bullets[: limit or len(self.bullets)]

    async def apply_memory_deltas(self, deltas: list[MemoryDelta], user_id: Any) -> None:
        self.applied.extend(deltas)


@pytest.mark.anyio
async def test_build_memory_context(monkeypatch: pytest.MonkeyPatch) -> None:
    bullets = [
        SimpleNamespace(
            id="mem-1",
            is_global=False,
            section="preferences",
            content="Prefer morning workouts",
            helpful_count=1,
            harmful_count=0,
        )
    ]
    service = StubMemoryService(bullets)
    agent_service = MemoryAgentService(service)

    async def fake_run(agent: Any, payload: str, max_turns: int = 5) -> Any:
        return SimpleNamespace(
            final_output=MemoryContextResult(context="User prefers mornings.", selected_ids=["mem-1"])
        )

    monkeypatch.setattr("app.domain.memory.agent_service.Runner.run", fake_run)

    result = await agent_service.build_memory_context(
        user_id=SimpleNamespace(), user_message="Schedule a workout"
    )

    assert result is not None
    assert result.context == "User prefers mornings."


@pytest.mark.anyio
async def test_update_memory_after_response(monkeypatch: pytest.MonkeyPatch) -> None:
    bullets: list[Any] = []
    service = StubMemoryService(bullets)
    agent_service = MemoryAgentService(service)

    async def fake_run(agent: Any, payload: str, max_turns: int = 5) -> Any:
        return SimpleNamespace(
            final_output=MemoryUpdateResult(
                deltas=[
                    MemoryDelta(
                        action=MemoryDeltaAction.ADD,
                        scope=MemoryScope.USER,
                        section="preferences",
                        content="Prefers mornings",
                    )
                ]
            )
        )

    monkeypatch.setattr("app.domain.memory.agent_service.Runner.run", fake_run)

    await agent_service.update_memory_after_response(
        user_id=SimpleNamespace(),
        user_message="Schedule a workout",
        agent_response="Sure, I will schedule it in the morning.",
    )

    assert len(service.applied) == 1
    assert service.applied[0].content == "Prefers mornings"
