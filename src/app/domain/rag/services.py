"""Services for rag domain."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService

from app.config import get_settings
from app.db import models as m
from app.domain.rag.lightrag_client import LightRagClient, LightRagDocument
from app.domain.rag.schemas import RagDocumentStatus, RagQuerySource

if TYPE_CHECKING:
    from app.domain.rag.queue import RagQueueService

__all__ = ["RagDocumentService"]

_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{12}\b"
)
_SCORE_PATTERN = re.compile(r"(?:score|similarity)\s*[:=]\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
_LIGHTRAG_CHUNKS_PATTERN = re.compile(
    r"(?ms)^Document Chunks.*?^\s*```json\s*(.*?)\s*^\s*```"
)
_LIGHTRAG_REFERENCES_PATTERN = re.compile(
    r"(?ms)^Reference Document List.*?^\s*```\s*(.*?)\s*^\s*```"
)
_LIGHTRAG_REFERENCE_LINE_PATTERN = re.compile(r"^\[(?P<reference_id>[^\]]+)\]\s+(?P<path>.+)$", re.MULTILINE)


class RagDocumentService(SQLAlchemyAsyncRepositoryService[m.RagDocument]):
    """Handles document metadata and indexing orchestration for RAG."""

    class Repository(SQLAlchemyAsyncRepository[m.RagDocument]):
        """RAG document SQLAlchemy repository."""

        model_type = m.RagDocument

    repository_type = Repository

    async def upload_plain_text_document(
        self,
        *,
        user_id: UUID,
        file_name: str,
        mime_type: str,
        payload: bytes,
        display_name: str | None,
        queue_service: "RagQueueService",
    ) -> m.RagDocument:
        """Persist upload metadata and enqueue async indexing."""
        settings = get_settings()
        if not settings.ai.RAG_ENABLED:
            msg = "RAG is disabled by server configuration"
            raise ValueError(msg)

        if not payload:
            msg = "Uploaded file is empty"
            raise ValueError(msg)

        if len(payload) > settings.ai.RAG_MAX_UPLOAD_BYTES:
            msg = f"File too large. Max bytes: {settings.ai.RAG_MAX_UPLOAD_BYTES}"
            raise ValueError(msg)

        try:
            text_content = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            msg = "Only UTF-8 encoded plain-text files are supported"
            raise ValueError(msg) from exc

        if not text_content.strip():
            msg = "Uploaded text content is empty"
            raise ValueError(msg)

        document_id = uuid4()
        resolved_name = (display_name or Path(file_name).stem or file_name).strip()
        safe_file_name = Path(file_name).name
        raw_path = self._raw_file_path(user_id=user_id, document_id=document_id)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(text_content, encoding="utf-8")

        document = await self.create(
            {
                "id": document_id,
                "user_id": user_id,
                "display_name": resolved_name,
                "original_filename": safe_file_name,
                "mime_type": mime_type,
                "size_bytes": len(payload),
                "sha256": sha256(payload).hexdigest(),
                "status": RagDocumentStatus.QUEUED.value,
                "error_message": None,
                "storage_path": str(raw_path),
                "indexed_at": None,
            },
            auto_commit=True,
        )

        get_unavailable_reason = getattr(queue_service, "get_unavailable_reason", None)
        unavailable_reason = get_unavailable_reason() if callable(get_unavailable_reason) else None
        enqueued = await queue_service.enqueue_document_index(user_id=user_id, document_id=document_id)
        if not enqueued:
            error_message = unavailable_reason or "RAG indexing queue unavailable"
            await self.update(
                item_id=document_id,
                data={
                    "status": RagDocumentStatus.FAILED.value,
                    "error_message": error_message,
                },
                auto_commit=True,
            )
            msg = error_message
            raise RuntimeError(msg)

        return document

    async def list_user_documents(
        self,
        *,
        user_id: UUID,
        status: RagDocumentStatus | None = None,
    ) -> list[m.RagDocument]:
        """List user documents excluding deleted rows by default."""
        filters = [m.RagDocument.user_id == user_id, m.RagDocument.status != RagDocumentStatus.DELETED.value]
        if status is not None:
            filters.append(m.RagDocument.status == status.value)

        documents, _ = await self.list_and_count(*filters)
        return sorted(documents, key=lambda document: document.created_at, reverse=True)

    async def get_user_document(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        include_deleted: bool = False,
    ) -> m.RagDocument | None:
        """Get one user document with ownership checks."""
        filters = [m.RagDocument.id == document_id, m.RagDocument.user_id == user_id]
        if not include_deleted:
            filters.append(m.RagDocument.status != RagDocumentStatus.DELETED.value)
        return await self.get_one_or_none(*filters)

    async def delete_document_and_queue_rebuild(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        queue_service: "RagQueueService",
    ) -> m.RagDocument:
        """Soft-delete document then queue full user rebuild."""
        document = await self.get_user_document(user_id=user_id, document_id=document_id)
        if document is None:
            msg = "Document not found"
            raise LookupError(msg)

        previous_status = document.status
        await self.update(
            item_id=document.id,
            data={
                "status": RagDocumentStatus.DELETED.value,
                "error_message": None,
            },
            auto_commit=True,
        )

        get_unavailable_reason = getattr(queue_service, "get_unavailable_reason", None)
        unavailable_reason = get_unavailable_reason() if callable(get_unavailable_reason) else None
        enqueued = await queue_service.enqueue_user_rebuild(user_id=user_id)
        if not enqueued:
            error_message = unavailable_reason or "Queue unavailable for rebuild"
            await self.update(
                item_id=document.id,
                data={
                    "status": previous_status,
                    "error_message": error_message,
                },
                auto_commit=True,
            )
            msg = error_message
            raise RuntimeError(msg)

        return await self.get(document.id)

    async def process_index_job(
        self,
        *,
        user_id: UUID,
        client: LightRagClient,
    ) -> None:
        """Rebuild user and per-document workspaces from active rows."""
        active_documents = await self._list_active_documents(user_id)
        if not active_documents:
            client.clear_user_workspaces(user_id)
            return

        for document in active_documents:
            await self.update(
                item_id=document.id,
                data={
                    "status": RagDocumentStatus.INDEXING.value,
                    "error_message": None,
                },
                auto_commit=True,
            )

        indexable_documents: list[tuple[m.RagDocument, LightRagDocument]] = []
        for document in active_documents:
            source_path = Path(document.storage_path)
            if not source_path.exists():
                await self.update(
                    item_id=document.id,
                    data={
                        "status": RagDocumentStatus.FAILED.value,
                        "error_message": "Raw file is missing",
                    },
                    auto_commit=True,
                )
                continue

            content = source_path.read_text(encoding="utf-8")
            if not content.strip():
                await self.update(
                    item_id=document.id,
                    data={
                        "status": RagDocumentStatus.FAILED.value,
                        "error_message": "Raw file is empty",
                    },
                    auto_commit=True,
                )
                continue

            indexable_documents.append(
                (
                    document,
                    LightRagDocument(
                        document_id=document.id,
                        file_name=document.display_name,
                        text=content,
                        source_path=str(source_path),
                    ),
                )
            )

        if not indexable_documents:
            client.clear_user_workspaces(user_id)
            return

        indexed_at = datetime.now(UTC)
        try:
            await client.rebuild_user_workspace(
                user_id=user_id,
                documents=[item[1] for item in indexable_documents],
            )
            for _, light_document in indexable_documents:
                await client.rebuild_document_workspace(user_id=user_id, document=light_document)
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)[:1000]
            for document, _ in indexable_documents:
                await self.update(
                    item_id=document.id,
                    data={
                        "status": RagDocumentStatus.FAILED.value,
                        "error_message": error_message,
                    },
                    auto_commit=True,
                )
            return

        for document, _ in indexable_documents:
            await self.update(
                item_id=document.id,
                data={
                    "status": RagDocumentStatus.READY.value,
                    "error_message": None,
                    "indexed_at": indexed_at,
                },
                auto_commit=True,
            )

    async def query_documents(
        self,
        *,
        user_id: UUID,
        question: str,
        top_k: int,
        client: LightRagClient,
        document_id: UUID | None = None,
    ) -> tuple[str, list[RagQuerySource], list[UUID]]:
        """Run RAG query and normalize citations."""
        if document_id is not None:
            target = await self.get_user_document(user_id=user_id, document_id=document_id)
            if target is None:
                msg = "Document not found"
                raise LookupError(msg)
            if target.status != RagDocumentStatus.READY.value:
                msg = "Document is not indexed yet"
                raise ValueError(msg)

            await self._ensure_document_workspace_queryable(
                user_id=user_id,
                document=target,
                client=client,
            )

            result = await client.query_document_workspace(
                user_id=user_id,
                document_id=target.id,
                question=question,
                top_k=top_k,
            )
            document_map = {target.id: target}
            sources = self._extract_sources(
                context=result.context,
                document_map=document_map,
                top_k=top_k,
                forced_document_id=target.id,
            )
            used_ids = [target.id] if sources else []
            return result.answer, sources, used_ids

        ready_documents = await self._list_ready_documents(user_id)
        if not ready_documents:
            msg = "No indexed documents found. Upload a file and wait for indexing to complete."
            raise ValueError(msg)

        result = await client.query_user_workspace(user_id=user_id, question=question, top_k=top_k)
        document_map = {document.id: document for document in ready_documents}
        sources = self._extract_sources(
            context=result.context,
            document_map=document_map,
            top_k=top_k,
            forced_document_id=None,
        )

        used_ids: list[UUID] = []
        for source in sources:
            if source.document_id is not None and source.document_id not in used_ids:
                used_ids.append(source.document_id)

        return result.answer, sources, used_ids

    async def _ensure_document_workspace_queryable(
        self,
        *,
        user_id: UUID,
        document: m.RagDocument,
        client: LightRagClient,
    ) -> None:
        if client.document_workspace_is_queryable(user_id=user_id, document_id=document.id):
            return

        source_path = Path(document.storage_path)
        if not source_path.exists():
            await self.update(
                item_id=document.id,
                data={
                    "status": RagDocumentStatus.FAILED.value,
                    "error_message": "Raw file is missing",
                },
                auto_commit=True,
            )
            msg = "Document index is unavailable because the source file is missing. Please re-upload the document."
            raise ValueError(msg)

        content = source_path.read_text(encoding="utf-8")
        if not content.strip():
            await self.update(
                item_id=document.id,
                data={
                    "status": RagDocumentStatus.FAILED.value,
                    "error_message": "Raw file is empty",
                },
                auto_commit=True,
            )
            msg = "Document index is unavailable because the source file is empty. Please re-upload the document."
            raise ValueError(msg)

        try:
            await client.rebuild_document_workspace(
                user_id=user_id,
                document=LightRagDocument(
                    document_id=document.id,
                    file_name=document.display_name,
                    text=content,
                    source_path=str(source_path),
                ),
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"Failed to rebuild document index: {exc}"
            raise RuntimeError(msg) from exc

        if not client.document_workspace_is_queryable(user_id=user_id, document_id=document.id):
            msg = "Document index rebuild completed without queryable chunks. Please re-upload the document."
            raise RuntimeError(msg)

    async def _list_ready_documents(self, user_id: UUID) -> list[m.RagDocument]:
        documents, _ = await self.list_and_count(
            m.RagDocument.user_id == user_id,
            m.RagDocument.status == RagDocumentStatus.READY.value,
        )
        return list(documents)

    async def _list_active_documents(self, user_id: UUID) -> list[m.RagDocument]:
        documents, _ = await self.list_and_count(
            m.RagDocument.user_id == user_id,
            m.RagDocument.status != RagDocumentStatus.DELETED.value,
        )
        return list(documents)

    def _raw_file_path(self, *, user_id: UUID, document_id: UUID) -> Path:
        root = Path(get_settings().ai.RAG_WORKING_DIR_ROOT) / "raw"
        return root / str(user_id) / f"{document_id}.txt"

    @classmethod
    def _extract_sources(
        cls,
        *,
        context: str | None,
        document_map: dict[UUID, m.RagDocument],
        top_k: int,
        forced_document_id: UUID | None,
    ) -> list[RagQuerySource]:
        if not context:
            return []

        lightrag_sources = cls._extract_lightrag_sources(
            context=context,
            document_map=document_map,
            top_k=top_k,
            forced_document_id=forced_document_id,
        )
        if lightrag_sources is not None:
            return lightrag_sources

        parsed = cls._parse_context_payload(context)
        sources: list[RagQuerySource] = []
        for index, chunk in enumerate(parsed[:top_k], start=1):
            source = cls._build_source(
                index=index,
                chunk=chunk,
                document_map=document_map,
                forced_document_id=forced_document_id,
            )
            if source is not None:
                sources.append(source)
        return sources

    @classmethod
    def _extract_lightrag_sources(
        cls,
        *,
        context: str,
        document_map: dict[UUID, m.RagDocument],
        top_k: int,
        forced_document_id: UUID | None,
    ) -> list[RagQuerySource] | None:
        chunk_match = _LIGHTRAG_CHUNKS_PATTERN.search(context)
        if chunk_match is None:
            return None

        references_match = _LIGHTRAG_REFERENCES_PATTERN.search(context)
        reference_path_map = cls._parse_lightrag_reference_paths(references_match.group(1) if references_match else "")
        chunk_entries = cls._parse_lightrag_chunk_entries(chunk_match.group(1))

        sources: list[RagQuerySource] = []
        for index, entry in enumerate(chunk_entries[:top_k], start=1):
            excerpt_raw = entry.get("content") or entry.get("text") or entry.get("chunk") or entry.get("excerpt")
            if excerpt_raw is None:
                continue

            reference_id = str(entry.get("reference_id") or entry.get("referenceId") or "").strip()
            reference_path = reference_path_map.get(reference_id)
            resolved_document_id, file_name = cls._resolve_source_document(
                document_map=document_map,
                forced_document_id=forced_document_id,
                reference_path=reference_path,
            )

            score = entry.get("score")
            if not isinstance(score, int | float):
                score = cls._extract_score(json.dumps(entry, ensure_ascii=False))

            raw_chunk_id = entry.get("chunk_id") or entry.get("chunkId") or entry.get("id") or reference_id
            chunk_id = str(raw_chunk_id).strip() if raw_chunk_id else f"chunk-{index}"

            sources.append(
                RagQuerySource(
                    document_id=resolved_document_id,
                    file_name=file_name,
                    chunk_id=chunk_id,
                    score=float(score) if isinstance(score, int | float) else None,
                    excerpt=str(excerpt_raw)[:500],
                )
            )

        return sources

    @classmethod
    def _build_source(
        cls,
        *,
        index: int,
        chunk: str,
        document_map: dict[UUID, m.RagDocument],
        forced_document_id: UUID | None,
    ) -> RagQuerySource | None:
        cleaned = chunk.strip()
        if not cleaned:
            return None

        resolved_document_id = forced_document_id or cls._extract_document_id(cleaned, document_map)
        file_name = None
        if resolved_document_id is not None and resolved_document_id in document_map:
            file_name = document_map[resolved_document_id].display_name
        score = cls._extract_score(cleaned)

        return RagQuerySource(
            document_id=resolved_document_id,
            file_name=file_name,
            chunk_id=f"chunk-{index}",
            score=score,
            excerpt=cleaned[:500],
        )

    @classmethod
    def _resolve_source_document(
        cls,
        *,
        document_map: dict[UUID, m.RagDocument],
        forced_document_id: UUID | None,
        reference_path: str | None,
    ) -> tuple[UUID | None, str | None]:
        if forced_document_id is not None:
            document = document_map.get(forced_document_id)
            if document is not None:
                return forced_document_id, document.display_name
            return forced_document_id, Path(reference_path).name if reference_path else None

        if reference_path:
            normalized_reference_path = Path(reference_path).as_posix()
            for document_id, document in document_map.items():
                storage_path = getattr(document, "storage_path", None)
                if not storage_path:
                    continue

                normalized_storage_path = Path(storage_path).as_posix()
                if (
                    normalized_storage_path == normalized_reference_path
                    or normalized_storage_path.endswith(normalized_reference_path)
                    or normalized_reference_path.endswith(normalized_storage_path)
                ):
                    return document_id, document.display_name

            reference_name = Path(normalized_reference_path).name
            for document_id, document in document_map.items():
                if reference_name in {
                    getattr(document, "original_filename", None),
                    getattr(document, "display_name", None),
                    Path(getattr(document, "storage_path", "")).name,
                }:
                    return document_id, document.display_name

            return None, reference_name

        if len(document_map) == 1:
            document_id, document = next(iter(document_map.items()))
            return document_id, document.display_name

        return None, None

    @staticmethod
    def _parse_context_payload(context: str) -> list[str]:
        stripped = context.strip()
        if not stripped:
            return []

        if stripped.startswith(("{", "[")):
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, list):
                chunks: list[str] = []
                for item in payload:
                    if isinstance(item, dict):
                        candidate = item.get("content") or item.get("text") or item.get("chunk")
                        if candidate is not None:
                            chunks.append(str(candidate))
                        else:
                            chunks.append(json.dumps(item, ensure_ascii=False))
                    else:
                        chunks.append(str(item))
                return chunks
            if isinstance(payload, dict):
                candidate = payload.get("content") or payload.get("text")
                if candidate is not None:
                    return [str(candidate)]
                return [json.dumps(payload, ensure_ascii=False)]

        return [part.strip() for part in re.split(r"\n\s*\n", stripped) if part.strip()]

    @staticmethod
    def _parse_lightrag_reference_paths(block: str) -> dict[str, str]:
        references: dict[str, str] = {}
        for match in _LIGHTRAG_REFERENCE_LINE_PATTERN.finditer(block):
            reference_id = match.group("reference_id").strip()
            path = match.group("path").strip()
            if reference_id:
                references[reference_id] = path
        return references

    @staticmethod
    def _parse_lightrag_chunk_entries(block: str) -> list[dict[str, Any]]:
        payload = block.strip()
        if not payload:
            return []

        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            decoded = None
        else:
            if isinstance(decoded, list):
                return [item for item in decoded if isinstance(item, dict)]
            if isinstance(decoded, dict):
                return [decoded]

        entries: list[dict[str, Any]] = []
        for line in payload.splitlines():
            candidate = line.strip().rstrip(",")
            if not candidate or not candidate.startswith("{"):
                continue
            try:
                decoded_line = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded_line, dict):
                entries.append(decoded_line)
        return entries

    @staticmethod
    def _extract_document_id(chunk: str, document_map: dict[UUID, m.RagDocument]) -> UUID | None:
        for match in _UUID_PATTERN.findall(chunk):
            try:
                candidate = UUID(match)
            except ValueError:
                continue
            if candidate in document_map:
                return candidate
        return None

    @staticmethod
    def _extract_score(chunk: str) -> float | None:
        match = _SCORE_PATTERN.search(chunk)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None
