from __future__ import annotations

# ruff: noqa: TC003
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .user import User


class RagDocument(UUIDAuditBase):
    """Uploaded plain-text documents indexed for RAG queries."""

    __tablename__ = "rag_document"
    __table_args__ = {"comment": "User uploaded plain-text documents for RAG indexing"}
    __pii_columns__ = {"display_name", "original_filename", "storage_path", "error_message"}

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(length=255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(length=128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(length=64), nullable=False)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, index=True, default="queued")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_path: Mapped[str] = mapped_column(String(length=1024), nullable=False)
    indexed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    user: Mapped[User] = relationship(
        back_populates="rag_documents",
        lazy="joined",
        uselist=False,
        innerjoin=True,
    )
