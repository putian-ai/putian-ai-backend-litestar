"""Tool definitions for todo agent.

This module contains the FunctionTool definitions that expose the
implementation functions to the agent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agents import FunctionTool

if TYPE_CHECKING:
    from collections.abc import Sequence

from .argument_models import (
    AnalyzeScheduleArgs,
    BatchUpdateScheduleArgs,
    CreateTodoArgs,
    DeleteTodoArgs,
    GetTodoListArgs,
    GetUserDatetimeArgs,
    GetUserQuotaArgs,
    ScheduleTodoArgs,
    UpdateTodoArgs,
)
from .todo_crud_tools import create_todo_impl, delete_todo_impl, update_todo_impl
from .todo_schedule_tools import (
    analyze_schedule_impl,
    batch_update_schedule_impl,
    get_todo_list_impl,
    schedule_todo_impl,
)
from .todo_support_tools import get_user_quota_impl
from .universal_tools import get_user_datetime_impl

__all__ = [
    "get_crud_tool_definitions",
    "get_schedule_tool_definitions",
    "get_support_tool_definitions",
    "get_tool_definitions",
    "get_universal_tool_definitions",
]


def _build_tool_objects() -> dict[str, FunctionTool]:
    """Create FunctionTool objects for all available todo tools."""

    get_user_datetime_tool = FunctionTool(
        name="get_user_datetime",
        description=(
            "Get the user's current date, time, and timezone information. "
            "Use this tool before performing any time-based operations."
        ),
        params_json_schema=GetUserDatetimeArgs.model_json_schema(),
        on_invoke_tool=get_user_datetime_impl,
    )

    get_user_quota_tool = FunctionTool(
        name="get_user_quota",
        description=(
            "Get the user's current agent usage quota information including used requests, remaining quota, "
            "and reset date."
        ),
        params_json_schema=GetUserQuotaArgs.model_json_schema(),
        on_invoke_tool=get_user_quota_impl,
    )

    create_todo_tool = FunctionTool(
        name="create_todo",
        description="Create a new todo item using the TodoService.",
        params_json_schema=CreateTodoArgs.model_json_schema(),
        on_invoke_tool=create_todo_impl,
    )

    delete_todo_tool = FunctionTool(
        name="delete_todo",
        description="Delete a todo item using the TodoService.",
        params_json_schema=DeleteTodoArgs.model_json_schema(),
        on_invoke_tool=delete_todo_impl,
    )

    update_todo_tool = FunctionTool(
        name="update_todo",
        description="Update an existing todo item using the TodoService.",
        params_json_schema=UpdateTodoArgs.model_json_schema(),
        on_invoke_tool=update_todo_impl,
    )

    get_todo_list_tool = FunctionTool(
        name="get_todo_list",
        description="Get a list of all todos for the current user.",
        params_json_schema=GetTodoListArgs.model_json_schema(),
        on_invoke_tool=get_todo_list_impl,
    )

    analyze_schedule_tool = FunctionTool(
        name="analyze_schedule",
        description="Analyze the user's schedule to identify free time slots and potential conflicts.",
        params_json_schema=AnalyzeScheduleArgs.model_json_schema(),
        on_invoke_tool=analyze_schedule_impl,
    )

    schedule_todo_tool = FunctionTool(
        name="schedule_todo",
        description="Intelligently schedule a todo by finding optimal time slots based on existing schedule.",
        params_json_schema=ScheduleTodoArgs.model_json_schema(),
        on_invoke_tool=schedule_todo_impl,
    )

    batch_update_schedule_tool = FunctionTool(
        name="batch_update_schedule",
        description="Apply batch schedule updates after user confirmation to resolve conflicts and optimize timing.",
        params_json_schema=BatchUpdateScheduleArgs.model_json_schema(),
        on_invoke_tool=batch_update_schedule_impl,
    )

    return {
        "get_user_datetime": get_user_datetime_tool,
        "get_user_quota": get_user_quota_tool,
        "create_todo": create_todo_tool,
        "delete_todo": delete_todo_tool,
        "update_todo": update_todo_tool,
        "get_todo_list": get_todo_list_tool,
        "analyze_schedule": analyze_schedule_tool,
        "schedule_todo": schedule_todo_tool,
        "batch_update_schedule": batch_update_schedule_tool,
    }


def _get_universal_tools(tool_map: dict[str, FunctionTool]) -> list[FunctionTool]:
    return [tool_map["get_user_datetime"]]


def _get_crud_tools(tool_map: dict[str, FunctionTool]) -> list[FunctionTool]:
    return [
        tool_map["create_todo"],
        tool_map["delete_todo"],
        tool_map["update_todo"],
    ]


def _get_schedule_tools(tool_map: dict[str, FunctionTool]) -> list[FunctionTool]:
    # Only expose read/analysis scheduling helpers for now. Add write helpers once stabilized.
    return [
        tool_map["get_todo_list"],
        tool_map["analyze_schedule"],
    ]


def _get_support_tools(tool_map: dict[str, FunctionTool]) -> list[FunctionTool]:
    return [tool_map["get_user_quota"]]


def get_tool_definitions() -> Sequence[FunctionTool]:
    """Return the full list of FunctionTool definitions for the combined todo agent."""
    tools = _build_tool_objects()
    return [
        *_get_universal_tools(tools),
        *_get_support_tools(tools),
        *_get_crud_tools(tools),
        *_get_schedule_tools(tools),
    ]


def get_crud_tool_definitions(include_universal: bool = True) -> Sequence[FunctionTool]:
    """Return FunctionTool definitions for CRUD-only agents."""
    tools = _build_tool_objects()
    result: list[FunctionTool] = []
    if include_universal:
        result.extend(_get_universal_tools(tools))
    result.extend(_get_crud_tools(tools))
    return result


def get_schedule_tool_definitions(include_universal: bool = True) -> Sequence[FunctionTool]:
    """Return FunctionTool definitions for scheduling/search agents."""
    tools = _build_tool_objects()
    result: list[FunctionTool] = []
    if include_universal:
        result.extend(_get_universal_tools(tools))
    result.extend(_get_schedule_tools(tools))
    return result


def get_support_tool_definitions(include_universal: bool = True) -> Sequence[FunctionTool]:
    """Return FunctionTool definitions for supporting/other agents."""
    tools = _build_tool_objects()
    result: list[FunctionTool] = []
    if include_universal:
        result.extend(_get_universal_tools(tools))
    result.extend(_get_support_tools(tools))
    return result


def get_universal_tool_definitions() -> Sequence[FunctionTool]:
    """Return FunctionTool definitions that should be available to all agents."""
    tools = _build_tool_objects()
    return list(_get_universal_tools(tools))
