"""Universal tools for AI agents.

This module contains tools that can be used by any AI agent across the system.
These tools provide common functionality that multiple agents may need.
"""

import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, available_timezones

from agents import RunContextWrapper

from .tool_context import get_user_timezone
__all__ = [
    "get_user_datetime_impl",
]


def _parse_timezone(timezone_str: str) -> tuple[ZoneInfo, str] | str:
    """Parse and validate timezone string.

    Returns:
        Tuple of (ZoneInfo, display_name) if valid, error message if invalid
    """
    if timezone_str.upper() == "UTC":
        return ZoneInfo("UTC"), "UTC"

    if timezone_str not in available_timezones():
        return (f"❌ Error: Invalid timezone '{timezone_str}'. "
                "Please use a valid timezone like 'America/New_York', 'Europe/London', 'Asia/Shanghai', etc.")

    return ZoneInfo(timezone_str), timezone_str


def _format_utc_offset(current_user_time: datetime) -> str:
    """Format UTC offset display string."""
    utc_offset = current_user_time.strftime("%z")
    if not utc_offset:
        return "UTC+0"

    hours = int(utc_offset[:3])
    minutes = int(utc_offset[3:])

    if hours >= 0:
        offset_display = f"UTC+{hours}"
        if minutes != 0:
            offset_display += f":{minutes:02d}"
    else:
        offset_display = f"UTC{hours}"  # hours already includes the minus sign
        if minutes != 0:
            offset_display += f":{abs(minutes):02d}"

    return offset_display


def _get_time_period(hour_24: int) -> str:
    """Get time period emoji and description based on hour."""
    if 5 <= hour_24 < 12:
        return "🌅 Morning"
    if 12 <= hour_24 < 17:
        return "☀️ Afternoon"
    if 17 <= hour_24 < 21:
        return "🌆 Evening"
    return "🌙 Night"


def _get_business_day_info(weekday: int) -> str:
    """Get business day information based on weekday."""
    return "💼 Business day: Yes (weekday)" if weekday < 5 else "🏖️ Business day: No (weekend)"


async def get_user_datetime_impl(ctx: RunContextWrapper, args: str) -> str:
    """Get the user's current date, time, and timezone information.

    This tool provides the current date and time in the user's specified timezone,
    or in UTC if no timezone is specified. It's useful when the language model
    needs to know the current time context for scheduling, filtering, or any
    time-based operations.

    Args:
        ctx: The runtime context wrapper containing user information
        args: JSON string containing optional timezone specification:
               {
                 "timezone": "America/New_York"  // optional, defaults to UTC
               }

    Returns:
        Formatted string with current date, time, timezone, and additional context
    """
    try:
        # Parse arguments
        try:
            parsed_args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            parsed_args = {}

        # Prefer context timezone to avoid tool call overrides.
        timezone_str = get_user_timezone()
        if not timezone_str:
            timezone_str = parsed_args.get("timezone") or "UTC"

        # Validate and parse timezone
        try:
            timezone_result = _parse_timezone(timezone_str)
            if isinstance(timezone_result, str):
                return timezone_result  # Error message

            user_tz, tz_display_name = timezone_result

        except (ValueError, KeyError) as e:
            return f"❌ Error: Could not parse timezone '{timezone_str}': {e!s}"

        # Get current time in user's timezone
        current_utc = datetime.now(tz=UTC)
        current_user_time = current_utc.astimezone(user_tz)

        # Format basic time information
        formatted_datetime = current_user_time.strftime(
            "%A, %B %d, %Y at %I:%M:%S %p %Z")
        iso_format = current_user_time.isoformat()
        day_of_week = current_user_time.strftime("%A")
        week_number = current_user_time.isocalendar()[1]

        # Calculate UTC offset
        offset_display = _format_utc_offset(current_user_time)

        # Build comprehensive response
        response_parts = [
            f"🕐 Current date and time: {formatted_datetime}",
            f"🌍 Timezone: {tz_display_name} ({offset_display})",
            f"📅 ISO format: {iso_format}",
            f"📆 Day of week: {day_of_week}",
            f"📊 Week number: {week_number}",
            f"⏰ Time period: {_get_time_period(current_user_time.hour)}",
            _get_business_day_info(current_user_time.weekday()),
        ]

        return "\n".join(response_parts)

    except (ValueError, KeyError, TypeError) as e:
        return f"❌ Error getting current date and time: {e!s}"


# Tool registration for the agent system
UNIVERSAL_TOOLS = {
    "get_user_datetime": {
        "function": get_user_datetime_impl,
        "description": "Get the user's current date, time, and timezone information",
        "parameters": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "The user's timezone (e.g., 'America/New_York', 'Europe/London'). Defaults to UTC if not specified."
                }
            },
            "required": []
        }
    }
}
