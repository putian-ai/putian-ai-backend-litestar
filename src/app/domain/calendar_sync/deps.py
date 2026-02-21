"""Dependency providers for calendar sync domain."""

from __future__ import annotations

# ruff: noqa: PLC0415
from typing import TYPE_CHECKING

from sqlalchemy.orm import joinedload

from app.db import models as m
from app.domain.calendar_sync.services import (
    CalendarConnectionService,
    CalendarEventService,
    TodoCalendarLinkService,
    create_calendar_sync_service,
)
from app.lib.deps import create_service_provider

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.domain.calendar_sync.services import CalendarSyncService


provide_calendar_connection_service = create_service_provider(
    CalendarConnectionService,
    load=[
        joinedload(m.CalendarConnection.user, innerjoin=True),
    ],
    error_messages={
        "duplicate_key": "Calendar connection already exists.",
        "integrity": "Calendar connection operation failed.",
    },
)

provide_calendar_event_service = create_service_provider(
    CalendarEventService,
    load=[
        joinedload(m.CalendarEvent.connection, innerjoin=True),
    ],
    error_messages={
        "duplicate_key": "Calendar event already exists.",
        "integrity": "Calendar event operation failed.",
    },
)

provide_todo_calendar_link_service = create_service_provider(
    TodoCalendarLinkService,
    load=[
        joinedload(m.TodoCalendarLink.connection, innerjoin=True),
        joinedload(m.TodoCalendarLink.todo, innerjoin=True),
    ],
    error_messages={
        "duplicate_key": "Todo calendar link already exists.",
        "integrity": "Todo calendar link operation failed.",
    },
)


async def provide_calendar_sync_service(
    db_session: "AsyncSession",
) -> "CalendarSyncService":
    from app.domain.todo.services import TodoService

    return create_calendar_sync_service(
        connection_service=CalendarConnectionService(session=db_session),
        event_service=CalendarEventService(session=db_session),
        link_service=TodoCalendarLinkService(session=db_session),
        todo_service=TodoService(session=db_session),
    )
