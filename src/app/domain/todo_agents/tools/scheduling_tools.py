"""Scheduling tool implementations for todo agent.

This module contains tool implementations for scheduling-related operations:
- Analyzing schedule for free time slots
- Finding optimal time slots
- Scheduling todos intelligently
- Batch updating schedules
- Searching todos

These tools are designed to be used by the Scheduling Agent.

Agent Role: Scheduling Agent
- Find available time slots
- Analyze daily/weekly schedules
- Intelligently schedule new tasks
- Resolve scheduling conflicts
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.db import models as m
from app.db.models.importance import Importance

from .argument_models import (
    AnalyzeScheduleArgs,
    BatchUpdateScheduleArgs,
    ScheduleTodoArgs,
    SearchTodoArgs,
)
from .tool_context import get_current_user_id, get_tag_service, get_todo_service

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from agents import RunContextWrapper

    from app.db.models.todo import Todo

__all__ = [
    "analyze_schedule_impl",
    "batch_update_schedule_impl",
    "schedule_todo_impl",
    "search_todos_impl",
]


def _preprocess_args(args: str) -> str:
    """Preprocess tool arguments to handle double-encoded JSON arrays."""
    try:
        data = json.loads(args)
        for key, value in data.items():
            if isinstance(value, str) and value.startswith("[") and value.endswith("]"):
                try:
                    parsed_array = json.loads(value)
                    if isinstance(parsed_array, list):
                        data[key] = parsed_array
                except (json.JSONDecodeError, ValueError):
                    pass
        return json.dumps(data)
    except (json.JSONDecodeError, ValueError):
        return args


async def search_todos_impl(ctx: RunContextWrapper, args: str) -> str:
    """Implementation of the search_todos function.

    Searches for todos based on text query, importance, and date range.

    Args:
        ctx: The runtime context wrapper
        args: JSON string containing search parameters

    Returns:
        Formatted list of matching todos or message if none found
    """
    todo_service = get_todo_service()
    current_user_id = get_current_user_id()

    if not todo_service or not current_user_id:
        return "Error: Agent context not properly initialized"

    try:
        parsed = SearchTodoArgs.model_validate_json(args)
    except ValueError as e:
        return f"Error: Invalid arguments '{args}': {e}"

    filters = [m.Todo.user_id == current_user_id]
    user_tz = ZoneInfo("UTC")

    if parsed.timezone:
        try:
            user_tz = ZoneInfo(parsed.timezone)
        except Exception:
            return f"Error: Invalid timezone '{parsed.timezone}'"

    # Apply date filters
    if parsed.from_date:
        try:
            from_obj = datetime.strptime(
                parsed.from_date, "%Y-%m-%d").replace(tzinfo=user_tz)
            filters.append(m.Todo.start_time >= from_obj.astimezone(UTC))
        except ValueError:
            return f"Error: Invalid from_date format '{parsed.from_date}'. Use YYYY-MM-DD"

    if parsed.to_date:
        try:
            to_obj = datetime.strptime(parsed.to_date, "%Y-%m-%d").replace(
                tzinfo=user_tz, hour=23, minute=59, second=59
            )
            filters.append(m.Todo.start_time <= to_obj.astimezone(UTC))
        except ValueError:
            return f"Error: Invalid to_date format '{parsed.to_date}'. Use YYYY-MM-DD"

    if parsed.importance:
        try:
            filters.append(m.Todo.importance == Importance(
                parsed.importance.lower()))
        except ValueError:
            return f"Error: Invalid importance level '{parsed.importance}'. Use: none, low, medium, high"

    try:
        from advanced_alchemy.filters import LimitOffset
        from sqlalchemy import or_

        # Add text search if query provided
        if parsed.query:
            search_filter = or_(
                m.Todo.item.ilike(f"%{parsed.query}%"),
                m.Todo.description.ilike(f"%{parsed.query}%"),
            )
            filters.append(search_filter)

        todos, total = await todo_service.list_and_count(
            *filters, LimitOffset(limit=parsed.limit, offset=0)
        )

        if not todos:
            return "No todos found matching your search criteria."

        results = []
        for t in todos:
            time_info = ""
            if t.start_time and t.end_time:
                start_local = t.start_time.astimezone(user_tz)
                end_local = t.end_time.astimezone(user_tz)
                time_info = f"\n  Time: {start_local.strftime('%Y-%m-%d %H:%M')} - {end_local.strftime('%H:%M')}"

            results.append(
                f"• {t.item} (ID: {t.id})\n"
                f"  Description: {t.description or 'No description'}{time_info}\n"
                f"  Importance: {t.importance.value}"
            )

        return f"Found {total} todos (showing {len(todos)}):\n\n" + "\n\n".join(results)

    except Exception as e:
        return f"Error searching todos: {e!s}"


async def analyze_schedule_impl(ctx: RunContextWrapper, args: str) -> str:
    """Implementation of the analyze_schedule function.

    Analyzes the user's schedule to identify free time slots and potential conflicts.

    Args:
        ctx: The runtime context wrapper
        args: JSON string containing analysis parameters

    Returns:
        Detailed schedule analysis with free time slots
    """
    todo_service = get_todo_service()
    current_user_id = get_current_user_id()

    if not todo_service or not current_user_id:
        return "Error: Agent context not properly initialized"

    try:
        parsed = AnalyzeScheduleArgs.model_validate_json(args)
    except ValueError as e:
        return f"Error: Invalid arguments '{args}': {e}"

    try:
        user_tz, start_date = _parse_timezone_and_date(
            parsed.timezone, parsed.target_date)
        todos = await _get_todos_for_date_range(start_date, parsed.include_days, todo_service, current_user_id)
        analysis = _analyze_schedule_by_days(
            todos, start_date, parsed.include_days, user_tz)

        result = (
            f"📊 Schedule Analysis ({parsed.include_days} days starting from {start_date.strftime('%Y-%m-%d')}):\n\n"
            + "\n\n".join(analysis)
        )

        if parsed.timezone and str(user_tz) != "UTC":
            result += f"\n\n🌍 Times shown in {parsed.timezone} timezone"

        return result
    except (ValueError, ZoneInfoNotFoundError) as e:
        return f"Error: {e!s}"
    except Exception as e:
        return f"Error analyzing schedule: {e!s}"


async def schedule_todo_impl(ctx: RunContextWrapper, args: str) -> str:
    """Implementation of the schedule_todo function.

    Intelligently schedules a todo by finding optimal time slots based on
    existing schedule and user preferences.

    Args:
        ctx: The runtime context wrapper
        args: JSON string containing scheduling parameters

    Returns:
        Success message with scheduled time or suggestions for alternatives
    """
    todo_service = get_todo_service()
    tag_service = get_tag_service()
    current_user_id = get_current_user_id()

    if not todo_service or not tag_service or not current_user_id:
        return "Error: Agent context not properly initialized"

    try:
        args = _preprocess_args(args)
        parsed = ScheduleTodoArgs.model_validate_json(args)
    except ValueError as e:
        return f"Error: Invalid arguments '{args}': {e}"

    try:
        user_tz, target_date = _determine_schedule_target_date(
            parsed.timezone, parsed.target_date)
        existing = await _get_existing_todos_for_day(target_date, user_tz, todo_service, current_user_id)
        suggested = _find_optimal_time_slot(
            target_date, parsed, existing, user_tz)

        if not suggested:
            return _handle_no_available_slot(target_date, parsed, existing, user_tz)

        todo, associated_tags = await _create_scheduled_todo(
            parsed,
            suggested,
            todo_service,
            tag_service,
            current_user_id,
        )
        return _format_scheduling_success(todo, suggested, user_tz, associated_tags)
    except (ValueError, ZoneInfoNotFoundError) as e:
        return f"Error: {e!s}"
    except Exception as e:
        return f"Error scheduling todo: {e!s}"


async def batch_update_schedule_impl(ctx: RunContextWrapper, args: str) -> str:
    """Implementation of the batch_update_schedule function.

    Applies batch schedule updates after user confirmation to resolve
    conflicts and optimize timing.

    Args:
        ctx: The runtime context wrapper
        args: JSON string containing batch update parameters

    Returns:
        Preview of changes or results of applied updates
    """
    todo_service = get_todo_service()
    current_user_id = get_current_user_id()

    if not todo_service or not current_user_id:
        return "Error: Agent context not properly initialized"

    try:
        parsed = BatchUpdateScheduleArgs.model_validate_json(args)
    except ValueError as e:
        return f"Error: Invalid arguments '{args}': {e}"

    if not parsed.confirm:
        return _generate_update_preview(parsed)

    user_tz = _get_user_timezone(parsed.timezone)
    if isinstance(user_tz, str):
        return user_tz

    success, failed = await _apply_schedule_updates(parsed.updates, user_tz, todo_service, current_user_id)
    return _format_update_results(success, failed)


# ============================================================================
# Helper Functions for Scheduling
# ============================================================================


def _parse_timezone_and_date(timezone_str: str | None, target_date_str: str | None) -> tuple[ZoneInfo, datetime]:
    """Parse timezone and target date from input arguments."""
    user_tz = ZoneInfo("UTC")
    if timezone_str:
        try:
            user_tz = ZoneInfo(timezone_str)
        except ZoneInfoNotFoundError as e:
            msg = f"Invalid timezone '{timezone_str}'"
            raise ValueError(msg) from e

    if target_date_str:
        try:
            start_date = datetime.strptime(
                target_date_str, "%Y-%m-%d").replace(tzinfo=user_tz)
        except ValueError as e:
            msg = f"Invalid target_date format '{target_date_str}'. Use YYYY-MM-DD"
            raise ValueError(msg) from e
    else:
        start_date = datetime.now(user_tz).replace(
            hour=0, minute=0, second=0, microsecond=0)

    return user_tz, start_date


async def _get_todos_for_date_range(
    start_date: datetime, include_days: int, todo_service, current_user_id: UUID
) -> Sequence[Todo]:
    """Get todos for the specified date range."""
    end_date = start_date + timedelta(days=include_days)
    start_utc = start_date.astimezone(UTC)
    end_utc = end_date.astimezone(UTC)

    from advanced_alchemy.filters import LimitOffset

    filters = [
        m.Todo.user_id == current_user_id,
        m.Todo.alarm_time >= start_utc,
        m.Todo.alarm_time <= end_utc,
    ]
    todos, _ = await todo_service.list_and_count(*filters, LimitOffset(limit=100, offset=0))
    return todos


def _analyze_schedule_by_days(
    todos: Sequence[Todo], start_date: datetime, include_days: int, user_tz: ZoneInfo
) -> list[str]:
    """Analyze schedule day by day and return analysis for each day."""
    analysis = []
    for offset in range(include_days):
        current = start_date + timedelta(days=offset)
        analysis.append(_analyze_single_day(todos, current, user_tz))
    return analysis


def _analyze_single_day(todos: Sequence[Todo], current_date: datetime, user_tz: ZoneInfo) -> str:
    """Analyze a single day's schedule."""
    day_start = current_date.replace(hour=0, minute=0, second=0)
    day_end = current_date.replace(hour=23, minute=59, second=59)
    day_start_utc = day_start.astimezone(UTC)
    day_end_utc = day_end.astimezone(UTC)

    day_todos = [
        t for t in todos if t.alarm_time is not None and day_start_utc <= t.alarm_time <= day_end_utc
    ]
    day_todos.sort(
        key=lambda x: x.alarm_time or datetime.min.replace(tzinfo=UTC))
    free_slots = _find_free_time_slots(day_todos, current_date, user_tz)

    day_str = current_date.strftime("%A, %B %d, %Y")
    result = f"📅 {day_str}:\n"

    if day_todos:
        result += "  Scheduled todos:\n"
        for t in day_todos:
            if t.alarm_time:
                local_time = t.alarm_time.astimezone(user_tz)
                result += f"    • {local_time.strftime('%H:%M')} - {t.item} (importance: {t.importance.value})\n"
    else:
        result += "  No scheduled todos\n"

    if free_slots:
        result += "  Available time slots:\n" + "\n".join(free_slots)
    else:
        result += "  ⚠️  No significant free time slots available"

    return result


def _find_free_time_slots(day_todos: list, current_date: datetime, user_tz: ZoneInfo) -> list[str]:
    """Find free time slots in a day."""
    work_start = current_date.replace(hour=8, minute=0)
    work_end = current_date.replace(hour=22, minute=0)

    if not day_todos:
        return [f"  🟢 {work_start.strftime('%H:%M')} - {work_end.strftime('%H:%M')} (14 hours available)"]

    free = []
    current_time = work_start

    for todo in day_todos:
        if todo.alarm_time is not None:
            todo_time_local = todo.alarm_time.astimezone(user_tz)
            if current_time < todo_time_local:
                gap_hours = (todo_time_local -
                             current_time).total_seconds() / 3600
                if gap_hours >= 0.5:
                    free.append(
                        f"  🟢 {current_time.strftime('%H:%M')} - {todo_time_local.strftime('%H:%M')} ({gap_hours:.1f} hours available)"
                    )
            current_time = max(
                current_time, todo_time_local + timedelta(hours=1))

    if current_time < work_end:
        gap_hours = (work_end - current_time).total_seconds() / 3600
        if gap_hours >= 0.5:
            free.append(
                f"  🟢 {current_time.strftime('%H:%M')} - {work_end.strftime('%H:%M')} ({gap_hours:.1f} hours available)"
            )

    return free


def _determine_schedule_target_date(
    timezone_str: str | None, target_date_str: str | None
) -> tuple[ZoneInfo, datetime]:
    """Determine the target date and timezone for scheduling."""
    user_tz = ZoneInfo("UTC")
    if timezone_str:
        try:
            user_tz = ZoneInfo(timezone_str)
        except ZoneInfoNotFoundError as e:
            msg = f"Invalid timezone '{timezone_str}'"
            raise ValueError(msg) from e

    if target_date_str:
        try:
            target_date = datetime.strptime(
                target_date_str, "%Y-%m-%d").replace(tzinfo=user_tz)
        except ValueError as e:
            msg = f"Invalid target_date format '{target_date_str}'. Use YYYY-MM-DD"
            raise ValueError(msg) from e
        return user_tz, target_date

    # Default to tomorrow if current time is after 6 PM, otherwise today
    now = datetime.now(user_tz)
    if now.hour >= 18:
        target_date = now.replace(
            hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        target_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    return user_tz, target_date


async def _get_existing_todos_for_day(
    target_date: datetime, user_tz: ZoneInfo, todo_service, current_user_id: UUID
) -> list:
    """Get existing todos for the target date."""
    day_start = target_date.replace(hour=0, minute=0, second=0)
    day_end = target_date.replace(hour=23, minute=59, second=59)
    day_start_utc = day_start.astimezone(UTC)
    day_end_utc = day_end.astimezone(UTC)

    from advanced_alchemy.filters import LimitOffset

    filters = [
        m.Todo.user_id == current_user_id,
        m.Todo.start_time >= day_start_utc,
        m.Todo.start_time <= day_end_utc,
    ]
    existing, _ = await todo_service.list_and_count(*filters, LimitOffset(limit=50, offset=0))

    # Filter todos that have start_time and end_time for proper scheduling
    valid = [
        t for t in existing if t.start_time is not None and t.end_time is not None]
    valid.sort(key=lambda x: x.start_time)
    return valid


def _find_optimal_time_slot(
    target_date: datetime, parsed: ScheduleTodoArgs, existing: list, user_tz: ZoneInfo
) -> datetime | None:
    """Find the optimal time slot for scheduling the todo."""
    prefs = {"morning": (8, 12), "afternoon": (12, 17), "evening": (17, 21)}

    # Try preferred time of day first
    if parsed.preferred_time_of_day and parsed.preferred_time_of_day.lower() in prefs:
        s, e = prefs[parsed.preferred_time_of_day.lower()]
        slot = _find_free_slot(
            target_date, s, e, parsed.duration_minutes, existing, user_tz)
        if slot:
            return slot

    # Try all time slots in order of preference
    for period in ["morning", "afternoon", "evening"]:
        s, e = prefs[period]
        slot = _find_free_slot(
            target_date, s, e, parsed.duration_minutes, existing, user_tz)
        if slot:
            return slot

    return None


def _handle_no_available_slot(
    target_date: datetime, parsed: ScheduleTodoArgs, existing: list, user_tz: ZoneInfo
) -> str:
    """Handle the case when no time slot is available."""
    conflicts = _detect_scheduling_conflicts(
        target_date, parsed.duration_minutes, existing, user_tz)
    if conflicts:
        info = "\n".join(
            [f"  • {c['time']} - {c['item']} (importance: {c['importance']})" for c in conflicts]
        )
        return (
            f"⚠️ No free time slots found for '{parsed.item}' on {target_date.strftime('%Y-%m-%d')}.\n\n"
            f"Existing todos that might conflict:\n{info}\n\n"
            "Would you like me to suggest rescheduling some todos to make room?"
        )
    return (
        f"⚠️ No suitable time slots found for '{parsed.item}' on {target_date.strftime('%Y-%m-%d')}. "
        "The day appears to be fully booked."
    )


async def _create_scheduled_todo(
    parsed: ScheduleTodoArgs,
    suggested_time: datetime,
    todo_service,
    tag_service,
    current_user_id: UUID,
) -> tuple[Todo, list[str]]:
    """Create a new todo with the suggested time."""
    session = getattr(todo_service.repository, "session", None)
    if session is None:
        msg = "Database session not available"
        raise RuntimeError(msg)

    try:
        importance_enum = Importance(parsed.importance.lower())
    except ValueError:
        importance_enum = Importance.NONE

    duration_delta = timedelta(minutes=parsed.duration_minutes)
    end_time = suggested_time + duration_delta

    conflicts = await todo_service.check_time_conflict(
        current_user_id,
        suggested_time.astimezone(UTC),
        end_time.astimezone(UTC),
    )
    if conflicts:
        details = [f"'{c.item}'" for c in conflicts]
        msg = f"Time conflict detected with: {', '.join(details)}"
        raise RuntimeError(msg)

    data: dict[str, object] = {
        "item": parsed.item,
        "description": parsed.description,
        "importance": importance_enum,
        "user_id": current_user_id,
        "start_time": suggested_time.astimezone(UTC),
        "end_time": end_time.astimezone(UTC),
        "alarm_time": suggested_time.astimezone(UTC),
    }

    associated_tags: list[str] = []
    try:
        todo = await todo_service.create(data)
        await session.flush()

        if parsed.tags:
            from app.db import models as m

            seen_tag_ids: set[UUID] = set()
            for raw_tag in parsed.tags:
                tag_name = raw_tag.strip()
                if not tag_name:
                    continue

                tag_obj = await tag_service.get_or_create_tag(current_user_id, tag_name)
                if tag_obj.id in seen_tag_ids:
                    continue

                seen_tag_ids.add(tag_obj.id)
                todo.todo_tags.append(
                    m.TodoTag(todo_id=todo.id, tag_id=tag_obj.id))
                associated_tags.append(tag_obj.name)

        await session.commit()
        await session.refresh(todo)
    except Exception:
        await session.rollback()
        raise

    return todo, associated_tags


def _format_scheduling_success(
    todo: Todo,
    suggested_time: datetime,
    user_tz: ZoneInfo,
    associated_tags: list[str] | None = None,
) -> str:
    """Format the success message for scheduling."""
    ts = suggested_time.strftime("%Y-%m-%d %H:%M:%S")
    if str(user_tz) != "UTC":
        ts += f" ({user_tz})"

    tag_line = ""
    if associated_tags:
        tag_line = f"\n\nTags: {', '.join(associated_tags)}"

    base_message = (
        f"✅ Successfully scheduled '{todo.item}' for {ts}\n\n"
        "This time slot was chosen based on your existing schedule and preferences."
    )

    return base_message + tag_line


def _find_free_slot(
    target_date: datetime,
    start_hour: int,
    end_hour: int,
    duration_minutes: int,
    existing: list,
    user_tz: ZoneInfo,
) -> datetime | None:
    """Find a free time slot within the specified time range."""
    slot_start = target_date.replace(hour=start_hour, minute=0)
    slot_end = target_date.replace(hour=end_hour, minute=0)
    duration_delta = timedelta(minutes=duration_minutes)

    current = slot_start
    for todo in existing:
        if todo.start_time and todo.end_time:
            t_start = todo.start_time.astimezone(user_tz)
            t_end = todo.end_time.astimezone(user_tz)
        elif todo.alarm_time:
            t_start = todo.alarm_time.astimezone(user_tz)
            t_end = t_start + timedelta(hours=1)
        else:
            continue

        if current + duration_delta <= t_start:
            return current
        current = max(current, t_end)

    if current + duration_delta <= slot_end:
        return current
    return None


def _detect_scheduling_conflicts(
    target_date: datetime, duration_minutes: int, existing: list, user_tz: ZoneInfo
) -> list:
    """Detect potential scheduling conflicts."""
    conflicts = []
    for todo in existing:
        if todo.alarm_time is not None:
            todo_time_local = todo.alarm_time.astimezone(user_tz)
            conflicts.append(
                {"time": todo_time_local.strftime(
                    "%H:%M"), "item": todo.item, "importance": todo.importance.value}
            )
    return conflicts


def _generate_update_preview(parsed: BatchUpdateScheduleArgs) -> str:
    """Generate a preview of proposed schedule changes."""
    preview = "📋 Proposed Schedule Changes:\n\n"
    for i, upd in enumerate(parsed.updates, 1):
        preview += (
            f"{i}. Todo ID ending in ...{upd.todo_id[-8:]}:\n"
            f"   New time: {upd.new_time}\n"
            f"   Reason: {upd.reason}\n\n"
        )
    preview += "⚠️  To confirm these changes, set 'confirm: true' in your request."
    return preview


def _get_user_timezone(timezone_str: str | None) -> ZoneInfo | str:
    """Get user timezone or return error message."""
    user_tz = ZoneInfo("UTC")
    if timezone_str:
        try:
            user_tz = ZoneInfo(timezone_str)
        except ZoneInfoNotFoundError:
            return f"Error: Invalid timezone '{timezone_str}'"
    return user_tz


async def _apply_schedule_updates(
    updates: list, user_tz: ZoneInfo, todo_service, current_user_id: UUID
) -> tuple[list[str], list[str]]:
    """Apply the schedule updates and return results."""
    success, failed = [], []

    for upd in updates:
        try:
            from uuid import UUID

            todo_uuid = UUID(upd.todo_id)
            todo = await todo_service.get_todo_by_id(todo_uuid, current_user_id)

            if not todo:
                failed.append(f"Todo {upd.todo_id} not found")
                continue

            try:
                new_time_obj = datetime.strptime(
                    upd.new_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=user_tz)
            except ValueError:
                failed.append(
                    f"Invalid time format for todo {upd.todo_id}: {upd.new_time}")
                continue

            todo.alarm_time = new_time_obj.astimezone(UTC)
            await todo_service.update(todo)
            success.append(f"✅ '{todo.item}' rescheduled to {upd.new_time}")

        except Exception as e:
            failed.append(f"Error updating todo {upd.todo_id}: {e!s}")

    return success, failed


def _format_update_results(successful: list[str], failed: list[str]) -> str:
    """Format the batch update results."""
    result = "📅 Schedule Update Results:\n\n"

    if successful:
        result += "Successful updates:\n" + "\n".join(successful) + "\n\n"

    if failed:
        result += "Failed updates:\n" + "\n".join(failed)

    return result
