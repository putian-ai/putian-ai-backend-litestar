from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from litestar.exceptions import NotAuthorizedException
from litestar.middleware.authentication import AuthenticationResult

from app.domain.accounts import guards

if TYPE_CHECKING:
    from pytest import MonkeyPatch


class StubUserService:
    def __init__(self, user: Any | None) -> None:
        self.user = user
        self.last_lookup_id: UUID | None = None

    async def get_one_or_none(self, **kwargs: Any) -> Any | None:
        self.last_lookup_id = kwargs.get("id")
        return self.user


def _build_connection(*, headers: dict[str, str] | None = None, cookies: dict[str, str] | None = None) -> Any:
    return SimpleNamespace(
        headers=headers or {},
        cookies=cookies or {},
        app=SimpleNamespace(state=SimpleNamespace()),
        scope={},
    )


def _build_middleware() -> guards.DevJWTCookieAuthenticationMiddleware:
    middleware = guards.DevJWTCookieAuthenticationMiddleware.__new__(guards.DevJWTCookieAuthenticationMiddleware)
    middleware.auth_header = "Authorization"
    middleware.auth_cookie_key = "token"
    return middleware


@pytest.mark.anyio
async def test_get_dev_user_from_header_returns_none_when_header_missing() -> None:
    connection = _build_connection()

    result = await guards._get_dev_user_from_header(connection)

    assert result is None


@pytest.mark.anyio
async def test_get_dev_user_from_header_returns_none_when_header_invalid_uuid() -> None:
    connection = _build_connection(headers={guards.DEV_USER_ID_HEADER: "not-a-uuid"})

    result = await guards._get_dev_user_from_header(connection)

    assert result is None


@pytest.mark.anyio
async def test_get_dev_user_from_header_returns_active_verified_user(monkeypatch: MonkeyPatch) -> None:
    user = SimpleNamespace(id=UUID("5ef29f3c-3560-4d15-ba6b-a2e5c721e4d2"), is_active=True, is_verified=True)
    service = StubUserService(user=user)

    async def fake_provider(_: Any) -> Any:
        yield service

    monkeypatch.setattr(guards, "provide_users_service", fake_provider)
    monkeypatch.setattr(guards.alchemy, "provide_session", lambda _state, _scope: object())

    connection = _build_connection(headers={guards.DEV_USER_ID_HEADER: "5ef29f3c-3560-4d15-ba6b-a2e5c721e4d2"})

    result = await guards._get_dev_user_from_header(connection)

    assert result is user
    assert service.last_lookup_id == UUID("5ef29f3c-3560-4d15-ba6b-a2e5c721e4d2")


@pytest.mark.anyio
async def test_get_dev_user_from_header_rejects_inactive_or_unverified_user(monkeypatch: MonkeyPatch) -> None:
    user = SimpleNamespace(id=UUID("7ef29f3c-3560-4d15-ba6b-a2e5c721e4e1"), is_active=False, is_verified=True)
    service = StubUserService(user=user)

    async def fake_provider(_: Any) -> Any:
        yield service

    monkeypatch.setattr(guards, "provide_users_service", fake_provider)
    monkeypatch.setattr(guards.alchemy, "provide_session", lambda _state, _scope: object())

    connection = _build_connection(headers={guards.DEV_USER_ID_HEADER: "7ef29f3c-3560-4d15-ba6b-a2e5c721e4e1"})

    result = await guards._get_dev_user_from_header(connection)

    assert result is None


@pytest.mark.anyio
async def test_authenticate_request_uses_jwt_when_authorization_header_present(monkeypatch: MonkeyPatch) -> None:
    async def fake_super(self: Any, connection: Any) -> AuthenticationResult:
        return AuthenticationResult(user="jwt-user", auth="jwt-auth")

    monkeypatch.setattr(guards.JWTCookieAuthenticationMiddleware, "authenticate_request", fake_super)
    monkeypatch.setattr(guards.settings.app, "ENV", "development")

    middleware = _build_middleware()
    connection = _build_connection(headers={"Authorization": "Bearer token"})

    result = await middleware.authenticate_request(connection)

    assert result.user == "jwt-user"
    assert result.auth == "jwt-auth"


@pytest.mark.anyio
async def test_authenticate_request_uses_jwt_outside_development(monkeypatch: MonkeyPatch) -> None:
    async def fake_super(self: Any, connection: Any) -> AuthenticationResult:
        return AuthenticationResult(user="jwt-user", auth="jwt-auth")

    monkeypatch.setattr(guards.JWTCookieAuthenticationMiddleware, "authenticate_request", fake_super)
    monkeypatch.setattr(guards.settings.app, "ENV", "production")

    middleware = _build_middleware()
    connection = _build_connection(headers={guards.DEV_USER_ID_HEADER: "5ef29f3c-3560-4d15-ba6b-a2e5c721e4d2"})

    result = await middleware.authenticate_request(connection)

    assert result.user == "jwt-user"
    assert result.auth == "jwt-auth"


@pytest.mark.anyio
async def test_authenticate_request_returns_dev_user_when_header_valid(monkeypatch: MonkeyPatch) -> None:
    dev_user = SimpleNamespace(id="dev-user-id")

    async def fake_get_dev_user(connection: Any) -> Any:
        return dev_user

    monkeypatch.setattr(guards, "_get_dev_user_from_header", fake_get_dev_user)
    monkeypatch.setattr(guards.settings.app, "ENV", "development")

    middleware = _build_middleware()
    connection = _build_connection(headers={guards.DEV_USER_ID_HEADER: "5ef29f3c-3560-4d15-ba6b-a2e5c721e4d2"})

    result = await middleware.authenticate_request(connection)

    assert result.user == dev_user
    assert result.auth is None


@pytest.mark.anyio
async def test_authenticate_request_raises_401_when_dev_header_missing_or_invalid(monkeypatch: MonkeyPatch) -> None:
    async def fake_get_dev_user(connection: Any) -> Any:
        return None

    monkeypatch.setattr(guards, "_get_dev_user_from_header", fake_get_dev_user)
    monkeypatch.setattr(guards.settings.app, "ENV", "development")

    middleware = _build_middleware()
    connection = _build_connection()

    with pytest.raises(NotAuthorizedException):
        await middleware.authenticate_request(connection)
