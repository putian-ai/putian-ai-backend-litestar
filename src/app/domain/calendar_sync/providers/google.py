from __future__ import annotations

# ruff: noqa: TC001,TRY003,EM101,EM102
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from app.config.base import get_settings
from app.db.models.calendar_connection import CalendarConnection

from .base import (
    CalendarProvider,
    CalendarProviderError,
    CalendarSyncCursorError,
    ExternalCalendarEvent,
    ProviderFetchResult,
    ProviderUpsertResult,
    ensure_utc,
)

GOOGLE_OAUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105
GOOGLE_API_ROOT = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar provider with bidirectional sync."""

    async def build_authorize_url(self, *, state: str) -> str:
        settings = get_settings()
        scopes = " ".join(settings.calendar.GOOGLE_OAUTH_SCOPES)

        params = {
            "client_id": settings.calendar.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.calendar.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": scopes,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        return str(httpx.URL(GOOGLE_OAUTH_URL, params=params))

    async def exchange_code(self, *, code: str) -> dict[str, Any]:
        settings = get_settings()
        payload = {
            "code": code,
            "client_id": settings.calendar.GOOGLE_CLIENT_ID,
            "client_secret": settings.calendar.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.calendar.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(GOOGLE_TOKEN_URL, data=payload)

        if response.status_code >= 400:
            raise CalendarProviderError(f"Google token exchange failed: {response.text}")

        token = response.json()
        expires_in = int(token.get("expires_in", 3600))
        return {
            "access_token": token["access_token"],
            "refresh_token": token.get("refresh_token"),
            "token_type": token.get("token_type", "Bearer"),
            "scope": token.get("scope"),
            "expires_at": int((datetime.now(UTC) + timedelta(seconds=expires_in)).timestamp()),
        }

    async def fetch_events(
        self,
        connection: CalendarConnection,
        credentials: dict[str, Any],
        *,
        start: datetime,
        end: datetime,
        cursor: str | None,
    ) -> ProviderFetchResult:
        credentials = await self._ensure_access_token(credentials)

        params: dict[str, Any] = {
            "singleEvents": "true",
            "showDeleted": "true",
            "maxResults": "2500",
        }
        if cursor:
            params["syncToken"] = cursor
        else:
            params["timeMin"] = start.astimezone(UTC).isoformat().replace("+00:00", "Z")
            params["timeMax"] = end.astimezone(UTC).isoformat().replace("+00:00", "Z")

        calendar_id = quote(connection.calendar_id, safe="")
        url = f"{GOOGLE_API_ROOT}/calendars/{calendar_id}/events"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params=params, headers=self._auth_headers(credentials))

        if response.status_code == 401:
            credentials = await self._refresh_access_token(credentials)
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, params=params, headers=self._auth_headers(credentials))

        if response.status_code == 410 and cursor:
            raise CalendarSyncCursorError("Google sync token expired")

        if response.status_code >= 400:
            raise CalendarProviderError(f"Google fetch events failed: {response.text}")

        payload = response.json()
        events = [self._to_external_event(item) for item in payload.get("items", []) if item.get("id")]

        return ProviderFetchResult(
            events=events,
            next_cursor=payload.get("nextSyncToken") or cursor,
            credentials=credentials,
        )

    async def upsert_event(
        self,
        connection: CalendarConnection,
        credentials: dict[str, Any],
        *,
        event: ExternalCalendarEvent,
        remote_event_id: str | None,
    ) -> ProviderUpsertResult:
        credentials = await self._ensure_access_token(credentials)
        calendar_id = quote(connection.calendar_id, safe="")

        body = self._to_google_payload(event)

        if remote_event_id:
            event_id = quote(remote_event_id, safe="")
            method = "PUT"
            url = f"{GOOGLE_API_ROOT}/calendars/{calendar_id}/events/{event_id}"
        else:
            method = "POST"
            url = f"{GOOGLE_API_ROOT}/calendars/{calendar_id}/events"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(method, url, json=body, headers=self._auth_headers(credentials))

        if response.status_code == 401:
            credentials = await self._refresh_access_token(credentials)
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.request(method, url, json=body, headers=self._auth_headers(credentials))

        if response.status_code >= 400:
            raise CalendarProviderError(f"Google upsert event failed: {response.text}")

        return ProviderUpsertResult(
            event=self._to_external_event(response.json()),
            credentials=credentials,
        )

    async def delete_event(
        self,
        connection: CalendarConnection,
        credentials: dict[str, Any],
        *,
        remote_event_id: str,
    ) -> dict[str, Any]:
        credentials = await self._ensure_access_token(credentials)
        calendar_id = quote(connection.calendar_id, safe="")
        event_id = quote(remote_event_id, safe="")
        url = f"{GOOGLE_API_ROOT}/calendars/{calendar_id}/events/{event_id}"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.delete(url, headers=self._auth_headers(credentials))

        if response.status_code == 401:
            credentials = await self._refresh_access_token(credentials)
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.delete(url, headers=self._auth_headers(credentials))

        if response.status_code not in {200, 204, 404}:
            raise CalendarProviderError(f"Google delete event failed: {response.text}")

        return credentials

    async def _ensure_access_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        expires_at = int(credentials.get("expires_at", 0) or 0)
        if expires_at <= int(datetime.now(UTC).timestamp()) + 30:
            return await self._refresh_access_token(credentials)
        return credentials

    async def _refresh_access_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise CalendarProviderError("Google refresh token is missing")

        settings = get_settings()
        payload = {
            "client_id": settings.calendar.GOOGLE_CLIENT_ID,
            "client_secret": settings.calendar.GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(GOOGLE_TOKEN_URL, data=payload)

        if response.status_code >= 400:
            raise CalendarProviderError(f"Google refresh token failed: {response.text}")

        token = response.json()
        expires_in = int(token.get("expires_in", 3600))
        next_credentials = dict(credentials)
        next_credentials["access_token"] = token["access_token"]
        next_credentials["token_type"] = token.get("token_type", "Bearer")
        next_credentials["expires_at"] = int((datetime.now(UTC) + timedelta(seconds=expires_in)).timestamp())
        if token.get("refresh_token"):
            next_credentials["refresh_token"] = token["refresh_token"]
        return next_credentials

    @staticmethod
    def _auth_headers(credentials: dict[str, Any]) -> dict[str, str]:
        token = credentials.get("access_token")
        if not token:
            raise CalendarProviderError("Google access token is missing")
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _to_google_payload(event: ExternalCalendarEvent) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "summary": event.title,
            "description": event.description or "",
            "status": event.status or "confirmed",
        }

        if event.all_day:
            start_date = event.start_time.date()
            end_date = event.end_time.date()
            if end_date <= start_date:
                end_date = start_date + timedelta(days=1)
            payload["start"] = {"date": start_date.isoformat()}
            payload["end"] = {"date": end_date.isoformat()}
        else:
            timezone = event.source_timezone or "UTC"
            payload["start"] = {
                "dateTime": event.start_time.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                "timeZone": timezone,
            }
            payload["end"] = {
                "dateTime": event.end_time.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                "timeZone": timezone,
            }

        return payload

    @staticmethod
    def _parse_google_datetime(value: dict[str, Any], *, is_end: bool = False) -> tuple[datetime, bool, str | None]:
        timezone = value.get("timeZone")

        date_time = value.get("dateTime")
        if date_time:
            normalized = datetime.fromisoformat(date_time)
            if normalized.tzinfo is None:
                normalized = normalized.replace(tzinfo=UTC)
            return normalized.astimezone(UTC), False, timezone

        date_value = value.get("date")
        if not date_value:
            now = datetime.now(UTC)
            return now, False, timezone

        dt, all_day = ensure_utc(date.fromisoformat(date_value), is_end=is_end)
        return dt, all_day, timezone

    def _to_external_event(self, item: dict[str, Any]) -> ExternalCalendarEvent:
        start_time, all_day_from_start, timezone = self._parse_google_datetime(item.get("start", {}), is_end=False)
        end_time, all_day_from_end, timezone_from_end = self._parse_google_datetime(item.get("end", {}), is_end=True)

        created_at = item.get("created")
        updated_at = item.get("updated")

        return ExternalCalendarEvent(
            remote_event_id=str(item["id"]),
            title=item.get("summary") or "(No title)",
            description=item.get("description"),
            start_time=start_time,
            end_time=end_time,
            all_day=all_day_from_start or all_day_from_end,
            status=(item.get("status") or "confirmed").lower(),
            source_timezone=timezone or timezone_from_end,
            etag=item.get("etag"),
            remote_created_at=datetime.fromisoformat(created_at) if created_at else None,
            remote_updated_at=datetime.fromisoformat(updated_at) if updated_at else None,
            payload=item,
        )
