# type: ignore
"""add rag document

Revision ID: 3d2a7f9e8b1c
Revises: 7b9c1d2e3f4a
Create Date: 2026-03-02 00:00:00.000000+00:00

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
revision = "3d2a7f9e8b1c"
down_revision = "7b9c1d2e3f4a"
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
        "rag_document",
        sa.Column("id", sa.GUID(length=16), nullable=False),
        sa.Column("user_id", sa.GUID(length=16), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("indexed_at", sa.DateTimeUTC(timezone=True), nullable=True),
        sa.Column("sa_orm_sentinel", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTimeUTC(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("fk_rag_document_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rag_document")),
    )
    with op.batch_alter_table("rag_document", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_rag_document_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_rag_document_status"), ["status"], unique=False)
        batch_op.create_index("idx_rag_document_user_status", ["user_id", "status"], unique=False)
        batch_op.create_index("idx_rag_document_user_sha256", ["user_id", "sha256"], unique=False)

    with op.batch_alter_table("rag_document", schema=None) as batch_op:
        batch_op.create_table_comment(
            "User uploaded plain-text documents for RAG indexing",
            existing_comment=None,
        )


def schema_downgrades() -> None:
    """Schema downgrade migrations go here."""
    with op.batch_alter_table("rag_document", schema=None) as batch_op:
        batch_op.drop_table_comment(existing_comment="User uploaded plain-text documents for RAG indexing")

    with op.batch_alter_table("rag_document", schema=None) as batch_op:
        batch_op.drop_index("idx_rag_document_user_sha256")
        batch_op.drop_index("idx_rag_document_user_status")
        batch_op.drop_index(batch_op.f("ix_rag_document_status"))
        batch_op.drop_index(batch_op.f("ix_rag_document_user_id"))

    op.drop_table("rag_document")


def data_upgrades() -> None:
    """Add any optional data upgrade migrations here!"""


def data_downgrades() -> None:
    """Add any optional data downgrade migrations here!"""
