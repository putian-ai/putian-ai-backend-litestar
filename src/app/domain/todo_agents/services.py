"""Services for todo_agents domain."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from agents import ItemHelpers, Runner, SQLiteSession
from openai.types.responses import ResponseTextDeltaEvent

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.domain.memory.agent_service import MemoryAgentService
    from app.domain.memory.queue import MemoryQueueService
    from app.domain.quota.services import UserUsageQuotaService
    from app.domain.todo.services import TagService, TodoService
    from app.lib.rate_limit_service import RateLimitService

from app.lib.exceptions import RateLimitExceededException

from .tools.agent_factory import get_agent_by_name
from .tools.tool_context import set_agent_context

__all__ = (
    "TodoAgentService",
    "create_todo_agent_service",
)

# Tools & agent implementation imported from todo_agent_tools.


class TodoAgentService:
    """Service class for managing todo agent interactions with SQLite session persistence.

    This class uses the official Agents SDK SQLiteSession for persistent conversation
    history, eliminating the need for manual session management.
    """

    def __init__(
        self,
        todo_service: "TodoService",
        tag_service: "TagService",
        rate_limit_service: "RateLimitService",
        quota_service: "UserUsageQuotaService",
        memory_agent_service: "MemoryAgentService | None" = None,
        memory_queue_service: "MemoryQueueService | None" = None,
        session_db_path: str = "conversations.db",
    ) -> None:
        """Initialize the service with required dependencies.

        Args:
            todo_service: Service for todo operations
            tag_service: Service for tag operations
            rate_limit_service: Service for rate limiting
            quota_service: Service for quota management
            memory_queue_service: Optional queue service for async memory updates
            session_db_path: Path to SQLite database for storing conversations
        """
        self.todo_service = todo_service
        self.tag_service = tag_service
        self.rate_limit_service = rate_limit_service
        self.quota_service = quota_service
        self.memory_agent_service = memory_agent_service
        self.memory_queue_service = memory_queue_service
        self.session_db_path = session_db_path
        self._sessions: dict[str, SQLiteSession] = {}

    async def chat_with_agent(
        self,
        user_id: str,
        message: str,
        session_id: str | None = None,
        agent_name: str = "TodoAssistant",
    ) -> str:
        """Send a message to the todo agent and get a response with persistent conversation history.

        Args:
            user_id: ID of the user sending the message
            message: The message to send to the agent
            session_id: Optional session ID. If None, a new unique session ID will be generated
            agent_name: Optional agent name to route to a specialized agent. Defaults to TodoAssistant.

        Returns:
            The agent's response, or an error message if user has exceeded their monthly quota
        """
        # Check rate limit before processing
        try:
            await self.rate_limit_service.check_and_increment_usage(
                UUID(user_id), self.quota_service
            )
        except RateLimitExceededException as e:
            # Return user-friendly message when usage quota is exceeded
            return f"You have exceeded your monthly usage limit. {e.detail}"

        # Generate unique session ID if not provided
        if session_id is None:
            session_id = f"user_{user_id}_{uuid.uuid4().hex[:8]}"

        # Ensure tools have service context for this user
        set_agent_context(
            self.todo_service,
            self.tag_service,
            UUID(user_id),
            quota_service=self.quota_service,
            rate_limit_service=self.rate_limit_service,
        )

        # Get or create SQLite session
        if session_id not in self._sessions:
            self._sessions[session_id] = SQLiteSession(
                session_id, self.session_db_path)

        session = self._sessions[session_id]

        # Get the requested todo agent (with tools)
        agent = get_agent_by_name(agent_name)
        memory_context = await self._build_memory_context(UUID(user_id), message)
        agent, input_payload = self._prepare_agent_run(agent, message, memory_context)

        # Run the agent with session - conversation history is automatically managed!
        result = await Runner.run(agent, input_payload, session=session, max_turns=20)
        final_output = str(result.final_output)
        await self._update_memory_after_response(UUID(user_id), message, final_output)

        return final_output

    async def stream_chat_with_agent(
        self,
        user_id: str,
        message: str,
        session_id: str | None = None,
        *,
        history_limit: int = 10,
        agent_name: str = "TodoAssistant",
    ) -> "AsyncGenerator[dict[str, Any], None]":
        """Stream agent responses as structured events.

        Args:
            user_id: ID of the user sending the message.
            message: Message to send to the agent.
            session_id: Optional existing session identifier.
            history_limit: Reserved for compatibility; streaming no longer emits
                history events.
            agent_name: Optional agent name to route to a specialized agent. Defaults to TodoAssistant.

        Yields:
            Dictionaries containing ``event`` and ``data`` keys suitable for
            conversion into Server-Sent Events.
        """

        # NOTE: Rate limit checks are intentionally disabled for streaming to avoid
        # double-counting usage. Re-enable by emitting a ``rate_limit_exceeded``
        # event similar to ``chat_with_agent`` once streaming quotas are supported.

        # Generate unique session ID if not provided
        if session_id is None:
            session_id = f"user_{user_id}_{uuid.uuid4().hex[:8]}"

        yield {
            "event": "session_initialized",
            "data": {"session_id": session_id},
        }

        # Ensure tools have service context for this user
        set_agent_context(
            self.todo_service,
            self.tag_service,
            UUID(user_id),
            quota_service=self.quota_service,
            rate_limit_service=self.rate_limit_service,
        )

        # Get or create SQLite session
        if session_id not in self._sessions:
            self._sessions[session_id] = SQLiteSession(
                session_id, self.session_db_path
            )

        session = self._sessions[session_id]

        # Get the requested todo agent (with tools)
        agent = get_agent_by_name(agent_name)
        memory_context = await self._build_memory_context(UUID(user_id), message)
        agent, input_payload = self._prepare_agent_run(agent, message, memory_context)

        stream = Runner.run_streamed(
            agent,
            input_payload,
            session=session,
            max_turns=20,
        )

        last_message: str | None = None
        last_message_chunks: list[str] = []

        try:
            async for event in stream.stream_events():
                handled, payloads, message_update = self._dispatch_stream_event(
                    event,
                    last_message_chunks,
                )

                if message_update is not None:
                    last_message = message_update

                if handled:
                    for payload in payloads:
                        yield payload
                    continue

                yield {
                    "event": "event",
                    "data": {
                        "type": event.type,
                    },
                }

            # Stream completed, include summary event
            yield {
                "event": "completed",
                "data": {
                    "final_message": last_message
                    if last_message is not None
                    else ("".join(last_message_chunks) if last_message_chunks else None),
                },
            }

        except Exception as exc:  # noqa: BLE001  # pragma: no cover - defensive
            yield {
                "event": "error",
                "data": {
                    "message": f"Agent streaming failed: {exc!s}",
                },
            }
            return

        final_message = last_message if last_message is not None else "".join(last_message_chunks)
        if final_message:
            await self._update_memory_after_response(UUID(user_id), message, final_message)

    def _dispatch_stream_event(
        self,
        event: Any,
        last_message_chunks: list[str],
    ) -> tuple[bool, list[dict[str, Any]], str | None]:
        handled, payloads, message_update = self._handle_raw_response_event(
            event,
            last_message_chunks,
        )
        if handled:
            return handled, payloads, message_update

        if event.type == "agent_updated_stream_event":
            agent_name = getattr(
                getattr(event, "new_agent", None), "name", None)
            return (
                True,
                [
                    {
                        "event": "agent_updated",
                        "data": {"name": agent_name},
                    }
                ],
                None,
            )

        if event.type == "run_item_stream_event":
            return self._handle_run_item_stream_event(event)

        return False, [], None

    @staticmethod
    def _handle_raw_response_event(
        event: Any,
        last_message_chunks: list[str],
    ) -> tuple[bool, list[dict[str, Any]], str | None]:
        if event.type != "raw_response_event":
            return False, [], None

        event_data = getattr(event, "data", None)
        if not isinstance(event_data, ResponseTextDeltaEvent):
            return True, [], None

        delta_obj = getattr(event_data, "delta", None)
        if delta_obj is None:
            return True, [], None

        if isinstance(delta_obj, str):
            delta_text = delta_obj
        else:
            delta_text = getattr(delta_obj, "text", None)
            if delta_text is None and delta_obj is not None:
                delta_text = str(delta_obj)

        if not delta_text:
            return True, [], None

        last_message_chunks.append(delta_text)
        return (
            True,
            [
                {
                    "event": "message_delta",
                    "data": {
                        "content": delta_text,
                    },
                }
            ],
            "".join(last_message_chunks),
        )

    @staticmethod
    def _handle_run_item_stream_event(
        event: Any,
    ) -> tuple[bool, list[dict[str, Any]], str | None]:
        if event.type != "run_item_stream_event":
            return False, [], None

        item_type = getattr(event.item, "type", "")

        if item_type == "tool_call_item":
            return (
                True,
                [
                    {
                        "event": "tool_call",
                        "data": {
                            "tool_name": getattr(event.item, "tool_name", ""),
                            "arguments": getattr(event.item, "arguments", {}),
                        },
                    }
                ],
                None,
            )

        if item_type == "tool_call_output_item":
            return (
                True,
                [
                    {
                        "event": "tool_result",
                        "data": {
                            "output": getattr(event.item, "output", None),
                        },
                    }
                ],
                None,
            )

        if item_type == "message_output_item":
            message_output = ItemHelpers.text_message_output(
                cast("Any", event.item))
            return (
                True,
                [],
                message_output,
            )

        return False, [], None

    async def get_session_history(
        self,
        session_id: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get conversation history for a session.

        Args:
            session_id: The session ID to get history for
            limit: Maximum number of items to retrieve (None for all)

        Returns:
            List of conversation items in chronological order
        """
        if session_id not in self._sessions:
            # Return empty history if session doesn't exist
            return []

        session = self._sessions[session_id]
        items = await session.get_items(limit=limit)

        # Convert items to dict format for consistency
        return [dict(item) for item in items]

    async def clear_session_history(
        self,
        session_id: str,
    ) -> None:
        """Clear all messages from a session.

        Args:
            session_id: The session ID to clear
        """
        if session_id in self._sessions:
            session = self._sessions[session_id]
            await session.clear_session()

    async def _build_memory_context(
        self,
        user_id: UUID,
        message: str,
    ) -> str | None:
        if not self.memory_agent_service:
            return None
        result = await self.memory_agent_service.build_memory_context(user_id, message)
        if not result:
            return None
        if not result.context.strip():
            return None
        return result.context.strip()

    async def _update_memory_after_response(
        self,
        user_id: UUID,
        message: str,
        agent_response: str,
    ) -> None:
        if not self.memory_agent_service:
            return
        if self.memory_queue_service:
            enqueued = await self.memory_queue_service.enqueue_memory_update(
                user_id,
                message,
                agent_response,
            )
            if enqueued:
                return
        await self.memory_agent_service.update_memory_after_response(user_id, message, agent_response)

    @staticmethod
    def _prepare_agent_run(
        agent: Any,
        message: str,
        memory_context: str | None,
    ) -> tuple[Any, str | list[dict[str, str]]]:
        if not memory_context:
            return agent, message

        if isinstance(agent.instructions, str):
            enhanced_instructions = "\n\n".join(
                [agent.instructions, "MEMORY CONTEXT:", memory_context]
            )
            return agent.clone(instructions=enhanced_instructions), message

        system_message = {"role": "system", "content": f"MEMORY CONTEXT:\n{memory_context}"}
        user_message = {"role": "user", "content": message}
        return agent, [system_message, user_message]

    def list_active_sessions(self) -> list[str]:
        """List all active session IDs currently in memory.

        Returns:
            List of active session IDs
        """
        return list(self._sessions.keys())

    async def create_new_session(self, user_id: str) -> str:
        """Create a new session with a unique ID.

        Args:
            user_id: The user ID to create the session for

        Returns:
            The new session ID
        """
        session_id = f"user_{user_id}_{uuid.uuid4().hex[:8]}"
        self._sessions[session_id] = SQLiteSession(
            session_id, self.session_db_path)
        return session_id


def create_todo_agent_service(
    todo_service: "TodoService",
    tag_service: "TagService",
    rate_limit_service: "RateLimitService",
    quota_service: "UserUsageQuotaService",
    memory_agent_service: "MemoryAgentService | None" = None,
    memory_queue_service: "MemoryQueueService | None" = None,
    session_db_path: str = "conversations.db",
) -> TodoAgentService:
    """Factory function to create TodoAgentService with proper dependencies.

    Args:
        todo_service: Service for todo operations
        tag_service: Service for tag operations
        rate_limit_service: Service for rate limiting
        quota_service: Service for quota management
        memory_queue_service: Optional queue service for async memory updates
        session_db_path: Path to SQLite database for storing conversations

    Returns:
        Configured TodoAgentService instance
    """
    return TodoAgentService(
        todo_service=todo_service,
        tag_service=tag_service,
        rate_limit_service=rate_limit_service,
        quota_service=quota_service,
        memory_agent_service=memory_agent_service,
        memory_queue_service=memory_queue_service,
        session_db_path=session_db_path,
    )
