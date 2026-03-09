from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from app.domain.rag import deps as rag_deps
from app.domain.rag.schemas import RagQuerySource
from app.domain.rag.services import RagDocumentService

if TYPE_CHECKING:
    from httpx import AsyncClient
    from pytest import MonkeyPatch


class StubRagQueueService:
    def __init__(self) -> None:
        self.document_calls: list[tuple[UUID, UUID]] = []
        self.rebuild_calls: list[UUID] = []

    async def enqueue_document_index(self, *, user_id: UUID, document_id: UUID) -> bool:
        self.document_calls.append((user_id, document_id))
        return True

    async def enqueue_user_rebuild(self, *, user_id: UUID) -> bool:
        self.rebuild_calls.append(user_id)
        return True


def _install_queue_stub(monkeypatch: "MonkeyPatch") -> StubRagQueueService:
    stub = StubRagQueueService()
    monkeypatch.setattr(rag_deps, "get_rag_queue_service", lambda: stub)
    return stub


def _first_existing(payload: dict[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


@pytest.mark.anyio
async def test_rag_upload_and_list(
    client: "AsyncClient",
    superuser_token_headers: dict[str, str],
    monkeypatch: "MonkeyPatch",
) -> None:
    queue_stub = _install_queue_stub(monkeypatch)

    upload_response = await client.post(
        "/api/rag/documents/upload",
        headers=superuser_token_headers,
        files={"file": ("example.txt", b"hello rag", "text/plain")},
        data={"display_name": "Example"},
    )
    assert upload_response.status_code == 202
    payload = upload_response.json()
    assert payload["status"] == "queued"
    document_id_value = _first_existing(payload, "documentid", "document_id", "documentId")
    assert document_id_value is not None
    assert UUID(str(document_id_value))
    assert len(queue_stub.document_calls) == 1

    list_response = await client.get("/api/rag/documents", headers=superuser_token_headers)
    assert list_response.status_code == 200
    documents = list_response.json()
    assert len(documents) == 1
    display_name = _first_existing(documents[0], "displayname", "display_name", "displayName")
    assert display_name == "Example"
    assert documents[0]["status"] == "queued"


@pytest.mark.anyio
async def test_rag_upload_rejects_non_text_plain(
    client: "AsyncClient",
    superuser_token_headers: dict[str, str],
    monkeypatch: "MonkeyPatch",
) -> None:
    _install_queue_stub(monkeypatch)

    response = await client.post(
        "/api/rag/documents/upload",
        headers=superuser_token_headers,
        files={"file": ("example.json", b'{"a":1}', "application/json")},
    )
    assert response.status_code == 400
    assert "detail" in response.json()


@pytest.mark.anyio
async def test_rag_delete_queues_rebuild(
    client: "AsyncClient",
    superuser_token_headers: dict[str, str],
    monkeypatch: "MonkeyPatch",
) -> None:
    queue_stub = _install_queue_stub(monkeypatch)

    upload_response = await client.post(
        "/api/rag/documents/upload",
        headers=superuser_token_headers,
        files={"file": ("example.txt", b"hello rag", "text/plain")},
        data={"display_name": "DeleteMe"},
    )
    upload_payload = upload_response.json()
    document_id_value = _first_existing(upload_payload, "documentid", "document_id", "documentId")
    assert document_id_value is not None
    document_id = str(document_id_value)

    delete_response = await client.delete(
        f"/api/rag/documents/{document_id}",
        headers=superuser_token_headers,
    )
    assert delete_response.status_code == 202
    assert delete_response.json()["status"] == "queued_for_rebuild"
    assert len(queue_stub.rebuild_calls) == 1

    list_response = await client.get("/api/rag/documents", headers=superuser_token_headers)
    assert list_response.status_code == 200
    assert list_response.json() == []


@pytest.mark.anyio
async def test_rag_query_with_document_filter(
    client: "AsyncClient",
    superuser_token_headers: dict[str, str],
    monkeypatch: "MonkeyPatch",
) -> None:
    requested_document_id = uuid4()
    captured: dict[str, UUID | None] = {"document_id": None}

    async def fake_query_documents(
        self: RagDocumentService,
        *,
        user_id: UUID,
        question: str,
        top_k: int,
        client: object,
        document_id: UUID | None = None,
    ) -> tuple[str, list[RagQuerySource], list[UUID]]:
        captured["document_id"] = document_id
        source = RagQuerySource(
            document_id=document_id,
            file_name="example.txt",
            chunk_id="chunk-1",
            score=0.92,
            excerpt="hello rag",
        )
        return "answer", [source], [document_id] if document_id else []

    monkeypatch.setattr(RagDocumentService, "query_documents", fake_query_documents)

    response = await client.post(
        "/api/rag/query",
        headers=superuser_token_headers,
        json={
            "question": "What is this document about?",
            "document_id": str(requested_document_id),
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "answer"
    source_document_id = _first_existing(payload["sources"][0], "documentid", "document_id", "documentId")
    assert source_document_id == str(requested_document_id)
    assert captured["document_id"] == requested_document_id
