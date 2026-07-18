"""
Enterprise RAG AI Assistant — ProcessedDocument Pydantic Schemas
=================================================================
Response schemas for the document text extraction API.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, computed_field

# Preview character limit exposed in the API response
_PREVIEW_MAX_CHARS = 500


class ProcessedDocumentResponse(BaseModel):
    """
    Full response returned by ``GET /api/v1/documents/{id}/text``.

    Includes all extraction statistics plus a truncated preview of the
    clean text so clients don't need to fetch potentially large payloads
    for the listing view.
    """

    model_config = {"from_attributes": True}

    id: uuid.UUID
    document_id: uuid.UUID

    # ── Extracted Content ─────────────────────────────────────────────────────
    raw_text: str
    clean_text: str

    # ── Language & Statistics ─────────────────────────────────────────────────
    language: str
    page_count: int
    word_count: int
    character_count: int
    processing_time: float = Field(description="Extraction time in seconds.")

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: datetime
    updated_at: datetime

    # ── Computed Fields ───────────────────────────────────────────────────────
    @computed_field  # type: ignore[misc]
    @property
    def preview(self) -> str:
        """First ``_PREVIEW_MAX_CHARS`` characters of clean text."""
        return self.clean_text[:_PREVIEW_MAX_CHARS]

    @computed_field  # type: ignore[misc]
    @property
    def is_truncated(self) -> bool:
        """True when clean_text exceeds the preview limit."""
        return len(self.clean_text) > _PREVIEW_MAX_CHARS


class ProcessedDocumentSummary(BaseModel):
    """
    Lightweight summary for embedding in the document list API response.
    Does not include full text content.
    """

    model_config = {"from_attributes": True}

    language: str
    page_count: int
    word_count: int
    character_count: int
    processing_time: float
    preview: str = ""

    @classmethod
    def from_processed(cls, pd: ProcessedDocumentResponse) -> ProcessedDocumentSummary:
        return cls(
            language=pd.language,
            page_count=pd.page_count,
            word_count=pd.word_count,
            character_count=pd.character_count,
            processing_time=pd.processing_time,
            preview=pd.preview,
        )
