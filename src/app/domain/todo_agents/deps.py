"""Dependency providers for todo_agents domain."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.memory.agent_service import MemoryAgentService
    from app.domain.memory.services import MemoryService
    from app.domain.quota.services import UserUsageQuotaService
    from app.domain.todo.services import TagService, TodoService
    from app.domain.todo_agents.services import TodoAgentService
    from app.lib.rate_limit_service import RateLimitService

from app.domain.memory.agent_service import create_memory_agent_service
from app.domain.quota.deps import provide_user_usage_quota_service
from app.domain.todo_agents.services import TodoAgentService, create_todo_agent_service
from app.lib.rate_limit_service import RateLimitService

__all__ = ("provide_todo_agent_service", "provide_rate_limit_service",
           "provide_user_usage_quota_service")


async def provide_todo_agent_service(
    todo_service: "TodoService",
    tag_service: "TagService",
    rate_limit_service: "RateLimitService",
    quota_service: "UserUsageQuotaService",
    memory_service: "MemoryService",
) -> "TodoAgentService":
    """Dependency provider for TodoAgentService.

    This function provides TodoAgentService instances to controllers
    through Litestar's dependency injection system.

    Args:
        todo_service: TodoService instance for todo operations
        tag_service: TagService instance for tag operations
        rate_limit_service: RateLimitService instance for rate limiting
        quota_service: UserUsageQuotaService instance for quota management

    Returns:
        Configured TodoAgentService instance with SQLite session storage
    """
    return create_todo_agent_service(
        todo_service=todo_service,
        tag_service=tag_service,
        rate_limit_service=rate_limit_service,
        quota_service=quota_service,
        memory_agent_service=create_memory_agent_service(memory_service),
    )


async def provide_rate_limit_service() -> "RateLimitService":
    """Dependency provider for RateLimitService.

    Returns:
        RateLimitService instance with default configuration
    """
    return RateLimitService()
