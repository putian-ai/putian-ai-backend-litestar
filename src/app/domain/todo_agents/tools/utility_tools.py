"""Utility tool implementations for todo agent.

This module contains utility and informational tools:
- Getting todo list with filters
- Getting user quota information

These tools are designed to be used by the Utility/Information Agent.

Agent Role: Utility Agent
- List and filter todos
- Provide user quota and usage information
- General informational queries
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.db import models as m
from app.db.models.importance import Importance

from .argument_models import GetTodoListArgs, GetUserQuotaArgs
from .tool_context import (
    get_current_user_id,
    get_quota_service,
    get_rate_limit_service,
    get_todo_service,
)

if TYPE_CHECKING:
    from agents import RunContextWrapper

__all__ = [
    "get_todo_list_impl",
    "get_user_quota_impl",
]


async def get_todo_list_impl(ctx: RunContextWrapper, args: str) -> str:
    """Implementation of the get_todo_list function.

    Retrieves a list of todos with optional filtering by date range,
    importance, and limit.

    Args:
        ctx: The runtime context wrapper
        args: JSON string containing filter parameters

    Returns:
        Formatted list of todos or message if none found
    """
    todo_service = get_todo_service()
    current_user_id = get_current_user_id()

    if not todo_service or not current_user_id:
        return "Error: Agent context not properly initialized"

    try:
        parsed = GetTodoListArgs.model_validate_json(args)
    except ValueError as e:
        return f"Error: Invalid arguments '{args}': {e}"

    filters = [m.Todo.user_id == current_user_id]
    user_tz = ZoneInfo("UTC")

    if parsed.timezone:
        try:
            user_tz = ZoneInfo(parsed.timezone)
        except Exception:
            return f"Error: Invalid timezone '{parsed.timezone}'. Use a valid timezone name like 'America/New_York' or 'Asia/Shanghai'"

    # Apply date filters
    if parsed.from_date:
        try:
            from_obj = datetime.strptime(
                parsed.from_date, "%Y-%m-%d").replace(tzinfo=user_tz)
            filters.append(m.Todo.alarm_time >= from_obj.astimezone(UTC))
        except ValueError:
            return f"Error: Invalid from_date format '{parsed.from_date}'. Use YYYY-MM-DD"

    if parsed.to_date:
        try:
            to_obj = datetime.strptime(parsed.to_date, "%Y-%m-%d").replace(
                tzinfo=user_tz, hour=23, minute=59, second=59
            )
            filters.append(m.Todo.alarm_time <= to_obj.astimezone(UTC))
        except ValueError:
            return f"Error: Invalid to_date format '{parsed.to_date}'. Use YYYY-MM-DD"

    if parsed.importance:
        try:
            filters.append(m.Todo.importance == Importance(
                parsed.importance.lower()))
        except ValueError:
            return f"Error: Invalid importance level '{parsed.importance}'. Use: none, low, medium, high"

    # Fetch todos
    try:
        from advanced_alchemy.filters import LimitOffset

        todos, total = await todo_service.list_and_count(
            *filters, LimitOffset(limit=parsed.limit, offset=0)
        )

        if not todos:
            filter_parts = _build_filter_description(parsed)
            filter_text = f" with filters: {', '.join(filter_parts)}" if filter_parts else ""
            return f"No todos found{filter_text}."

        results = _format_todo_results(todos, user_tz)
        filter_parts = _build_filter_description(parsed, include_timezone=True)
        filter_text = f" with filters: {', '.join(filter_parts)}" if filter_parts else ""

        return (
            f"Your todos{filter_text} (showing {min(len(todos), parsed.limit)} of {total} total):\n\n"
            + "\n\n".join(results)
        )
    except Exception as e:
        return f"Error getting todo list: {e!s}"


async def get_user_quota_impl(ctx: RunContextWrapper, args: str) -> str:
    """Implementation of the get_user_quota function.

    Retrieves the user's current agent usage quota information including
    used requests, remaining quota, and reset date.

    Args:
        ctx: The runtime context wrapper
        args: JSON string containing quota query parameters

    Returns:
        Formatted quota information or error message
    """
    quota_service = get_quota_service()
    rate_limit_service = get_rate_limit_service()
    current_user_id = get_current_user_id()

    if not quota_service or not rate_limit_service or not current_user_id:
        return "Error: Agent context not properly initialized for quota information"

    try:
        parsed = GetUserQuotaArgs.model_validate_json(args)
    except ValueError as e:
        return f"Error: Invalid arguments '{args}': {e}"

    try:
        # Get current usage statistics from rate limit service
        usage_stats = await rate_limit_service.get_user_usage_stats(
            user_id=current_user_id, quota_service=quota_service
        )

        if parsed.include_details:
            # Return detailed quota information
            reset_date_str = usage_stats.reset_date.strftime("%B %d, %Y")
            percentage_used = (usage_stats.usage_count /
                               usage_stats.monthly_limit) * 100

            result = (
                f"📊 **Your Agent Usage Quota**\n\n"
                f"**Current Month:** {usage_stats.current_month}\n"
                f"**Used:** {usage_stats.usage_count}/{usage_stats.monthly_limit} requests ({percentage_used:.1f}%)\n"
                f"**Remaining:** {usage_stats.remaining_quota} requests\n"
                f"**Quota Resets:** {reset_date_str}\n\n"
            )

            if usage_stats.remaining_quota > 0:
                if percentage_used >= 80:
                    result += "⚠️ **Warning:** You're approaching your monthly limit. Consider spacing out your requests."
                elif percentage_used >= 50:
                    result += "📈 **Notice:** You've used more than half of your monthly quota."
                else:
                    result += "✅ **Status:** You have plenty of quota remaining for this month."
            else:
                result += "🚫 **Limit Reached:** You have exceeded your monthly quota. Your quota will reset next month."
        else:
            # Return simple quota information
            result = f"You have {usage_stats.remaining_quota} out of {usage_stats.monthly_limit} agent requests remaining this month."

        return result

    except Exception as e:
        return f"Error retrieving quota information: {e!s}"


# ============================================================================
# Helper Functions
# ============================================================================


def _build_filter_description(parsed: GetTodoListArgs, include_timezone: bool = False) -> list[str]:
    """Build description of applied filters."""
    parts = []
    if parsed.from_date:
        parts.append(f"from {parsed.from_date}")
    if parsed.to_date:
        parts.append(f"to {parsed.to_date}")
    if parsed.importance:
        parts.append(f"importance: {parsed.importance}")
    if include_timezone and parsed.timezone:
        parts.append(f"timezone: {parsed.timezone}")
    return parts


def _format_todo_results(todos, user_tz: ZoneInfo) -> list[str]:
    """Format todo results for display."""
    results = []
    for t in todos:
        if t.start_time and t.end_time:
            start_local = t.start_time.astimezone(user_tz)
            end_local = t.end_time.astimezone(user_tz)
            plan_str = (
                start_local.strftime("%Y-%m-%d %H:%M")
                + " - "
                + end_local.strftime("%Y-%m-%d %H:%M")
            )
            if str(user_tz) != "UTC":
                plan_str += f" ({start_local.tzinfo})"
        else:
            plan_str = "No plan time"
        results.append(
            f"• {t.item} (ID: {t.id})\n"
            f"  Description: {t.description or 'No description'}\n"
            f"  Plan time: {plan_str}\n"
            f"  Importance: {t.importance.value}"
        )
    return results
