"""Tool definitions for todo agent.

This module contains the FunctionTool definitions that expose the
implementation functions to the agent. Tools are organized by agent role:

- CRUD Agent Tools: create_todo, update_todo, delete_todo
- Scheduling Agent Tools: search_todos, analyze_schedule, schedule_todo, batch_update_schedule
- Utility Agent Tools: get_todo_list, get_user_quota, get_user_datetime
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from agents import FunctionTool

from .argument_models import (
    AnalyzeScheduleArgs,
    BatchUpdateScheduleArgs,
    CreateTodoArgs,
    DeleteTodoArgs,
    GetTodoListArgs,
    GetUserDatetimeArgs,
    GetUserQuotaArgs,
    ScheduleTodoArgs,
    SearchTodoArgs,
    UpdateTodoArgs,
)

# Import from organized tool modules
from .crud_tools import create_todo_impl, delete_todo_impl, update_todo_impl
from .scheduling_tools import (
    analyze_schedule_impl,
    batch_update_schedule_impl,
    schedule_todo_impl,
    search_todos_impl,
)
from .universal_tools import get_user_datetime_impl
from .utility_tools import get_todo_list_impl, get_user_quota_impl

if TYPE_CHECKING:
    from collections.abc import Sequence

    from agents import FunctionTool

__all__ = [
    "get_crud_tool_definitions",
    "get_scheduling_tool_definitions",
    "get_tool_definitions",
    "get_utility_tool_definitions",
]


# ============================================================================
# Individual Tool Factories
# ============================================================================


def _create_datetime_tool():
    """Create the get_user_datetime tool."""
    from agents import FunctionTool

    return FunctionTool(
        name="get_user_datetime",
        description="Get the user's current date, time, and timezone information. Use this tool before performing any time-based operations.",
        params_json_schema=GetUserDatetimeArgs.model_json_schema(),
        on_invoke_tool=get_user_datetime_impl,
    )


def _create_crud_tools() -> list:
    """Create CRUD-related tools."""
    from agents import FunctionTool

    return [
        FunctionTool(
            name="create_todo",
            description="Create a new todo item using the TodoService.",
            params_json_schema=CreateTodoArgs.model_json_schema(),
            on_invoke_tool=create_todo_impl,
        ),
        FunctionTool(
            name="delete_todo",
            description="Delete a todo item using the TodoService.",
            params_json_schema=DeleteTodoArgs.model_json_schema(),
            on_invoke_tool=delete_todo_impl,
        ),
        FunctionTool(
            name="update_todo",
            description="Update an existing todo item using the TodoService.",
            params_json_schema=UpdateTodoArgs.model_json_schema(),
            on_invoke_tool=update_todo_impl,
        ),
    ]


def _create_scheduling_tools() -> list:
    """Create scheduling-related tools."""
    from agents import FunctionTool

    return [
        FunctionTool(
            name="search_todos",
            description="Search for todos by text query, importance level, or date range. Use this to find specific todos.",
            params_json_schema=SearchTodoArgs.model_json_schema(),
            on_invoke_tool=search_todos_impl,
        ),
        FunctionTool(
            name="analyze_schedule",
            description="Analyze the user's schedule to identify free time slots and potential conflicts.",
            params_json_schema=AnalyzeScheduleArgs.model_json_schema(),
            on_invoke_tool=analyze_schedule_impl,
        ),
        FunctionTool(
            name="schedule_todo",
            description="Intelligently schedule a todo by finding optimal time slots based on existing schedule.",
            params_json_schema=ScheduleTodoArgs.model_json_schema(),
            on_invoke_tool=schedule_todo_impl,
        ),
        FunctionTool(
            name="batch_update_schedule",
            description="Apply batch schedule updates after user confirmation to resolve conflicts and optimize timing.",
            params_json_schema=BatchUpdateScheduleArgs.model_json_schema(),
            on_invoke_tool=batch_update_schedule_impl,
        ),
    ]


def _create_utility_tools() -> list:
    """Create utility-related tools."""
    from agents import FunctionTool

    return [
        FunctionTool(
            name="get_todo_list",
            description="Get a list of all todos for the current user.",
            params_json_schema=GetTodoListArgs.model_json_schema(),
            on_invoke_tool=get_todo_list_impl,
        ),
        FunctionTool(
            name="get_user_quota",
            description="Get the user's current agent usage quota information including used requests, remaining quota, and reset date.",
            params_json_schema=GetUserQuotaArgs.model_json_schema(),
            on_invoke_tool=get_user_quota_impl,
        ),
    ]


# ============================================================================
# Agent-Specific Tool Definition Functions
# ============================================================================


def get_tool_definitions() -> Sequence[FunctionTool]:
    """Return all tool definitions for the main TodoAssistant agent.

    This includes all tools:
    - Universal: get_user_datetime
    - CRUD: create_todo, update_todo, delete_todo
    - Scheduling: search_todos, analyze_schedule, schedule_todo, batch_update_schedule
    - Utility: get_todo_list, get_user_quota
    """
    return [
        _create_datetime_tool(),
        *_create_utility_tools(),
        *_create_crud_tools(),
        *_create_scheduling_tools(),
    ]


def get_crud_tool_definitions() -> Sequence[FunctionTool]:
    """Return tool definitions for the CRUD Agent.

    Includes:
    - get_user_datetime (for time context)
    - create_todo
    - update_todo
    - delete_todo
    """
    return [
        _create_datetime_tool(),
        *_create_crud_tools(),
    ]


def get_scheduling_tool_definitions() -> Sequence[FunctionTool]:
    """Return tool definitions for the Scheduling Agent.

    Includes:
    - get_user_datetime (for time context)
    - search_todos
    - analyze_schedule
    - schedule_todo
    - batch_update_schedule
    """
    return [
        _create_datetime_tool(),
        *_create_scheduling_tools(),
    ]


def get_utility_tool_definitions() -> Sequence[FunctionTool]:
    """Return tool definitions for the Utility Agent.

    Includes:
    - get_user_datetime (for time context)
    - get_todo_list
    - get_user_quota
    """
    return [
        _create_datetime_tool(),
        *_create_utility_tools(),
    ]
