from __future__ import annotations

from typing import TYPE_CHECKING, Iterable
from uuid import UUID

from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService

from app.db import models as m

from .schemas import MemoryDelta, MemoryDeltaAction, MemoryScope

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["MemoryService"]


class MemoryService(SQLAlchemyAsyncRepositoryService[m.Memory]):
    """Handles database operations for memory bullets."""

    class Repository(SQLAlchemyAsyncRepository[m.Memory]):
        """Memory SQLAlchemy Repository."""

        model_type = m.Memory

    repository_type = Repository

    async def list_global_memory(self) -> Sequence[m.Memory]:
        memories, _ = await self.list_and_count(m.Memory.is_global == True)  # noqa: E712
        return memories

    async def list_user_memory(self, user_id: UUID) -> Sequence[m.Memory]:
        memories, _ = await self.list_and_count(m.Memory.user_id == user_id)
        return memories

    async def list_effective_memory(
        self,
        user_id: UUID,
        *,
        limit: int | None = None,
    ) -> Sequence[m.Memory]:
        filters = [
            (m.Memory.is_global == True) | (m.Memory.user_id == user_id)  # noqa: E712
        ]
        if limit is not None:
            from advanced_alchemy.filters import LimitOffset

            memories, _ = await self.list_and_count(*filters, LimitOffset(limit=limit, offset=0))
            return memories

        memories, _ = await self.list_and_count(*filters)
        return memories

    async def apply_memory_deltas(
        self,
        deltas: Iterable[MemoryDelta],
        user_id: UUID,
    ) -> list[m.Memory]:
        results: list[m.Memory] = []
        for delta in deltas:
            scopes = _expand_scopes(delta.scope)
            for scope in scopes:
                target_user_id = None if scope == MemoryScope.GLOBAL else user_id
                if delta.action == MemoryDeltaAction.ADD:
                    if not delta.content or not delta.section:
                        continue
                    payload = {
                        "is_global": scope == MemoryScope.GLOBAL,
                        "user_id": target_user_id,
                        "content": delta.content,
                        "section": delta.section,
                        "metadata_json": delta.metadata or {},
                    }
                    results.append(await self.create(payload, auto_commit=True))
                    continue

                if delta.action in {MemoryDeltaAction.UPDATE, MemoryDeltaAction.TAG, MemoryDeltaAction.REMOVE}:
                    if not delta.target_id:
                        continue
                    try:
                        target_uuid = UUID(delta.target_id)
                    except ValueError:
                        continue

                    memory_item = await self.get_one_or_none(m.Memory.id == target_uuid)
                    if not memory_item:
                        continue
                    if scope == MemoryScope.GLOBAL and memory_item.user_id is not None:
                        continue
                    if scope == MemoryScope.USER and memory_item.user_id != user_id:
                        continue

                    if delta.action == MemoryDeltaAction.REMOVE:
                        await self.delete(memory_item.id, auto_commit=True)
                        continue

                    if delta.action == MemoryDeltaAction.TAG:
                        helpful_delta = delta.helpful_delta or 0
                        harmful_delta = delta.harmful_delta or 0
                        await self.update(
                            item_id=memory_item.id,
                            data={
                                "helpful_count": memory_item.helpful_count + helpful_delta,
                                "harmful_count": memory_item.harmful_count + harmful_delta,
                            },
                            auto_commit=True,
                        )
                        continue

                    update_data: dict[str, object] = {}
                    if delta.content is not None:
                        update_data["content"] = delta.content
                    if delta.section is not None:
                        update_data["section"] = delta.section
                    if delta.metadata is not None:
                        update_data["metadata_json"] = delta.metadata
                    if update_data:
                        await self.update(item_id=memory_item.id, data=update_data, auto_commit=True)
                        results.append(memory_item)

        return results


def _expand_scopes(scope: MemoryScope) -> list[MemoryScope]:
    if scope == MemoryScope.BOTH:
        return [MemoryScope.GLOBAL, MemoryScope.USER]
    return [scope]
