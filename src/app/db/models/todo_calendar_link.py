from __future__ import annotations

# ruff: noqa: TC003
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .calendar_connection import CalendarConnection
    from .todo import Todo


class TodoCalendarLink(UUIDAuditBase):
    """Mapping table between local todos and remote calendar events."""

    __tablename__ = "todo_calendar_link"
    __table_args__ = (
        UniqueConstraint("todo_id", name="uq_todo_calendar_link_todo"),
        UniqueConstraint("connection_id", "remote_event_id", name="uq_todo_calendar_link_connection_remote_event"),
        {"comment": "Bidirectional mapping between todos and remote events"},
    )

    todo_id: Mapped[UUID] = mapped_column(
        ForeignKey("todo.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("calendar_connection.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    remote_event_id: Mapped[str] = mapped_column(String(length=512), nullable=False)
    etag: Mapped[str | None] = mapped_column(String(length=255), nullable=True)

    # pull | push
    last_sync_source: Mapped[str | None] = mapped_column(String(length=16), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)

    todo: Mapped[Todo] = relationship(lazy="joined", uselist=False, innerjoin=True)
    connection: Mapped[CalendarConnection] = relationship(back_populates="todo_links", lazy="joined", uselist=False, innerjoin=True)
