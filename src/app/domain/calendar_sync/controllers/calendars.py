from __future__ import annotations

# ruff: noqa: TC001,TC003
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

import structlog
from litestar import Controller, Request, Response, delete, get, patch, post
from litestar.di import Provide
from litestar.params import Dependency, Parameter

import app.db.models as m
from app.config.base import get_settings
from app.domain.calendar_sync import urls
from app.domain.calendar_sync.deps import (
    provide_calendar_connection_service,
    provide_calendar_event_service,
    provide_calendar_sync_service,
    provide_todo_calendar_link_service,
)
from app.domain.calendar_sync.schemas import (
    CalendarConnectionCreate,
    CalendarConnectionModel,
    CalendarConnectionUpdate,
    CalendarEventModel,
    CalendarEventsResponse,
    CalendarSyncRequest,
    CalendarSyncResult,
    GoogleAuthorizeResponse,
    GoogleCallbackResponse,
)
from app.domain.calendar_sync.services import (
    CalendarConnectionService,
    CalendarSyncService,
    SyncCounters,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = structlog.get_logger()


class CalendarSyncController(Controller):
    """Calendar sync endpoints for connection management and bidirectional sync."""

    tags = ["Calendar Sync"]
    path = urls.CALENDAR_BASE

    dependencies = {
        "calendar_connection_service": Provide(provide_calendar_connection_service),
        "calendar_event_service": Provide(provide_calendar_event_service),
        "todo_calendar_link_service": Provide(provide_todo_calendar_link_service),
        "calendar_sync_service": Provide(provide_calendar_sync_service),
    }

    @post(path="/connections", operation_id="create_calendar_connection")
    async def create_connection(
        self,
        current_user: m.User,
        data: CalendarConnectionCreate,
        calendar_sync_service: Annotated[CalendarSyncService, Dependency(skip_validation=True)],
    ) -> CalendarConnectionModel:
        connection = await calendar_sync_service.create_connection(user_id=current_user.id, data=data)
        return CalendarConnectionModel.model_validate(connection, from_attributes=True)

    @patch(path="/connections/{connection_id:uuid}", operation_id="update_calendar_connection")
    async def update_connection(
        self,
        current_user: m.User,
        connection_id: UUID,
        data: CalendarConnectionUpdate,
        calendar_sync_service: Annotated[CalendarSyncService, Dependency(skip_validation=True)],
    ) -> CalendarConnectionModel:
        connection = await calendar_sync_service.update_connection(
            user_id=current_user.id,
            connection_id=connection_id,
            data=data,
        )
        return CalendarConnectionModel.model_validate(connection, from_attributes=True)

    @get(path="/connections", operation_id="list_calendar_connections")
    async def list_connections(
        self,
        current_user: m.User,
        calendar_sync_service: Annotated[CalendarSyncService, Dependency(skip_validation=True)],
    ) -> list[CalendarConnectionModel]:
        connections = await calendar_sync_service.list_connections(user_id=current_user.id)
        return [CalendarConnectionModel.model_validate(connection, from_attributes=True) for connection in connections]

    @delete(path="/connections/{connection_id:uuid}", operation_id="delete_calendar_connection", status_code=200)
    async def delete_connection(
        self,
        current_user: m.User,
        connection_id: UUID,
        calendar_sync_service: Annotated[CalendarSyncService, Dependency(skip_validation=True)],
    ) -> dict[str, str]:
        await calendar_sync_service.delete_connection(user_id=current_user.id, connection_id=connection_id)
        return {"status": "success", "message": "Connection deleted"}

    @post(path="/connections/{connection_id:uuid}/sync", operation_id="sync_calendar_connection")
    async def sync_connection(
        self,
        current_user: m.User,
        connection_id: UUID,
        data: CalendarSyncRequest,
        calendar_sync_service: Annotated[CalendarSyncService, Dependency(skip_validation=True)],
    ) -> CalendarSyncResult:
        counters = await calendar_sync_service.sync_connection(
            user_id=current_user.id,
            connection_id=connection_id,
            mode=data.mode,
            start_time=data.start_time,
            end_time=data.end_time,
        )
        return self._build_sync_result(counters=counters, mode=data.mode)

    @get(path="/events", operation_id="list_calendar_events")
    async def list_events(
        self,
        current_user: m.User,
        calendar_sync_service: Annotated[CalendarSyncService, Dependency(skip_validation=True)],
        start_time: Annotated[datetime | None, Parameter(query="start_time")] = None,
        end_time: Annotated[datetime | None, Parameter(query="end_time")] = None,
    ) -> CalendarEventsResponse:
        now = datetime.now(UTC)
        start = start_time or (now - timedelta(days=30))
        end = end_time or (now + timedelta(days=180))

        events, total = await calendar_sync_service.get_events(
            user_id=current_user.id,
            start_time=start,
            end_time=end,
        )
        return CalendarEventsResponse(
            items=self._to_event_models(events),
            total=total,
        )

    @get(path="/providers/google/authorize", operation_id="google_calendar_authorize")
    async def google_authorize(
        self,
        current_user: m.User,
        connection_id: Annotated[UUID, Parameter(query="connection_id")],
        calendar_sync_service: Annotated[CalendarSyncService, Dependency(skip_validation=True)],
    ) -> GoogleAuthorizeResponse:
        authorize_url = await calendar_sync_service.get_google_authorize_url(
            user_id=current_user.id,
            connection_id=connection_id,
        )
        return GoogleAuthorizeResponse(authorize_url=authorize_url)

    @get(
        path="/providers/google/callback",
        operation_id="google_calendar_callback",
        exclude_from_auth=True,
    )
    async def google_callback(
        self,
        code: Annotated[str, Parameter(query="code")],
        oauth_state: Annotated[str, Parameter(query="state")],
        calendar_sync_service: Annotated[CalendarSyncService, Dependency(skip_validation=True)],
    ) -> Response:
        await calendar_sync_service.handle_google_callback(code=code, state=oauth_state)

        content = (
            "<html><body><h3>Google calendar connected.</h3>"
            "<p>你可以回到应用点击“立即同步”。</p></body></html>"
        )
        return Response(content=content, status_code=200, media_type="text/html")

    @post(
        path="/webhooks/google",
        operation_id="google_calendar_webhook",
        exclude_from_auth=True,
    )
    async def google_webhook(
        self,
        request: Request,
        calendar_sync_service: Annotated[CalendarSyncService, Dependency(skip_validation=True)],
        calendar_connection_service: Annotated[CalendarConnectionService, Dependency(skip_validation=True)],
    ) -> GoogleCallbackResponse:
        channel_token = request.headers.get("x-goog-channel-token")
        expected_token = get_settings().calendar.GOOGLE_WEBHOOK_TOKEN
        if expected_token and channel_token != expected_token:
            return GoogleCallbackResponse(status="ignored", message="invalid webhook token")

        resource_id = request.headers.get("x-goog-resource-id")
        channel_id = request.headers.get("x-goog-channel-id")
        if not resource_id:
            return GoogleCallbackResponse(status="ignored", message="missing resource id")

        connection = await calendar_connection_service.get_one_or_none(
            m.CalendarConnection.provider == "google",
            m.CalendarConnection.webhook_resource_id == resource_id,
            m.CalendarConnection.webhook_channel_id == channel_id,
            m.CalendarConnection.is_active.is_(True),
        )
        if connection is None:
            return GoogleCallbackResponse(status="ignored", message="connection not found")

        try:
            await calendar_sync_service.sync_connection(
                user_id=connection.user_id,
                connection_id=connection.id,
                mode="pull",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Google webhook sync failed", error=str(exc), connection_id=str(connection.id))
            return GoogleCallbackResponse(status="error", message=str(exc))

        return GoogleCallbackResponse(status="success", message="sync queued")

    @staticmethod
    def _to_event_models(events: "Sequence[m.CalendarEvent]") -> list[CalendarEventModel]:
        return [CalendarEventModel.model_validate(event, from_attributes=True) for event in events]

    @staticmethod
    def _build_sync_result(*, counters: SyncCounters, mode: str) -> CalendarSyncResult:
        return CalendarSyncResult(
            status="success",
            mode=mode,
            pulled_inserted=counters.pulled_inserted,
            pulled_updated=counters.pulled_updated,
            pulled_deleted=counters.pulled_deleted,
            pushed_inserted=counters.pushed_inserted,
            pushed_updated=counters.pushed_updated,
            pushed_deleted=counters.pushed_deleted,
            message="sync completed",
        )
