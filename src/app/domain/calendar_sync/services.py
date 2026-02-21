from __future__ import annotations

# ruff: noqa: TRY003, EM101, RET504
import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from inspect import isawaitable
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import structlog
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService

from app.config.base import get_settings
from app.db import models as m
from app.domain.calendar_sync.providers import get_calendar_provider
from app.domain.calendar_sync.providers.base import (
    CalendarProvider,
    CalendarProviderError,
    CalendarSyncCursorError,
    ExternalCalendarEvent,
)

if TYPE_CHECKING:
    from app.db.models.calendar_connection import CalendarConnection
    from app.domain.calendar_sync.providers.google import GoogleCalendarProvider
    from app.domain.calendar_sync.schemas import CalendarConnectionCreate, CalendarConnectionUpdate
    from app.domain.todo.services import TodoService

logger = structlog.get_logger()


@dataclass(slots=True)
class SyncCounters:
    pulled_inserted: int = 0
    pulled_updated: int = 0
    pulled_deleted: int = 0
    pushed_inserted: int = 0
    pushed_updated: int = 0
    pushed_deleted: int = 0


class CalendarConnectionService(SQLAlchemyAsyncRepositoryService[m.CalendarConnection]):
    """Database service for calendar connections."""

    class Repository(SQLAlchemyAsyncRepository[m.CalendarConnection]):
        model_type = m.CalendarConnection

    repository_type = Repository

    @staticmethod
    def serialize_credentials(credentials: dict[str, Any] | None) -> str | None:
        if credentials is None:
            return None
        return json.dumps(credentials, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def deserialize_credentials(blob: str | None) -> dict[str, Any]:
        if not blob:
            return {}
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    async def set_default_connection(self, *, user_id: UUID, connection_id: UUID) -> None:
        user_connections, _ = await self.list_and_count(m.CalendarConnection.user_id == user_id)
        for connection in user_connections:
            should_default = connection.id == connection_id
            if connection.is_default == should_default:
                continue
            await self.update(item_id=connection.id, data={"is_default": should_default})

    async def get_default_active_connection(self, *, user_id: UUID, allow_read_only: bool = False) -> m.CalendarConnection | None:
        connection = await self.get_one_or_none(
            m.CalendarConnection.user_id == user_id,
            m.CalendarConnection.is_default.is_(True),
            m.CalendarConnection.is_active.is_(True),
            m.CalendarConnection.status == "active",
        )
        if connection is None:
            return None
        if not allow_read_only and connection.provider == "ics":
            return None
        return connection


class CalendarEventService(SQLAlchemyAsyncRepositoryService[m.CalendarEvent]):
    """Database service for mirrored calendar events."""

    class Repository(SQLAlchemyAsyncRepository[m.CalendarEvent]):
        model_type = m.CalendarEvent

    repository_type = Repository


class TodoCalendarLinkService(SQLAlchemyAsyncRepositoryService[m.TodoCalendarLink]):
    """Database service for todo <-> remote event mapping."""

    class Repository(SQLAlchemyAsyncRepository[m.TodoCalendarLink]):
        model_type = m.TodoCalendarLink

    repository_type = Repository


class CalendarSyncService:
    """Orchestrates bidirectional sync between local todos and remote calendars."""

    def __init__(
        self,
        *,
        connection_service: CalendarConnectionService,
        event_service: CalendarEventService,
        link_service: TodoCalendarLinkService,
        todo_service: "TodoService",
    ) -> None:
        self.connection_service = connection_service
        self.event_service = event_service
        self.link_service = link_service
        self.todo_service = todo_service

    async def create_connection(self, *, user_id: UUID, data: CalendarConnectionCreate) -> m.CalendarConnection:
        provider = data.provider.lower()
        status = "pending_auth" if provider == "google" else "active"

        credentials = data.credentials or {}
        if provider in {"caldav", "ics"} and not credentials:
            msg = f"{provider} provider requires credentials"
            raise ValueError(msg)

        payload = {
            "user_id": user_id,
            "provider": provider,
            "display_name": data.display_name,
            "calendar_id": data.calendar_id or "primary",
            "status": status,
            "sync_mode": data.sync_mode,
            "is_default": data.is_default,
            "is_active": True,
            "credential_blob": self.connection_service.serialize_credentials(credentials),
        }

        connection = await self.connection_service.create(payload)

        if data.is_default:
            await self.connection_service.set_default_connection(user_id=user_id, connection_id=connection.id)

        return connection

    async def update_connection(self, *, user_id: UUID, connection_id: UUID, data: CalendarConnectionUpdate) -> m.CalendarConnection:
        connection = await self._get_user_connection(user_id=user_id, connection_id=connection_id)

        patch = data.to_dict()
        credentials = patch.pop("credentials", None)
        if credentials is not None:
            patch["credential_blob"] = self.connection_service.serialize_credentials(credentials)

        if patch:
            connection = await self.connection_service.update(item_id=connection.id, data=patch)

        if data.is_default:
            await self.connection_service.set_default_connection(user_id=user_id, connection_id=connection.id)

        return connection

    async def list_connections(self, *, user_id: UUID) -> list[m.CalendarConnection]:
        connections, _ = await self.connection_service.list_and_count(
            m.CalendarConnection.user_id == user_id,
        )
        return list(connections)

    async def delete_connection(self, *, user_id: UUID, connection_id: UUID) -> None:
        connection = await self._get_user_connection(user_id=user_id, connection_id=connection_id)
        await self.connection_service.delete(connection.id)

    async def get_events(
        self,
        *,
        user_id: UUID,
        start_time: datetime,
        end_time: datetime,
    ) -> tuple[list[m.CalendarEvent], int]:
        return await self.event_service.list_and_count(
            m.CalendarEvent.user_id == user_id,
            m.CalendarEvent.start_time < end_time,
            m.CalendarEvent.end_time > start_time,
        )

    async def get_google_authorize_url(self, *, user_id: UUID, connection_id: UUID) -> str:
        connection = await self._get_user_connection(user_id=user_id, connection_id=connection_id)
        if connection.provider != "google":
            msg = "Connection provider must be google"
            raise ValueError(msg)

        provider = cast("GoogleCalendarProvider", get_calendar_provider("google"))
        state = self._build_google_state(user_id=user_id, connection_id=connection.id)
        return await provider.build_authorize_url(state=state)

    async def handle_google_callback(self, *, code: str, state: str) -> m.CalendarConnection:
        state_payload = self._decode_google_state(state)
        user_id = UUID(state_payload["user_id"])
        connection_id = UUID(state_payload["connection_id"])

        connection = await self._get_user_connection(user_id=user_id, connection_id=connection_id)

        if connection.provider != "google":
            msg = "Invalid google callback connection"
            raise ValueError(msg)

        provider = cast("GoogleCalendarProvider", get_calendar_provider("google"))
        credentials = await provider.exchange_code(code=code)

        updated = await self.connection_service.update(
            item_id=connection.id,
            data={
                "credential_blob": self.connection_service.serialize_credentials(credentials),
                "status": "active",
                "is_active": True,
                "last_error": None,
            },
        )
        return updated

    async def sync_connection(
        self,
        *,
        user_id: UUID,
        connection_id: UUID,
        mode: str = "both",
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> SyncCounters:
        connection = await self._get_user_connection(user_id=user_id, connection_id=connection_id)
        connection_item_id = connection.id
        provider = self._provider_for_connection(connection)

        if mode not in {"pull", "push", "both"}:
            msg = f"Unsupported sync mode: {mode}"
            raise ValueError(msg)

        settings = get_settings()
        now = datetime.now(UTC)
        start = start_time or now - timedelta(days=settings.calendar.SYNC_LOOKBACK_DAYS)
        end = end_time or now + timedelta(days=settings.calendar.SYNC_LOOKAHEAD_DAYS)

        credentials = self.connection_service.deserialize_credentials(connection.credential_blob)
        counters = SyncCounters()

        try:
            if mode in {"pull", "both"} and connection.sync_mode != "push_only":
                credentials, next_cursor = await self._pull_from_provider(
                    connection=connection,
                    provider=provider,
                    credentials=credentials,
                    start=start,
                    end=end,
                    counters=counters,
                )
                connection = await self.connection_service.update(
                    item_id=connection_item_id,
                    data={
                        "sync_cursor": next_cursor,
                        "last_pull_at": now,
                    },
                )

            if mode in {"push", "both"} and connection.sync_mode != "pull_only" and connection.provider != "ics":
                credentials = await self._push_todos_to_provider(
                    connection=connection,
                    provider=provider,
                    credentials=credentials,
                    start=start,
                    end=end,
                    counters=counters,
                )
                connection = await self.connection_service.update(
                    item_id=connection_item_id,
                    data={"last_push_at": now},
                )

            await self.connection_service.update(
                item_id=connection_item_id,
                data={
                    "credential_blob": self.connection_service.serialize_credentials(credentials),
                    "status": "active",
                    "last_synced_at": now,
                    "last_error": None,
                },
            )
        except Exception as exc:
            await self._safe_session_rollback()
            await self.connection_service.update(
                item_id=connection_item_id,
                data={
                    "status": "error",
                    "last_error": str(exc),
                },
            )
            raise

        return counters

    async def sync_todo_after_upsert(self, *, todo: m.Todo) -> None:
        connection = await self.connection_service.get_default_active_connection(user_id=todo.user_id)
        if connection is None:
            return
        connection_item_id = connection.id
        if connection.sync_mode == "pull_only":
            return

        provider = self._provider_for_connection(connection)
        credentials = self.connection_service.deserialize_credentials(connection.credential_blob)
        counters = SyncCounters()

        try:
            credentials = await self._push_single_todo(
                connection=connection,
                provider=provider,
                credentials=credentials,
                todo=todo,
                counters=counters,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Todo push sync failed",
                todo_id=str(todo.id),
                connection_id=str(connection.id),
                error=str(exc),
            )
            await self._safe_session_rollback()
            await self.connection_service.update(
                item_id=connection_item_id,
                data={
                    "status": "error",
                    "last_error": str(exc),
                },
            )
            return

        await self.connection_service.update(
            item_id=connection_item_id,
            data={
                "credential_blob": self.connection_service.serialize_credentials(credentials),
                "last_push_at": datetime.now(UTC),
                "status": "active",
                "last_error": None,
            },
        )

    async def sync_todo_before_delete(self, *, todo: m.Todo) -> None:
        link = await self.link_service.get_one_or_none(m.TodoCalendarLink.todo_id == todo.id)
        if link is None:
            return

        connection = await self.connection_service.get_one_or_none(
            m.CalendarConnection.id == link.connection_id,
            m.CalendarConnection.user_id == todo.user_id,
            m.CalendarConnection.is_active.is_(True),
        )
        if connection is None:
            return
        connection_item_id = connection.id
        if connection.provider == "ics" or connection.sync_mode == "pull_only":
            return

        provider = self._provider_for_connection(connection)
        credentials = self.connection_service.deserialize_credentials(connection.credential_blob)

        try:
            credentials = await provider.delete_event(
                connection,
                credentials,
                remote_event_id=link.remote_event_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Todo delete sync failed",
                todo_id=str(todo.id),
                connection_id=str(connection.id),
                error=str(exc),
            )
            await self._safe_session_rollback()
            await self.connection_service.update(
                item_id=connection_item_id,
                data={
                    "status": "error",
                    "last_error": str(exc),
                },
            )
            return

        mirrored = await self.event_service.get_one_or_none(
            m.CalendarEvent.connection_id == connection.id,
            m.CalendarEvent.remote_event_id == link.remote_event_id,
        )
        if mirrored is not None:
            await self.event_service.delete(mirrored.id)

        await self.link_service.delete(link.id)
        await self.connection_service.update(
            item_id=connection_item_id,
            data={
                "credential_blob": self.connection_service.serialize_credentials(credentials),
                "last_push_at": datetime.now(UTC),
                "status": "active",
                "last_error": None,
            },
        )

    async def _pull_from_provider(
        self,
        *,
        connection: CalendarConnection,
        provider: CalendarProvider,
        credentials: dict[str, Any],
        start: datetime,
        end: datetime,
        counters: SyncCounters,
    ) -> tuple[dict[str, Any], str | None]:
        cursor = connection.sync_cursor

        try:
            result = await provider.fetch_events(
                connection,
                credentials,
                start=start,
                end=end,
                cursor=cursor,
            )
        except CalendarSyncCursorError:
            result = await provider.fetch_events(
                connection,
                credentials,
                start=start,
                end=end,
                cursor=None,
            )

        for remote_event in result.events:
            await self._apply_remote_event(connection=connection, remote_event=remote_event, counters=counters)

        return result.credentials, result.next_cursor

    async def _apply_remote_event(
        self,
        *,
        connection: CalendarConnection,
        remote_event: ExternalCalendarEvent,
        counters: SyncCounters,
    ) -> None:
        link = await self.link_service.get_one_or_none(
            m.TodoCalendarLink.connection_id == connection.id,
            m.TodoCalendarLink.remote_event_id == remote_event.remote_event_id,
        )

        if remote_event.status == "cancelled":
            if link is None:
                return

            todo = await self.todo_service.get_one_or_none(m.Todo.id == link.todo_id)
            if todo is not None:
                await self.todo_service.delete(todo.id)
            mirrored = await self.event_service.get_one_or_none(
                m.CalendarEvent.connection_id == connection.id,
                m.CalendarEvent.remote_event_id == link.remote_event_id,
            )
            if mirrored is not None:
                await self.event_service.delete(mirrored.id)
            await self.link_service.delete(link.id)
            counters.pulled_deleted += 1
            return

        if (
            link is not None
            and link.etag is not None
            and remote_event.etag is not None
            and link.etag == remote_event.etag
        ):
            await self._upsert_mirrored_event(
                connection=connection,
                remote_event=remote_event,
                linked_todo_id=link.todo_id,
            )
            return

        todo_payload = {
            "item": remote_event.title,
            "description": remote_event.description,
            "start_time": remote_event.start_time,
            "end_time": remote_event.end_time,
            "importance": m.Importance.NONE,
        }

        if link is None:
            todo = await self.todo_service.create({**todo_payload, "user_id": connection.user_id})
            link = await self.link_service.create(
                {
                    "todo_id": todo.id,
                    "connection_id": connection.id,
                    "remote_event_id": remote_event.remote_event_id,
                    "etag": remote_event.etag,
                    "last_sync_source": "pull",
                    "last_synced_at": datetime.now(UTC),
                }
            )
            counters.pulled_inserted += 1
        else:
            todo = await self.todo_service.get(link.todo_id)
            if todo is None:
                todo = await self.todo_service.create({**todo_payload, "user_id": connection.user_id})
                link = await self.link_service.update(
                    item_id=link.id,
                    data={
                        "todo_id": todo.id,
                        "etag": remote_event.etag,
                        "last_sync_source": "pull",
                        "last_synced_at": datetime.now(UTC),
                    },
                )
                counters.pulled_inserted += 1
            else:
                if self._todo_needs_update(todo=todo, payload=todo_payload):
                    await self.todo_service.update(item_id=todo.id, data=todo_payload)
                    counters.pulled_updated += 1
                link = await self.link_service.update(
                    item_id=link.id,
                    data={
                        "etag": remote_event.etag,
                        "last_sync_source": "pull",
                        "last_synced_at": datetime.now(UTC),
                    },
                )

        await self._upsert_mirrored_event(
            connection=connection,
            remote_event=remote_event,
            linked_todo_id=link.todo_id,
        )

    async def _push_todos_to_provider(
        self,
        *,
        connection: CalendarConnection,
        provider: CalendarProvider,
        credentials: dict[str, Any],
        start: datetime,
        end: datetime,
        counters: SyncCounters,
    ) -> dict[str, Any]:
        todos, _ = await self.todo_service.list_and_count(
            m.Todo.user_id == connection.user_id,
            m.Todo.start_time < end,
            m.Todo.end_time > start,
        )

        current_credentials = credentials
        for todo in todos:
            current_credentials = await self._push_single_todo(
                connection=connection,
                provider=provider,
                credentials=current_credentials,
                todo=todo,
                counters=counters,
            )

        return current_credentials

    async def _push_single_todo(
        self,
        *,
        connection: CalendarConnection,
        provider: CalendarProvider,
        credentials: dict[str, Any],
        todo: m.Todo,
        counters: SyncCounters,
    ) -> dict[str, Any]:
        link = await self.link_service.get_one_or_none(
            m.TodoCalendarLink.todo_id == todo.id,
            m.TodoCalendarLink.connection_id == connection.id,
        )

        remote_event = self._todo_to_external_event(todo)

        result = await provider.upsert_event(
            connection,
            credentials,
            event=remote_event,
            remote_event_id=link.remote_event_id if link else None,
        )

        if link is None:
            link = await self.link_service.create(
                {
                    "todo_id": todo.id,
                    "connection_id": connection.id,
                    "remote_event_id": result.event.remote_event_id,
                    "etag": result.event.etag,
                    "last_sync_source": "push",
                    "last_synced_at": datetime.now(UTC),
                }
            )
            counters.pushed_inserted += 1
        else:
            link = await self.link_service.update(
                item_id=link.id,
                data={
                    "remote_event_id": result.event.remote_event_id,
                    "etag": result.event.etag,
                    "last_sync_source": "push",
                    "last_synced_at": datetime.now(UTC),
                },
            )
            counters.pushed_updated += 1

        await self._upsert_mirrored_event(
            connection=connection,
            remote_event=result.event,
            linked_todo_id=link.todo_id,
        )

        return result.credentials

    async def _upsert_mirrored_event(
        self,
        *,
        connection: CalendarConnection,
        remote_event: ExternalCalendarEvent,
        linked_todo_id: UUID | None,
    ) -> None:
        existing = await self.event_service.get_one_or_none(
            m.CalendarEvent.connection_id == connection.id,
            m.CalendarEvent.remote_event_id == remote_event.remote_event_id,
        )

        payload = {
            "connection_id": connection.id,
            "user_id": connection.user_id,
            "linked_todo_id": linked_todo_id,
            "provider": connection.provider,
            "remote_event_id": remote_event.remote_event_id,
            "etag": remote_event.etag,
            "title": remote_event.title,
            "description": remote_event.description,
            "start_time": remote_event.start_time,
            "end_time": remote_event.end_time,
            "all_day": remote_event.all_day,
            "source_timezone": remote_event.source_timezone,
            "status": remote_event.status,
            "remote_created_at": remote_event.remote_created_at,
            "remote_updated_at": remote_event.remote_updated_at,
            "payload": remote_event.payload,
        }

        if existing is None:
            await self.event_service.create(payload)
            return

        await self.event_service.update(item_id=existing.id, data=payload)

    @staticmethod
    def _todo_to_external_event(todo: m.Todo) -> ExternalCalendarEvent:
        return ExternalCalendarEvent(
            remote_event_id=str(todo.id),
            title=todo.item,
            description=todo.description,
            start_time=todo.start_time.astimezone(UTC) if todo.start_time.tzinfo else todo.start_time.replace(tzinfo=UTC),
            end_time=todo.end_time.astimezone(UTC) if todo.end_time.tzinfo else todo.end_time.replace(tzinfo=UTC),
            all_day=False,
            status="confirmed",
            source_timezone="UTC",
            etag=None,
            remote_created_at=None,
            remote_updated_at=todo.updated_at,
            payload={
                "todo_id": str(todo.id),
                "importance": str(todo.importance),
            },
        )

    @staticmethod
    def _provider_for_connection(connection: CalendarConnection) -> CalendarProvider:
        try:
            return get_calendar_provider(connection.provider)
        except ValueError as exc:
            raise CalendarProviderError(str(exc)) from exc

    async def _get_user_connection(self, *, user_id: UUID, connection_id: UUID) -> m.CalendarConnection:
        connection = await self.connection_service.get_one_or_none(
            m.CalendarConnection.id == connection_id,
            m.CalendarConnection.user_id == user_id,
        )
        if connection is None:
            msg = "Calendar connection not found"
            raise ValueError(msg)
        return connection

    def _build_google_state(self, *, user_id: UUID, connection_id: UUID) -> str:
        payload = {
            "user_id": str(user_id),
            "connection_id": str(connection_id),
            "ts": int(datetime.now(UTC).timestamp()),
        }
        raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        body = base64.urlsafe_b64encode(raw).decode("utf-8")
        signature = self._state_signature(body)
        return f"{body}.{signature}"

    def _decode_google_state(self, state: str) -> dict[str, str]:
        try:
            body, signature = state.rsplit(".", 1)
        except ValueError as exc:
            raise ValueError("Invalid OAuth state format") from exc

        expected = self._state_signature(body)
        if not hmac.compare_digest(signature, expected):
            msg = "Invalid OAuth state signature"
            raise ValueError(msg)

        payload = json.loads(base64.urlsafe_b64decode(body.encode("utf-8")))
        timestamp = int(payload.get("ts", 0))
        now_ts = int(datetime.now(UTC).timestamp())
        ttl_seconds = get_settings().calendar.GOOGLE_STATE_TTL_SECONDS
        if now_ts - timestamp > ttl_seconds:
            raise ValueError("OAuth state expired")

        return {
            "user_id": str(payload["user_id"]),
            "connection_id": str(payload["connection_id"]),
        }

    @staticmethod
    def _state_signature(body: str) -> str:
        secret = get_settings().app.SECRET_KEY.encode("utf-8")
        digest = hmac.new(secret, body.encode("utf-8"), hashlib.sha256).hexdigest()
        return digest

    @staticmethod
    def _todo_needs_update(*, todo: m.Todo, payload: dict[str, Any]) -> bool:
        return any(
            (
                todo.item != payload["item"],
                (todo.description or None) != payload["description"],
                todo.start_time != payload["start_time"],
                todo.end_time != payload["end_time"],
                todo.importance != payload["importance"],
            )
        )

    async def _safe_session_rollback(self) -> None:
        session = getattr(self.connection_service.repository, "session", None)
        if session is None:
            return

        rollback = getattr(session, "rollback", None)
        if not callable(rollback):
            return

        maybe_awaitable = rollback()
        if isawaitable(maybe_awaitable):
            await maybe_awaitable


def create_calendar_sync_service(
    *,
    connection_service: CalendarConnectionService,
    event_service: CalendarEventService,
    link_service: TodoCalendarLinkService,
    todo_service: TodoService,
) -> CalendarSyncService:
    return CalendarSyncService(
        connection_service=connection_service,
        event_service=event_service,
        link_service=link_service,
        todo_service=todo_service,
    )
