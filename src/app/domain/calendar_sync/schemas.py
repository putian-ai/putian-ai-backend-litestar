from __future__ import annotations

# ruff: noqa: TC003
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.domain.accounts.schemas import PydanticBaseModel

CalendarProviderName = Literal["google", "caldav", "ics"]
CalendarSyncMode = Literal["pull", "push", "both"]
ConnectionSyncMode = Literal["two_way", "pull_only", "push_only"]


class CalendarConnectionCreate(PydanticBaseModel):
    provider: CalendarProviderName
    display_name: str = Field(min_length=1, max_length=255)
    calendar_id: str = "primary"
    sync_mode: ConnectionSyncMode = "two_way"
    is_default: bool = True
    credentials: dict[str, Any] | None = None


class CalendarConnectionUpdate(PydanticBaseModel):
    display_name: str | None = None
    calendar_id: str | None = None
    sync_mode: ConnectionSyncMode | None = None
    is_default: bool | None = None
    is_active: bool | None = None
    credentials: dict[str, Any] | None = None


class CalendarConnectionModel(PydanticBaseModel):
    id: UUID
    provider: str
    display_name: str
    calendar_id: str
    status: str
    sync_mode: str
    is_default: bool
    is_active: bool
    last_synced_at: datetime | None = None
    last_pull_at: datetime | None = None
    last_push_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class CalendarEventModel(PydanticBaseModel):
    id: UUID
    connection_id: UUID
    linked_todo_id: UUID | None = None
    provider: str
    remote_event_id: str
    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime
    all_day: bool
    status: str
    source_timezone: str | None = None
    remote_updated_at: datetime | None = None


class CalendarEventsResponse(PydanticBaseModel):
    items: list[CalendarEventModel]
    total: int


class CalendarSyncRequest(PydanticBaseModel):
    mode: CalendarSyncMode = "both"
    start_time: datetime | None = None
    end_time: datetime | None = None


class CalendarSyncResult(PydanticBaseModel):
    status: str
    mode: CalendarSyncMode
    pulled_inserted: int = 0
    pulled_updated: int = 0
    pulled_deleted: int = 0
    pushed_inserted: int = 0
    pushed_updated: int = 0
    pushed_deleted: int = 0
    message: str | None = None


class GoogleAuthorizeResponse(PydanticBaseModel):
    authorize_url: str


class GoogleCallbackResponse(PydanticBaseModel):
    status: str
    message: str


class CalendarPushTodoRequest(PydanticBaseModel):
    todo_id: UUID


class CalendarPullRequest(PydanticBaseModel):
    connection_id: UUID
    start_time: datetime | None = None
    end_time: datetime | None = None
