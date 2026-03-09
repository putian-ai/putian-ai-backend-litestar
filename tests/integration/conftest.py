import os
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.utils.fixtures import open_fixture_async
from dotenv import dotenv_values
from httpx import AsyncClient
from litestar import Litestar
from litestar.testing import AsyncTestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import app as config
from app.config import get_settings
from app.db.models import User
from app.domain.accounts.guards import auth
from app.domain.accounts.services import RoleService, UserService

if TYPE_CHECKING:
    from pytest_databases.docker.postgres import PostgresService

here = Path(__file__).parent
pytestmark = pytest.mark.anyio


def _resolve_integration_database_url() -> str | None:
    """Resolve a Postgres URL for integration tests without docker fixture."""
    candidates = [
        os.getenv("INTEGRATION_DATABASE_URL"),
        os.getenv("TEST_DATABASE_URL"),
        dotenv_values(".env.testing").get("INTEGRATION_DATABASE_URL"),
        dotenv_values(".env.testing").get("TEST_DATABASE_URL"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        value = str(candidate).strip()
        if value.startswith("postgresql+asyncpg://"):
            return value
    return None


@pytest.fixture(name="engine")
async def fx_engine(request: pytest.FixtureRequest) -> AsyncEngine:
    """Postgresql instance for end-to-end testing.

    Returns:
        Async SQLAlchemy engine instance.
    """
    database_url = _resolve_integration_database_url()
    if database_url:
        return create_async_engine(
            database_url,
            echo=False,
            poolclass=NullPool,
        )

    postgres_service = request.getfixturevalue("postgres_service")
    postgres_service = cast("PostgresService", postgres_service)
    fallback_url = (
        f"postgresql+asyncpg://{postgres_service.user}:{postgres_service.password}"
        f"@{postgres_service.host}:{postgres_service.port}/{postgres_service.database}"
    )
    return create_async_engine(
        fallback_url,
        echo=False,
        poolclass=NullPool,
    )


@pytest.fixture(name="sessionmaker")
async def fx_session_maker_factory(engine: AsyncEngine) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    yield async_sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture(name="session")
async def fx_session(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncGenerator[AsyncSession, None]:
    async with sessionmaker() as session:
        yield session


@pytest.fixture(autouse=True)
async def _seed_db(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
    raw_users: list[User | dict[str, Any]],
) -> AsyncGenerator[None, None]:
    """Populate test database with.

    Args:
        engine: The SQLAlchemy engine instance.
        sessionmaker: The SQLAlchemy sessionmaker factory.
        raw_users: Test users to add to the database

    """

    settings = get_settings()
    fixtures_path = Path(settings.db.FIXTURE_PATH)
    metadata = UUIDAuditBase.registry.metadata
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
    async with RoleService.new(sessionmaker()) as service:
        fixture = await open_fixture_async(fixtures_path, "role")
        for obj in fixture:
            _ = await service.repository.get_or_upsert(match_fields="name", upsert=True, **obj)
        await service.repository.session.commit()
    async with UserService.new(sessionmaker()) as users_service:
        await users_service.create_many(raw_users, auto_commit=True)

    yield


@pytest.fixture(autouse=True)
def _patch_db(
    app: "Litestar",
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config.alchemy, "session_maker", sessionmaker)
    monkeypatch.setattr(config.alchemy, "engine_instance", engine)


@pytest.fixture(name="client")
async def fx_client(app: Litestar) -> AsyncIterator[AsyncClient]:
    """Async client that calls requests on the app.

    ```text
    ValueError: The future belongs to a different loop than the one specified as the loop argument
    ```
    """
    async with AsyncTestClient(app) as client:
        yield client


@pytest.fixture(name="superuser_token_headers")
def fx_superuser_token_headers() -> dict[str, str]:
    """Valid superuser token.

    ```text
    ValueError: The future belongs to a different loop than the one specified as the loop argument
    ```
    """
    return {"Authorization": f"Bearer {auth.create_token(identifier='superuser@example.com')}"}


@pytest.fixture(name="user_token_headers")
def fx_user_token_headers() -> dict[str, str]:
    """Valid user token.

    ```text
    ValueError: The future belongs to a different loop than the one specified as the loop argument
    ```
    """
    return {"Authorization": f"Bearer {auth.create_token(identifier='user@example.com')}"}
