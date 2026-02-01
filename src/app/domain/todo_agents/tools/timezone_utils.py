"""Shared helpers for timezone handling in todo agent tools."""

from __future__ import annotations

from typing import Final
from zoneinfo import ZoneInfo

__all__ = ["resolve_timezone"]

DEFAULT_TIMEZONE: Final[str] = "UTC"


def resolve_timezone(
    requested_timezone: str | None,
    fallback_timezone: str | None = None,
    default_timezone: str = DEFAULT_TIMEZONE,
) -> tuple[ZoneInfo, str] | str:
    """Resolve timezone string to ZoneInfo.

    Returns:
        Tuple of (ZoneInfo, timezone_name) if valid, otherwise an error string.
    """
    timezone_name = requested_timezone or fallback_timezone or default_timezone
    try:
        return ZoneInfo(timezone_name), timezone_name
    except Exception:
        return (
            f"Error: Invalid timezone '{timezone_name}'. "
            "Use a valid timezone name like 'America/New_York' or 'Asia/Shanghai'"
        )
