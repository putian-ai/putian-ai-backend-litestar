"""LightRAG client wrapper for indexing and querying."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.config import get_settings
from app.lib.exceptions import MissingDependencyError

if TYPE_CHECKING:
    from uuid import UUID

__all__ = [
    "LightRagClient",
    "LightRagDocument",
    "LightRagQueryResult",
    "create_light_rag_client",
]


@dataclass(frozen=True)
class LightRagDocument:
    """Single document payload used by LightRAG indexing."""

    document_id: UUID
    file_name: str
    text: str
    source_path: str


@dataclass(frozen=True)
class LightRagQueryResult:
    """Answer and retrieved context from a LightRAG query."""

    answer: str
    context: str | None


class LightRagClient:
    """Small adapter over LightRAG with user/document workspace helpers."""

    def __init__(self) -> None:
        settings = get_settings()
        self._ai_settings = settings.ai
        self._workspace_root = Path(self._ai_settings.RAG_WORKING_DIR_ROOT) / "workspaces"

    async def rebuild_user_workspace(self, user_id: UUID, documents: list[LightRagDocument]) -> None:
        """Rebuild the merged workspace for one user from provided documents."""
        workspace = self._user_workspace(user_id)
        self._reset_workspace(workspace)
        if not documents:
            return

        rag, _ = await self._create_rag(workspace)
        await rag.ainsert(
            [document.text for document in documents],
            ids=[str(document.document_id) for document in documents],
            file_paths=[document.source_path for document in documents],
        )

    async def rebuild_document_workspace(self, user_id: UUID, document: LightRagDocument) -> None:
        """Rebuild one dedicated workspace to guarantee strict document filtering."""
        workspace = self._document_workspace(user_id, document.document_id)
        self._reset_workspace(workspace)

        rag, _ = await self._create_rag(workspace)
        await rag.ainsert(
            document.text,
            ids=str(document.document_id),
            file_paths=document.source_path,
        )

    async def query_user_workspace(self, user_id: UUID, question: str, top_k: int) -> LightRagQueryResult:
        """Query merged user workspace."""
        workspace = self._user_workspace(user_id)
        if not workspace.exists():
            return LightRagQueryResult(answer="[no-context]", context=None)

        rag, query_param_cls = await self._create_rag(workspace)
        return await self._query_rag(rag=rag, query_param_cls=query_param_cls, question=question, top_k=top_k)

    async def query_document_workspace(
        self,
        user_id: UUID,
        document_id: UUID,
        question: str,
        top_k: int,
    ) -> LightRagQueryResult:
        """Query a single document workspace for strict filtering."""
        workspace = self._document_workspace(user_id, document_id)
        if not workspace.exists():
            return LightRagQueryResult(answer="[no-context]", context=None)

        rag, query_param_cls = await self._create_rag(workspace)
        return await self._query_rag(rag=rag, query_param_cls=query_param_cls, question=question, top_k=top_k)

    def document_workspace_is_queryable(self, user_id: UUID, document_id: UUID) -> bool:
        """Return whether one document workspace contains persisted chunk index data."""
        return self._workspace_has_queryable_chunks(self._document_workspace(user_id, document_id))

    def clear_user_workspaces(self, user_id: UUID) -> None:
        """Remove all LightRAG workspaces for one user."""
        workspace_root = self._workspace_root / str(user_id)
        if workspace_root.exists():
            shutil.rmtree(workspace_root)

    async def _create_rag(self, workspace: Path) -> tuple[Any, Any]:
        if not self._ai_settings.DEEPSEEK_API_KEY:
            msg = "DEEPSEEK_API_KEY is required for LightRAG LLM calls"
            raise ValueError(msg)
        if not self._ai_settings.SILICON_FLOW_API_KEY:
            msg = "SILICON_FLOW_API_KEY is required for LightRAG embedding calls"
            raise ValueError(msg)

        try:
            from lightrag import LightRAG, QueryParam  # noqa: PLC0415
            from lightrag.llm.openai import openai_complete_if_cache, openai_embed  # noqa: PLC0415
            from lightrag.utils import EmbeddingFunc  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - dependent on environment
            raise MissingDependencyError(detail="Install lightrag-hku to enable RAG features") from exc

        workspace.mkdir(parents=True, exist_ok=True)
        workspace_name = self._workspace_name(workspace)

        async def llm_model_func(
            prompt: str,
            system_prompt: str | None = None,
            history_messages: list[dict[str, Any]] | None = None,
            **kwargs: Any,
        ) -> str:
            kwargs.pop("model", None)
            keyword_extraction = bool(kwargs.pop("keyword_extraction", False))
            kwargs.pop("response_format", None)
            return await openai_complete_if_cache(
                model=self._ai_settings.LLM_MODEL,
                prompt=prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=self._ai_settings.DEEPSEEK_API_KEY,
                base_url=self._ai_settings.LLM_BINDING_HOST,
                keyword_extraction=False if keyword_extraction else False,
                **kwargs,
            )

        embedding_func = EmbeddingFunc(
            embedding_dim=self._ai_settings.EMBEDDING_DIM,
            max_token_size=self._ai_settings.MAX_EMBED_TOKENS,
            func=partial(
                openai_embed.func,
                model=self._ai_settings.EMBEDDING_MODEL,
                api_key=self._ai_settings.SILICON_FLOW_API_KEY,
                base_url=self._ai_settings.EMBEDDING_BINDING_HOST,
            ),
            model_name=self._ai_settings.EMBEDDING_MODEL,
        )

        rag = LightRAG(
            working_dir=str(self._workspace_root),
            workspace=workspace_name,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
        )
        await rag.initialize_storages()
        return rag, QueryParam

    async def _query_rag(
        self,
        *,
        rag: Any,
        query_param_cls: Any,
        question: str,
        top_k: int,
    ) -> LightRagQueryResult:
        answer_raw = await rag.aquery(
            question,
            param=query_param_cls(mode="mix", top_k=top_k),
        )
        answer = answer_raw if isinstance(answer_raw, str) else str(answer_raw)

        context: str | None = None
        try:
            context_raw = await rag.aquery(
                question,
                param=query_param_cls(mode="mix", top_k=top_k, only_need_context=True),
            )
        except Exception:  # noqa: BLE001
            context = None
        else:
            if context_raw is None:
                context = None
            elif isinstance(context_raw, str):
                context = context_raw
            else:
                context = str(context_raw)

        return LightRagQueryResult(answer=answer, context=context)

    def _user_workspace(self, user_id: UUID) -> Path:
        return self._workspace_root / str(user_id) / "all"

    def _document_workspace(self, user_id: UUID, document_id: UUID) -> Path:
        return self._workspace_root / str(user_id) / "documents" / str(document_id)

    def _workspace_name(self, workspace: Path) -> str:
        return workspace.relative_to(self._workspace_root).as_posix()

    @staticmethod
    def _workspace_has_queryable_chunks(workspace: Path) -> bool:
        if not workspace.exists():
            return False

        chunk_index_path = workspace / "vdb_chunks.json"
        if chunk_index_path.exists():
            try:
                payload = json.loads(chunk_index_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
            else:
                data = payload.get("data") if isinstance(payload, dict) else None
                if isinstance(data, list) and len(data) > 0:
                    return True

        text_chunks_path = workspace / "kv_store_text_chunks.json"
        if text_chunks_path.exists():
            try:
                payload = json.loads(text_chunks_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
            else:
                if isinstance(payload, dict) and len(payload) > 0:
                    return True

        return False

    @staticmethod
    def _reset_workspace(workspace: Path) -> None:
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)


def create_light_rag_client() -> LightRagClient:
    """Create LightRAG client with current runtime settings."""
    return LightRagClient()
