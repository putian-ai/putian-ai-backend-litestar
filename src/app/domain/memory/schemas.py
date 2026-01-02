"""Schemas for memory domain."""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from app.domain.accounts.schemas import PydanticBaseModel

__all__ = [
    "MemoryContextResult",
    "MemoryDelta",
    "MemoryDeltaAction",
    "MemoryScope",
    "MemoryUpdateResult",
]


class MemoryScope(str, Enum):
    """Scope of memory updates."""

    GLOBAL = "global"
    USER = "user"
    BOTH = "both"


class MemoryDeltaAction(str, Enum):
    """Actions for memory updates."""

    ADD = "add"
    UPDATE = "update"
    TAG = "tag"
    REMOVE = "remove"


class MemoryDelta(PydanticBaseModel):
    """A single memory update instruction."""

    action: MemoryDeltaAction = Field(..., description="Delta action: add/update/tag/remove")
    scope: MemoryScope = Field(..., description="Scope of the update: global/user/both")
    section: str | None = Field(default=None, description="Memory section for add/update")
    content: str | None = Field(default=None, description="Memory content for add/update")
    target_id: str | None = Field(default=None, description="Target memory ID for update/tag/remove")
    helpful_delta: int | None = Field(default=None, description="Increment for helpful_count")
    harmful_delta: int | None = Field(default=None, description="Increment for harmful_count")
    metadata: dict[str, str] | None = Field(default=None, description="Optional metadata payload")


class MemoryContextResult(PydanticBaseModel):
    """Structured memory context to inject into a business agent."""

    context: str = Field(..., description="Condensed memory context to inject")
    selected_ids: list[str] = Field(
        default_factory=list,
        description="Memory IDs referenced in the context",
    )


class MemoryUpdateResult(PydanticBaseModel):
    """Structured memory updates after a response is generated."""

    deltas: list[MemoryDelta] = Field(default_factory=list, description="Memory updates to apply")
