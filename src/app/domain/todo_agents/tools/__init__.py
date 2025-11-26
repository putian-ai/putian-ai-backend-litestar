"""Todo agent tools module.

This module contains all the tool-related components for todo agents,
organized into focused modules for better maintainability.

Agent Types:
- TodoAssistant (get_todo_agent): Main agent with all tools
- CRUDAgent (get_crud_agent): Create, Update, Delete operations
- SchedulingAgent (get_scheduling_agent): Schedule management
- UtilityAgent (get_utility_agent): List and information queries

Tool Organization by Agent Role:
- crud_tools.py: Create, Update, Delete todo operations (CRUD Agent)
- scheduling_tools.py: Search, schedule, analyze schedule (Scheduling Agent)
- utility_tools.py: List todos, quota info (Utility Agent)
- universal_tools.py: Common tools like get_user_datetime
"""

from .agent_factory import (
    AGENT_TYPES,
    get_agent_by_type,
    get_crud_agent,
    get_scheduling_agent,
    get_todo_agent,
    get_utility_agent,
)
from .crud_tools import create_todo_impl, delete_todo_impl, update_todo_impl
from .scheduling_tools import (
    analyze_schedule_impl,
    batch_update_schedule_impl,
    schedule_todo_impl,
    search_todos_impl,
)
from .tool_definitions import (
    get_crud_tool_definitions,
    get_scheduling_tool_definitions,
    get_tool_definitions,
    get_utility_tool_definitions,
)
from .universal_tools import get_user_datetime_impl
from .utility_tools import get_todo_list_impl, get_user_quota_impl

__all__ = [
    "AGENT_TYPES",
    "analyze_schedule_impl",
    "batch_update_schedule_impl",
    "create_todo_impl",
    "delete_todo_impl",
    "get_agent_by_type",
    "get_crud_agent",
    "get_crud_tool_definitions",
    "get_scheduling_agent",
    "get_scheduling_tool_definitions",
    "get_todo_agent",
    "get_todo_list_impl",
    "get_tool_definitions",
    "get_user_datetime_impl",
    "get_user_quota_impl",
    "get_utility_agent",
    "get_utility_tool_definitions",
    "schedule_todo_impl",
    "search_todos_impl",
    "update_todo_impl",
]
