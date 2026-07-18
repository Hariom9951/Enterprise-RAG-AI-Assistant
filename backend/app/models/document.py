"""
Enterprise RAG AI Assistant — Document ORM Model
=================================================
Defines the ``documents`` table using SQLAlchemy 2.0 ``mapped_column`` syntax.

Database compatibility:
  - PostgreSQL (production): Uses native UUID columns.
  - SQLite (test suite):     Automatically maps UUID to character columns.

Table: documents
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.processed_document import ProcessedDocument
    from app.models.user import User


class Document(TimestampMixin, Base):
    """
    ORM model representing an uploaded document.

    Columns
    -------
    id                  UUID primary key, generated automatically.
    user_id             UUID foreign key referencing users.id.
    original_filename   Name of the file provided by the user (e.g. "proposal.pdf").
    stored_filename     Secure random filename on disk (e.g. "uuid.pdf").
    mime_type           Verified MIME type of the file (e.g. "application/pdf").
    file_size           File size in bytes.
    sha256_hash         SHA-256 hash of file content (used for per-user deduplication).
    storage_path        Absolute or relative path to the file on disk.
    processing_status   Parsing/chunking status: "uploaded", "processing", "completed", "failed".
    created_at          Audit creation timestamp (UTC).
    updated_at          Audit modification timestamp (UTC).
    """

    __tablename__ = "documents"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        comment="Universally unique identifier for this document.",
    )

    # ── Ownership ─────────────────────────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner of this document.",
    )

    # ── File Metadata ─────────────────────────────────────────────────────────
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Original name of the file upon upload.",
    )
    stored_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        comment="Obfuscated filename stored physically on disk.",
    )
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Content MIME type of the document.",
    )
    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Size of the document in bytes.",
    )
    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="SHA-256 integrity checksum for duplicate detection.",
    )
    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Physical location of the file on the local storage partition.",
    )

    # ── Processing Status ─────────────────────────────────────────────────────
    processing_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="UPLOADED",
        server_default="UPLOADED",
        comment="Document state: 'UPLOADED','QUEUED','PROCESSING','PROCESSED','FAILED'.",
    )

    # ── Relationships (Lazy Async Loading) ───────────────────────────────────
    user: Mapped["User"] = relationship(
        "User",
        back_populates="documents",
        lazy="raise",  # Prevent implicit synchronous query triggers
    )
    processed_document: Mapped["ProcessedDocument | None"] = relationship(
        "ProcessedDocument",
        back_populates="document",
        lazy="raise",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id!s} name={self.original_filename!r} status={self.processing_status!r}>"
