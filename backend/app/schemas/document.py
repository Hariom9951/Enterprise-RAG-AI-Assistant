"""
Enterprise RAG AI Assistant — Document Pydantic Schemas
=========================================================
Request and response models for document upload and metadata operations.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class _BaseSchema(BaseModel):
    """Base schema config for documents."""

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
        "str_strip_whitespace": True,
    }


class DocumentResponse(_BaseSchema):
    """
    Public representation of a document's metadata returned by the API.

    Safety:
      - `storage_path` and `stored_filename` are omitted intentionally
        so client requests cannot expose internal folder structures.
    """

    id: uuid.UUID = Field(
        ...,
        description="Unique database identifier of the document.",
    )
    original_filename: str = Field(
        ...,
        description="Original name of the file (e.g. 'resume.pdf').",
    )
    mime_type: str = Field(
        ...,
        description="MIME standard type identifier (e.g. 'application/pdf').",
    )
    file_size: int = Field(
        ...,
        description="File size in bytes.",
    )
    processing_status: str = Field(
        ...,
        description="Parsing and ingestion state of the document.",
    )
    created_at: datetime = Field(
        ...,
        description="UTC creation timestamp.",
    )
    updated_at: datetime = Field(
        ...,
        description="UTC last update timestamp.",
    )


class DocumentUpdate(_BaseSchema):
    """
    Schema for renaming or modifying metadata on an existing document.
    """

    original_filename: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="New display name for the document. Must include valid extension.",
    )
