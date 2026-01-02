from __future__ import annotations

from typing import TYPE_CHECKING
import base64
import json
from uuid import UUID  # noqa: TC003

from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

if TYPE_CHECKING:
    from .user import User


class MetadataJSON(TypeDecorator):
    """Normalize metadata to a dict for ORM reads."""

    impl = JSONB
    cache_ok = True

    def process_bind_param(self, value: object, dialect: object) -> dict[str, str]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value  # type: ignore[return-value]
        if isinstance(value, str):
            parsed = _decode_metadata(value)
            return parsed
        return {}

    def process_result_value(self, value: object, dialect: object) -> dict[str, str]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value  # type: ignore[return-value]
        if isinstance(value, str):
            return _decode_metadata(value)
        return {}


def _decode_metadata(raw: str) -> dict[str, str]:
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        return json.loads(decoded)
    except Exception:
        pass
    try:
        return json.loads(raw)
    except Exception:
        return {}


class Memory(UUIDAuditBase):
    """Memory bullets for user and global context."""

    __tablename__ = "memory"
    __table_args__ = (
        CheckConstraint(
            "(is_global IS TRUE AND user_id IS NULL) OR (is_global IS FALSE AND user_id IS NOT NULL)",
            name="ck_memory_global_user",
        ),
        {"comment": "Memory bullets for agent context"},
    )
    __pii_columns__ = {"content", "metadata_json"}

    is_global: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str] = mapped_column(String(length=255), nullable=False, index=True)
    helpful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    harmful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict[str, str]] = mapped_column(
        "metadata",
        JSON().with_variant(MetadataJSON(), "postgresql"),
        default=dict,
        nullable=False,
    )

    # -----------
    # ORM Relationships
    # -----------

    user: Mapped[User | None] = relationship(
        back_populates="memories",
        lazy="joined",
    )
