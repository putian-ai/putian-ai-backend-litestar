# Development Auth Bypass & E2E Workflow

This document describes the development-only authentication bypass and the local end-to-end (E2E) workflow for the todo API.

## Purpose

In development mode, the API allows requests without a JWT token by injecting a fixed test user. This enables local debugging and E2E flows without a login step while keeping production behavior unchanged.

## Development Mode Behavior

When `APP_ENV=development` and a request does not provide a JWT token (via `Authorization` header or auth cookie), the authentication middleware injects a development user:

- Email: `dev@local.test`
- Name: `Development User`
- Status: `is_active=True`, `is_verified=True`
- `verified_at` is set when missing to keep data consistent.

If the user does not exist, it is created automatically. If it exists but is not active/verified or missing a name, the record is updated to satisfy development assumptions.

If a valid JWT token is provided, the system follows the normal authentication path.

## How It Works (Code References)

- `src/app/config/base.py`: reads `APP_ENV` into `AppSettings.ENV`.
- `src/app/domain/accounts/guards.py`: `DevJWTCookieAuthenticationMiddleware` injects the dev user when `APP_ENV=development` and no token is present.
- `examples/dev_e2e_httpx.py`: dev E2E script using `httpx` to exercise the todo API.

## Run the E2E Script

1) Start the API in development mode:

```bash
make dev
```

2) Run the script:

```bash
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

## Notes / Troubleshooting

- If you see `401 Unauthorized`, confirm `APP_ENV=development` and that the request has no invalid token attached.
- If the list call does not return the created todo, check the database or rerun the script (it deletes the created todo on success).

## Safety

This bypass is strictly scoped to `APP_ENV=development`. Production mode requires valid JWT authentication as before.
