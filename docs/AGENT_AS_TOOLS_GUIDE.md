# Agent-as-Tools Architecture Guide

This document describes the implementation of **Agents as Tools** in the Putian AI Todo Backend. The architecture enables specialized AI agents to handle specific domains of functionality, improving response quality and maintainability.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Agent Types](#agent-types)
- [Tool Module Organization](#tool-module-organization)
- [Usage Examples](#usage-examples)
- [Implementation Details](#implementation-details)
- [Creating New Agents](#creating-new-agents)
- [Best Practices](#best-practices)
- [API Reference](#api-reference)

---

## Overview

The Agent-as-Tools pattern allows us to:

1. **Specialize agents** for specific tasks (CRUD, scheduling, utilities)
2. **Improve response quality** by focusing each agent on its domain expertise
3. **Maintain clean separation** of concerns between different tool types
4. **Enable agent composition** where a main agent can delegate to specialized sub-agents

### Key Benefits

- **Better tool selection**: Each agent only sees tools relevant to its task
- **Improved context management**: Smaller, focused contexts lead to better responses
- **Easier testing**: Each agent's tools can be tested in isolation
- **Scalable architecture**: New agents and tools can be added without affecting existing ones

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Application / API Layer                        │
└───────────────────────────────┬───────────────────────────────────┘
                                │
                                │ Select agent based on task
                                │
        ┌───────────────────────┼───────────────────────┬───────────────────────┐
        │                       │                       │                       │
        ▼                       ▼                       ▼                       ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│ TodoAssistant │      │   CRUDAgent   │      │  Scheduling   │      │   Utility     │
│   (Main)      │      │               │      │    Agent      │      │    Agent      │
├───────────────┤      ├───────────────┤      ├───────────────┤      ├───────────────┤
│ ALL TOOLS     │      │ • create_todo │      │ • search_todos│      │ • get_todo_   │
│               │      │ • update_todo │      │ • analyze_    │      │     list      │
│ • datetime    │      │ • delete_todo │      │     schedule  │      │ • get_user_   │
│ • quota       │      │ • datetime    │      │ • schedule_   │      │     quota     │
│ • CRUD        │      │               │      │     todo      │      │ • datetime    │
│ • scheduling  │      │               │      │ • batch_update│      │               │
│ • utility     │      │               │      │ • datetime    │      │               │
└───────────────┘      └───────────────┘      └───────────────┘      └───────────────┘
```

### File Structure

```
src/app/domain/todo_agents/tools/
├── __init__.py              # Module exports (agents + tools)
├── agent_factory.py         # Agent creation functions
├── argument_models.py       # Pydantic models for tool arguments
├── tool_context.py          # Global context for services and user info
├── tool_definitions.py      # FunctionTool definitions for all agents
├── system_instructions.py   # System prompts for all agents
├── universal_tools.py       # Tools shared across all agents
│
├── crud_tools.py            # CRUD Agent tools (create, update, delete)
├── scheduling_tools.py      # Scheduling Agent tools (search, schedule)
└── utility_tools.py         # Utility Agent tools (list, quota)
```

---

## Agent Types

### 1. TodoAssistant (Main Agent)

**Factory Function**: `get_todo_agent()`

**Purpose**: Full-featured agent with all capabilities.

**Tools**: All tools from all agents combined.

**Use Cases**:
- General todo management
- When task type is unknown
- Complex operations spanning multiple domains

```python
from app.domain.todo_agents.tools import get_todo_agent

agent = get_todo_agent()
```

### 2. CRUD Agent

**Factory Function**: `get_crud_agent()`

**Purpose**: Handle Create, Read, Update, Delete operations on todo items.

**Tools**:
| Tool | Description |
|------|-------------|
| `get_user_datetime` | Get current time context |
| `create_todo` | Create a new todo with validation and conflict checking |
| `update_todo` | Update existing todo fields with time validation |
| `delete_todo` | Delete a todo by ID after ownership verification |

**Use Cases**:
- "Add a new task called 'Buy groceries' for tomorrow at 3pm"
- "Update my meeting to be high importance"
- "Delete the task with ID xxx"

```python
from app.domain.todo_agents.tools import get_crud_agent

agent = get_crud_agent()
```

### 3. Scheduling Agent

**Factory Function**: `get_scheduling_agent()`

**Purpose**: Handle scheduling operations, time slot analysis, and conflict resolution.

**Tools**:
| Tool | Description |
|------|-------------|
| `get_user_datetime` | Get current time context |
| `search_todos` | Search todos by text, importance, or date range |
| `analyze_schedule` | Analyze schedule for free time slots |
| `schedule_todo` | Intelligently schedule a todo based on preferences |
| `batch_update_schedule` | Apply multiple schedule changes at once |

**Use Cases**:
- "Find all high-priority tasks this week"
- "When am I free tomorrow afternoon?"
- "Schedule a 2-hour study session sometime today"
- "Reschedule all my afternoon meetings to morning"

```python
from app.domain.todo_agents.tools import get_scheduling_agent

agent = get_scheduling_agent()
```

### 4. Utility Agent

**Factory Function**: `get_utility_agent()`

**Purpose**: Provide informational queries and utility operations.

**Tools**:
| Tool | Description |
|------|-------------|
| `get_user_datetime` | Get current time context |
| `get_todo_list` | List todos with filtering options |
| `get_user_quota` | Get agent usage quota information |

**Use Cases**:
- "Show me all my tasks"
- "List high-priority tasks from last week"
- "How many agent requests do I have left?"

```python
from app.domain.todo_agents.tools import get_utility_agent

agent = get_utility_agent()
```

---

## Usage Examples

### Using the Main Agent

```python
from app.domain.todo_agents.tools import get_todo_agent, set_agent_context
from agents import Runner

# Set up context
set_agent_context(
    todo_service=todo_service,
    tag_service=tag_service,
    user_id=current_user.id,
    quota_service=quota_service,
    rate_limit_service=rate_limit_service,
)

# Create and run agent
agent = get_todo_agent()
result = await Runner.run(agent, "Create a meeting for tomorrow at 2pm")
```

### Using Specialized Agents

```python
from app.domain.todo_agents.tools import (
    get_crud_agent,
    get_scheduling_agent,
    get_utility_agent,
)

# For CRUD operations
crud_agent = get_crud_agent()
result = await Runner.run(crud_agent, "Delete my morning task")

# For scheduling
scheduling_agent = get_scheduling_agent()
result = await Runner.run(scheduling_agent, "Find free time slots this week")

# For information queries
utility_agent = get_utility_agent()
result = await Runner.run(utility_agent, "Show me my tasks for today")
```

### Agent Routing

```python
def route_to_agent(user_message: str):
    """Route user message to appropriate specialized agent."""
    message_lower = user_message.lower()
    
    # Scheduling keywords
    if any(word in message_lower for word in ["schedule", "when", "free", "available", "analyze"]):
        return get_scheduling_agent()
    
    # CRUD keywords
    if any(word in message_lower for word in ["create", "add", "delete", "remove", "update", "change"]):
        return get_crud_agent()
    
    # Utility keywords
    if any(word in message_lower for word in ["list", "show", "quota", "how many"]):
        return get_utility_agent()
    
    # Default to main agent
    return get_todo_agent()
```

---

## Tool Module Organization

### CRUD Tools (`crud_tools.py`)

```python
"""CRUD tool implementations for todo agent.

Agent Role: Todo Management Agent
- Create new todo items with validation
- Update existing todo items
- Delete todo items
"""

# Key functions:
async def create_todo_impl(ctx: RunContextWrapper, args: str) -> str:
    """Creates a todo with time validation and conflict checking."""

async def update_todo_impl(ctx: RunContextWrapper, args: str) -> str:
    """Updates todo fields with validation."""

async def delete_todo_impl(ctx: RunContextWrapper, args: str) -> str:
    """Deletes a todo after ownership verification."""
```

### Scheduling Tools (`scheduling_tools.py`)

```python
"""Scheduling tool implementations for todo agent.

Agent Role: Scheduling Agent
- Find available time slots
- Analyze daily/weekly schedules
- Intelligently schedule new tasks
- Resolve scheduling conflicts
"""

# Key functions:
async def search_todos_impl(ctx: RunContextWrapper, args: str) -> str:
    """Search todos by query, importance, or date range."""

async def analyze_schedule_impl(ctx: RunContextWrapper, args: str) -> str:
    """Analyze schedule for free time slots."""

async def schedule_todo_impl(ctx: RunContextWrapper, args: str) -> str:
    """Find optimal time slot and create todo."""

async def batch_update_schedule_impl(ctx: RunContextWrapper, args: str) -> str:
    """Apply multiple schedule updates."""
```

### Utility Tools (`utility_tools.py`)

```python
"""Utility tool implementations for todo agent.

Agent Role: Utility Agent
- List and filter todos
- Provide user quota and usage information
"""

# Key functions:
async def get_todo_list_impl(ctx: RunContextWrapper, args: str) -> str:
    """List todos with optional filters."""

async def get_user_quota_impl(ctx: RunContextWrapper, args: str) -> str:
    """Get user's agent usage quota."""
```

---

## Implementation Details

### Tool Context (`tool_context.py`)

The tool context provides access to services and user information:

```python
from app.domain.todo_agents.tools.tool_context import (
    set_agent_context,
    get_todo_service,
    get_tag_service,
    get_current_user_id,
    get_quota_service,
    get_rate_limit_service,
)

# Set context before running agent
set_agent_context(
    todo_service=todo_service,
    tag_service=tag_service,
    user_id=current_user.id,
    quota_service=quota_service,
    rate_limit_service=rate_limit_service,
)
```

### Argument Models (`argument_models.py`)

All tool arguments use Pydantic models for validation:

```python
class CreateTodoArgs(BaseModel):
    item: str = Field(..., description="The name/title of the todo")
    description: str | None = Field(default=None)
    start_time: str = Field(..., description="Start time in YYYY-MM-DD HH:MM:SS")
    end_time: str = Field(..., description="End time in YYYY-MM-DD HH:MM:SS")
    tags: list[str] | None = Field(default=None)
    importance: str = Field(default="none")
    timezone: str | None = Field(default=None)
```

### Tool Definitions (`tool_definitions.py`)

Tools are registered using the OpenAI Agents SDK:

```python
from agents import FunctionTool

def get_tool_definitions() -> Sequence[FunctionTool]:
    create_todo_tool = FunctionTool(
        name="create_todo",
        description="Create a new todo item using the TodoService.",
        params_json_schema=CreateTodoArgs.model_json_schema(),
        on_invoke_tool=create_todo_impl,
    )
    # ... more tools
    return [create_todo_tool, ...]
```

---

## Creating New Agents

### Step 1: Define Argument Models

Add new argument models to `argument_models.py`:

```python
class MyNewToolArgs(BaseModel):
    param1: str = Field(..., description="Description of param1")
    param2: int = Field(default=10, description="Optional param2")
```

### Step 2: Implement Tool Functions

Create a new file or add to existing module:

```python
# my_agent_tools.py
async def my_new_tool_impl(ctx: RunContextWrapper, args: str) -> str:
    """Implementation of my new tool."""
    service = get_todo_service()
    user_id = get_current_user_id()
    
    parsed = MyNewToolArgs.model_validate_json(args)
    
    # Tool logic here
    
    return "Result message"
```

### Step 3: Register Tool Definition

Add to `tool_definitions.py`:

```python
from .my_agent_tools import my_new_tool_impl

my_new_tool = FunctionTool(
    name="my_new_tool",
    description="What this tool does",
    params_json_schema=MyNewToolArgs.model_json_schema(),
    on_invoke_tool=my_new_tool_impl,
)
```

### Step 4: Update Exports

Add exports to `__init__.py`:

```python
from .my_agent_tools import my_new_tool_impl

__all__ = [
    # ... existing exports
    "my_new_tool_impl",
]
```

---

## Best Practices

### 1. Tool Function Design

```python
async def good_tool_impl(ctx: RunContextWrapper, args: str) -> str:
    """Clear docstring explaining the tool.
    
    Args:
        ctx: The runtime context wrapper
        args: JSON string containing tool arguments
        
    Returns:
        Human-readable result message
    """
    # 1. Get services and validate context
    service = get_todo_service()
    user_id = get_current_user_id()
    if not service or not user_id:
        return "Error: Agent context not properly initialized"
    
    # 2. Parse and validate arguments
    try:
        parsed = MyArgs.model_validate_json(args)
    except ValueError as e:
        return f"Error: Invalid arguments: {e}"
    
    # 3. Execute business logic with proper error handling
    try:
        result = await service.do_something(parsed.param)
        return f"Successfully completed: {result}"
    except Exception as e:
        return f"Error: {e!s}"
```

### 2. Error Messages

- Use clear, user-friendly error messages
- Include context about what went wrong
- Suggest next steps when appropriate

```python
# Good
return "❌ Time conflict detected! The requested time slot conflicts with:\n• Meeting (14:00-15:00)\n\nTry scheduling for 15:30 instead."

# Avoid
return "Error: Conflict"
```

### 3. Timezone Handling

Always handle timezones explicitly:

```python
from zoneinfo import ZoneInfo
from datetime import UTC

user_tz = ZoneInfo(parsed.timezone) if parsed.timezone else ZoneInfo("UTC")
utc_time = local_time.astimezone(UTC)  # Store in UTC
display_time = utc_time.astimezone(user_tz)  # Display in user's timezone
```

### 4. Validation

- Validate ownership before operations
- Check time conflicts before creating/updating
- Validate importance levels and other enums

```python
todo = await service.get(todo_id)
if not todo:
    return "Todo not found"
if todo.user_id != current_user_id:
    return "You don't have permission to modify this todo"
```

---

## API Reference

### Tool Context Functions

| Function | Returns | Description |
|----------|---------|-------------|
| `set_agent_context(...)` | `None` | Initialize context for tool execution |
| `get_todo_service()` | `TodoService \| None` | Get todo service instance |
| `get_tag_service()` | `TagService \| None` | Get tag service instance |
| `get_current_user_id()` | `UUID \| None` | Get current user's ID |
| `get_quota_service()` | `UserUsageQuotaService \| None` | Get quota service |
| `get_rate_limit_service()` | `RateLimitService \| None` | Get rate limit service |

### Argument Models

| Model | Tool | Key Fields |
|-------|------|------------|
| `CreateTodoArgs` | `create_todo` | `item`, `start_time`, `end_time`, `tags` |
| `UpdateTodoArgs` | `update_todo` | `todo_id`, all fields optional |
| `DeleteTodoArgs` | `delete_todo` | `todo_id` |
| `GetTodoListArgs` | `get_todo_list` | `limit`, `from_date`, `to_date`, `importance` |
| `SearchTodoArgs` | `search_todos` | `query`, `importance`, date range |
| `AnalyzeScheduleArgs` | `analyze_schedule` | `target_date`, `include_days` |
| `ScheduleTodoArgs` | `schedule_todo` | `item`, `duration_minutes`, `preferred_time_of_day` |
| `BatchUpdateScheduleArgs` | `batch_update_schedule` | `updates`, `confirm` |
| `GetUserDatetimeArgs` | `get_user_datetime` | `timezone` |
| `GetUserQuotaArgs` | `get_user_quota` | `include_details` |

---

## Migration from Single-File Implementation

The tools have been migrated from a single `tool_implementations.py` to specialized modules. For backward compatibility, the old module now re-exports all implementations:

```python
# Old import (still works)
from app.domain.todo_agents.tools.tool_implementations import create_todo_impl

# New recommended import
from app.domain.todo_agents.tools.crud_tools import create_todo_impl
```

---

## Related Documentation

- [OpenAI Agents Integration Guide](./OPENAI_AGENTS_INTEGRATION.md)
- [Agent Tools Architecture Guide](./AGENT_TOOLS_ARCHITECTURE_GUIDE.md)
- [SQLite Session Migration](../SQLITE_SESSION_MIGRATION.md)

---

*Last updated: November 2025*
