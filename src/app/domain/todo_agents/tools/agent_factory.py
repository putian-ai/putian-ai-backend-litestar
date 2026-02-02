"""Agent factory for creating todo agents.

This module contains the factory function for creating a configured
todo agent with all necessary tools and configurations.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING, cast

from agents import Agent
from agents.extensions.models.litellm_model import LitellmModel
from app.config import get_settings

from .system_instructions import (
    ORCHESTRATOR_SYSTEM_INSTRUCTIONS,
    TODO_SCHEDULE_INSTRUCTIONS,
    TODO_SUPPORT_INSTRUCTIONS,
    TODO_SYSTEM_INSTRUCTIONS,
)
from .tool_definitions import (
    get_crud_tool_definitions,
    get_schedule_tool_definitions,
    get_support_tool_definitions,
    get_tool_definitions,
    get_universal_tool_definitions,
)

if TYPE_CHECKING:
    from agents import Tool

__all__ = [
    "get_agent_by_name",
    "get_orchestrator_agent",
    "get_todo_agent",
    "get_todo_schedule_agent",
    "get_todo_support_agent",
]


def _get_model() -> Any:
    """Get the configured LiteLLM model instance."""
    settings = get_settings()

    return LitellmModel(
        model="deepseek/deepseek-chat",
        api_key=settings.ai.DEEPSEEK_API_KEY,
        base_url=settings.ai.DEEPSEEK_BASE_URL,
    )


def _build_agent(
    name: str,
    tools: list["Tool"],
    instructions: str = TODO_SYSTEM_INSTRUCTIONS,
    handoff_description: str | None = None,
) -> "Agent":
    return Agent(
        name=name,
        instructions=instructions,
        model=_get_model(),
        tools=tools,
        handoff_description=handoff_description,
    )


def get_todo_agent() -> "Agent":
    """Create and return a configured todo agent with LiteLLM."""
    tools = cast("list[Tool]", list(get_tool_definitions()))
    return _build_agent("TodoAssistant", tools)


def get_todo_schedule_agent() -> "Agent":
    """Create a scheduling/search todo agent."""
    tools = cast("list[Tool]", list(get_schedule_tool_definitions()))
    return _build_agent(
        "TodoScheduleAssistant",
        tools,
        instructions=TODO_SCHEDULE_INSTRUCTIONS,
        handoff_description="Specialist for listing todos, analyzing schedules, and finding optimal time slots",
    )


def get_todo_support_agent() -> "Agent":
    """Create a support/auxiliary todo agent (quota and future helpers)."""
    tools = cast("list[Tool]", list(get_support_tool_definitions()))
    return _build_agent(
        "TodoSupportAssistant",
        tools,
        instructions=TODO_SUPPORT_INSTRUCTIONS,
        handoff_description="Specialist for quota information and user account status",
    )


def get_orchestrator_agent() -> "Agent":
    """Create an orchestrator agent that delegates to specialized sub-agents.

    This agent uses the agents-as-tools pattern, where each sub-agent is exposed
    as a tool that the orchestrator can call to handle specific types of requests.
    """
    # Create sub-agents
    schedule_agent = get_todo_schedule_agent()
    support_agent = get_todo_support_agent()

    # Convert sub-agents to tools
    orchestrator_tools = [
        schedule_agent.as_tool(
            tool_name="delegate_to_schedule_assistant",
            tool_description=(
                "Delegate to the schedule assistant for listing todos, analyzing schedules, "
                "finding free time slots, or automatically scheduling todos. Use this tool when "
                "the user wants to view their todos, find optimal times, or resolve scheduling conflicts."
            ),
        ),
        support_agent.as_tool(
            tool_name="delegate_to_support_assistant",
            tool_description=(
                "Delegate to the support assistant for quota information and account status. "
                "Use this tool when the user asks about their usage limits, remaining quota, "
                "or account-related questions."
            ),
        ),
    ]

    orchestrator_tools.extend(get_crud_tool_definitions(include_universal=False))
    orchestrator_tools.extend(get_universal_tool_definitions())

    return Agent(
        name="TodoOrchestratorAgent",
        instructions=ORCHESTRATOR_SYSTEM_INSTRUCTIONS,
        model=_get_model(),
        tools=orchestrator_tools,
    )


def get_todo_crud_agent() -> "Agent":
    """Deprecated shim: CRUD sub-agent removed; use get_orchestrator_agent instead."""
    return get_orchestrator_agent()


def get_agent_by_name(name: str) -> "Agent":
    """Create an agent instance by name, falling back to the default."""
    builders = {
        "TodoAssistant": get_todo_agent,
        "TodoScheduleAssistant": get_todo_schedule_agent,
        "TodoSupportAssistant": get_todo_support_agent,
        "TodoOrchestratorAgent": get_orchestrator_agent,
    }

    builder = builders.get(name) or get_todo_agent
    return builder()
