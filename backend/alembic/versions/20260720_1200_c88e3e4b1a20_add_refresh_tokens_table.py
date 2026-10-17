"""add_refresh_tokens_table

Revision ID: c88e3e4b1a20
Revises: a77b9a151b5c
Create Date: 2026-07-20 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c88e3e4b1a20"
down_revision: str | None = "a77b9a151b5c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id", sa.Uuid(), nullable=False, comment="Unique token record identifier."
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False, comment="Owner user UUID."),
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 hash of the refresh token.",
        ),
        sa.Column(
            "jti",
            sa.String(length=36),
            nullable=False,
            comment="Unique JWT ID (jti) claim of the refresh token.",
        ),
        sa.Column(
            "family_id",
            sa.Uuid(),
            nullable=False,
            comment="Rotation token family identifier.",
        ),
        sa.Column(
            "is_revoked",
            sa.Boolean(),
            server_default="0",
            nullable=False,
            comment="Revocation flag for this token and lineage.",
        ),
        sa.Column(
            "is_consumed",
            sa.Boolean(),
            server_default="0",
            nullable=False,
            comment="Single-use consumption flag.",
        ),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when token was rotated/consumed.",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Token expiration timestamp.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
            comment="UTC timestamp when this record was first created.",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
            comment="UTC timestamp of the most recent update to this record.",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_refresh_tokens_token_hash"),
        "refresh_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_refresh_tokens_jti"), "refresh_tokens", ["jti"], unique=True
    )
    op.create_index(
        op.f("ix_refresh_tokens_family_id"),
        "refresh_tokens",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_refresh_tokens_is_revoked"),
        "refresh_tokens",
        ["is_revoked"],
        unique=False,
    )
    op.create_index(
        op.f("ix_refresh_tokens_is_consumed"),
        "refresh_tokens",
        ["is_consumed"],
        unique=False,
    )
    op.create_index(
        op.f("ix_refresh_tokens_expires_at"),
        "refresh_tokens",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_refresh_tokens_expires_at"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_is_consumed"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_is_revoked"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_family_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_jti"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_token_hash"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
