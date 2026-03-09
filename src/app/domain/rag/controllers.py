"""Controllers for rag domain."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any

from litestar import Controller, Request, delete, get, post
from litestar.datastructures import UploadFile
from litestar.di import Provide
from litestar.exceptions import HTTPException, NotFoundException
from litestar.params import Dependency
from litestar.status_codes import HTTP_400_BAD_REQUEST, HTTP_503_SERVICE_UNAVAILABLE

from app.domain.rag import urls
from app.domain.rag.deps import provide_rag_document_service, provide_rag_queue_service
from app.domain.rag.lightrag_client import create_light_rag_client
from app.domain.rag.queue import RagQueueService  # noqa: TC001
from app.domain.rag.schemas import (
    RagDeleteQueuedResponse,
    RagDocumentModel,
    RagDocumentStatus,
    RagQueryRequest,
    RagQueryResponse,
    RagRateLimitErrorResponse,
    RagUploadQueuedResponse,
)
from app.domain.todo_agents.deps import provide_rate_limit_service, provide_user_usage_quota_service
from app.lib.exceptions import RateLimitExceededException

if TYPE_CHECKING:
    from uuid import UUID

    import app.db.models as m
    from app.domain.quota.services import UserUsageQuotaService
    from app.domain.rag.services import RagDocumentService
    from app.lib.rate_limit_service import RateLimitService

__all__ = ["RagController"]


class RagController(Controller):
    """Controller for user-scoped RAG document operations."""

    tags = ["RAG"]
    path = urls.RAG_BASE

    dependencies = {
        "rag_document_service": Provide(provide_rag_document_service),
        "rag_queue_service": Provide(provide_rag_queue_service),
        "rate_limit_service": Provide(provide_rate_limit_service),
        "quota_service": Provide(provide_user_usage_quota_service),
    }

    @post(path="/documents/upload", operation_id="upload_rag_document", status_code=202)
    async def upload_document(
        self,
        current_user: "m.User",
        request: Request[Any, Any, Any],
        rag_document_service: Annotated["RagDocumentService", Dependency(skip_validation=True)],
        rag_queue_service: Annotated[RagQueueService, Dependency(skip_validation=True)],
    ) -> RagUploadQueuedResponse:
        """Upload one plain-text file and enqueue indexing."""
        form = await request.form()
        upload = form.get("file")
        display_name_raw = form.get("display_name")

        if not isinstance(upload, UploadFile):
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Missing multipart field: file")

        if not (upload.content_type or "").lower().startswith("text/plain"):
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Only text/plain uploads are supported")

        display_name = display_name_raw if isinstance(display_name_raw, str) else None
        payload = await upload.read()

        try:
            document = await rag_document_service.upload_plain_text_document(
                user_id=current_user.id,
                file_name=upload.filename or "uploaded.txt",
                mime_type=upload.content_type or "text/plain",
                payload=payload,
                display_name=display_name,
                queue_service=rag_queue_service,
            )
        except ValueError as exc:
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

        return RagUploadQueuedResponse(
            document_id=document.id,
            queued_at=datetime.now(UTC),
        )

    @get(path="/documents", operation_id="list_rag_documents")
    async def list_documents(
        self,
        current_user: "m.User",
        rag_document_service: Annotated["RagDocumentService", Dependency(skip_validation=True)],
        status: RagDocumentStatus | None = None,
    ) -> list[RagDocumentModel]:
        """List all active documents for current user."""
        documents = await rag_document_service.list_user_documents(user_id=current_user.id, status=status)
        return [RagDocumentModel.model_validate(document, from_attributes=True) for document in documents]

    @delete(path="/documents/{document_id:uuid}", operation_id="delete_rag_document", status_code=202)
    async def delete_document(
        self,
        current_user: "m.User",
        document_id: "UUID",
        rag_document_service: Annotated["RagDocumentService", Dependency(skip_validation=True)],
        rag_queue_service: Annotated[RagQueueService, Dependency(skip_validation=True)],
    ) -> RagDeleteQueuedResponse:
        """Soft delete one document and enqueue user index rebuild."""
        try:
            await rag_document_service.delete_document_and_queue_rebuild(
                user_id=current_user.id,
                document_id=document_id,
                queue_service=rag_queue_service,
            )
        except LookupError as exc:
            raise NotFoundException(detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

        return RagDeleteQueuedResponse(document_id=document_id, queued_at=datetime.now(UTC))

    @post(path="/query", operation_id="query_rag", status_code=200)
    async def query_rag(
        self,
        current_user: "m.User",
        data: RagQueryRequest,
        rag_document_service: Annotated["RagDocumentService", Dependency(skip_validation=True)],
        rate_limit_service: Annotated["RateLimitService", Dependency(skip_validation=True)],
        quota_service: Annotated["UserUsageQuotaService", Dependency(skip_validation=True)],
    ) -> RagQueryResponse | RagRateLimitErrorResponse:
        """Run user-scoped RAG query and return answer with citations."""
        try:
            await rate_limit_service.check_and_increment_usage(
                current_user.id,
                quota_service,
            )
        except RateLimitExceededException as exc:
            return RagRateLimitErrorResponse(
                message=exc.detail,
                current_usage=exc.current_usage,
                monthly_limit=exc.monthly_limit,
                reset_date=exc.reset_date,
                remaining_quota=max(0, exc.monthly_limit - exc.current_usage),
            )

        try:
            answer, sources, used_document_ids = await rag_document_service.query_documents(
                user_id=current_user.id,
                question=data.question,
                top_k=data.top_k,
                document_id=data.document_id,
                client=create_light_rag_client(),
            )
        except LookupError as exc:
            raise NotFoundException(detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

        return RagQueryResponse(
            answer=answer,
            sources=sources,
            used_document_ids=used_document_ids,
        )
