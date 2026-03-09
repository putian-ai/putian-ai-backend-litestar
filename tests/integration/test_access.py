import pytest
from httpx import AsyncClient

from app.domain.accounts.controllers import access

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("username", "password", "expected_status_code"),
    (
        ("superuser@example1.com", "Test_Password1!", 403),
        ("superuser@example.com", "Test_Password1!", 201),
        ("user@example.com", "Test_Password1!", 403),
        ("user@example.com", "Test_Password2!", 201),
        ("inactive@example.com", "Old_Password2!", 403),
        ("inactive@example.com", "Old_Password3!", 403),
    ),
)
async def test_user_login(client: AsyncClient, username: str, password: str, expected_status_code: int) -> None:
    response = await client.post("/api/access/login", data={"username": username, "password": password})
    assert response.status_code == expected_status_code


@pytest.mark.parametrize(
    ("username", "password"),
    (("superuser@example.com", "Test_Password1!"),),
)
async def test_user_logout(client: AsyncClient, username: str, password: str) -> None:
    response = await client.post("/api/access/login", data={"username": username, "password": password})
    assert response.status_code == 201
    cookies = dict(response.cookies)

    assert cookies.get("token") is not None

    me_response = await client.get("/api/me")
    assert me_response.status_code == 200

    response = await client.post("/api/access/logout")
    assert response.status_code == 200

    # the user can no longer access the /me route.
    me_response = await client.get("/api/me")
    assert me_response.status_code == 401


async def test_user_signup_in_development_skips_email_verification(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(access.settings.app, "ENV", "development")

    email = "dev-signup@example.com"
    password = "Test_Password4!"

    signup_response = await client.post(
        "/api/access/signup",
        json={"email": email, "password": password, "name": "Dev Signup"},
    )

    assert signup_response.status_code == 201
    assert signup_response.json()["isVerified"] is True

    login_response = await client.post(
        "/api/access/login",
        data={"username": email, "password": password},
    )

    assert login_response.status_code == 201
