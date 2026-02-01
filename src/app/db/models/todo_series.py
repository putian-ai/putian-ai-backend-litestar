from __future__ import annotations

import enum
from datetime import date, time
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy import Date, Enum, ForeignKey, Integer, JSON, String, Time
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .todo import Todo


class TodoSeriesRuleType(enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    INTERVAL = "interval"


class TodoSeries(UUIDAuditBase):
    """Recurring todo series configuration."""

    __tablename__ = "todo_series"
    __table_args__ = {"comment": "Recurring todo series"}

    name: Mapped[str] = mapped_column(String(length=100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(length=1024), nullable=True)
    rule_type: Mapped[TodoSeriesRuleType] = mapped_column(
        Enum(TodoSeriesRuleType, name="todo_series_rule_type_enum", native_enum=False),
        nullable=False,
    )
    rule_payload: Mapped[dict[str, object]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(length=64), nullable=False)
    default_start_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"),
        nullable=False,
    )

    todos: Mapped[list[Todo]] = relationship(
        back_populates="series",
        lazy="selectin",
        uselist=True,
        cascade="all, delete-orphan",
    )
