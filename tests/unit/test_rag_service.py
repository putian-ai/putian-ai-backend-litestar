from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.domain.rag.lightrag_client import LightRagQueryResult
from app.domain.rag.services import RagDocumentService


def test_extract_sources_parses_document_id_and_score() -> None:
    document_id = uuid4()
    document_map = {document_id: SimpleNamespace(display_name="example.txt")}
    context = f"matched document {document_id}\nscore: 0.87\ncontent line"

    sources = RagDocumentService._extract_sources(
        context=context,
        document_map=document_map,
        top_k=3,
        forced_document_id=None,
    )

    assert len(sources) == 1
    source = sources[0]
    assert source.document_id == document_id
    assert source.file_name == "example.txt"
    assert source.score == 0.87
    assert source.chunk_id == "chunk-1"


def test_extract_sources_respects_forced_document_filter() -> None:
    forced_document_id = uuid4()
    unrelated_document_id = uuid4()
    document_map = {forced_document_id: SimpleNamespace(display_name="forced.txt")}
    context = f"contains another uuid {unrelated_document_id}\ncontent line"

    sources = RagDocumentService._extract_sources(
        context=context,
        document_map=document_map,
        top_k=3,
        forced_document_id=forced_document_id,
    )

    assert len(sources) == 1
    source = sources[0]
    assert source.document_id == forced_document_id
    assert source.file_name == "forced.txt"


def test_extract_sources_parses_lightrag_reference_paths() -> None:
    document_id = uuid4()
    other_document_id = uuid4()
    storage_path = "/workspace/project/data/rag/raw/test-user/example-rag.txt"
    document_map = {
        document_id: SimpleNamespace(
            display_name="Example.txt",
            original_filename="example-rag.txt",
            storage_path=storage_path,
        ),
        other_document_id: SimpleNamespace(
            display_name="Other.txt",
            original_filename="other-rag.txt",
            storage_path="/workspace/project/data/rag/raw/test-user/other-rag.txt",
        ),
    }
    context = """
Document Chunks (Each entry has a reference_id refer to the `Reference Document List`):

```json
{"reference_id": "1", "content": "hello rag upload"}
```

Reference Document List (Each entry starts with a [reference_id] that corresponds to entries in the Document Chunks):

```
[1] data/rag/raw/test-user/example-rag.txt
```
"""

    sources = RagDocumentService._extract_sources(
        context=context,
        document_map=document_map,
        top_k=3,
        forced_document_id=None,
    )

    assert len(sources) == 1
    source = sources[0]
    assert source.document_id == document_id
    assert source.file_name == "Example.txt"
    assert source.chunk_id == "1"
    assert source.excerpt == "hello rag upload"


@pytest.mark.anyio
async def test_query_documents_rebuilds_missing_document_workspace(tmp_path: Path) -> None:
    document_id = uuid4()
    user_id = uuid4()
    source_path = tmp_path / "source.txt"
    source_path.write_text("hello rag upload", encoding="utf-8")

    document = SimpleNamespace(
        id=document_id,
        status="ready",
        display_name="Example",
        storage_path=str(source_path),
        original_filename="source.txt",
    )

    class StubClient:
        def __init__(self) -> None:
            self.workspace_ready = False
            self.rebuild_calls: list[tuple[object, object]] = []

        def document_workspace_is_queryable(self, *, user_id: object, document_id: object) -> bool:
            return self.workspace_ready

        async def rebuild_document_workspace(self, *, user_id: object, document: object) -> None:
            self.rebuild_calls.append((user_id, document))
            self.workspace_ready = True

        async def query_document_workspace(
            self,
            *,
            user_id: object,
            document_id: object,
            question: str,
            top_k: int,
        ) -> LightRagQueryResult:
            return LightRagQueryResult(
                answer="answer",
                context=(
                    "Document Chunks (Each entry has a reference_id refer to the `Reference Document List`):\n\n"
                    "```json\n"
                    "{\"reference_id\": \"1\", \"content\": \"hello rag upload\"}\n"
                    "```\n\n"
                    "Reference Document List (Each entry starts with a [reference_id] that corresponds to entries in the Document Chunks):\n\n"
                    "```\n"
                    f"[1] {source_path.as_posix()}\n"
                    "```"
                ),
            )

    class StubRagDocumentService(RagDocumentService):
        def __init__(self) -> None:
            pass

        async def get_user_document(
            self,
            *,
            user_id: object,
            document_id: object,
            include_deleted: bool = False,
        ) -> object:
            return document

        async def update(
            self,
            *,
            item_id: object,
            data: dict[str, object],
            auto_commit: bool = True,
        ) -> None:
            raise AssertionError("update should not be called for rebuildable workspace")

    service = StubRagDocumentService()
    client = StubClient()

    answer, sources, used_ids = await service.query_documents(
        user_id=user_id,
        question="what is this",
        top_k=5,
        client=client,
        document_id=document_id,
    )

    assert answer == "answer"
    assert len(client.rebuild_calls) == 1
    assert sources[0].excerpt == "hello rag upload"
    assert used_ids == [document_id]


@pytest.mark.anyio
async def test_query_documents_fails_when_document_source_missing() -> None:
    document_id = uuid4()
    user_id = uuid4()

    document = SimpleNamespace(
        id=document_id,
        status="ready",
        display_name="Missing",
        storage_path="/tmp/missing-source.txt",
        original_filename="missing-source.txt",
    )

    class StubClient:
        def document_workspace_is_queryable(self, *, user_id: object, document_id: object) -> bool:
            return False

    class StubRagDocumentService(RagDocumentService):
        def __init__(self) -> None:
            self.updated_payloads: list[dict[str, object]] = []

        async def get_user_document(
            self,
            *,
            user_id: object,
            document_id: object,
            include_deleted: bool = False,
        ) -> object:
            return document

        async def update(
            self,
            *,
            item_id: object,
            data: dict[str, object],
            auto_commit: bool = True,
        ) -> None:
            self.updated_payloads.append(data)

    service = StubRagDocumentService()

    with pytest.raises(ValueError, match="source file is missing"):
        await service.query_documents(
            user_id=user_id,
            question="what is this",
            top_k=5,
            client=StubClient(),
            document_id=document_id,
        )

    assert service.updated_payloads[0]["status"] == "failed"
    assert service.updated_payloads[0]["error_message"] == "Raw file is missing"


@pytest.mark.anyio
async def test_upload_plain_text_document_surfaces_queue_reason(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    queue_reason = "Missing RAG provider credentials: SILICON_FLOW_API_KEY"

    settings = SimpleNamespace(
        ai=SimpleNamespace(
            RAG_ENABLED=True,
            RAG_MAX_UPLOAD_BYTES=1024 * 1024,
        )
    )
    monkeypatch.setattr("app.domain.rag.services.get_settings", lambda: settings)

    class StubQueueService:
        def get_unavailable_reason(self) -> str:
            return queue_reason

        async def enqueue_document_index(self, *, user_id: object, document_id: object) -> bool:
            return False

    class StubRagDocumentService(RagDocumentService):
        def __init__(self) -> None:
            self.updated_payloads: list[dict[str, object]] = []

        async def create(self, data: dict[str, object], auto_commit: bool = True) -> SimpleNamespace:
            return SimpleNamespace(**data)

        async def update(
            self,
            *,
            item_id: object,
            data: dict[str, object],
            auto_commit: bool = True,
        ) -> None:
            self.updated_payloads.append(data)

        def _raw_file_path(self, *, user_id: object, document_id: object) -> Path:
            return tmp_path / f"{document_id}.txt"

    service = StubRagDocumentService()

    with pytest.raises(RuntimeError, match="Missing RAG provider credentials: SILICON_FLOW_API_KEY"):
        await service.upload_plain_text_document(
            user_id=uuid4(),
            file_name="example.txt",
            mime_type="text/plain",
            payload=b"hello rag",
            display_name="Example",
            queue_service=StubQueueService(),
        )

    assert service.updated_payloads[0]["error_message"] == queue_reason
