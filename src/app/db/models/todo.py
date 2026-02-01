from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.importance import Importance

if TYPE_CHECKING:
    from .tag import Tag
    from .todo_tag import TodoTag
    from .todo_series import TodoSeries
    from .user import User


class Todo(UUIDAuditBase):
    """Todo item"""

    __tablename__ = "todo"
    __table_args__ = {"comment": "Todo items"}
    __pii_columns__ = {"item", "created_time", "alarm_time",
                       "content", "user", "importance", "tags"}

    item: Mapped[str] = mapped_column(
        String(length=100), index=True, nullable=False)
    description: Mapped[str] = mapped_column(
        String(length=1024), nullable=True)
    created_time: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False)
    alarm_time: Mapped[datetime | None] = mapped_column(
        nullable=True)
    importance: Mapped[Importance] = mapped_column(Enum(
        Importance, name="importance_enum", native_enum=False), nullable=False, default=Importance.NONE)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    series_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("todo_series.id", ondelete="CASCADE"), nullable=True, index=True
    )
    start_time: Mapped[datetime] = mapped_column(nullable=False)
    end_time: Mapped[datetime] = mapped_column(nullable=False)

    # -----------
    # ORM Relationships
    # ------------

    todo_tags: Mapped[list[TodoTag]] = relationship(
        back_populates="todo", lazy="selectin", uselist=True, cascade="all, delete-orphan"
    )
    tags: AssociationProxy[list[Tag]] = association_proxy(
        "todo_tags", "tag",
    )
    series: Mapped[TodoSeries | None] = relationship(
        back_populates="todos", lazy="joined", uselist=False
    )

    user: Mapped[User] = relationship(
        back_populates="todos", lazy="joined", uselist=False, innerjoin=True
    )
