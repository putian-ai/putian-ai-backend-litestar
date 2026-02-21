# Todo Backend with OpenAI Agents SDK Integration

A powerful todo management backend built with Litestar, featuring integrated AI agents powered by the OpenAI Agents SDK for intelligent task management and persistent conversation sessions.

## OpenAI Agents SDK Integration

This project includes comprehensive integration with the OpenAI Agents SDK, providing persistent conversation sessions for AI-powered todo management.

### Key Features

- 🔒 **User Isolation** - Sessions are properly scoped to users with security
- 📝 **Persistent History** - Conversations survive application restarts  
- 🔧 **Tool Support** - Full support for tool calls and metadata
- 🚀 **Performance** - Optimized queries with proper indexing
- 🧪 **Tested** - Comprehensive test coverage for reliability
- 📚 **Documented** - Complete usage examples and best practices

### Usage Examples

#### Using TodoAgentSessionService

```python
from app.domain.todo.todo_agents import TodoAgentSessionService

# Create the service (typically done via dependency injection)
service = TodoAgentSessionService(
    db_session=db_session,
    todo_service=todo_service,
    tag_service=tag_service,
)

# Chat with the agent - conversation history is persistent!
response = await service.chat_with_agent(
    session_id="user_123_todo",
    user_id="user_123",
    message="Create a todo for buying groceries tomorrow at 2 PM",
)

# Follow-up message - agent remembers previous context
response = await service.chat_with_agent(
    session_id="user_123_todo", 
    user_id="user_123",
    message="What time is that todo scheduled for?"
)
# Agent responds: "The grocery shopping todo is scheduled for 2 PM tomorrow."
```

#### Direct Session Usage with OpenAI Agents SDK

```python
from agents import Runner
from app.domain.todo.todo_agents import create_todo_agent_session, get_todo_agent, set_agent_context

# Set agent context for this user
set_agent_context(todo_service, tag_service, UUID(user_id))

# Create a database session for persistent conversation history
session = create_todo_agent_session(
    session_id=f"user_{user_id}_todo_assistant",
    user_id=user_id,
    db_session=db_session,
    todo_service=todo_service,
    tag_service=tag_service,
    session_name="Todo Management Chat",
)

# Get the todo agent
agent = get_todo_agent()

# Use with OpenAI Agents SDK - conversation history is persistent!
result = await Runner.run(
    agent,
    "Create a todo item for grocery shopping tomorrow",
    session=session
)

# Subsequent calls remember previous context
result = await Runner.run(
    agent,
    "What time is it scheduled for?",
    session=session
)
```

### Integration Benefits

The OpenAI Agents SDK integration provides several key advantages:

1. **Persistent Conversation Memory**: Unlike stateless API calls, the agent remembers previous interactions within the same session
2. **User-Scoped Sessions**: Each user has isolated conversation histories for privacy and security
3. **Tool Integration**: Seamless integration with todo management tools (create, update, delete, schedule)
4. **Intelligent Scheduling**: The agent can automatically find optimal time slots and prevent scheduling conflicts
5. **Database-Backed Storage**: Conversation history is stored in the database and survives application restarts

### Documentation

- **[Agent Tool Implementation](AGENT_TOOLING.md)** - How tools are organized across CRUD, scheduling, and supporting agents
- **[AGENTS.md](AGENTS.md)** - Collaboration and contribution guidelines for the todo agents
- **[Agent Tools Architecture Guide](docs/AGENT_TOOLS_ARCHITECTURE_GUIDE.md)** - Tool modules, agent variants, and API routing via `agent_name`
- **[Google Calendar Sync Development](docs/GOOGLE_CALENDAR_SYNC_DEVELOPMENT.md)** - Google OAuth、双向同步、最小联调与排障指南

### Implementation Details

The integration includes:

- **Database Models**: `AgentSession` and `SessionMessage` for storing conversation history
- **DatabaseSession Class**: Custom session implementation following OpenAI Agents SDK protocol
- **TodoAgentSessionService**: High-level service for managing todo agent conversations
- **Enhanced Todo Agent**: Existing todo agent with session support and conflict detection

## Todo Management Features

The application provides comprehensive todo management capabilities through both REST API and intelligent agent interfaces:

- ✅ Create, read, update, delete todos
- 📅 Intelligent scheduling with conflict detection
- 🏷️ Tag management and categorization
- ⭐ Priority levels and importance tracking
- 🕒 Timezone-aware date/time handling
- 🤖 AI-powered task management through conversational interface

## Getting Started

1. **Install Dependencies**
   ```bash
   uv install
   ```

2. **Set Up Database**
   ```bash
   uv run app database upgrade
   ```

3. **Configure Environment**
   Set up your environment variables for AI integration (see OpenAI Agents Integration Guide)

4. **Run the Application**
   ```bash
   uv run app run
   ```

## Architecture

The application follows a clean architecture pattern with:

- **Domain Layer**: Business logic and entities (`src/app/domain/`)
- **Infrastructure Layer**: Database models and external services (`src/app/db/`)
- **Application Layer**: API controllers and services (`src/app/server/`)
- **AI Integration**: OpenAI Agents SDK integration (`src/app/lib/database_session.py`)

## License

MIT License
