from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from litestar.exceptions import NotAuthorizedException, PermissionDeniedException
from litestar.middleware.authentication import AuthenticationResult
from litestar.security.jwt import JWTCookieAuthenticationMiddleware, OAuth2PasswordBearerAuth

from app.config import constants
from app.config.app import alchemy
from app.config.base import get_settings
from app.db import models as m
from app.domain.accounts import urls
from app.domain.accounts.deps import provide_users_service

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection
    from litestar.handlers.base import BaseRouteHandler
    from litestar.security.jwt import Token


__all__ = ("auth", "current_user_from_token", "requires_active_user",
           "requires_superuser", "requires_verified_user")


settings = get_settings()
DEV_ENV_NAME = "development"
DEV_USER_ID_HEADER = "X-Dev-User-Id"


async def _get_dev_user_from_header(connection: ASGIConnection[Any, Any, Any, Any]) -> m.User | None:
    raw_user_id = connection.headers.get(DEV_USER_ID_HEADER)
    if raw_user_id is None:
        return None
    try:
        user_id = UUID(raw_user_id)
    except (ValueError, TypeError):
        return None

    service = await anext(provide_users_service(alchemy.provide_session(connection.app.state, connection.scope)))
    user = await service.get_one_or_none(id=user_id)
    return user if user and user.is_active and user.is_verified else None


class DevJWTCookieAuthenticationMiddleware(JWTCookieAuthenticationMiddleware):
    """JWT middleware that supports development authentication via X-Dev-User-Id."""

    async def authenticate_request(self, connection: ASGIConnection[Any, Any, Any, Any]) -> AuthenticationResult:
        auth_header = connection.headers.get(self.auth_header) or connection.cookies.get(self.auth_cookie_key)
        if auth_header:
            return await super().authenticate_request(connection)
        if settings.app.ENV.lower() != DEV_ENV_NAME:
            return await super().authenticate_request(connection)

        user = await _get_dev_user_from_header(connection)
        if user is None:
            msg = f"Missing or invalid {DEV_USER_ID_HEADER} header for development authentication."
            raise NotAuthorizedException(detail=msg)
        return AuthenticationResult(user=user, auth=None)


def requires_active_user(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    """Request requires active user.

    Verifies the request user is active.

    Args:
        connection (ASGIConnection): HTTP Request
        _ (BaseRouteHandler): Route handler

    Raises:
        PermissionDeniedException: Permission denied exception
    """
    if connection.user.is_active:
        return
    msg = "Inactive account"
    raise PermissionDeniedException(msg)


def requires_superuser(connection: ASGIConnection[m.User, Any, Any, Any], _: BaseRouteHandler) -> None:
    """Request requires active superuser.

    Args:
        connection (ASGIConnection): HTTP Request
        _ (BaseRouteHandler): Route handler

    Raises:
        PermissionDeniedException: Permission denied exception

    Returns:
        None: Returns None when successful
    """
    if connection.user.is_superuser:
        return
    raise PermissionDeniedException(detail="Insufficient privileges")


def requires_verified_user(connection: ASGIConnection[m.User, Any, Any, Any], _: BaseRouteHandler) -> None:
    """Verify the connection user is a superuser.

    Args:
        connection (ASGIConnection): Request/Connection object.
        _ (BaseRouteHandler): Route handler.

    Raises:
        PermissionDeniedException: Not authorized

    Returns:
        None: Returns None when successful
    """
    if connection.user.is_verified:
        return
    raise PermissionDeniedException(detail="User account is not verified.")


async def current_user_from_token(token: Token, connection: ASGIConnection[Any, Any, Any, Any]) -> m.User | None:
    """Lookup current user from local JWT token.

    Fetches the user information from the database


    Args:
        token (str): JWT Token Object
        connection (ASGIConnection[Any, Any, Any, Any]): ASGI connection.


    Returns:
        User: User record mapped to the JWT identifier if user exists, is active, and is verified
    """
    service = await anext(provide_users_service(alchemy.provide_session(connection.app.state, connection.scope)))
    user = await service.get_one_or_none(email=token.sub)
    return user if user and user.is_active and user.is_verified else None


auth = OAuth2PasswordBearerAuth[m.User](
    retrieve_user_handler=current_user_from_token,
    token_secret=settings.app.SECRET_KEY,
    token_url=urls.ACCOUNT_LOGIN,
    authentication_middleware_class=DevJWTCookieAuthenticationMiddleware,
    exclude=[
        constants.HEALTH_ENDPOINT,
        urls.ACCOUNT_LOGIN,
        urls.ACCOUNT_REGISTER,
        urls.ACCOUNT_VERIFY_EMAIL,
        urls.ACCOUNT_RESEND_VERIFICATION,
        "^/schema",
        "^/public/",
    ],
)
