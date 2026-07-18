"""
Enterprise RAG AI Assistant — ProcessedDocument ORM Model
==========================================================
Stores the output of the document processing pipeline.

Relationship:
  - One ``Document`` (upload record) has at most one ``ProcessedDocument``
    (extraction result). The relationship is ``unique=True`` on ``document_id``.
  - Deleting a ``Document`` cascades to delete its ``ProcessedDocument``.

Table: processed_documents
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document


class ProcessedDocument(TimestampMixin, Base):
    """
    ORM model storing extracted text and statistics for an uploaded document.

    Columns
    -------
    id                UUID primary key.
    document_id       FK → documents.id (CASCADE DELETE, unique).
    raw_text          Full text as extracted, before normalisation.
    clean_text        Text after the normalisation pipeline.
    language          ISO 639-1 language code or ``"und"``.
    page_count        Number of pages (1 for TXT files).
    word_count        Whitespace-delimited word count of clean_text.
    character_count   ``len(clean_text)``.
    processing_time   Wall-clock seconds elapsed during extraction.
    created_at        UTC creation timestamp (from TimestampMixin).
    updated_at        UTC last-update timestamp (from TimestampMixin).
    """

    __tablename__ = "processed_documents"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        comment="Universally unique identifier for this processing record.",
    )

    # ── Foreign Key ───────────────────────────────────────────────────────────
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="The source document this record was extracted from.",
    )

    # ── Extracted Content ─────────────────────────────────────────────────────
    raw_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Full text as extracted from the file before normalisation.",
    )
    clean_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Text after Unicode normalisation and whitespace collapsing.",
    )

    # ── Language & Statistics ─────────────────────────────────────────────────
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="und",
        comment="ISO 639-1 language code detected from clean_text.",
    )
    page_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Number of pages in the source document.",
    )
    word_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Whitespace-delimited word count of clean_text.",
    )
    character_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Character count (len) of clean_text.",
    )
    processing_time: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Elapsed seconds for the extraction pipeline.",
    )

    # ── Relationship ─────────────────────────────────────────────────────────
    document: Mapped[Document] = relationship(
        "Document",
        back_populates="processed_document",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<ProcessedDocument id={self.id!s} doc={self.document_id!s} "
            f"lang={self.language!r} words={self.word_count}>"
        )
