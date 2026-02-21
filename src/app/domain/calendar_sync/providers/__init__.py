from __future__ import annotations

from .base import CalendarProvider
from .caldav import CalDAVCalendarProvider
from .google import GoogleCalendarProvider
from .ics import ICSCalendarProvider


def get_calendar_provider(provider: str) -> CalendarProvider:
    normalized = provider.lower()
    if normalized == "google":
        return GoogleCalendarProvider()
    if normalized == "caldav":
        return CalDAVCalendarProvider()
    if normalized == "ics":
        return ICSCalendarProvider()
    msg = f"Unsupported calendar provider: {provider}"
    raise ValueError(msg)


__all__ = [
    "CalDAVCalendarProvider",
    "CalendarProvider",
    "GoogleCalendarProvider",
    "ICSCalendarProvider",
    "get_calendar_provider",
]
