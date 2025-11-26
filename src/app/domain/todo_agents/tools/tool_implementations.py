"""Tool implementation functions for todo agent tools (DEPRECATED).

This module is maintained for backward compatibility. All implementations
have been moved to specialized modules:

- crud_tools.py: create_todo_impl, update_todo_impl, delete_todo_impl
- scheduling_tools.py: analyze_schedule_impl, schedule_todo_impl, batch_update_schedule_impl, search_todos_impl
- utility_tools.py: get_todo_list_impl, get_user_quota_impl

Please import directly from those modules for new code.
"""

from __future__ import annotations

# Re-export all implementations for backward compatibility
from .crud_tools import create_todo_impl, delete_todo_impl, update_todo_impl
from .scheduling_tools import (
    analyze_schedule_impl,
    batch_update_schedule_impl,
    schedule_todo_impl,
    search_todos_impl,
)
from .utility_tools import get_todo_list_impl, get_user_quota_impl

__all__ = [
    "analyze_schedule_impl",
    "batch_update_schedule_impl",
    "create_todo_impl",
    "delete_todo_impl",
    "get_todo_list_impl",
    "get_user_quota_impl",
    "schedule_todo_impl",
    "search_todos_impl",
    "update_todo_impl",
]
