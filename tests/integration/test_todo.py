from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

pytestmark = pytest.mark.anyio

DEFAULT_START_TIME = "2026-02-01T09:00:00Z"
DEFAULT_END_TIME = "2026-02-01T10:00:00Z"


async def _create_todo(client: "AsyncClient", headers: dict[str, str], item: str = "Test Todo") -> dict:
    response = await client.post(
        "/todos",
        json={
            "item": item,
            "description": "This is a test todo item.",
            "start_time": DEFAULT_START_TIME,
            "end_time": DEFAULT_END_TIME,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_todo_list(client: "AsyncClient", superuser_token_headers: dict[str, str]) -> None:
    await _create_todo(client, superuser_token_headers, item="List Todo")
    response = await client.get("/todos", headers=superuser_token_headers)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    assert isinstance(payload.get("items"), list)
    assert len(payload.get("items", [])) > 0


async def test_todo_create(client: "AsyncClient", superuser_token_headers: dict[str, str]) -> None:
    created = await _create_todo(client, superuser_token_headers, item="Test Todo")
    assert created["item"] == "Test Todo"


async def test_todo_get(client: "AsyncClient", superuser_token_headers: dict[str, str]) -> None:
    created = await _create_todo(client, superuser_token_headers, item="Get Todo")
    response = await client.get(f"/todos/{created['id']}", headers=superuser_token_headers)
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_todo_update(client: "AsyncClient", superuser_token_headers: dict[str, str]) -> None:
    created = await _create_todo(client, superuser_token_headers, item="Update Todo")
    response = await client.patch(
        f"/todos/{created['id']}",
        json={
            "item": "Updated Todo",
            "description": "This todo has been updated.",
            "start_time": DEFAULT_START_TIME,
            "end_time": DEFAULT_END_TIME,
        },
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    assert response.json()["item"] == "Updated Todo"
    assert response.json()["description"] == "This todo has been updated."


async def test_todo_delete(client: "AsyncClient", superuser_token_headers: dict[str, str]) -> None:
    created = await _create_todo(client, superuser_token_headers, item="Delete Todo")
    response = await client.delete(f"/todos/{created['id']}", headers=superuser_token_headers)
    assert response.status_code == 200
