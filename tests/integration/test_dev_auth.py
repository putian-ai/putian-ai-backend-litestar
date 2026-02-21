from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.domain.accounts import guards

if TYPE_CHECKING:
    from httpx import AsyncClient
    from pytest import MonkeyPatch

pytestmark = pytest.mark.anyio

DEV_USER_ID_HEADER = "X-Dev-User-Id"
VALID_USER_ID = "5ef29f3c-3560-4d15-ba6b-a2e5c721e4d2"
INACTIVE_USER_ID = "7ef29f3c-3560-4d15-ba6b-a2e5c721e4e1"


async def test_dev_auth_requires_dev_user_id_header(client: AsyncClient, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(guards.settings.app, "ENV", "development")

    response = await client.get("/todos")

    assert response.status_code == 401


async def test_dev_auth_accepts_valid_dev_user_id_header(client: AsyncClient, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(guards.settings.app, "ENV", "development")

    response = await client.get("/todos", headers={DEV_USER_ID_HEADER: VALID_USER_ID})

    assert response.status_code == 200


async def test_dev_auth_rejects_invalid_uuid_header(client: AsyncClient, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(guards.settings.app, "ENV", "development")

    response = await client.get("/todos", headers={DEV_USER_ID_HEADER: "not-a-uuid"})

    assert response.status_code == 401


async def test_dev_auth_rejects_inactive_user(client: AsyncClient, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(guards.settings.app, "ENV", "development")

    response = await client.get("/todos", headers={DEV_USER_ID_HEADER: INACTIVE_USER_ID})

    assert response.status_code == 401


async def test_dev_user_id_header_ignored_outside_development(client: AsyncClient, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(guards.settings.app, "ENV", "production")

    response = await client.get("/todos", headers={DEV_USER_ID_HEADER: VALID_USER_ID})

    assert response.status_code == 401
