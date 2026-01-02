"""Services for memory agents."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from agents import Runner

from app.config import get_settings

from .agent_factory import get_memory_context_agent, get_memory_update_agent
from .schemas import MemoryContextResult, MemoryUpdateResult
from .services import MemoryService

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.db.models import Memory

__all__ = ["MemoryAgentService", "create_memory_agent_service"]

logger = structlog.get_logger()


class MemoryAgentService:
    """Orchestrates memory context generation and updates."""

    def __init__(self, memory_service: MemoryService) -> None:
        self.memory_service = memory_service

    async def build_memory_context(
        self,
        user_id: UUID,
        user_message: str,
    ) -> MemoryContextResult | None:
        settings = get_settings()
        if not settings.ai.MEMORY_ENABLED:
            return None

        bullets = await self._load_memory_bullets(user_id, settings.ai.MEMORY_MAX_BULLETS)
        if not bullets:
            return None

        payload = _format_context_input(user_message, bullets)
        agent = get_memory_context_agent()

        try:
            result = await Runner.run(agent, payload, max_turns=5)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Memory context generation failed", error=str(exc))
            return None

        output = result.final_output
        if isinstance(output, MemoryContextResult) and output.context.strip():
            return output
        return None

    async def update_memory_after_response(
        self,
        user_id: UUID,
        user_message: str,
        agent_response: str,
    ) -> None:
        settings = get_settings()
        if not settings.ai.MEMORY_ENABLED:
            return

        bullets = await self._load_memory_bullets(user_id, settings.ai.MEMORY_MAX_BULLETS)
        payload = _format_update_input(user_message, agent_response, bullets)
        agent = get_memory_update_agent()

        try:
            result = await Runner.run(agent, payload, max_turns=5)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Memory update planning failed", error=str(exc))
            return

        output = result.final_output
        update_result: MemoryUpdateResult | None
        if isinstance(output, MemoryUpdateResult):
            update_result = output
        elif isinstance(output, str):
            update_result = _parse_memory_update_output(output)
        else:
            update_result = None
        if update_result and update_result.deltas:
            try:
                await self.memory_service.apply_memory_deltas(update_result.deltas, user_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Memory update apply failed", error=str(exc))

    async def _load_memory_bullets(
        self,
        user_id: UUID,
        limit: int,
    ) -> Sequence[Memory]:
        return await self.memory_service.list_effective_memory(user_id=user_id, limit=limit)


def _format_context_input(user_message: str, bullets: Sequence[Memory]) -> str:
    lines = [f"User message: {user_message}", "", "Memory bullets:"]
    for bullet in bullets:
        scope = "global" if bullet.is_global else "user"
        lines.append(
            f"- id={bullet.id} scope={scope} section={bullet.section} "
            f"helpful={bullet.helpful_count} harmful={bullet.harmful_count} content={bullet.content}"
        )
    return "\n".join(lines)


def _format_update_input(
    user_message: str,
    agent_response: str,
    bullets: Sequence[Memory],
) -> str:
    lines = [
        f"User message: {user_message}",
        f"Assistant response: {agent_response}",
        "",
        "Existing memory bullets:",
    ]
    for bullet in bullets:
        scope = "global" if bullet.is_global else "user"
        lines.append(
            f"- id={bullet.id} scope={scope} section={bullet.section} "
            f"helpful={bullet.helpful_count} harmful={bullet.harmful_count} content={bullet.content}"
        )
    return "\n".join(lines)


def _strip_code_fence(payload: str) -> str:
    cleaned = payload.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _parse_memory_update_output(payload: str) -> MemoryUpdateResult | None:
    cleaned = _strip_code_fence(payload)
    try:
        return MemoryUpdateResult.model_validate_json(cleaned)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Memory update output parse failed", error=str(exc))
        return None


def create_memory_agent_service(memory_service: MemoryService) -> MemoryAgentService:
    return MemoryAgentService(memory_service=memory_service)
