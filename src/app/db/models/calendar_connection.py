from __future__ import annotations

# ruff: noqa: TC003
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.types import EncryptedText
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.base import get_settings

if TYPE_CHECKING:
    from .calendar_event import CalendarEvent
    from .todo_calendar_link import TodoCalendarLink
    from .user import User


def _credential_encryption_key() -> str:
    return get_settings().app.SECRET_KEY


class CalendarConnection(UUIDAuditBase):
    """External calendar connection owned by one user."""

    __tablename__ = "calendar_connection"
    __table_args__ = {"comment": "External calendar account connections"}
    __pii_columns__ = {"display_name", "credential_blob", "last_error"}

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    provider: Mapped[str] = mapped_column(String(length=32), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    calendar_id: Mapped[str] = mapped_column(String(length=255), nullable=False, default="primary")

    # active | pending_auth | error | disabled
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="pending_auth")
    # two_way | pull_only | push_only
    sync_mode: Mapped[str] = mapped_column(String(length=16), nullable=False, default="two_way")

    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    credential_blob: Mapped[str | None] = mapped_column(
        EncryptedText(key=_credential_encryption_key),
        nullable=True,
    )
    sync_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_state: Mapped[str | None] = mapped_column(Text, nullable=True)

    webhook_channel_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    webhook_resource_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    webhook_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_pull_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_push_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(lazy="joined", uselist=False, innerjoin=True)
    events: Mapped[list[CalendarEvent]] = relationship(
        back_populates="connection",
        lazy="selectin",
        uselist=True,
        cascade="all, delete-orphan",
    )
    todo_links: Mapped[list[TodoCalendarLink]] = relationship(
        back_populates="connection",
        lazy="selectin",
        uselist=True,
        cascade="all, delete-orphan",
    )
