from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from app.domain.accounts.controllers import access
from app.domain.accounts.controllers.access import AccessController
from app.domain.accounts.schemas import AccountRegister

pytestmark = pytest.mark.anyio


async def test_signup_skips_email_verification_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(access.settings.app, "ENV", "development")

    request = SimpleNamespace(
        base_url=SimpleNamespace(scheme="http", netloc="localhost:8089"),
        app=SimpleNamespace(emit=Mock()),
    )
    user = SimpleNamespace(id=UUID("97108ac1-ffcb-411d-8b1e-d9183399f63b"))
    users_service = SimpleNamespace(
        default_role="user",
        create=AsyncMock(return_value=user),
        send_verification_email=AsyncMock(),
        to_schema=Mock(return_value={"id": str(user.id), "isVerified": True}),
    )
    roles_service = SimpleNamespace(get_one_or_none=AsyncMock(return_value=SimpleNamespace(id=UUID(int=1))))
    email_verification_service = SimpleNamespace(create_verification_token=AsyncMock())

    handler = AccessController.signup

    result = await handler.fn(  # type: ignore[attr-defined]
        SimpleNamespace(),
        request=request,
        users_service=users_service,
        roles_service=roles_service,
        email_verification_service=email_verification_service,
        data=AccountRegister(email="dev-signup@example.com", password="Test_Password4!", name="Dev Signup"),
    )

    assert result["isVerified"] is True
    create_payload = users_service.create.await_args.args[0]
    assert create_payload["is_verified"] is True
    assert isinstance(create_payload["verified_at"], date)
    email_verification_service.create_verification_token.assert_not_awaited()
    users_service.send_verification_email.assert_not_awaited()
    request.app.emit.assert_called_once_with(event_id="user_created", user_id=user.id, email_sent=False)


async def test_signup_sends_verification_email_outside_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(access.settings.app, "ENV", "production")

    request = SimpleNamespace(
        base_url=SimpleNamespace(scheme="http", netloc="localhost:8089"),
        app=SimpleNamespace(emit=Mock()),
    )
    user = SimpleNamespace(id=UUID("5ef29f3c-3560-4d15-ba6b-a2e5c721e4d2"))
    users_service = SimpleNamespace(
        default_role="user",
        create=AsyncMock(return_value=user),
        send_verification_email=AsyncMock(return_value=True),
        to_schema=Mock(return_value={"id": str(user.id), "isVerified": False}),
    )
    roles_service = SimpleNamespace(get_one_or_none=AsyncMock(return_value=SimpleNamespace(id=UUID(int=2))))
    email_verification_service = SimpleNamespace(
        create_verification_token=AsyncMock(return_value=SimpleNamespace(token="verification-token")),
    )

    handler = AccessController.signup

    result = await handler.fn(  # type: ignore[attr-defined]
        SimpleNamespace(),
        request=request,
        users_service=users_service,
        roles_service=roles_service,
        email_verification_service=email_verification_service,
        data=AccountRegister(email="prod-signup@example.com", password="Test_Password5!", name="Prod Signup"),
    )

    assert result["isVerified"] is False
    create_payload = users_service.create.await_args.args[0]
    assert create_payload["is_verified"] is False
    assert "verified_at" not in create_payload
    email_verification_service.create_verification_token.assert_awaited_once_with(user.id)
    users_service.send_verification_email.assert_awaited_once()
    request.app.emit.assert_called_once_with(event_id="user_created", user_id=user.id, email_sent=True)
