"""URL constants for calendar sync domain."""

CALENDAR_BASE = "/api/calendar"
CALENDAR_CONNECTIONS = f"{CALENDAR_BASE}/connections"
CALENDAR_CONNECTION_SYNC = f"{CALENDAR_CONNECTIONS}/{{connection_id:uuid}}/sync"
CALENDAR_EVENTS = f"{CALENDAR_BASE}/events"

CALENDAR_GOOGLE_AUTHORIZE = f"{CALENDAR_BASE}/providers/google/authorize"
CALENDAR_GOOGLE_CALLBACK = f"{CALENDAR_BASE}/providers/google/callback"
CALENDAR_GOOGLE_WEBHOOK = f"{CALENDAR_BASE}/webhooks/google"
