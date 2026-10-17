"""
Enterprise RAG AI Assistant — OAuth Connected Apps ORM Model
=============================================================
Stores encrypted OAuth credentials and connection states for personal applications (Gmail, Notion, Jira).

Database compatibility:
  - PostgreSQL (production): Uses native UUID, LargeBinary (BYTEA), JSON, and TIMESTAMP WITH TIME ZONE.
  - SQLite (test suite):     Automatically maps to CHAR/VARCHAR, BLOB, and JSON string fallback.

Table: user_connected_apps
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User

VALID_PROVIDERS = {"gmail", "google_drive", "github", "linkedin"}
VALID_STATUSES = {"connected", "expired", "revoked"}


class UserConnectedApp(TimestampMixin, Base):
    """
    ORM model representing an authorized personal application connection for a user.

    Security & Privacy Guarantees:
    - Never stores raw tokens. Plaintext tokens are encrypted via AES-256-GCM before write.
    - Token columns (encrypted_access_token, encrypted_refresh_token) are LargeBinary.
    - Sensitive credentials are strictly excluded from __repr__ and serialization schemas.
    - user_id is enforced with CASCADE delete on account removal.
    """

    __tablename__ = "user_connected_apps"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "provider",
            name="uq_user_connected_apps_user_provider",
        ),
        CheckConstraint(
            "provider IN ('gmail', 'google_drive', 'github', 'linkedin')",
            name="ck_user_connected_apps_provider",
        ),
        CheckConstraint(
            "connection_status IN ('connected', 'expired', 'revoked')",
            name="ck_user_connected_apps_status",
        ),
    )

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique connection record identifier.",
    )

    # ── Ownership ─────────────────────────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner user UUID.",
    )

    # ── Application Identity ──────────────────────────────────────────────────
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Provider identifier (gmail, notion, jira).",
    )

    # ── Encrypted Credentials (AES-256-GCM binary payload) ────────────────────
    encrypted_access_token: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
        comment="AES-256-GCM encrypted OAuth access token payload.",
    )

    encrypted_refresh_token: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        nullable=True,
        comment="AES-256-GCM encrypted OAuth refresh token payload (optional).",
    )

    # ── Scope & Lifecycle Metadata ────────────────────────────────────────────
    scopes: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="List of granted OAuth permission scopes.",
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC timestamp when the current access token expires.",
    )

    connection_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="connected",
        comment="Connection state: connected, expired, or revoked.",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped[User] = relationship("User", lazy="raise")

    def __repr__(self) -> str:
        """Safe representation excluding all secret bytes."""
        return (
            f"<UserConnectedApp id={self.id!s} user_id={self.user_id!s} "
            f"provider={self.provider!r} status={self.connection_status!r}>"
        )
