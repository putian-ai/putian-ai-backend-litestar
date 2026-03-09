from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy import String
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .agent_session import AgentSession
    from .email_verification_token import EmailVerificationToken
    from .memory import Memory
    from .oauth_account import UserOauthAccount
    from .password_reset_token import PasswordResetToken
    from .rag_document import RagDocument
    from .tag import Tag
    from .todo import Todo
    from .user_role import UserRole
    from .user_usage_quota import UserUsageQuota


class User(UUIDAuditBase):
    __tablename__ = "user_account"
    __table_args__ = {"comment": "User accounts for application access"}
    __pii_columns__ = {"name", "email", "avatar_url"}

    email: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(nullable=True, default=None)
    hashed_password: Mapped[str | None] = mapped_column(
        String(length=255), nullable=True, default=None)
    avatar_url: Mapped[str | None] = mapped_column(
        String(length=500), nullable=True, default=None)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    verified_at: Mapped[date] = mapped_column(nullable=True, default=None)
    joined_at: Mapped[date] = mapped_column(default=datetime.now)
    login_count: Mapped[int] = mapped_column(default=0)
    # -----------
    # ORM Relationships
    # ------------

    roles: Mapped[list[UserRole]] = relationship(
        back_populates="user",
        lazy="selectin",
        uselist=True,
        cascade="all, delete",
    )
    oauth_accounts: Mapped[list[UserOauthAccount]] = relationship(
        back_populates="user",
        lazy="noload",
        cascade="all, delete",
        uselist=True,
    )
    todos: Mapped[list[Todo]] = relationship(
        back_populates="user",
        lazy="selectin",
        uselist=True,
        cascade="all, delete-orphan",
    )
    tags: Mapped[list[Tag]] = relationship(
        back_populates="user",
        lazy="selectin",
        uselist=True,
        cascade="all, delete-orphan",
    )
    agent_sessions: Mapped[list[AgentSession]] = relationship(
        back_populates="user",
        lazy="selectin",
        uselist=True,
        cascade="all, delete-orphan",
    )
    memories: Mapped[list[Memory]] = relationship(
        back_populates="user",
        lazy="selectin",
        uselist=True,
        cascade="all, delete-orphan",
    )
    rag_documents: Mapped[list[RagDocument]] = relationship(
        back_populates="user",
        lazy="selectin",
        uselist=True,
        cascade="all, delete-orphan",
    )
    usage_quotas: Mapped[list[UserUsageQuota]] = relationship(
        back_populates="user",
        lazy="noload",
        uselist=True,
        cascade="all, delete-orphan",
    )
    verification_tokens: Mapped[list[EmailVerificationToken]] = relationship(
        back_populates="user",
        lazy="noload",
        uselist=True,
        cascade="all, delete-orphan",
    )
    password_reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        back_populates="user",
        lazy="noload",
        uselist=True,
        cascade="all, delete-orphan",
    )

    @hybrid_property
    def has_password(self) -> bool:
        return self.hashed_password is not None
