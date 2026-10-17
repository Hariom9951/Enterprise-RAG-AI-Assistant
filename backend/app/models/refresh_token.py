"""
Enterprise RAG AI Assistant — Refresh Token ORM Model
======================================================
Defines the ``refresh_tokens`` table using SQLAlchemy 2.0 ``mapped_column`` syntax.
Tracks refresh-token lifecycle, single-use consumption, token families, and revocation.

Database compatibility:
  - PostgreSQL (production): Uses native UUID and TIMESTAMP WITH TIME ZONE.
  - SQLite (test suite):     Automatically maps to CHAR/VARCHAR and DATETIME fallback.

Table: refresh_tokens
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(TimestampMixin, Base):
    """
    ORM model representing a tracked refresh token.

    Columns
    -------
    id          UUID primary key.
    user_id     Foreign key to ``users.id`` with CASCADE deletion.
    token_hash  SHA-256 digest of the raw JWT string (never store plain tokens).
    jti         Cryptographically unique JWT ID embedded in the token payload.
    family_id   UUID grouping all rotated descendants of an original login session.
    is_revoked  True if this specific token or its whole family was revoked.
    is_consumed True once exchanged for a new token pair during single-use rotation.
    consumed_at UTC timestamp when this token was consumed.
    expires_at  UTC expiration timestamp matching token ``exp`` claim.
    created_at  Managed by TimestampMixin.
    updated_at  Managed by TimestampMixin.
    """

    __tablename__ = "refresh_tokens"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique token record identifier.",
    )

    # ── Ownership ─────────────────────────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner user UUID.",
    )

    # ── Token Tracking & Lookup ───────────────────────────────────────────────
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="SHA-256 hash of the refresh token.",
    )
    jti: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique JWT ID (jti) claim of the refresh token.",
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
        default=uuid.uuid4,
        comment="Rotation token family identifier.",
    )

    # ── Lifecycle & State ─────────────────────────────────────────────────────
    is_revoked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        index=True,
        comment="Revocation flag for this token and lineage.",
    )
    is_consumed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        index=True,
        comment="Single-use consumption flag.",
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Timestamp when token was rotated/consumed.",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Token expiration timestamp.",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped[User] = relationship("User", lazy="raise")

    def __repr__(self) -> str:
        return (
            f"<RefreshToken id={self.id!s} user_id={self.user_id!s} "
            f"family_id={self.family_id!s} is_consumed={self.is_consumed} "
            f"is_revoked={self.is_revoked}>"
        )
