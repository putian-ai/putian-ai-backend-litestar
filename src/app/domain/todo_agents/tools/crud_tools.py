"""CRUD tool implementations for todo agent.

This module contains tool implementations for Create, Read, Update, Delete
operations on todo items. These tools are designed to be used by the
Todo Management Agent.

Agent Role: Todo Management Agent
- Create new todo items with validation
- Update existing todo items
- Delete todo items
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.db import models as m
from app.db.models.importance import Importance

from .argument_models import CreateTodoArgs, DeleteTodoArgs, UpdateTodoArgs
from .tool_context import get_current_user_id, get_tag_service, get_todo_service

if TYPE_CHECKING:
    from uuid import UUID

    from agents import RunContextWrapper

__all__ = [
    "create_todo_impl",
    "delete_todo_impl",
    "update_todo_impl",
]


def _preprocess_args(args: str) -> str:
    """Preprocess tool arguments to handle double-encoded JSON arrays.

    Some LLMs may send array fields as stringified JSON within the JSON string,
    e.g., tags: '["study"]' instead of tags: ["study"].
    This function parses the JSON and re-serializes it to ensure proper structure.

    Args:
        args: JSON string containing tool arguments

    Returns:
        Preprocessed JSON string with proper array encoding
    """
    try:
        data = json.loads(args)

        # Check if any field is a string that looks like a JSON array
        for key, value in data.items():
            if isinstance(value, str) and value.startswith("[") and value.endswith("]"):
                try:
                    # Try to parse it as JSON
                    parsed_array = json.loads(value)
                    if isinstance(parsed_array, list):
                        data[key] = parsed_array
                except (json.JSONDecodeError, ValueError):
                    # If it fails to parse, leave it as is
                    pass

        return json.dumps(data)
    except (json.JSONDecodeError, ValueError):
        # If we can't parse the args, return them as-is
        return args


def _parse_datetime_with_timezone(date_str: str, user_tz: ZoneInfo) -> datetime | None:
    """Parse datetime string with timezone support."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=user_tz).astimezone(UTC)
        except ValueError:
            continue
    return None


async def delete_todo_impl(ctx: RunContextWrapper, args: str) -> str:
    """Implementation of the delete_todo function.

    Deletes a todo item by its UUID after validating ownership.

    Args:
        ctx: The runtime context wrapper
        args: JSON string containing the todo_id to delete

    Returns:
        Success or error message
    """
    todo_service = get_todo_service()
    current_user_id = get_current_user_id()

    if not todo_service or not current_user_id:
        return "Error: Agent context not properly initialized"

    try:
        parsed = DeleteTodoArgs.model_validate_json(args)
    except ValueError:
        return f"Error: Invalid todo ID '{args}'"

    try:
        from uuid import UUID
        todo_uuid = UUID(parsed.todo_id)
        todo = await todo_service.get(todo_uuid)
        if not todo:
            return f"Todo item with ID {parsed.todo_id} not found."
        if todo.user_id != current_user_id:
            return f"Todo item with ID {parsed.todo_id} does not belong to you."
        await todo_service.delete(todo_uuid)
        return f"Successfully deleted todo '{todo.item}' (ID: {parsed.todo_id})"
    except ValueError:
        return f"Error: Invalid UUID format '{parsed.todo_id}'"
    except Exception as e:
        return f"Error deleting todo: {e!s}"


async def create_todo_impl(ctx: RunContextWrapper, args: str) -> str:
    """Implementation of the create_todo function.

    Creates a new todo item with time validation and conflict checking.
    Supports tags and timezone-aware date handling.

    Args:
        ctx: The runtime context wrapper
        args: JSON string containing todo creation parameters

    Returns:
        Success message with todo details or error message
    """
    todo_service = get_todo_service()
    tag_service = get_tag_service()
    current_user_id = get_current_user_id()

    if not todo_service or not tag_service or not current_user_id:
        return "Error: Agent context not properly initialized"

    session = getattr(todo_service.repository, "session", None)
    if session is None:
        return "Error: Database session not available"

    # Preprocess args to handle double-encoded arrays
    args = _preprocess_args(args)
    parsed = CreateTodoArgs.model_validate_json(args)
    user_tz = ZoneInfo(parsed.timezone) if parsed.timezone else ZoneInfo("UTC")

    # Parse alarm_time
    alarm_time_obj = None
    if parsed.alarm_time:
        alarm_time_obj = _parse_datetime_with_timezone(
            parsed.alarm_time, user_tz)
        if alarm_time_obj is None:
            return f"Error: Invalid alarm time format '{parsed.alarm_time}'. Use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS"

    # Parse start_time
    start_time_obj = _parse_datetime_with_timezone(parsed.start_time, user_tz)
    if start_time_obj is None:
        return f"Error: Invalid start time format '{parsed.start_time}'. Use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS"

    # Parse end_time
    end_time_obj = _parse_datetime_with_timezone(parsed.end_time, user_tz)
    if end_time_obj is None:
        return f"Error: Invalid end time format '{parsed.end_time}'. Use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS"

    if end_time_obj <= start_time_obj:
        return "Error: End time must be after start time"

    # Check for conflicts
    try:
        conflicts = await todo_service.check_time_conflict(current_user_id, start_time_obj, end_time_obj)
        if conflicts:
            details = [
                f"• '{c.item}' ({c.start_time.astimezone(user_tz).strftime('%Y-%m-%d %H:%M')} - {c.end_time.astimezone(user_tz).strftime('%Y-%m-%d %H:%M')})"
                for c in conflicts
            ]
            return (
                "❌ Time conflict detected! The requested time slot conflicts with existing todos:\n"
                + "\n".join(details)
                + "\n\nPlease choose a different time or use the schedule_todo tool to find an available slot."
            )
    except Exception as e:
        return f"Error checking for time conflicts: {e!s}"

    # Create todo
    try:
        importance_enum = Importance(parsed.importance.lower())
    except ValueError:
        importance_enum = Importance.NONE

    todo_data: dict[str, object] = {
        "item": parsed.item,
        "description": parsed.description,
        "importance": importance_enum,
        "start_time": start_time_obj,
        "end_time": end_time_obj,
        "user_id": current_user_id,
    }

    if alarm_time_obj is not None:
        todo_data["alarm_time"] = alarm_time_obj

    associated_tags: list[str] = []
    try:
        todo = await todo_service.create(todo_data)
        await session.flush()

        if parsed.tags:
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
    except Exception as e:
        await session.rollback()
        return f"Error creating todo: {e!s}"

    tag_info = f" (tags: {', '.join(associated_tags)})" if associated_tags else ""
    start_str = start_time_obj.astimezone(user_tz).strftime("%Y-%m-%d %H:%M")
    end_str = end_time_obj.astimezone(user_tz).strftime("%Y-%m-%d %H:%M")
    return f"Successfully created todo '{todo.item}' (ID: {todo.id}) scheduled from {start_str} to {end_str}{tag_info}"


async def update_todo_impl(ctx: RunContextWrapper, args: str) -> str:
    """Implementation of the update_todo function.

    Updates an existing todo item with validation and conflict checking.

    Args:
        ctx: The runtime context wrapper
        args: JSON string containing todo_id and fields to update

    Returns:
        Success message with updated fields or error message
    """
    todo_service = get_todo_service()
    current_user_id = get_current_user_id()

    if not todo_service or not current_user_id:
        return "Error: Agent context not properly initialized"

    try:
        parsed = UpdateTodoArgs.model_validate_json(args)
    except ValueError as e:
        return f"Error: Invalid arguments '{args}': {e}"

    try:
        from uuid import UUID
        todo_uuid = UUID(parsed.todo_id)
        todo = await todo_service.get_todo_by_id(todo_uuid, current_user_id)
        if not todo:
            return f"Todo item with ID {parsed.todo_id} not found."
    except ValueError:
        return f"Error: Invalid UUID format '{parsed.todo_id}'"
    except Exception as e:
        return f"Error finding todo: {e!s}"

    update_data: dict[str, object] = {}
    user_tz = ZoneInfo("UTC")

    if parsed.timezone:
        try:
            user_tz = ZoneInfo(parsed.timezone)
        except Exception:
            return f"Error: Invalid timezone '{parsed.timezone}'. Use a valid timezone name like 'America/New_York' or 'Asia/Shanghai'"

    # Process updates
    if parsed.item is not None:
        update_data["item"] = parsed.item
    if parsed.description is not None:
        update_data["description"] = parsed.description
    if parsed.alarm_time is not None:
        parsed_ok = _parse_datetime_with_timezone(parsed.alarm_time, user_tz)
        if parsed_ok is None:
            return f"Error: Invalid date format '{parsed.alarm_time}'. Use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS"
        update_data["alarm_time"] = parsed_ok
    if parsed.importance is not None:
        try:
            update_data["importance"] = Importance(parsed.importance.lower())
        except ValueError:
            return f"Error: Invalid importance level '{parsed.importance}'. Use: none, low, medium, high"
    if parsed.start_time is not None:
        start_ok = _parse_datetime_with_timezone(parsed.start_time, user_tz)
        if start_ok is None:
            return f"Error: Invalid start time format '{parsed.start_time}'. Use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS"
        update_data["start_time"] = start_ok
    if parsed.end_time is not None:
        end_ok = _parse_datetime_with_timezone(parsed.end_time, user_tz)
        if end_ok is None:
            return f"Error: Invalid end time format '{parsed.end_time}'. Use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS"
        update_data["end_time"] = end_ok

    # Validate time ordering and check conflicts
    validation_result = await _validate_time_updates(
        update_data, todo, user_tz, todo_service, current_user_id)
    if validation_result:
        return validation_result

    # Apply updates
    try:
        updated_fields = []
        for field, value in update_data.items():
            setattr(todo, field, value)
            updated_fields.append(field)
        updated = await todo_service.update(todo)
        return f"Successfully updated todo '{updated.item}' (ID: {updated.id}). Updated fields: {', '.join(updated_fields)}"
    except Exception as e:
        return f"Error updating todo: {e!s}"


async def _validate_time_updates(update_data: dict, todo, user_tz: ZoneInfo, todo_service, current_user_id: UUID) -> str | None:
    """Validate time ordering and check for conflicts."""
    # Validate ordering
    if "start_time" in update_data and "end_time" in update_data:
        if update_data["end_time"] <= update_data["start_time"]:
            return "Error: End time must be after start time"
    elif "start_time" in update_data and todo.end_time is not None and todo.end_time <= update_data["start_time"]:
        return "Error: New start time must be before existing end time"
    elif "end_time" in update_data and todo.start_time is not None and update_data["end_time"] <= todo.start_time:
        return "Error: New end time must be after existing start time"

    # Check for conflicts
    if "start_time" in update_data or "end_time" in update_data:
        final_start = update_data.get("start_time", todo.start_time)
        final_end = update_data.get("end_time", todo.end_time)

        if isinstance(final_start, datetime) and isinstance(final_end, datetime):
            try:
                conflicts = await todo_service.check_time_conflict(current_user_id, final_start, final_end, todo.id)
                if conflicts:
                    details = [
                        f"• '{c.item}' ({c.start_time.astimezone(user_tz).strftime('%Y-%m-%d %H:%M')} - {c.end_time.astimezone(user_tz).strftime('%Y-%m-%d %H:%M')})"
                        for c in conflicts
                    ]
                    return (
                        "❌ Time conflict detected! The updated time slot conflicts with existing todos:\n"
                        + "\n".join(details)
                        + "\n\nPlease choose a different time."
                    )
            except Exception as e:
                return f"Error checking for time conflicts: {e!s}"

    return None
