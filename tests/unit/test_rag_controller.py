from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from litestar.datastructures import UploadFile

from app.domain.rag.controllers import RagController
from app.domain.rag.schemas import RagQueryRequest


class StubRequest:
    def __init__(self, form_data: dict[str, Any]) -> None:
        self._form_data = form_data

    async def form(self) -> dict[str, Any]:
        return self._form_data


class StubRagQueueService:
    async def enqueue_document_index(self, *, user_id: UUID, document_id: UUID) -> bool:
        return True


class StubRateLimitService:
    async def check_and_increment_usage(self, user_id: UUID, quota_service: Any) -> None:
        return None


@pytest.mark.anyio
async def test_upload_document_success() -> None:
    controller = SimpleNamespace()
    user = SimpleNamespace(id=uuid4())
    queue_service = StubRagQueueService()
    captured: dict[str, str | None] = {"display_name": None}
    request = StubRequest(
        {
            "file": UploadFile(content_type="text/plain", filename="example.txt", file_data=b"hello"),
            "display_name": "Example",
        }
    )

    class StubRagDocumentService:
        async def upload_plain_text_document(
            self,
            *,
            user_id: UUID,
            file_name: str,
            mime_type: str,
            payload: bytes,
            display_name: str | None,
            queue_service: StubRagQueueService,
        ) -> Any:
            captured["display_name"] = display_name
            return SimpleNamespace(id=uuid4())

    handler = RagController.upload_document
    response = await handler.fn(  # type: ignore[attr-defined]
        controller,
        current_user=user,
        request=request,
        rag_document_service=StubRagDocumentService(),
        rag_queue_service=queue_service,
    )

    assert response.status == "queued"
    assert response.document_id
    assert captured["display_name"] == "Example"


@pytest.mark.anyio
async def test_query_document_filter_success() -> None:
    controller = SimpleNamespace()
    user = SimpleNamespace(id=uuid4())
    requested_document_id = uuid4()
    captured_document_id: dict[str, UUID | None] = {"value": None}

    class StubRagDocumentService:
        async def query_documents(
            self,
            *,
            user_id: UUID,
            question: str,
            top_k: int,
            client: object,
            document_id: UUID | None = None,
        ) -> tuple[str, list[Any], list[UUID]]:
            captured_document_id["value"] = document_id
            return "answer", [], [document_id] if document_id else []

    data = RagQueryRequest(question="What is this?", document_id=requested_document_id, top_k=5)

    handler = RagController.query_rag
    response = await handler.fn(  # type: ignore[attr-defined]
        controller,
        current_user=user,
        data=data,
        rag_document_service=StubRagDocumentService(),
        rate_limit_service=StubRateLimitService(),
        quota_service=SimpleNamespace(),
    )

    assert response.status == "success"
    assert response.answer == "answer"
    assert captured_document_id["value"] == requested_document_id
