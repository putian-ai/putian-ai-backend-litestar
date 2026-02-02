"""Recurring todo creation tool implementation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from app.db import models as m
from app.db.models.importance import Importance

from .argument_models import RecurringTodoArgs, RecurringTodoTemplate
from .scheduling_utils import TimeBlock, find_free_slot_in_blocks, has_conflict
from .timezone_utils import resolve_timezone
from .todo_crud_tools import _preprocess_args, _safe_session_rollback
from .tool_context import get_current_user_id, get_tag_service, get_todo_service, get_user_timezone

if TYPE_CHECKING:
    from collections.abc import Iterable
    from uuid import UUID

    from agents import RunContextWrapper


__all__ = ["create_recurring_todos_impl"]


_WEEKDAY_ALIASES: dict[str, int] = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}
_WEEKDAY_NAMES: dict[int, list[str]] = {
    0: ["mon", "monday"],
    1: ["tue", "tues", "tuesday"],
    2: ["wed", "wednesday"],
    3: ["thu", "thur", "thurs", "thursday"],
    4: ["fri", "friday"],
    5: ["sat", "saturday"],
    6: ["sun", "sunday"],
}


@dataclass(frozen=True)
class Occurrence:
    target_date: date
    template: RecurringTodoTemplate


@dataclass(frozen=True)
class ResolvedTodo:
    item: str
    description: str | None
    start_time: datetime
    end_time: datetime
    alarm_time: datetime
    tags: list[str]
    importance: Importance


async def create_recurring_todos_impl(ctx: RunContextWrapper, args: str) -> str:
    """Implementation of the create_recurring_todos function."""
    todo_service = get_todo_service()
    tag_service = get_tag_service()
    current_user_id = get_current_user_id()

    if not todo_service or not tag_service or not current_user_id:
        return "Error: Agent context not properly initialized"

    session = getattr(todo_service.repository, "session", None)
    if session is None:
        return "Error: Database session not available"

    try:
        args = _preprocess_args(args)
        parsed = RecurringTodoArgs.model_validate_json(args)
    except ValueError as exc:
        return f"Error: Invalid arguments '{args}': {exc}"

    timezone_result = resolve_timezone(parsed.timezone, get_user_timezone())
    if isinstance(timezone_result, str):
        return timezone_result
    user_tz, timezone_name = timezone_result

    try:
        start_date = _parse_date(parsed.start_date)
        end_date = _parse_date(parsed.end_date)
    except ValueError as exc:
        return f"Error: {exc!s}"

    if end_date < start_date:
        return "Error: end_date must be on or after start_date"

    range_days = (end_date - start_date).days
    if range_days > 183:
        return "Error: Date range exceeds 6 months (max 183 days)"

    if parsed.max_items < 1 or parsed.max_items > 100:
        return "Error: max_items must be between 1 and 100"

    rule_type = _normalize_rule_type(parsed.rule_type)
    try:
        rule_payload = _parse_rule_payload(parsed.rule_payload)
    except ValueError as exc:
        return f"Error: {exc!s}"

    try:
        occurrences, month_adjustments = _build_occurrences(
            rule_type,
            rule_payload,
            start_date,
            end_date,
            parsed.default_template,
        )
    except ValueError as exc:
        return f"Error: {exc!s}"

    if not occurrences:
        return "Error: No occurrences generated for the provided rule"

    if len(occurrences) > parsed.max_items:
        return (
            f"Error: Generated {len(occurrences)} occurrences which exceeds max_items={parsed.max_items}. "
            "Please narrow the range or rule."
        )

    try:
        default_start_time = _resolve_default_start_time(parsed)
    except ValueError as exc:
        return f"Error: {exc!s}"
    default_duration = _resolve_default_duration(parsed)
    if default_duration <= 0:
        return "Error: default_duration_minutes must be positive"

    existing_blocks = await _load_existing_blocks(
        todo_service,
        current_user_id,
        start_date,
        end_date,
        user_tz,
    )

    planned: list[ResolvedTodo] = []
    failures: list[str] = []
    rescheduled_count = 0

    for occurrence in occurrences:
        try:
            resolved = _resolve_template(
                occurrence.template,
                parsed.default_template,
                default_start_time,
                default_duration,
                parsed.default_tags,
                parsed.default_importance,
                user_tz,
                occurrence.target_date,
            )
        except ValueError as exc:
            failures.append(f"{occurrence.target_date}: {exc!s}")
            continue

        blocks_for_day = existing_blocks.setdefault(occurrence.target_date, [])
        desired_start = resolved.start_time
        desired_end = resolved.end_time

        if has_conflict(desired_start, desired_end, blocks_for_day):
            new_start = _find_next_free_slot(
                occurrence.target_date,
                desired_start,
                resolved.end_time - resolved.start_time,
                blocks_for_day,
                user_tz,
            )
            if new_start is None:
                failures.append(f"{occurrence.target_date}: no free time slot available")
                continue
            rescheduled_count += 1
            start_time = new_start
            end_time = start_time + (resolved.end_time - resolved.start_time)
        else:
            start_time = desired_start
            end_time = desired_end

        blocks_for_day.append(TimeBlock(start_time, end_time))

        planned.append(
            ResolvedTodo(
                item=resolved.item,
                description=resolved.description,
                start_time=start_time,
                end_time=end_time,
                alarm_time=start_time,
                tags=resolved.tags,
                importance=resolved.importance,
            )
        )

    if not planned:
        failure_preview = "\n".join(f"  • {item}" for item in failures[:5])
        details = f"\n\nFailures:\n{failure_preview}" if failures else ""
        return f"Error: No todos could be scheduled.{details}"

    series = m.TodoSeries(
        name=parsed.series_name,
        description=parsed.series_description,
        rule_type=m.TodoSeriesRuleType(rule_type),
        rule_payload=rule_payload,
        start_date=start_date,
        end_date=end_date,
        timezone=str(user_tz),
        default_start_time=default_start_time,
        duration_minutes=default_duration,
        user_id=current_user_id,
    )

    created_todos: list[m.Todo] = []

    try:
        session.add(series)
        await session.flush()

        for todo_plan in planned:
            todo_data: dict[str, object] = {
                "item": todo_plan.item,
                "description": todo_plan.description,
                "importance": todo_plan.importance,
                "start_time": todo_plan.start_time.astimezone(UTC),
                "end_time": todo_plan.end_time.astimezone(UTC),
                "alarm_time": todo_plan.alarm_time.astimezone(UTC),
                "user_id": current_user_id,
                "series_id": series.id,
            }
            todo = await todo_service.create(todo_data)
            await session.flush()

            if todo_plan.tags:
                seen_tag_ids: set[UUID] = set()
                for raw_tag in todo_plan.tags:
                    tag_name = raw_tag.strip()
                    if not tag_name:
                        continue
                    tag_obj = await tag_service.get_or_create_tag(current_user_id, tag_name)
                    if tag_obj.id in seen_tag_ids:
                        continue
                    seen_tag_ids.add(tag_obj.id)
                    todo.todo_tags.append(m.TodoTag(todo_id=todo.id, tag_id=tag_obj.id))

            created_todos.append(todo)

        await session.commit()
    except Exception as exc:
        await _safe_session_rollback(session)
        return f"Error creating recurring todos: {exc!s}"

    return _format_recurring_result(
        series_name=parsed.series_name,
        start_date=start_date,
        end_date=end_date,
        rule_type=rule_type,
        timezone_name=timezone_name,
        created=created_todos,
        planned_count=len(occurrences),
        rescheduled_count=rescheduled_count,
        failures=failures,
        month_adjustments=month_adjustments,
        user_tz=user_tz,
    )


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Invalid date format '{value}'. Use YYYY-MM-DD") from exc


def _parse_time(value: str) -> time:
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    msg = f"Invalid time format '{value}'. Use HH:MM"
    raise ValueError(msg)


def _parse_rule_payload(value: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"rule_payload must be valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("rule_payload must be a JSON object")
    return payload


def _normalize_rule_type(value: str) -> str:
    rule = value.strip().lower()
    allowed = {"daily", "weekly", "monthly", "interval"}
    if rule not in allowed:
        raise ValueError(f"Unsupported rule_type '{value}'. Use: daily, weekly, monthly, interval")
    return rule


def _normalize_weekdays(values: Iterable[object]) -> list[int]:
    normalized: list[int] = []
    for raw in values:
        if isinstance(raw, int):
            if 0 <= raw <= 6:
                normalized.append(raw)
                continue
            if 1 <= raw <= 7:
                normalized.append(raw - 1)
                continue
        if isinstance(raw, str):
            key = raw.strip().lower()
            if key.isdigit():
                num = int(key)
                if 0 <= num <= 6:
                    normalized.append(num)
                    continue
                if 1 <= num <= 7:
                    normalized.append(num - 1)
                    continue
            if key in _WEEKDAY_ALIASES:
                normalized.append(_WEEKDAY_ALIASES[key])
                continue
        raise ValueError(f"Invalid weekday value '{raw}'")
    if not normalized:
        raise ValueError("Weekly rule requires at least one weekday")
    return sorted(set(normalized))


def _parse_template(raw: Any) -> RecurringTodoTemplate:
    if raw is None:
        return RecurringTodoTemplate()
    if isinstance(raw, RecurringTodoTemplate):
        return raw
    if isinstance(raw, dict):
        return RecurringTodoTemplate.model_validate(raw)
    raise ValueError("Invalid template format")


def _build_occurrences(
    rule_type: str,
    rule_payload: dict[str, Any],
    start_date: date,
    end_date: date,
    default_template: RecurringTodoTemplate | None,
) -> tuple[list[Occurrence], list[str]]:
    occurrences: list[Occurrence] = []
    month_adjustments: list[str] = []
    fallback_template = default_template or RecurringTodoTemplate()

    if rule_type == "daily":
        template = _parse_template(rule_payload.get("template"))
        if _is_template_empty(template):
            template = fallback_template
        current = start_date
        while current <= end_date:
            occurrences.append(Occurrence(current, template))
            current += timedelta(days=1)
        return occurrences, month_adjustments

    if rule_type == "weekly":
        raw_days = rule_payload.get("days")
        if not isinstance(raw_days, list):
            raise ValueError("Weekly rule requires 'days' as a list")
        weekdays = _normalize_weekdays(raw_days)
        templates = rule_payload.get("templates", {}) if isinstance(rule_payload.get("templates", {}), dict) else {}
        current = start_date
        while current <= end_date:
            day_index = current.weekday()
            if day_index in weekdays:
                template = _template_for_weekday(day_index, templates, fallback_template)
                occurrences.append(Occurrence(current, template))
            current += timedelta(days=1)
        return occurrences, month_adjustments

    if rule_type == "monthly":
        raw_day = rule_payload.get("day")
        if not isinstance(raw_day, int) or raw_day < 1 or raw_day > 31:
            raise ValueError("Monthly rule requires 'day' between 1 and 31")
        template = _parse_template(rule_payload.get("template"))
        if _is_template_empty(template):
            template = fallback_template
        for year, month in _month_range(start_date, end_date):
            last_day = _last_day_of_month(year, month)
            target_day = raw_day
            if raw_day > last_day:
                target_day = last_day
                month_adjustments.append(
                    f"{year:04d}-{month:02d}-{raw_day:02d} -> {year:04d}-{month:02d}-{last_day:02d}"
                )
            target = date(year, month, target_day)
            if start_date <= target <= end_date:
                occurrences.append(Occurrence(target, template))
        return occurrences, month_adjustments

    if rule_type == "interval":
        cycle = _build_interval_cycle(rule_payload, fallback_template)
        if not cycle:
            raise ValueError("Interval rule requires a non-empty cycle")
        current = start_date
        index = 0
        while current <= end_date:
            cycle_type, template = cycle[index % len(cycle)]
            if cycle_type == "work":
                occurrences.append(Occurrence(current, template))
            current += timedelta(days=1)
            index += 1
        return occurrences, month_adjustments

    raise ValueError(f"Unsupported rule_type '{rule_type}'")


def _template_for_weekday(
    weekday: int,
    templates: dict[str, Any],
    fallback_template: RecurringTodoTemplate,
) -> RecurringTodoTemplate:
    if weekday in templates:
        return _parse_template(templates[weekday])
    key = str(weekday)
    if key in templates:
        return _parse_template(templates[key])
    for alias in _WEEKDAY_NAMES.get(weekday, []):
        if alias in templates:
            return _parse_template(templates[alias])
    return fallback_template


def _build_interval_cycle(
    rule_payload: dict[str, Any],
    fallback_template: RecurringTodoTemplate,
) -> list[tuple[str, RecurringTodoTemplate]]:
    cycle_payload = rule_payload.get("cycle")
    if isinstance(cycle_payload, list) and cycle_payload:
        cycle: list[tuple[str, RecurringTodoTemplate]] = []
        for entry in cycle_payload:
            if not isinstance(entry, dict):
                raise ValueError("Interval cycle entries must be objects")
            entry_type = str(entry.get("type", "")).strip().lower()
            if entry_type not in {"work", "rest"}:
                raise ValueError("Interval cycle type must be 'work' or 'rest'")
            if entry_type == "work":
                template = _parse_template(entry.get("template"))
                if _is_template_empty(template):
                    template = fallback_template
            else:
                template = fallback_template
            cycle.append((entry_type, template))
        return cycle

    work_days = rule_payload.get("work_days")
    rest_days = rule_payload.get("rest_days", 0)
    if isinstance(work_days, int) and work_days > 0 and isinstance(rest_days, int) and rest_days >= 0:
        template = _parse_template(rule_payload.get("template"))
        if _is_template_empty(template):
            template = fallback_template
        cycle = [("work", template) for _ in range(work_days)] + [("rest", fallback_template) for _ in range(rest_days)]
        return cycle

    raise ValueError("Interval rule requires 'cycle' or 'work_days'/'rest_days'")


def _month_range(start_date: date, end_date: date) -> Iterable[tuple[int, int]]:
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        yield year, month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1


def _last_day_of_month(year: int, month: int) -> int:
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (next_month - timedelta(days=1)).day


def _resolve_default_start_time(parsed: RecurringTodoArgs) -> time:
    if parsed.default_start_time:
        return _parse_time(parsed.default_start_time)
    if parsed.default_template and parsed.default_template.start_time:
        return _parse_time(parsed.default_template.start_time)
    return time(9, 0)


def _resolve_default_duration(parsed: RecurringTodoArgs) -> int:
    if parsed.default_template and parsed.default_template.duration_minutes:
        return parsed.default_template.duration_minutes
    return parsed.default_duration_minutes


def _is_template_empty(template: RecurringTodoTemplate) -> bool:
    return not template.model_dump(exclude_none=True)


def _resolve_template(
    template: RecurringTodoTemplate,
    fallback: RecurringTodoTemplate | None,
    default_start_time: time,
    default_duration: int,
    default_tags: list[str] | None,
    default_importance: str,
    user_tz: ZoneInfo,
    target_date: date,
) -> ResolvedTodo:
    base = fallback or RecurringTodoTemplate()
    item = template.item or base.item
    if not item:
        raise ValueError("missing item title")

    description = template.description if template.description is not None else base.description
    start_time_str = template.start_time or base.start_time
    start_clock = _parse_time(start_time_str) if start_time_str else default_start_time

    duration = template.duration_minutes or base.duration_minutes or default_duration
    if duration <= 0:
        raise ValueError("duration_minutes must be positive")

    tags = template.tags if template.tags is not None else base.tags
    if tags is None:
        tags = default_tags or []

    importance_raw = template.importance or base.importance or default_importance
    try:
        importance_enum = Importance(importance_raw.lower())
    except ValueError:
        importance_enum = Importance.NONE

    start_dt = datetime.combine(target_date, start_clock, tzinfo=user_tz)
    end_dt = start_dt + timedelta(minutes=duration)

    return ResolvedTodo(
        item=item,
        description=description,
        start_time=start_dt,
        end_time=end_dt,
        alarm_time=start_dt,
        tags=list(tags),
        importance=importance_enum,
    )


def _load_date_bounds(start_date: date, end_date: date, user_tz: ZoneInfo) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(start_date, time(0, 0), tzinfo=user_tz)
    end_dt = datetime.combine(end_date, time(23, 59, 59), tzinfo=user_tz)
    return start_dt.astimezone(UTC), end_dt.astimezone(UTC)


async def _load_existing_blocks(
    todo_service,
    current_user_id: UUID,
    start_date: date,
    end_date: date,
    user_tz: ZoneInfo,
) -> dict[date, list[TimeBlock]]:
    start_utc, end_utc = _load_date_bounds(start_date, end_date, user_tz)
    filters = [
        m.Todo.user_id == current_user_id,
        m.Todo.start_time < end_utc,
        m.Todo.end_time > start_utc,
    ]
    existing, _ = await todo_service.list_and_count(*filters)

    blocks: dict[date, list[TimeBlock]] = {}
    for todo in existing:
        if not todo.start_time or not todo.end_time:
            continue
        start_local = todo.start_time.astimezone(user_tz)
        end_local = todo.end_time.astimezone(user_tz)
        _add_blocks_for_range(blocks, start_local, end_local, user_tz)

    return blocks


def _add_blocks_for_range(
    blocks: dict[date, list[TimeBlock]],
    start_local: datetime,
    end_local: datetime,
    user_tz: ZoneInfo,
) -> None:
    current_day = start_local.date()
    last_day = end_local.date()
    while current_day <= last_day:
        day_start = datetime.combine(current_day, time(0, 0), tzinfo=user_tz)
        day_end = datetime.combine(current_day, time(23, 59, 59), tzinfo=user_tz)
        block_start = start_local if current_day == start_local.date() else day_start
        block_end = end_local if current_day == end_local.date() else day_end
        blocks.setdefault(current_day, []).append(TimeBlock(block_start, block_end))
        current_day += timedelta(days=1)


def _find_next_free_slot(
    target_date: date,
    desired_start: datetime,
    duration: timedelta,
    blocks: list[TimeBlock],
    user_tz: ZoneInfo,
) -> datetime | None:
    day_start = datetime.combine(target_date, time(8, 0), tzinfo=user_tz)
    day_end = datetime.combine(target_date, time(22, 0), tzinfo=user_tz)

    search_start = max(desired_start, day_start)
    return find_free_slot_in_blocks(search_start, day_end, duration, blocks)


def _format_recurring_result(
    *,
    series_name: str,
    start_date: date,
    end_date: date,
    rule_type: str,
    timezone_name: str | None,
    created: list[m.Todo],
    planned_count: int,
    rescheduled_count: int,
    failures: list[str],
    month_adjustments: list[str],
    user_tz: ZoneInfo,
) -> str:
    created_count = len(created)
    failure_count = len(failures)

    lines = [
        f"✅ Recurring todos created: {series_name}",
        f"Range: {start_date} to {end_date} | Rule: {rule_type}",
        f"Planned: {planned_count} | Created: {created_count} | Failed: {failure_count}",
    ]

    if rescheduled_count:
        lines.append(f"Rescheduled to free slots: {rescheduled_count}")

    if month_adjustments:
        preview = ", ".join(month_adjustments[:5])
        suffix = "..." if len(month_adjustments) > 5 else ""
        lines.append(f"⚠️ Monthly date adjusted to month-end: {preview}{suffix}")

    sample_lines: list[str] = []
    for todo in created[:5]:
        start_local = todo.start_time.astimezone(user_tz)
        end_local = todo.end_time.astimezone(user_tz)
        sample_lines.append(f"  • {start_local.strftime('%Y-%m-%d %H:%M')} - {end_local.strftime('%H:%M')} {todo.item}")
    if sample_lines:
        lines.append("Samples (up to 5):\n" + "\n".join(sample_lines))

    if failures:
        preview = "\n".join(f"  • {item}" for item in failures[:5])
        lines.append("Failures (up to 5):\n" + preview)

    if timezone_name and str(user_tz) != "UTC":
        lines.append(f"Times shown in {timezone_name} timezone")

    lines.append("Note: Recurring items are collapsed in default lists. Use include_series_items=true to show all.")

    return "\n".join(lines)
