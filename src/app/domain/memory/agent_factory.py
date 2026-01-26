"""Agent factory for memory agents."""

from __future__ import annotations

from typing import Any

from agents import Agent
from agents.extensions.models.litellm_model import LitellmModel
from app.config import get_settings

from .schemas import MemoryContextResult, MemoryUpdateResult
from .system_instructions import MEMORY_CONTEXT_INSTRUCTIONS, MEMORY_UPDATE_INSTRUCTIONS

__all__ = ["get_memory_context_agent", "get_memory_update_agent"]


def _get_model() -> Any:
    settings = get_settings()
    return LitellmModel(
        model="deepseek/deepseek-chat",
        api_key=settings.ai.DEEPSEEK_API_KEY,
        base_url=settings.ai.DEEPSEEK_BASE_URL,
    )


def get_memory_context_agent() -> Agent:
    """Agent that produces condensed memory context."""
    return Agent(
        name="MemoryContextAgent",
        instructions=MEMORY_CONTEXT_INSTRUCTIONS,
        model=_get_model(),
        output_type=MemoryContextResult,
    )


def get_memory_update_agent() -> Agent:
    """Agent that produces memory update deltas."""
    return Agent(
        name="MemoryUpdateAgent",
        instructions=MEMORY_UPDATE_INSTRUCTIONS,
        model=_get_model(),
        output_type=str,
    )
