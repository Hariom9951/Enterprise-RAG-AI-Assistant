"""add_user_connected_apps_table

Revision ID: d4e5f6a7b8c9
Revises: c88e3e4b1a20
Create Date: 2026-10-16 13:50:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c88e3e4b1a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_connected_apps",
        sa.Column(
            "id", sa.Uuid(), nullable=False, comment="Unique connection record identifier."
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False, comment="Owner user UUID."),
        sa.Column(
            "provider",
            sa.String(length=50),
            nullable=False,
            comment="Provider identifier (gmail, google_drive, github, linkedin).",
        ),
        sa.Column(
            "encrypted_access_token",
            sa.LargeBinary(),
            nullable=False,
            comment="AES-256-GCM encrypted OAuth access token payload.",
        ),
        sa.Column(
            "encrypted_refresh_token",
            sa.LargeBinary(),
            nullable=True,
            comment="AES-256-GCM encrypted OAuth refresh token payload (optional).",
        ),
        sa.Column(
            "scopes",
            sa.JSON(),
            nullable=False,
            comment="List of granted OAuth permission scopes.",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC timestamp when the current access token expires.",
        ),
        sa.Column(
            "connection_status",
            sa.String(length=20),
            server_default="connected",
            nullable=False,
            comment="Connection state: connected, expired, or revoked.",
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
        sa.UniqueConstraint(
            "user_id", "provider", name="uq_user_connected_apps_user_provider"
        ),
        sa.CheckConstraint(
            "provider IN ('gmail', 'google_drive', 'github', 'linkedin')",
            name="ck_user_connected_apps_provider",
        ),
        sa.CheckConstraint(
            "connection_status IN ('connected', 'expired', 'revoked')",
            name="ck_user_connected_apps_status",
        ),
    )
    op.create_index(
        op.f("ix_user_connected_apps_user_id"),
        "user_connected_apps",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_connected_apps_provider"),
        "user_connected_apps",
        ["provider"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_user_connected_apps_provider"), table_name="user_connected_apps"
    )
    op.drop_index(
        op.f("ix_user_connected_apps_user_id"), table_name="user_connected_apps"
    )
    op.drop_table("user_connected_apps")
