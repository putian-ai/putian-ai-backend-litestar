"""Agent factory for creating todo agents.

This module contains factory functions for creating configured
todo agents with all necessary tools and configurations.

Agent Types:
- TodoAssistant: Main agent with all tools (original)
- CRUDAgent: Specialized for create, update, delete operations
- SchedulingAgent: Specialized for scheduling and time management
- UtilityAgent: Specialized for listing and information queries
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from app.config import get_settings

from .system_instructions import (
    CRUD_AGENT_INSTRUCTIONS,
    SCHEDULING_AGENT_INSTRUCTIONS,
    TODO_SYSTEM_INSTRUCTIONS,
    UTILITY_AGENT_INSTRUCTIONS,
)
from .tool_definitions import (
    get_crud_tool_definitions,
    get_scheduling_tool_definitions,
    get_tool_definitions,
    get_utility_tool_definitions,
)

if TYPE_CHECKING:
    from agents import Agent, Tool

__all__ = [
    "AGENT_TYPES",
    "get_agent_by_type",
    "get_crud_agent",
    "get_scheduling_agent",
    "get_todo_agent",
    "get_utility_agent",
]

# Valid agent type names
AGENT_TYPES = frozenset({"TodoAssistant", "CRUDAgent",
                        "SchedulingAgent", "UtilityAgent"})


def _create_agent(name: str, instructions: str, tools: list) -> Agent:
    """Create an agent with the specified configuration.

    Args:
        name: The name of the agent
        instructions: System instructions for the agent
        tools: List of tools available to the agent

    Returns:
        Configured Agent instance
    """
    from agents import Agent
    from agents.extensions.models.litellm_model import LitellmModel

    settings = get_settings()

    model = LitellmModel(
        model="openai/glm-4.5",
        api_key=settings.ai.GLM_API_KEY,
        base_url=settings.ai.GLM_BASE_URL,
    )

    return Agent(
        name=name,
        instructions=instructions,
        model=model,
        tools=tools,
    )


def get_todo_agent() -> Agent:
    """Create and return a configured todo agent with all tools.

    This is the main agent with full capabilities including:
    - CRUD operations (create, update, delete)
    - Scheduling (analyze, schedule, batch update)
    - Utility (list todos, quota info)
    - Universal tools (datetime)

    Returns:
        Agent: Configured TodoAssistant agent
    """
    tools = cast("list[Tool]", list(get_tool_definitions()))
    return _create_agent(
        name="TodoAssistant",
        instructions=TODO_SYSTEM_INSTRUCTIONS,
        tools=tools,
    )


def get_crud_agent() -> Agent:
    """Create and return a CRUD-specialized agent.

    This agent focuses on Create, Read, Update, Delete operations:
    - Create new todos with validation
    - Update existing todos
    - Delete todos
    - Get current datetime (for context)

    Returns:
        Agent: Configured CRUDAgent
    """
    tools = cast("list[Tool]", list(get_crud_tool_definitions()))
    return _create_agent(
        name="CRUDAgent",
        instructions=CRUD_AGENT_INSTRUCTIONS,
        tools=tools,
    )


def get_scheduling_agent() -> Agent:
    """Create and return a scheduling-specialized agent.

    This agent focuses on schedule management:
    - Search todos
    - Analyze schedules for free time slots
    - Intelligently schedule new todos
    - Batch update schedules
    - Get current datetime (for context)

    Returns:
        Agent: Configured SchedulingAgent
    """
    tools = cast("list[Tool]", list(get_scheduling_tool_definitions()))
    return _create_agent(
        name="SchedulingAgent",
        instructions=SCHEDULING_AGENT_INSTRUCTIONS,
        tools=tools,
    )


def get_utility_agent() -> Agent:
    """Create and return a utility-specialized agent.

    This agent focuses on information queries:
    - List todos with filters
    - Get user quota information
    - Get current datetime

    Returns:
        Agent: Configured UtilityAgent
    """
    tools = cast("list[Tool]", list(get_utility_tool_definitions()))
    return _create_agent(
        name="UtilityAgent",
        instructions=UTILITY_AGENT_INSTRUCTIONS,
        tools=tools,
    )


def get_agent_by_type(agent_type: str = "TodoAssistant") -> Agent:
    """Get an agent by its type name.

    Args:
        agent_type: The type of agent to create. Valid values:
            - "TodoAssistant" (default): Full-featured agent with all tools
            - "CRUDAgent": Specialized for create, update, delete operations
            - "SchedulingAgent": Specialized for scheduling and time management
            - "UtilityAgent": Specialized for listing and information queries

    Returns:
        Agent: The configured agent instance

    Raises:
        ValueError: If agent_type is not a valid agent type
    """
    agent_factories = {
        "TodoAssistant": get_todo_agent,
        "CRUDAgent": get_crud_agent,
        "SchedulingAgent": get_scheduling_agent,
        "UtilityAgent": get_utility_agent,
    }

    if agent_type not in agent_factories:
        valid_types = ", ".join(sorted(agent_factories.keys()))
        msg = f"Invalid agent_type '{agent_type}'. Valid types: {valid_types}"
        raise ValueError(msg)

    return agent_factories[agent_type]()
