"""User Account Controllers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

import structlog
from advanced_alchemy.utils.text import slugify
from litestar import Controller, Request, Response, get, post
from litestar.di import Provide
from litestar.enums import RequestEncodingType
from litestar.params import Body, Parameter

from app.config.base import get_settings
from app.domain.accounts import urls
from app.domain.accounts.deps import provide_users_service, provide_email_verification_service
from app.domain.accounts.guards import auth, requires_active_user
from app.domain.accounts.schemas import AccountLogin, AccountRegister, User, Message
from app.domain.accounts.services import RoleService
from app.domain.accounts.services_email_verification import EmailVerificationService
from app.lib.deps import create_service_provider

if TYPE_CHECKING:
    from litestar.security.jwt import OAuth2Login

    from app.db import models as m
    from app.domain.accounts.services import UserService


settings = get_settings()


class AccessController(Controller):
    """User login and registration."""

    tags = ["Access"]
    dependencies = {
        "users_service": Provide(provide_users_service),
        "roles_service": Provide(create_service_provider(RoleService)),
        "email_verification_service": Provide(provide_email_verification_service),
    }

    @post(operation_id="AccountLogin", path=urls.ACCOUNT_LOGIN, exclude_from_auth=True)
    async def login(
        self,
        users_service: UserService,
        data: Annotated[AccountLogin, Body(title="OAuth2 Login", media_type=RequestEncodingType.URL_ENCODED)],
    ) -> Response[OAuth2Login]:
        """Authenticate a user."""
        user = await users_service.authenticate(data.username, data.password)
        return auth.login(user.email)

    @post(operation_id="AccountLogout", path=urls.ACCOUNT_LOGOUT, exclude_from_auth=True)
    async def logout(self, request: Request) -> Response:
        """Account Logout"""
        request.cookies.pop(auth.key, None)
        request.clear_session()

        response = Response(
            {"message": "OK"},
            status_code=200,
        )
        response.delete_cookie(auth.key)

        return response

    @post(operation_id="AccountRegister", path=urls.ACCOUNT_REGISTER)
    async def signup(
        self,
        request: Request,
        users_service: UserService,
        roles_service: RoleService,
        email_verification_service: EmailVerificationService,
        data: AccountRegister,
    ) -> User:
        """User signup with environment-aware email verification flow."""
        user_data = data.to_dict()
        is_development = settings.app.ENV.lower() == "development"

        if is_development:
            user_data["is_verified"] = True
            user_data["verified_at"] = datetime.now(UTC).date()
        else:
            user_data["is_verified"] = False

        # Add default role
        role_obj = await roles_service.get_one_or_none(slug=slugify(users_service.default_role))
        if role_obj is not None:
            user_data.update({"role_id": role_obj.id})

        # Create user
        user = await users_service.create(user_data)

        email_sent = False
        if not is_development:
            verification_token = await email_verification_service.create_verification_token(user.id)
            base_url = f"{request.base_url.scheme}://{request.base_url.netloc}"
            email_sent = await users_service.send_verification_email(
                user=user,
                verification_token=verification_token.token,
                base_url=base_url,
            )

        # Emit user creation event
        request.app.emit(event_id="user_created",
                         user_id=user.id, email_sent=email_sent)

        return users_service.to_schema(user, schema_type=User)

    @post(operation_id="VerifyEmail", path=urls.ACCOUNT_VERIFY_EMAIL, exclude_from_auth=True)
    async def verify_email(
        self,
        users_service: UserService,
        email_verification_service: EmailVerificationService,
        token: str = Body(media_type=RequestEncodingType.URL_ENCODED),
    ) -> Message:
        """Verify user email with verification token."""
        try:
            # Verify the token and get the user
            user = await email_verification_service.verify_token(token)

            # Mark user as verified
            await users_service.verify_user_email(user.id)

            return Message(message="Email verified successfully")

        except Exception as e:
            # Log the specific error for debugging
            logger = structlog.get_logger()
            await logger.aerror(
                "Email verification failed (POST)",
                error=str(e),
                error_type=type(e).__name__,
                token=token[:8] + "..." if len(token) > 8 else token,
                # Add more detail for repository errors
                **({
                    "error_detail": getattr(e, 'detail', None)
                } if hasattr(e, 'detail') else {}),
            )
            # Re-raise the exception to return proper error response
            raise

    @get(operation_id="VerifyEmailGet", path=urls.ACCOUNT_VERIFY_EMAIL, exclude_from_auth=True)
    async def verify_email_get(
        self,
        users_service: UserService,
        email_verification_service: EmailVerificationService,
        token: str = Parameter(query="token"),
    ) -> Response:
        """Verify user email with verification token via GET request."""
        try:
            # Verify the token and get the user
            user = await email_verification_service.verify_token(token)

            # Mark user as verified
            await users_service.verify_user_email(user.id)

            # Return success HTML page
            success_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Email Verified - Todo AI</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                    .container {{ max-width: 600px; margin: 50px auto; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); overflow: hidden; }}
                    .header {{ background-color: #10b981; color: white; padding: 30px; text-align: center; }}
                    .content {{ padding: 40px 30px; text-align: center; }}
                    .success-icon {{ font-size: 64px; color: #10b981; margin-bottom: 20px; }}
                    .button {{ display: inline-block; background-color: #4f46e5; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>✅ Email Verified Successfully!</h1>
                    </div>
                    <div class="content">
                        <div class="success-icon">🎉</div>
                        <h2>Welcome to Todo AI, {user.name or user.email}!</h2>
                        <p>Your email address has been successfully verified. You can now enjoy all the features of Todo AI.</p>
                        <p>You can now close this window and log in to your account.</p>
                        <a href="/" class="button">Go to Application</a>
                    </div>
                </div>
            </body>
            </html>
            """

            return Response(
                content=success_html,
                status_code=200,
                media_type="text/html"
            )

        except Exception as e:
            # Log the specific error for debugging
            logger = structlog.get_logger()
            await logger.aerror(
                "Email verification failed (GET)",
                error=str(e),
                error_type=type(e).__name__,
                token=token[:8] + "..." if len(token) > 8 else token,
                # Add more detail for repository errors
                **({
                    "error_detail": getattr(e, 'detail', None)
                } if hasattr(e, 'detail') else {}),
            )

            # Return error HTML page
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Verification Error - Todo AI</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                    .container {{ max-width: 600px; margin: 50px auto; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); overflow: hidden; }}
                    .header {{ background-color: #ef4444; color: white; padding: 30px; text-align: center; }}
                    .content {{ padding: 40px 30px; text-align: center; }}
                    .error-icon {{ font-size: 64px; color: #ef4444; margin-bottom: 20px; }}
                    .button {{ display: inline-block; background-color: #4f46e5; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>❌ Verification Failed</h1>
                    </div>
                    <div class="content">
                        <div class="error-icon">⚠️</div>
                        <h2>Unable to Verify Email</h2>
                        <p>The verification link is invalid, expired, or has already been used.</p>
                        <p>Please request a new verification email if needed.</p>
                        <a href="/" class="button">Go to Application</a>
                    </div>
                </div>
            </body>
            </html>
            """

            return Response(
                content=error_html,
                status_code=400,
                media_type="text/html"
            )

    @post(operation_id="ResendVerification", path=urls.ACCOUNT_RESEND_VERIFICATION, exclude_from_auth=True)
    async def resend_verification(
        self,
        request: Request,
        users_service: UserService,
        email_verification_service: EmailVerificationService,
        email: str = Body(media_type=RequestEncodingType.URL_ENCODED),
    ) -> Message:
        """Resend verification email to user."""
        # Find user by email
        user = await users_service.get_one_or_none(email=email)
        if user is None:
            return Message(message="If an account with this email exists, a verification email will be sent.")

        # Check if user is already verified
        if user.is_verified:
            return Message(message="Email address is already verified.")

        # Check if there's already a pending token
        existing_token = await email_verification_service.get_user_pending_token(user.id)

        if existing_token:
            # Use existing token
            verification_token = existing_token.token
        else:
            # Create new verification token
            new_token = await email_verification_service.create_verification_token(user.id)
            verification_token = new_token.token

        # Send verification email
        base_url = f"{request.base_url.scheme}://{request.base_url.netloc}"
        await users_service.send_verification_email(
            user=user,
            verification_token=verification_token,
            base_url=base_url
        )

        return Message(message="If an account with this email exists, a verification email will be sent.")

    @get(operation_id="AccountProfile", path=urls.ACCOUNT_PROFILE, guards=[requires_active_user])
    async def profile(self, current_user: m.User, users_service: UserService) -> User:
        """User Profile."""
        return users_service.to_schema(current_user, schema_type=User)
