"""add_user_memories_table

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-10-16 17:15:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_memories",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
            comment="Unique identifier for the memory record.",
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            nullable=False,
            comment="Foreign key referencing the owning user.",
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            comment="Non-empty text content of the persistent memory.",
        ),
        sa.Column(
            "memory_type",
            sa.String(length=50),
            server_default="fact",
            nullable=False,
            comment="Memory category: preference, fact, goal, context.",
        ),
        sa.Column(
            "provenance",
            sa.String(length=50),
            server_default="user_explicit",
            nullable=False,
            comment="Source provenance: user_explicit, agent_extracted, or system.",
        ),
        sa.Column(
            "confidence_score",
            sa.Float(),
            server_default="1.0",
            nullable=True,
            comment="Confidence score bounded in [0.0, 1.0]. Defaults to 1.0 for explicit inputs.",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="Lifecycle flag: True for active memories, False for soft-deleted / archived.",
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="Optional JSON metadata (e.g. source session ID, tags).",
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
        sa.CheckConstraint(
            "memory_type IN ('preference', 'fact', 'goal', 'context')",
            name="ck_user_memories_memory_type",
        ),
        sa.CheckConstraint(
            "provenance IN ('user_explicit', 'agent_extracted', 'system')",
            name="ck_user_memories_provenance",
        ),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0.0 AND confidence_score <= 1.0)",
            name="ck_user_memories_confidence_score",
        ),
    )
    op.create_index(
        op.f("ix_user_memories_user_id"),
        "user_memories",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_memories_memory_type"),
        "user_memories",
        ["memory_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_memories_is_active"),
        "user_memories",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_memories_user_active"),
        "user_memories",
        ["user_id", "is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_memories_user_type"),
        "user_memories",
        ["user_id", "memory_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_user_memories_user_type"), table_name="user_memories"
    )
    op.drop_index(
        op.f("ix_user_memories_user_active"), table_name="user_memories"
    )
    op.drop_index(
        op.f("ix_user_memories_is_active"), table_name="user_memories"
    )
    op.drop_index(
        op.f("ix_user_memories_memory_type"), table_name="user_memories"
    )
    op.drop_index(
        op.f("ix_user_memories_user_id"), table_name="user_memories"
    )
    op.drop_table("user_memories")
