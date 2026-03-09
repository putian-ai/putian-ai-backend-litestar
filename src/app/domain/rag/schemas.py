"""Schemas for rag domain."""

from __future__ import annotations

# ruff: noqa: TC003
from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field

from app.domain.accounts.schemas import PydanticBaseModel

__all__ = [
    "RagDeleteQueuedResponse",
    "RagDocumentModel",
    "RagDocumentStatus",
    "RagQueryRequest",
    "RagQueryResponse",
    "RagQuerySource",
    "RagRateLimitErrorResponse",
    "RagUploadQueuedResponse",
]


class RagDocumentStatus(str, Enum):
    """Allowed statuses for uploaded RAG documents."""

    QUEUED = "queued"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class RagDocumentModel(PydanticBaseModel):
    """Document metadata exposed by RAG APIs."""

    id: UUID
    display_name: str
    original_filename: str
    mime_type: str
    size_bytes: int
    status: RagDocumentStatus
    error_message: str | None = None
    indexed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RagUploadQueuedResponse(PydanticBaseModel):
    """Response returned when upload has been queued for indexing."""

    status: str = Field(default="queued")
    document_id: UUID
    queued_at: datetime


class RagDeleteQueuedResponse(PydanticBaseModel):
    """Response returned when deletion-triggered rebuild has been queued."""

    status: str = Field(default="queued_for_rebuild")
    document_id: UUID
    queued_at: datetime


class RagQueryRequest(PydanticBaseModel):
    """Request schema for RAG query endpoint."""

    question: str = Field(..., min_length=1, description="Natural-language question.")
    document_id: UUID | None = Field(
        default=None,
        description="Optional document filter. If provided, retrieval is strictly constrained to this document.",
    )
    top_k: int = Field(default=8, ge=1, le=20, description="Maximum number of context chunks to retrieve.")


class RagQuerySource(PydanticBaseModel):
    """Single cited context chunk in a RAG answer."""

    document_id: UUID | None = None
    file_name: str | None = None
    chunk_id: str | None = None
    score: float | None = None
    excerpt: str


class RagQueryResponse(PydanticBaseModel):
    """Response schema for RAG answers."""

    status: str = Field(default="success")
    answer: str
    sources: list[RagQuerySource] = Field(default_factory=list)
    used_document_ids: list[UUID] = Field(default_factory=list)


class RagRateLimitErrorResponse(PydanticBaseModel):
    """Response schema for rate-limit exceeded errors."""

    status: str = Field(default="error")
    message: str
    error_code: str = Field(default="RATE_LIMIT_EXCEEDED")
    current_usage: int
    monthly_limit: int
    reset_date: datetime
    remaining_quota: int
