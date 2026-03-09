"""Dependency providers for rag domain."""

from __future__ import annotations

from app.domain.rag.queue import RagQueueService, get_rag_queue_service
from app.domain.rag.services import RagDocumentService
from app.lib.deps import create_service_provider

__all__ = ["provide_rag_document_service", "provide_rag_queue_service"]


provide_rag_document_service = create_service_provider(
    RagDocumentService,
    error_messages={
        "duplicate_key": "RAG document already exists.",
        "integrity": "RAG document operation failed.",
    },
)


async def provide_rag_queue_service() -> "RagQueueService":
    return get_rag_queue_service()
