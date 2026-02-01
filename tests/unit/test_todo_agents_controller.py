from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

import pytest

from app.domain.todo_agents.controllers.todo_agents import TodoAgentController
from app.domain.todo_agents.schemas import AgentTodoRequest


class StubTodoAgentService:
    """Stub service returning deterministic streaming events."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def stream_chat_with_agent(
        self,
        *,
        user_id: str,
        message: str,
        session_id: str,
        user_timezone: str | None = None,
        agent_name: str = "TodoAssistant",
    ) -> "AsyncGenerator[dict[str, Any], None]":
        self.calls.append(
            {
                "user_id": user_id,
                "message": message,
                "session_id": session_id,
                "user_timezone": user_timezone,
                "agent_name": agent_name,
            }
        )

        yield {"event": "session_initialized", "data": {"session_id": session_id}}
        yield {"event": "message", "data": {"content": "Working on it"}}
        yield {"event": "completed", "data": {"final_message": "Done"}}
        yield {"event": "history", "data": [{"role": "assistant", "content": "Done"}]}


class ErrorStubTodoAgentService(StubTodoAgentService):
    async def stream_chat_with_agent(
        self,
        *,
        user_id: str,
        message: str,
        session_id: str,
        user_timezone: str | None = None,
        agent_name: str = "TodoAssistant",
    ) -> "AsyncGenerator[dict[str, Any], None]":
        self.calls.append(
            {
                "user_id": user_id,
                "message": message,
                "session_id": session_id,
                "user_timezone": user_timezone,
                "agent_name": agent_name,
            }
        )

        yield {
            "event": "error",
            "data": {"status": "error", "message": "Something went wrong"},
        }


@pytest.mark.anyio
async def test_agent_create_todo_stream_success() -> None:
    controller = SimpleNamespace()
    service = StubTodoAgentService()
    user = SimpleNamespace(id=123)

    request = AgentTodoRequest(
        messages=[{"role": "user", "content": "Create a todo"}],
        session_id=None,
        session_name=None,
    )

    handler = TodoAgentController.agent_create_todo_stream

    response = await handler.fn(  # type: ignore[attr-defined]
        controller,
        current_user=user,
        data=request,
        todo_agent_service=service,
    )

    events = [chunk.decode() async for chunk in response.iterator]

    assert any("event: message" in event for event in events)
    assert any("Working on it" in event for event in events)
    assert service.calls == [
        {
            "user_id": "123",
            "message": "Create a todo",
            "session_id": "user_123_todo_agent",
            "user_timezone": None,
            "agent_name": "TodoAssistant",
        }
    ]


@pytest.mark.anyio
async def test_agent_create_todo_stream_missing_message() -> None:
    controller = SimpleNamespace()
    service = StubTodoAgentService()
    user = SimpleNamespace(id=456)

    request = AgentTodoRequest(
        messages=[{"role": "system", "content": ""}],
        session_id=None,
        session_name=None,
    )

    handler = TodoAgentController.agent_create_todo_stream

    response = await handler.fn(  # type: ignore[attr-defined]
        controller,
        current_user=user,
        data=request,
        todo_agent_service=service,
    )

    chunks = [chunk.decode() async for chunk in response.iterator]

    assert len(chunks) == 1
    assert "event: error" in chunks[0]
    assert "No user message" in chunks[0]
    assert service.calls == []
