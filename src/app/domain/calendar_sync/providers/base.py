from __future__ import annotations

# ruff: noqa: TC001
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any, Protocol

from app.db.models.calendar_connection import CalendarConnection


class CalendarProviderError(RuntimeError):
    """Raised when a provider call fails."""


class CalendarSyncCursorError(CalendarProviderError):
    """Raised when provider incremental cursor/token is no longer valid."""


@dataclass(slots=True)
class ExternalCalendarEvent:
    remote_event_id: str
    title: str
    description: str | None
    start_time: datetime
    end_time: datetime
    all_day: bool
    status: str
    source_timezone: str | None
    etag: str | None
    remote_created_at: datetime | None
    remote_updated_at: datetime | None
    payload: dict[str, Any]


@dataclass(slots=True)
class ProviderFetchResult:
    events: list[ExternalCalendarEvent]
    next_cursor: str | None
    credentials: dict[str, Any]


@dataclass(slots=True)
class ProviderUpsertResult:
    event: ExternalCalendarEvent
    credentials: dict[str, Any]


class CalendarProvider(Protocol):
    """Provider protocol for calendar adapters."""

    async def fetch_events(
        self,
        connection: CalendarConnection,
        credentials: dict[str, Any],
        *,
        start: datetime,
        end: datetime,
        cursor: str | None,
    ) -> ProviderFetchResult: ...

    async def upsert_event(
        self,
        connection: CalendarConnection,
        credentials: dict[str, Any],
        *,
        event: ExternalCalendarEvent,
        remote_event_id: str | None,
    ) -> ProviderUpsertResult: ...

    async def delete_event(
        self,
        connection: CalendarConnection,
        credentials: dict[str, Any],
        *,
        remote_event_id: str,
    ) -> dict[str, Any]: ...


def ensure_utc(value: datetime | date, *, is_end: bool = False) -> tuple[datetime, bool]:
    """Convert date/datetime values into UTC datetimes and all-day marker."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC), False
        return value.astimezone(UTC), False

    base_time = time(23, 59, 59) if is_end else time(0, 0, 0)
    return datetime.combine(value, base_time, tzinfo=UTC), True
