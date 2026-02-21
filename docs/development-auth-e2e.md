# Development Auth Bypass & E2E Workflow

This document describes the development-only authentication bypass and the local end-to-end (E2E) workflow for the todo API.

## Purpose

In development mode, the API allows requests without a JWT token by resolving the user from a dedicated request header.
This enables local debugging and E2E flows without a login step while keeping production behavior unchanged.

## Development Mode Behavior

When `APP_ENV=development` and a request does not provide a JWT token (via `Authorization` header or auth cookie), the authentication middleware requires:

- Header: `X-Dev-User-Id: <uuid>`
- User must exist in database and be active + verified.

If the header is missing, malformed, or points to an invalid user, the request returns `401 Unauthorized`.

If a valid JWT token is provided, the system follows the normal authentication path.

## How It Works (Code References)

- `src/app/domain/accounts/guards.py`: `DevJWTCookieAuthenticationMiddleware` resolves user by `X-Dev-User-Id` when `APP_ENV=development` and no token is present.
- `examples/dev_e2e_httpx.py`: dev E2E script using `httpx` with `X-Dev-User-Id`.

## Run the E2E Script

1) Start the API in development mode:

```bash
make dev
```

2) Run the script:

```bash
DEV_E2E_USER_ID=<existing_user_uuid> \
uv run python examples/dev_e2e_httpx.py
```

You should see:

```
✔ health ok (200)
✔ create todo ok (201)
✔ list todos ok (200)
✔ update todo ok (200)
✔ delete todo ok (200)
```

## Environment Variables

- `APP_ENV`: must be `development` to enable the bypass.
- `APP_URL`: base URL for the API (default `http://localhost:8089`).
- `DEV_E2E_TIMEOUT`: request timeout in seconds (default `10`).
- `DEV_E2E_USER_ID`: required user UUID for dev-mode bypass.

## Notes / Troubleshooting

- If you see `401 Unauthorized`, confirm `APP_ENV=development` and provide a valid `X-Dev-User-Id`.
- If `DEV_E2E_USER_ID` is missing or invalid, the E2E script exits early.
- If the list call does not return the created todo, check the database or rerun the script (it deletes the created todo on success).

## Safety

This bypass is strictly scoped to `APP_ENV=development`. Production mode requires valid JWT authentication as before.
