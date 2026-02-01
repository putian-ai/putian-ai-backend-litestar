"""Context management for todo agent tools.

This module manages the global context (services and user information)
that tool implementations need to access during execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from app.domain.quota.services import UserUsageQuotaService
    from app.domain.todo.services import TagService, TodoService
    from app.lib.rate_limit_service import RateLimitService

__all__ = [
    "get_current_user_id",
    "get_tag_service",
    "get_todo_service",
    "get_quota_service",
    "get_rate_limit_service",
    "get_user_timezone",
    "set_agent_context",
]

# Global context variables (set per user/session)
_todo_service: TodoService | None = None
_tag_service: TagService | None = None
_quota_service: UserUsageQuotaService | None = None
_rate_limit_service: RateLimitService | None = None
_current_user_id: UUID | None = None
_user_timezone: str | None = None


def set_agent_context(
    todo_service: TodoService,
    tag_service: TagService,
    user_id: UUID,
    user_timezone: str | None = None,
    quota_service: UserUsageQuotaService | None = None,
    rate_limit_service: RateLimitService | None = None,
) -> None:
    """Inject services & user context for subsequent tool calls."""
    global _todo_service, _tag_service, _current_user_id, _quota_service, _rate_limit_service, _user_timezone  # noqa: PLW0603
    _todo_service = todo_service
    _tag_service = tag_service
    _current_user_id = user_id
    _quota_service = quota_service
    _rate_limit_service = rate_limit_service
    _user_timezone = user_timezone


def get_todo_service() -> TodoService | None:
    """Get the current todo service instance."""
    return _todo_service


def get_tag_service() -> TagService | None:
    """Get the current tag service instance."""
    return _tag_service


def get_current_user_id() -> UUID | None:
    """Get the current user ID."""
    return _current_user_id


def get_quota_service() -> UserUsageQuotaService | None:
    """Get the current quota service instance."""
    return _quota_service


def get_rate_limit_service() -> RateLimitService | None:
    """Get the current rate limit service instance."""
    return _rate_limit_service


def get_user_timezone() -> str | None:
    """Get the current user timezone string."""
    return _user_timezone
