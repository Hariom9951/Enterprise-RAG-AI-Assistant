"""
Enterprise RAG AI Assistant — Chunk ORM Model
=============================================
Stores semantic chunks extracted from processed documents.

Table: chunks
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document


class Chunk(TimestampMixin, Base):
    """
    ORM model storing text chunks and stats for RAG retrieval.

    Columns
    -------
    id                     UUID primary key.
    document_id            FK → documents.id (CASCADE DELETE).
    chunk_index            Sequence index of the chunk in the document.
    text                   The raw text content of this chunk.
    token_count            Number of tokens computed via tokenizer.
    character_count        Character count (len) of the raw chunk text.
    word_count             Word count of the chunk text.
    reading_time_estimate  Estimated reading time in seconds.
    page_number            Physical page number in source file (1-indexed).
    section_title          Header/Section title this chunk belongs to.
    heading_level          Header level (e.g. 1 for #, 2 for ##).
    language               ISO 639-1 language code or "und".
    metadata               JSON dictionary storing rich enrichment metadata.
    sha256_hash            SHA-256 hash of the chunk text.
    version                Chunking pipeline schema version.
    created_at             UTC timestamp (from TimestampMixin).
    updated_at             UTC timestamp (from TimestampMixin).
    """

    __tablename__ = "chunks"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        comment="Universally unique identifier for this chunk.",
    )

    # ── Foreign Key ───────────────────────────────────────────────────────────
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The source document this chunk belongs to.",
    )

    # ── Index & Text ──────────────────────────────────────────────────────────
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        comment="The sequence index of this chunk in the document.",
    )
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The semantic text content of this chunk.",
    )

    # ── Tokenization & Text Stats ─────────────────────────────────────────────
    token_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of tokens in the text.",
    )
    character_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Length of clean chunk text.",
    )
    word_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Whitespace-delimited word count.",
    )
    reading_time_estimate: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Estimated reading time in seconds.",
    )

    # ── Structural Metadata ───────────────────────────────────────────────────
    page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Page number of the source document where this chunk starts.",
    )
    section_title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Heading or section name this chunk belongs to.",
    )
    heading_level: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Heading level (e.g. 1 for H1, 2 for H2) if chunk is heading-bounded.",
    )
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="und",
        comment="ISO 639-1 language code.",
    )

    # ── Hashing & Versioning ──────────────────────────────────────────────────
    chunk_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        comment="Enriched key-value metadata.",
    )
    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="SHA-256 hash of the chunk text to prevent duplicates.",
    )
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0.0",
        comment="Chunking pipeline schema version.",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    document: Mapped[Document] = relationship(
        "Document",
        back_populates="chunks",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<Chunk id={self.id!s} idx={self.chunk_index} "
            f"tokens={self.token_count} sha={self.sha256_hash[:8]}>"
        )
