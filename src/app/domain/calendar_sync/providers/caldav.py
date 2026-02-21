from __future__ import annotations

# ruff: noqa: TC001,TRY003,EM101,S110
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from caldav import DAVClient
from caldav.lib import error as caldav_error
from icalendar import Calendar as ICalendar
from icalendar import Event as ICalEvent

from app.db.models.calendar_connection import CalendarConnection

from .base import (
    CalendarProvider,
    CalendarProviderError,
    ExternalCalendarEvent,
    ProviderFetchResult,
    ProviderUpsertResult,
    ensure_utc,
)


class CalDAVCalendarProvider(CalendarProvider):
    """CalDAV provider for iCloud and generic CalDAV servers."""

    async def fetch_events(
        self,
        connection: CalendarConnection,
        credentials: dict[str, Any],
        *,
        start: datetime,
        end: datetime,
        cursor: str | None,
    ) -> ProviderFetchResult:
        del cursor

        events = await asyncio.to_thread(
            self._fetch_events_sync,
            connection,
            credentials,
            start,
            end,
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
        mapped_event = await asyncio.to_thread(
            self._upsert_event_sync,
            connection,
            credentials,
            event,
            remote_event_id,
        )
        return ProviderUpsertResult(event=mapped_event, credentials=credentials)

    async def delete_event(
        self,
        connection: CalendarConnection,
        credentials: dict[str, Any],
        *,
        remote_event_id: str,
    ) -> dict[str, Any]:
        await asyncio.to_thread(
            self._delete_event_sync,
            connection,
            credentials,
            remote_event_id,
        )
        return credentials

    def _fetch_events_sync(
        self,
        connection: CalendarConnection,
        credentials: dict[str, Any],
        start: datetime,
        end: datetime,
    ) -> list[ExternalCalendarEvent]:
        with self._build_client(credentials) as client:
            principal = client.principal()
            calendar = self._select_calendar(principal, connection, credentials)
            resources = calendar.date_search(start, end, expand=True)
            return [self._to_external_event(resource) for resource in resources]

    def _upsert_event_sync(
        self,
        connection: CalendarConnection,
        credentials: dict[str, Any],
        event: ExternalCalendarEvent,
        remote_event_id: str | None,
    ) -> ExternalCalendarEvent:
        uid = remote_event_id or event.remote_event_id or str(uuid4())
        ical_payload = self._to_ical_event(event, uid=uid)

        with self._build_client(credentials) as client:
            principal = client.principal()
            calendar = self._select_calendar(principal, connection, credentials)
            resource = calendar.save_event(ical=ical_payload)
            return self._to_external_event(resource)

    def _delete_event_sync(
        self,
        connection: CalendarConnection,
        credentials: dict[str, Any],
        remote_event_id: str,
    ) -> None:
        with self._build_client(credentials) as client:
            principal = client.principal()
            calendar = self._select_calendar(principal, connection, credentials)
            try:
                event = calendar.event_by_uid(remote_event_id)
            except caldav_error.NotFoundError:
                return
            event.delete()

    @staticmethod
    def _build_client(credentials: dict[str, Any]) -> DAVClient:
        url = credentials.get("url")
        username = credentials.get("username")
        password = credentials.get("password")

        if not url or not username or not password:
            raise CalendarProviderError("CalDAV credentials require url, username and password")

        return DAVClient(
            url=url,
            username=username,
            password=password,
            ssl_verify_cert=credentials.get("ssl_verify", True),
            require_tls=credentials.get("require_tls", True),
        )

    @staticmethod
    def _select_calendar(principal: Any, connection: CalendarConnection, credentials: dict[str, Any]) -> Any:
        calendar_url = credentials.get("calendar_url")
        calendar_name = credentials.get("calendar_name")

        if calendar_url:
            return principal.calendar(cal_url=calendar_url)

        if connection.calendar_id and connection.calendar_id != "primary":
            try:
                return principal.calendar(cal_id=connection.calendar_id)
            except Exception:  # noqa: BLE001
                pass

        if calendar_name:
            try:
                return principal.calendar(name=calendar_name)
            except Exception:  # noqa: BLE001
                pass

        calendars = principal.calendars()
        if not calendars:
            raise CalendarProviderError("No CalDAV calendars found")

        return calendars[0]

    @staticmethod
    def _to_external_event(resource: Any) -> ExternalCalendarEvent:
        ical_instance = resource.icalendar_instance
        vevents = [component for component in ical_instance.walk() if component.name == "VEVENT"]
        if not vevents:
            raise CalendarProviderError("CalDAV event payload missing VEVENT")

        vevent = vevents[0]

        uid = str(vevent.get("UID") or resource.id)
        summary = str(vevent.get("SUMMARY") or "(No title)")
        description = str(vevent.get("DESCRIPTION")) if vevent.get("DESCRIPTION") else None

        start_raw = vevent.decoded("DTSTART")
        end_raw = vevent.decoded("DTEND") if vevent.get("DTEND") else start_raw

        start_time, all_day_start = ensure_utc(start_raw, is_end=False)
        end_time, all_day_end = ensure_utc(end_raw, is_end=True)

        dtstamp = vevent.get("DTSTAMP")
        remote_updated_at = None
        if dtstamp is not None:
            decoded = dtstamp.dt if hasattr(dtstamp, "dt") else dtstamp
            remote_updated_at, _ = ensure_utc(decoded, is_end=False)

        status_value = vevent.get("STATUS")
        status = str(status_value).lower() if status_value else "confirmed"

        return ExternalCalendarEvent(
            remote_event_id=uid,
            title=summary,
            description=description,
            start_time=start_time,
            end_time=end_time,
            all_day=all_day_start or all_day_end,
            status=status,
            source_timezone=None,
            etag=None,
            remote_created_at=None,
            remote_updated_at=remote_updated_at,
            payload={"ical": resource.data},
        )

    @staticmethod
    def _to_ical_event(event: ExternalCalendarEvent, *, uid: str) -> str:
        ical = ICalendar()
        ical.add("prodid", "-//Putian Todo//Calendar Sync//EN")
        ical.add("version", "2.0")

        vevent = ICalEvent()
        vevent.add("uid", uid)
        vevent.add("summary", event.title)
        if event.description:
            vevent.add("description", event.description)

        if event.all_day:
            start_date = event.start_time.date()
            end_date = event.end_time.date()
            if end_date <= start_date:
                end_date = start_date + timedelta(days=1)
            vevent.add("dtstart", start_date)
            vevent.add("dtend", end_date)
        else:
            vevent.add("dtstart", event.start_time.astimezone(UTC))
            vevent.add("dtend", event.end_time.astimezone(UTC))

        vevent.add("dtstamp", datetime.now(UTC))
        vevent.add("status", (event.status or "confirmed").upper())

        ical.add_component(vevent)
        return ical.to_ical().decode("utf-8")
