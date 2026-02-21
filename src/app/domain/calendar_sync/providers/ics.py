from __future__ import annotations

# ruff: noqa: TC001,TC003,TRY003,EM101,EM102
from datetime import datetime
from hashlib import sha1
from typing import Any

import httpx
from icalendar import Calendar

from app.db.models.calendar_connection import CalendarConnection

from .base import (
    CalendarProvider,
    CalendarProviderError,
    ExternalCalendarEvent,
    ProviderFetchResult,
    ProviderUpsertResult,
    ensure_utc,
)


class ICSCalendarProvider(CalendarProvider):
    """Read-only iCalendar subscription provider."""

    async def fetch_events(
        self,
        connection: CalendarConnection,
        credentials: dict[str, Any],
        *,
        start: datetime,
        end: datetime,
        cursor: str | None,
    ) -> ProviderFetchResult:
        del start, end, cursor

        ics_url = credentials.get("ics_url")
        if not ics_url:
            raise CalendarProviderError("ICS credentials require ics_url")

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(ics_url)

        if response.status_code >= 400:
            raise CalendarProviderError(f"ICS fetch failed: {response.text}")

        calendar = Calendar.from_ical(response.text)
        events: list[ExternalCalendarEvent] = []

        for component in calendar.walk():
            if component.name != "VEVENT":
                continue

            uid_value = component.get("UID")
            summary = str(component.get("SUMMARY") or "(No title)")
            description = str(component.get("DESCRIPTION")) if component.get("DESCRIPTION") else None

            start_raw = component.decoded("DTSTART")
            end_raw = component.decoded("DTEND") if component.get("DTEND") else start_raw
            start_time, all_day_from_start = ensure_utc(start_raw)
            end_time, all_day_from_end = ensure_utc(end_raw, is_end=True)

            last_modified = component.get("LAST-MODIFIED") or component.get("DTSTAMP")
            remote_updated_at = None
            if last_modified is not None:
                decoded = last_modified.dt if hasattr(last_modified, "dt") else last_modified
                remote_updated_at, _ = ensure_utc(decoded)

            remote_event_id = str(uid_value) if uid_value else sha1(
                f"{summary}-{start_time.isoformat()}-{end_time.isoformat()}".encode(),
                usedforsecurity=False,
            ).hexdigest()

            events.append(
                ExternalCalendarEvent(
                    remote_event_id=remote_event_id,
                    title=summary,
                    description=description,
                    start_time=start_time,
                    end_time=end_time,
                    all_day=all_day_from_start or all_day_from_end,
                    status=str(component.get("STATUS") or "confirmed").lower(),
                    source_timezone=None,
                    etag=None,
                    remote_created_at=None,
                    remote_updated_at=remote_updated_at,
                    payload={"ics": component.to_ical().decode("utf-8")},
                )
            )

        return ProviderFetchResult(events=events, next_cursor=None, credentials=credentials)

    async def upsert_event(
        self,
        connection: CalendarConnection,
        credentials: dict[str, Any],
        *,
        event: ExternalCalendarEvent,
        remote_event_id: str | None,
    ) -> ProviderUpsertResult:
        del connection, credentials, event, remote_event_id
        raise CalendarProviderError("ICS connections are read-only and do not support push")

    async def delete_event(
        self,
        connection: CalendarConnection,
        credentials: dict[str, Any],
        *,
        remote_event_id: str,
    ) -> dict[str, Any]:
        del connection, credentials, remote_event_id
        raise CalendarProviderError("ICS connections are read-only and do not support delete")
