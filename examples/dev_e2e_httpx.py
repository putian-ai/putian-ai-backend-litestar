from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx

DEFAULT_BASE_URL = "http://localhost:8089"
DEV_USER_ID_HEADER = "X-Dev-User-Id"


def _print_ok(message: str) -> None:
    print(f"✔ {message}")


def _print_fail(message: str) -> None:
    print(f"✖ {message}")


def _expect_status(response: httpx.Response, expected: set[int]) -> bool:
    if response.status_code in expected:
        return True
    _print_fail(f"unexpected status {response.status_code} for {response.request.method} {response.request.url}")
    _print_fail(f"response body: {response.text}")
    return False


def _parse_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        _print_fail(f"invalid json response: {exc}")
        _print_fail(f"response body: {response.text}")
        raise


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return items
    return []


def main() -> int:
    base_url = os.getenv("APP_URL", DEFAULT_BASE_URL).rstrip("/")
    timeout_seconds = float(os.getenv("DEV_E2E_TIMEOUT", "10"))
    dev_user_id = os.getenv("DEV_E2E_USER_ID", "").strip()

    if not dev_user_id:
        _print_fail("missing DEV_E2E_USER_ID environment variable")
        return 1
    try:
        UUID(dev_user_id)
    except ValueError:
        _print_fail("DEV_E2E_USER_ID must be a valid UUID")
        return 1

    with httpx.Client(
        base_url=base_url,
        timeout=timeout_seconds,
        headers={DEV_USER_ID_HEADER: dev_user_id},
    ) as client:
        health_response = client.get("/health")
        if not _expect_status(health_response, {200}):
            return 1
        _print_ok(f"health ok ({health_response.status_code})")

        now = datetime.now(UTC).replace(microsecond=0)
        start_time = now + timedelta(minutes=5)
        end_time = start_time + timedelta(minutes=30)
        create_payload = {
            "item": "dev e2e",
            "description": "created by dev e2e script",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "importance": "none",
        }
        create_response = client.post("/todos", json=create_payload)
        if not _expect_status(create_response, {200, 201}):
            return 1
        create_body = _parse_json(create_response)
        todo_id = create_body.get("id") if isinstance(create_body, dict) else None
        if not todo_id:
            _print_fail("create todo response missing id")
            return 1
        _print_ok(f"create todo ok ({create_response.status_code})")

        list_response = client.get("/todos")
        if not _expect_status(list_response, {200}):
            return 1
        list_body = _parse_json(list_response)
        items = _extract_items(list_body)
        if not any(isinstance(item, dict) and item.get("id") == todo_id for item in items):
            _print_fail("created todo not found in list response")
            return 1
        _print_ok(f"list todos ok ({list_response.status_code})")

        update_payload = {
            "item": create_payload["item"],
            "description": "updated by dev e2e script",
            "start_time": create_payload["start_time"],
            "end_time": create_payload["end_time"],
        }
        update_response = client.patch(f"/todos/{todo_id}", json=update_payload)
        if not _expect_status(update_response, {200}):
            return 1
        update_body = _parse_json(update_response)
        if isinstance(update_body, dict) and update_body.get("description") != update_payload["description"]:
            _print_fail("update todo response did not include updated description")
            return 1
        _print_ok(f"update todo ok ({update_response.status_code})")

        delete_response = client.delete(f"/todos/{todo_id}")
        if not _expect_status(delete_response, {200}):
            return 1
        _print_ok(f"delete todo ok ({delete_response.status_code})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
