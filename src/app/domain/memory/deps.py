"""Dependency providers for memory domain."""

from __future__ import annotations

from app.domain.memory.services import MemoryService
from app.lib.deps import create_service_provider

__all__ = ["provide_memory_service"]


provide_memory_service = create_service_provider(
    MemoryService,
    error_messages={
        "duplicate_key": "Memory entry already exists.",
        "integrity": "Memory operation failed.",
    },
)
