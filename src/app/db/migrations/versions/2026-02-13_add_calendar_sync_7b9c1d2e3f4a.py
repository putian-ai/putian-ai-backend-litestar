# type: ignore
"""add calendar sync

Revision ID: 7b9c1d2e3f4a
Revises: 17ca2745828b
Create Date: 2026-02-13 00:00:00.000000+00:00

"""
from __future__ import annotations

import warnings

import sqlalchemy as sa
from advanced_alchemy.types import GUID, ORA_JSONB, DateTimeUTC, EncryptedString, EncryptedText
from alembic import op

__all__ = ["data_downgrades", "data_upgrades", "downgrade", "schema_downgrades", "schema_upgrades", "upgrade"]

sa.GUID = GUID
sa.DateTimeUTC = DateTimeUTC
sa.ORA_JSONB = ORA_JSONB
sa.EncryptedString = EncryptedString
sa.EncryptedText = EncryptedText

# revision identifiers, used by Alembic.
revision = "7b9c1d2e3f4a"
down_revision = "17ca2745828b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning)
        with op.get_context().autocommit_block():
            schema_upgrades()
            data_upgrades()


def downgrade() -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning)
        with op.get_context().autocommit_block():
            data_downgrades()
            schema_downgrades()


def schema_upgrades() -> None:
    """Schema upgrade migrations go here."""
    op.create_table(
        "calendar_connection",
        sa.Column("id", sa.GUID(length=16), nullable=False),
        sa.Column("user_id", sa.GUID(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("calendar_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sync_mode", sa.String(length=16), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("credential_blob", sa.Text(), nullable=True),
        sa.Column("sync_cursor", sa.Text(), nullable=True),
        sa.Column("sync_state", sa.Text(), nullable=True),
        sa.Column("webhook_channel_id", sa.String(length=255), nullable=True),
        sa.Column("webhook_resource_id", sa.String(length=255), nullable=True),
        sa.Column("webhook_expires_at", sa.DateTimeUTC(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTimeUTC(timezone=True), nullable=True),
        sa.Column("last_pull_at", sa.DateTimeUTC(timezone=True), nullable=True),
        sa.Column("last_push_at", sa.DateTimeUTC(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sa_orm_sentinel", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("fk_calendar_connection_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_connection")),
    )
    with op.batch_alter_table("calendar_connection", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_calendar_connection_provider"), ["provider"], unique=False)
        batch_op.create_index(batch_op.f("ix_calendar_connection_user_id"), ["user_id"], unique=False)

    with op.batch_alter_table("calendar_connection", schema=None) as batch_op:
        batch_op.create_table_comment(
            "External calendar account connections",
            existing_comment=None,
        )

    op.create_table(
        "calendar_event",
        sa.Column("id", sa.GUID(length=16), nullable=False),
        sa.Column("connection_id", sa.GUID(length=16), nullable=False),
        sa.Column("user_id", sa.GUID(length=16), nullable=False),
        sa.Column("linked_todo_id", sa.GUID(length=16), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("remote_event_id", sa.String(length=512), nullable=False),
        sa.Column("etag", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_time", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.Column("all_day", sa.Boolean(), nullable=False),
        sa.Column("source_timezone", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("remote_created_at", sa.DateTimeUTC(timezone=True), nullable=True),
        sa.Column("remote_updated_at", sa.DateTimeUTC(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("sa_orm_sentinel", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["calendar_connection.id"],
            name=op.f("fk_calendar_event_connection_id_calendar_connection"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["linked_todo_id"],
            ["todo.id"],
            name=op.f("fk_calendar_event_linked_todo_id_todo"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("fk_calendar_event_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_event")),
        sa.UniqueConstraint("connection_id", "remote_event_id", name="uq_calendar_event_connection_remote_event"),
    )
    with op.batch_alter_table("calendar_event", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_calendar_event_connection_id"), ["connection_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_calendar_event_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_calendar_event_linked_todo_id"), ["linked_todo_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_calendar_event_provider"), ["provider"], unique=False)
        batch_op.create_index(batch_op.f("ix_calendar_event_start_time"), ["start_time"], unique=False)
        batch_op.create_index(batch_op.f("ix_calendar_event_end_time"), ["end_time"], unique=False)

    with op.batch_alter_table("calendar_event", schema=None) as batch_op:
        batch_op.create_table_comment(
            "Mirrored events from external calendars",
            existing_comment=None,
        )

    op.create_table(
        "todo_calendar_link",
        sa.Column("id", sa.GUID(length=16), nullable=False),
        sa.Column("todo_id", sa.GUID(length=16), nullable=False),
        sa.Column("connection_id", sa.GUID(length=16), nullable=False),
        sa.Column("remote_event_id", sa.String(length=512), nullable=False),
        sa.Column("etag", sa.String(length=255), nullable=True),
        sa.Column("last_sync_source", sa.String(length=16), nullable=True),
        sa.Column("last_synced_at", sa.DateTimeUTC(timezone=True), nullable=True),
        sa.Column("sa_orm_sentinel", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["calendar_connection.id"],
            name=op.f("fk_todo_calendar_link_connection_id_calendar_connection"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["todo_id"],
            ["todo.id"],
            name=op.f("fk_todo_calendar_link_todo_id_todo"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_todo_calendar_link")),
        sa.UniqueConstraint("connection_id", "remote_event_id", name="uq_todo_calendar_link_connection_remote_event"),
        sa.UniqueConstraint("todo_id", name="uq_todo_calendar_link_todo"),
    )
    with op.batch_alter_table("todo_calendar_link", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_todo_calendar_link_connection_id"), ["connection_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_todo_calendar_link_todo_id"), ["todo_id"], unique=False)

    with op.batch_alter_table("todo_calendar_link", schema=None) as batch_op:
        batch_op.create_table_comment(
            "Bidirectional mapping between todos and remote events",
            existing_comment=None,
        )


def schema_downgrades() -> None:
    """Schema downgrade migrations go here."""
    with op.batch_alter_table("todo_calendar_link", schema=None) as batch_op:
        batch_op.drop_table_comment(existing_comment="Bidirectional mapping between todos and remote events")

    with op.batch_alter_table("todo_calendar_link", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_todo_calendar_link_todo_id"))
        batch_op.drop_index(batch_op.f("ix_todo_calendar_link_connection_id"))

    op.drop_table("todo_calendar_link")

    with op.batch_alter_table("calendar_event", schema=None) as batch_op:
        batch_op.drop_table_comment(existing_comment="Mirrored events from external calendars")

    with op.batch_alter_table("calendar_event", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_calendar_event_end_time"))
        batch_op.drop_index(batch_op.f("ix_calendar_event_start_time"))
        batch_op.drop_index(batch_op.f("ix_calendar_event_provider"))
        batch_op.drop_index(batch_op.f("ix_calendar_event_linked_todo_id"))
        batch_op.drop_index(batch_op.f("ix_calendar_event_user_id"))
        batch_op.drop_index(batch_op.f("ix_calendar_event_connection_id"))

    op.drop_table("calendar_event")

    with op.batch_alter_table("calendar_connection", schema=None) as batch_op:
        batch_op.drop_table_comment(existing_comment="External calendar account connections")

    with op.batch_alter_table("calendar_connection", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_calendar_connection_user_id"))
        batch_op.drop_index(batch_op.f("ix_calendar_connection_provider"))

    op.drop_table("calendar_connection")


def data_upgrades() -> None:
    """Add any optional data upgrade migrations here!"""


def data_downgrades() -> None:
    """Add any optional data downgrade migrations here!"""
