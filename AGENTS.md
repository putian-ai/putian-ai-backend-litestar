# Repository Guidelines

This guide outlines how to collaborate on the Litestar todo backend with OpenAI Agents support. Keep it close while you explore the codebase.

## Project Structure & Module Organization
- Core services live in `src/app`: domain logic under `src/app/domain`, persistence in `src/app/db`, shared helpers in `src/app/lib`, and HTTP wiring in `src/app/server`.
- Agents sit in `src/app/domain/todo_agents` (CLI deps, controllers, services, and `tools/` implementations) and persist history through `src/app/domain/agent_sessions` plus `app/lib/database_session.py`.
- Tests mirror runtime modules: fast unit suites in `tests/unit`, API and agent flows in `tests/integration`, with fixtures in `tests/data_fixtures.py` and `tests/conftest.py`.
- Supporting assets include Docker and infra scripts in `deploy/`, docs in `docs/`, and runnable examples under `examples/`.
- Electron front-end lives in `electron-frontend/` (Vite Electron Builder scaffold), with its own `package.json`, tests, and README.

## Build, Test, and Development Commands
- `uv install` (or `make install`) provisions Python 3.13, dev extras, Node tooling, and pre-commit hooks.
- `make dev` runs the API with reload and correct `APP_ENV`; `make run` mirrors production flags; use `make start-infra` to boot local Postgres/Redis if your feature needs them.
- `uv run app run` launches the ASGI app directly; `uv run app database upgrade` applies migrations defined under `src/app/db/migrations`.
- Quality gates live in the Makefile: `make lint` (pre-commit, mypy, pyright, slotscheck), `make test` (pytest xdist), and `make coverage` (pytest + coverage HTML/XML).
- Electron front-end tooling is isolated under `electron-frontend/`; follow `electron-frontend/README.md` for `npm start`, `npm run compile`, and test workflows.

## Coding Style & Naming Conventions
- Python uses 4-space indentation, full type hints, and Ruff-enforced 120-column lines; match snake_case functions, PascalCase classes, and SCREAMING_SNAKE constants.
- Keep domain boundaries clear: controllers stay thin, services own business rules, SQLAlchemy models stay in `app/db/models`, and tools call services via the `tool_context` helpers.
- Run `uv run pre-commit run --all-files` before commits so Ruff, formatting, and static analysis stay green; only add comments when they clarify tricky logic.

## Testing Guidelines
- Default to `uv run pytest tests -n 2 --quiet`; integration suites rely on database fixtures, so ensure local infra matches `tests/conftest.py` expectations.
- Use `make coverage` when adding sizable features; maintain existing coverage thresholds and add regression cases near the logic being changed.
- Follow descriptive test names (`test_<behavior>`) and stage agent streaming or quota scenarios under `tests/integration/test_todo.py` or the matching service test module.

## Commit & Pull Request Guidelines
- Follow Conventional Commits (`feat:`, `fix:`, `refactor:`) aligned with `tool.git-cliff`; keep subjects ≤72 chars and expand in bodies when touching multiple subsystems.
- Verify `make lint` and `make test` before opening a PR, document manual verification steps, and link to relevant guides (`docs/OPENAI_AGENTS_INTEGRATION.md`, `docs/AGENT_TOOLS_ARCHITECTURE_GUIDE.md`).
- Update docs when introducing new tools or session behaviors, and note any schema tweaks alongside the Alembic migration ID.

## Agent & Session Architecture
- `TodoAgentService` orchestrates quota-checked chat, streaming via `Runner.run_streamed`, and session caching built on the Agents SDK `SQLiteSession` wrapper.
- Tool calls route through `src/app/domain/todo_agents/tools`, with argument models validating payloads, `tool_context` injecting services, and implementations ensuring conflict checking and tag management.
- Persistent history uses `AgentSessionService` and `SessionMessageService` backed by SQLAlchemy models (`app/db/models/agent_session.py`, `session_message.py`) or the lightweight SQLite fallback; keep business rules inside services and expose them via controllers.

## Security & Configuration Tips
- Do not commit secrets: configure OpenAI keys, GitHub OAuth, and database URLs via `.env` (see `src/app/config/base.py` and `docs/OPENAI_AGENTS_INTEGRATION.md`).
- CORS/CSRF defaults live in `src/app/config/app.py`; adjust there rather than ad-hoc middleware.
- Rate limiting and monthly quotas originate from `app/lib/rate_limit_service.py` and `app/domain/quota/services.py`; honor these when creating new entry points or background jobs.
