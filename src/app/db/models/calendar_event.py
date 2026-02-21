from __future__ import annotations

# ruff: noqa: TC003
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .calendar_connection import CalendarConnection
    from .todo import Todo
    from .user import User


class CalendarEvent(UUIDAuditBase):
    """Local mirror for one remote calendar event."""

    __tablename__ = "calendar_event"
    __table_args__ = (
        UniqueConstraint("connection_id", "remote_event_id", name="uq_calendar_event_connection_remote_event"),
        {"comment": "Mirrored events from external calendars"},
    )

    connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("calendar_connection.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    linked_todo_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("todo.id", ondelete="SET NULL"), nullable=True, index=True,
    )

    provider: Mapped[str] = mapped_column(String(length=32), nullable=False, index=True)
    remote_event_id: Mapped[str] = mapped_column(String(length=512), nullable=False)
    etag: Mapped[str | None] = mapped_column(String(length=255), nullable=True)

    title: Mapped[str] = mapped_column(String(length=255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    start_time: Mapped[datetime] = mapped_column(nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(nullable=False, index=True)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_timezone: Mapped[str | None] = mapped_column(String(length=64), nullable=True)

    # confirmed | cancelled | tentative
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="confirmed")

    remote_created_at: Mapped[datetime | None] = mapped_column(nullable=True)
    remote_updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    connection: Mapped[CalendarConnection] = relationship(back_populates="events", lazy="joined", uselist=False, innerjoin=True)
    user: Mapped[User] = relationship(lazy="joined", uselist=False, innerjoin=True)
    linked_todo: Mapped[Todo | None] = relationship(lazy="joined", uselist=False)
