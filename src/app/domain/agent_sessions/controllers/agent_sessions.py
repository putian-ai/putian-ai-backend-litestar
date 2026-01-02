"""Controllers for agent session management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from litestar import Controller, delete, get, patch, post, put
from litestar.di import Provide
from litestar.params import Dependency, Parameter

from app.domain.agent_sessions import urls
from app.domain.agent_sessions.deps import provide_agent_session_service, provide_session_message_service
from app.domain.agent_sessions.schemas import (
    AgentSessionCreate,
    AgentSessionSchema,
    AgentSessionUpdate,
    SessionConversationRequest,
    SessionConversationResponse,
)
from app.domain.todo.deps import provide_tag_service, provide_todo_service
from app.domain.todo_agents.deps import (
    provide_rate_limit_service,
    provide_todo_agent_service,
    provide_user_usage_quota_service,
)
from app.domain.memory.deps import provide_memory_service
from app.domain.todo_agents.tools.system_instructions import TODO_SYSTEM_INSTRUCTIONS
from app.lib.deps import create_filter_dependencies

if TYPE_CHECKING:
    from advanced_alchemy.filters import FilterTypes
    from advanced_alchemy.service import OffsetPagination

    from app.db import models as m
    from app.domain.agent_sessions.services import AgentSessionService, SessionMessageService
    from app.domain.quota.services import UserUsageQuotaService
    from app.domain.todo_agents.services import TodoAgentService


class AgentSessionController(Controller):
    """Controller for agent session operations."""

    tags = ["Agent Sessions"]
    dependencies = {
        "message_service": Provide(provide_session_message_service),
        "todo_service": Provide(provide_todo_service),
        "tag_service": Provide(provide_tag_service),
        "agent_session_service": Provide(provide_agent_session_service),
        "rate_limit_service": Provide(provide_rate_limit_service),
        "quota_service": Provide(provide_user_usage_quota_service),
        "memory_service": Provide(provide_memory_service),
        "todo_agent_service": Provide(provide_todo_agent_service),
    } | create_filter_dependencies(
        {
            "id_filter": UUID,
            "search": "session_name",
            "pagination_type": "limit_offset",
            "pagination_size": 20,
            "created_at": True,
            "updated_at": True,
            "sort_field": "created_at",
            "sort_order": "desc",
        },
    )

    @get(operation_id="ListAgentSessions", path=urls.AGENT_SESSIONS_LIST)
    async def list_sessions(
        self,
        current_user: "m.User",
        service: AgentSessionService,
        filters: Annotated[list["FilterTypes"], Dependency(skip_validation=True)],
    ) -> "OffsetPagination[AgentSessionSchema]":
        """List all agent sessions for the current user with pagination and filtering."""
        from app.db import models as m
        user_filter = m.AgentSession.user_id == current_user.id
        results, total = await service.list_and_count(user_filter, *filters)
        return service.to_schema(data=results, total=total, schema_type=AgentSessionSchema, filters=filters)

    @post(operation_id="CreateAgentSession", path=urls.AGENT_SESSIONS_CREATE)
    async def create_session(
        self,
        current_user: "m.User",
        service: AgentSessionService,
        data: AgentSessionCreate,
    ) -> AgentSessionSchema:
        """Create a new agent session."""
        session_dict = data.to_dict()
        session_dict["user_id"] = current_user.id
        obj = await service.create(session_dict)
        return service.to_schema(schema_type=AgentSessionSchema, data=obj)

    @get(operation_id="GetAgentSession", path=urls.AGENT_SESSIONS_DETAIL)
    async def get_session(
        self,
        current_user: "m.User",
        service: AgentSessionService,
        session_id: UUID = Parameter(
            title="Session ID", description="The agent session ID"),
    ) -> AgentSessionSchema:
        """Get an agent session by ID."""
        obj = await service.get(session_id)

        # Ensure the session belongs to the current user
        if obj.user_id != current_user.id:
            msg = "Session not found"
            raise ValueError(msg)

        return service.to_schema(schema_type=AgentSessionSchema, data=obj)

    @patch(operation_id="UpdateAgentSession", path=urls.AGENT_SESSIONS_UPDATE)
    async def update_session(
        self,
        current_user: "m.User",
        service: AgentSessionService,
        data: AgentSessionUpdate,
        session_id: UUID = Parameter(
            title="Session ID", description="The agent session ID"),
    ) -> AgentSessionSchema:
        """Update an agent session."""
        # First check if session belongs to user
        obj = await service.get(session_id)
        if obj.user_id != current_user.id:
            msg = "Session not found"
            raise ValueError(msg)

        obj = await service.update(obj, **data.to_dict())
        return service.to_schema(schema_type=AgentSessionSchema, data=obj)

    @delete(operation_id="DeleteAgentSession", path=urls.AGENT_SESSIONS_DELETE)
    async def delete_session(
        self,
        current_user: "m.User",
        service: AgentSessionService,
        session_id: UUID = Parameter(
            title="Session ID", description="The agent session ID"),
    ) -> None:
        """Delete an agent session."""
        # First check if session belongs to user
        obj = await service.get(session_id)
        if obj.user_id != current_user.id:
            msg = "Session not found"
            raise ValueError(msg)

        await service.delete(session_id)

    @put(operation_id="ActivateAgentSession", path=urls.SESSION_ACTIVATE)
    async def activate_session(
        self,
        current_user: "m.User",
        service: AgentSessionService,
        session_id: UUID = Parameter(
            title="Session ID", description="The agent session ID"),
    ) -> AgentSessionSchema:
        """Activate an agent session."""
        obj = await service.activate_session(session_id, current_user.id)
        if not obj:
            msg = "Session not found"
            raise ValueError(msg)
        return service.to_schema(schema_type=AgentSessionSchema, data=obj)

    @put(operation_id="DeactivateAgentSession", path=urls.SESSION_DEACTIVATE)
    async def deactivate_session(
        self,
        current_user: "m.User",
        service: AgentSessionService,
        session_id: UUID = Parameter(
            title="Session ID", description="The agent session ID"),
    ) -> AgentSessionSchema:
        """Deactivate an agent session."""
        obj = await service.deactivate_session(session_id, current_user.id)
        if not obj:
            msg = "Session not found"
            raise ValueError(msg)
        return service.to_schema(schema_type=AgentSessionSchema, data=obj)

    @post(operation_id="AgentConversation", path=urls.SESSION_CONVERSATION)
    async def agent_conversation(
        self,
        current_user: "m.User",
        agent_session_service: AgentSessionService,
        message_service: "SessionMessageService",
        todo_agent_service: "TodoAgentService",
        data: SessionConversationRequest,
    ) -> SessionConversationResponse:
        """Start or continue a conversation with an AI agent."""
        from datetime import UTC, datetime

        # Create or get existing session
        session = None
        if data.session_id:
            # Try to find existing session
            session = await agent_session_service.get_by_session_id(data.session_id, current_user.id)

        if not session:
            # Create new session
            session_data = {
                "session_id": data.session_id or f"session_{current_user.id}_{datetime.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}",
                "session_name": data.session_name or "AI Conversation",
                "user_id": current_user.id,
                "agent_name": "TodoAssistant",
                "agent_instructions": TODO_SYSTEM_INSTRUCTIONS,
                "is_active": True,
            }
            session = await agent_session_service.create(session_data)

        # Store user messages in the session
        for message in data.messages:
            if message.get("role") == "user":
                from app.db.models.session_message import MessageRole
                message_data = {
                    "session_id": session.id,
                    "role": MessageRole.USER,
                    "content": message["content"],
                    "tool_call_id": None,
                    "tool_name": None,
                    "extra_data": None,
                }
                await message_service.create(message_data)

        # Get the last user message to send to the agent
        user_message = None
        for message in reversed(data.messages):
            if message.get("role") == "user":
                user_message = message.get("content", "")
                break

        if not user_message:
            user_message = "Hello"

        # Use TodoAgentService for intelligent todo management
        try:
            response_content = await todo_agent_service.chat_with_agent(
                session_id=session.session_id,
                user_id=str(current_user.id),
                message=user_message,
            )
        except (ImportError, ModuleNotFoundError):
            # Fallback if todo_agents domain is not available
            response_content = f"I understand you want to discuss: '{user_message}'. However, the todo agent functionality is currently not available. Please try again later."
        except (ValueError, RuntimeError) as e:
            # Fallback response for business logic errors
            response_content = f"I apologize, but I encountered an error while processing your request. Please try again. Error: {e!s}"

        # Store assistant response
        from app.db.models.session_message import MessageRole
        assistant_message_data = {
            "session_id": session.id,
            "role": MessageRole.ASSISTANT,
            "content": response_content,
            "tool_call_id": None,
            "tool_name": None,
            "extra_data": None,
        }
        await message_service.create(assistant_message_data)

        # Get message count
        message_count = await message_service.get_session_message_count(session.id)

        return SessionConversationResponse(
            session_id=session.session_id,
            session_uuid=session.id,
            response=response_content,
            messages_count=message_count,
            session_active=session.is_active,
        )
