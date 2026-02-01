"""Pydantic argument models for todo agent tools."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "AnalyzeScheduleArgs",
    "BatchUpdateScheduleArgs",
    "CreateTodoArgs",
    "DeleteTodoArgs",
    "GetTodoListArgs",
    "GetUserDatetimeArgs",
    "GetUserQuotaArgs",
    "RecurringTodoArgs",
    "RecurringTodoTemplate",
    "ScheduleConflictResolution",
    "ScheduleTodoArgs",
    "SearchTodoArgs",
    "UpdateTodoArgs",
]


class CreateTodoArgs(BaseModel):
    item: str = Field(...,
                      description="The name/title of the todo item to create")
    description: str | None = Field(
        default=None, description="The description/content of the todo item")
    alarm_time: str | None = Field(
        default=None,
        description="The alarm time for the todo in format YYYY-MM-DD HH:MM:SS or YYYY-MM-DD, can be None if not specified",
    )
    start_time: str = Field(
        ..., description="The start time for the todo in format YYYY-MM-DD HH:MM:SS or YYYY-MM-DD")
    end_time: str = Field(
        ..., description="The end time for the todo in format YYYY-MM-DD HH:MM:SS or YYYY-MM-DD")
    tags: list[str] | None = Field(
        default=None, description="List of tag names to associate with the todo. Common tags: 'work', 'personal', 'study', 'entertainment'"
    )
    importance: str = Field(
        default="none", description="The importance level: none, low, medium, high")
    timezone: str | None = Field(
        default=None, description="Timezone for date parsing (e.g., 'America/New_York', 'Asia/Shanghai'). If not provided, UTC is used."
    )
    auto_schedule: bool = Field(
        default=False, description="Whether to automatically schedule this todo if no specific time is provided"
    )


class ScheduleTodoArgs(BaseModel):
    item: str = Field(...,
                      description="The name/title of the todo item to schedule")
    description: str | None = Field(
        default=None, description="The description/content of the todo item")
    target_date: str | None = Field(
        default=None, description="The target date for scheduling (YYYY-MM-DD). If not provided, defaults to today or tomorrow"
    )
    duration_minutes: int = Field(
        default=60, description="Estimated duration of the task in minutes (default: 60)")
    importance: str = Field(
        default="none", description="The importance level: none, low, medium, high")
    timezone: str | None = Field(
        default=None, description="Timezone for date parsing (e.g., 'America/New_York', 'Asia/Shanghai'). If not provided, UTC is used."
    )
    preferred_time_of_day: str | None = Field(
        default=None, description="Preferred time of day: 'morning' (8-12), 'afternoon' (12-17), 'evening' (17-21), or specific time range"
    )
    tags: list[str] | None = Field(
        default=None, description="List of tag names to associate with the todo")


class RecurringTodoTemplate(BaseModel):
    item: str | None = Field(default=None, description="Todo item title")
    description: str | None = Field(default=None, description="Todo description")
    start_time: str | None = Field(
        default=None, description="Start time in HH:MM (24-hour) format")
    duration_minutes: int | None = Field(
        default=None, description="Duration of the task in minutes")
    tags: list[str] | None = Field(
        default=None, description="List of tag names to associate with the todo")
    importance: str | None = Field(
        default=None, description="Importance level: none, low, medium, high")


class RecurringTodoArgs(BaseModel):
    series_name: str = Field(..., description="Name of the recurring todo series")
    series_description: str | None = Field(
        default=None, description="Description for the recurring todo series")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    timezone: str | None = Field(
        default=None,
        description="Timezone for date parsing (e.g., 'America/New_York', 'Asia/Shanghai'). If not provided, UTC is used.",
    )
    rule_type: str = Field(
        ...,
        description="Recurrence rule type: daily, weekly, monthly, interval",
    )
    rule_payload: str = Field(
        ...,
        description=(
            "Rule payload based on rule_type. "
            "daily: {\"template\": {...}}; "
            "weekly: {\"days\": [0-6], \"templates\": {\"0\": {...}}}; "
            "monthly: {\"day\": 1-31, \"template\": {...}}; "
            "interval: {\"cycle\": [{\"type\": \"work\", \"template\": {...}}, {\"type\": \"rest\"}]}."
        ),
    )
    default_template: RecurringTodoTemplate | None = Field(
        default=None, description="Fallback template when rule payload omits fields"
    )
    default_start_time: str | None = Field(
        default=None,
        description="Fallback start time in HH:MM format (default: 09:00)",
    )
    default_duration_minutes: int = Field(
        default=60, description="Fallback duration in minutes (default: 60)"
    )
    default_tags: list[str] | None = Field(
        default=None, description="Fallback tags when template omits tags"
    )
    default_importance: str = Field(
        default="none", description="Fallback importance level"
    )
    max_items: int = Field(
        default=100, description="Maximum todos to create (default: 100)"
    )

    @field_validator("rule_payload", mode="before")
    @classmethod
    def _normalize_rule_payload(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return json.dumps(value)
        if isinstance(value, str):
            return value
        raise ValueError("rule_payload must be a JSON object string")
        return value


class AnalyzeScheduleArgs(BaseModel):
    target_date: str | None = Field(
        default=None, description="The date to analyze (YYYY-MM-DD). If not provided, analyzes today and tomorrow"
    )
    timezone: str | None = Field(
        default=None, description="Timezone for date analysis (e.g., 'America/New_York', 'Asia/Shanghai'). If not provided, UTC is used."
    )
    include_days: int = Field(
        default=3, description="Number of days to analyze starting from target_date (default: 3)")


class ScheduleConflictResolution(BaseModel):
    todo_id: str = Field(..., description="The UUID of the todo to reschedule")
    new_time: str = Field(...,
                          description="New time in format YYYY-MM-DD HH:MM:SS")
    reason: str = Field(..., description="Reason for the time change")


class BatchUpdateScheduleArgs(BaseModel):
    updates: list[ScheduleConflictResolution] = Field(
        ..., description="List of schedule updates to apply")
    timezone: str | None = Field(
        default=None, description="Timezone for date parsing")
    confirm: bool = Field(
        default=False, description="Set to true to confirm and apply the changes")


class DeleteTodoArgs(BaseModel):
    todo_id: str = Field(...,
                         description="The UUID of the todo item to delete.")


class UpdateTodoArgs(BaseModel):
    todo_id: str = Field(...,
                         description="The UUID of the todo item to update")
    item: str | None = Field(
        default=None, description="The new name/title of the todo item")
    description: str | None = Field(
        default=None, description="The new description/content of the todo item")
    alarm_time: str | None = Field(
        default=None, description="The new planned date/time for the todo in format YYYY-MM-DD HH:MM:SS or YYYY-MM-DD, can be None if not specified"
    )
    start_time: str | None = Field(
        default=None, description="The new start time for the todo in format YYYY-MM-DD HH:MM:SS or YYYY-MM-DD")
    end_time: str | None = Field(
        default=None, description="The new end time for the todo in format YYYY-MM-DD HH:MM:SS or YYYY-MM-DD")
    importance: str | None = Field(
        default=None, description="The new importance level: none, low, medium, high")
    timezone: str | None = Field(
        default=None, description="Timezone for date parsing (e.g., 'America/New_York', 'Asia/Shanghai'). If not provided, UTC is used."
    )


class GetTodoListArgs(BaseModel):
    limit: int = Field(
        default=20, description="Maximum number of todos to return (default: 20)")
    from_date: str | None = Field(
        default=None, description="Filter todos from this date (YYYY-MM-DD)")
    to_date: str | None = Field(
        default=None, description="Filter todos to this date (YYYY-MM-DD)")
    importance: str | None = Field(
        default=None, description="Filter by importance level: none, low, medium, high")
    timezone: str | None = Field(
        default=None, description="Timezone for date filtering (e.g., 'America/New_York', 'Asia/Shanghai'). If not provided, UTC is used."
    )
    include_series_items: bool = Field(
        default=False,
        description="Whether to include items generated from recurring series (default: false)",
    )


class GetUserDatetimeArgs(BaseModel):
    """Arguments for getting user's current date and time information."""
    timezone: str | None = Field(
        default=None, description="The user's timezone (e.g., 'America/New_York', 'Europe/London', 'Asia/Shanghai'). Defaults to UTC if not specified."
    )


class GetUserQuotaArgs(BaseModel):
    """Arguments for getting user's quota and usage information."""
    include_details: bool = Field(
        default=True, description="Whether to include detailed usage statistics and reset date information"
    )


class SearchTodoArgs(BaseModel):
    query: str | None = Field(
        default=None, description="Search term to find in todo items or descriptions")
    importance: str | None = Field(
        default=None, description="Filter by importance level: none, low, medium, high")
    from_date: str | None = Field(
        default=None, description="Filter todos from this date (YYYY-MM-DD)")
    to_date: str | None = Field(
        default=None, description="Filter todos to this date (YYYY-MM-DD)")
    limit: int = Field(
        default=10, description="Maximum number of results to return")
    timezone: str | None = Field(
        default=None, description="Timezone for date filtering (e.g., 'America/New_York', 'Asia/Shanghai'). If not provided, UTC is used."
    )
