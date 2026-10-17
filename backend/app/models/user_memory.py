"""
Enterprise RAG AI Assistant — User Persistent Memory ORM Model
==============================================================
Stores user-scoped facts, preferences, goals, and project context across
sessions with provenance tracking and active/inactive lifecycle states.

Database compatibility:
  - PostgreSQL (production): Uses native UUID, JSON, and TIMESTAMP WITH TIME ZONE.
  - SQLite (test suite):     Automatically maps to CHAR/VARCHAR, JSON string, and CHECK constraints.

Table: user_memories
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User

VALID_MEMORY_TYPES: set[str] = {"preference", "fact", "goal", "context"}
VALID_PROVENANCE_TYPES: set[str] = {"user_explicit", "agent_extracted", "system"}


class UserMemory(TimestampMixin, Base):
    """
    ORM model representing a piece of persistent knowledge or preference
    associated with an authenticated user.

    Security & Privacy Guarantees:
    - Every memory belongs to exactly one user via user_id.
    - Cascades deletion when the owning user account is deleted.
    - Soft-deletion via is_active distinguishes active memories from deactivated ones.
    - Check constraints restrict memory_type and provenance to safe predefined sets.
    - Check constraint guarantees confidence_score is bounded within [0.0, 1.0].
    - Credentials, tokens, and raw passwords must NEVER be saved in content or metadata.
    """

    __tablename__ = "user_memories"

    __table_args__ = (
        CheckConstraint(
            "memory_type IN ('preference', 'fact', 'goal', 'context')",
            name="ck_user_memories_memory_type",
        ),
        CheckConstraint(
            "provenance IN ('user_explicit', 'agent_extracted', 'system')",
            name="ck_user_memories_provenance",
        ),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0.0 AND confidence_score <= 1.0)",
            name="ck_user_memories_confidence_score",
        ),
        Index(
            "ix_user_memories_user_active",
            "user_id",
            "is_active",
        ),
        Index(
            "ix_user_memories_user_type",
            "user_id",
            "memory_type",
        ),
    )

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for the memory record.",
    )

    # ── Ownership ─────────────────────────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Foreign key referencing the owning user.",
    )

    # ── Content ───────────────────────────────────────────────────────────────
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Non-empty text content of the persistent memory.",
    )

    # ── Classification & Provenance ───────────────────────────────────────────
    memory_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="fact",
        server_default="fact",
        index=True,
        comment="Memory category: preference, fact, goal, context.",
    )

    provenance: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="user_explicit",
        server_default="user_explicit",
        comment="Source provenance: user_explicit, agent_extracted, or system.",
    )

    confidence_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        default=1.0,
        server_default="1.0",
        comment="Confidence score bounded in [0.0, 1.0]. Defaults to 1.0 for explicit inputs.",
    )

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
        index=True,
        comment="Lifecycle flag: True for active memories, False for soft-deleted / archived.",
    )

    # ── Extensible Metadata ───────────────────────────────────────────────────
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        default=None,
        comment="Optional JSON metadata (e.g. source session ID, tags).",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user = relationship("User", lazy="raise")

    def __repr__(self) -> str:
        return (
            f"<UserMemory id={self.id!s} user_id={self.user_id!s} "
            f"type={self.memory_type!r} provenance={self.provenance!r} active={self.is_active}>"
        )
