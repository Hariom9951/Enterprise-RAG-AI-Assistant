"""
Enterprise RAG AI Assistant — Chunk Schemas
===========================================
Defines Pydantic response models and validator schemas for document chunking.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChunkBase(BaseModel):
    """Common attributes for a semantic chunk."""

    text: str = Field(description="The semantic text content of this chunk.")
    chunk_index: int = Field(
        description="The sequence index of this chunk in the document."
    )
    token_count: int = Field(description="Number of tokens in the text.")
    character_count: int = Field(description="Length of clean chunk text.")
    word_count: int = Field(description="Whitespace-delimited word count.")
    reading_time_estimate: float = Field(
        description="Estimated reading time in seconds."
    )
    page_number: int = Field(
        default=1,
        description="Page number of the source document where this chunk starts.",
    )
    section_title: str | None = Field(
        default=None, description="Heading or section name this chunk belongs to."
    )
    heading_level: int | None = Field(
        default=None, description="Heading level if chunk is heading-bounded."
    )
    language: str = Field(default="und", description="ISO 639-1 language code.")
    sha256_hash: str = Field(description="SHA-256 hash of the chunk text.")
    version: str = Field(
        default="1.0.0", description="Chunking pipeline schema version."
    )


class ChunkCreate(ChunkBase):
    """Schema used during chunk splitting and preparation."""

    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Enriched key-value metadata."
    )


class ChunkResponse(ChunkBase):
    """Schema returned by endpoints representing a stored chunk."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias="chunk_metadata",
        serialization_alias="metadata",
        description="Enriched key-value metadata.",
    )
    created_at: datetime
    updated_at: datetime

    # Embedding metadata (raw vector is served via a dedicated endpoint to save bandwidth)
    embedding_model: str | None = Field(
        default=None, description="The name of the embedding model."
    )
    embedding_version: str | None = Field(
        default=None, description="The pipeline schema version used."
    )
    embedded_at: datetime | None = Field(
        default=None, description="UTC timestamp of vector execution."
    )
    embedding_duration_ms: int | None = Field(
        default=None, description="Duration in ms."
    )


class ChunkSummaryResponse(BaseModel):
    """Summary of chunking statistics for a single document."""

    total_chunks: int = Field(description="Total number of chunks generated.")
    total_tokens: int = Field(description="Aggregate token count across all chunks.")
    average_chunk_size: float = Field(description="Mean chunk size in tokens.")
    min_chunk_size: int = Field(description="Smallest chunk size in tokens.")
    max_chunk_size: int = Field(description="Largest chunk size in tokens.")
    reading_time_estimate: float = Field(
        description="Total estimated reading time in seconds."
    )
    languages: list[str] = Field(
        description="List of detected languages across chunks."
    )


class ChunkEmbeddingResponse(BaseModel):
    """Raw vector embedding elements for a chunk."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    embedding: list[float] | None = Field(
        default=None, description="The float vector array elements."
    )


class DocumentEmbeddingStatusResponse(BaseModel):
    """Progress tracking information for document embedding generation."""

    document_id: uuid.UUID
    status: str = Field(
        description="Current status (QUEUED, PROCESSING, COMPLETED, FAILED)."
    )
    percentage_complete: float = Field(description="Processing completion percentage.")
    processed_chunks: int = Field(description="Number of chunks embedded successfully.")
    remaining_chunks: int = Field(description="Number of chunks yet to be embedded.")
    model_used: str = Field(description="Active SentenceTransformers model configured.")
    vector_dimension: int = Field(description="Dimensionality size (e.g. 768).")
    processing_time_ms: int = Field(
        description="Estimated processing time elapsed or total."
    )
    error_message: str | None = Field(
        default=None, description="Error details if execution failed."
    )


class DocumentEmbeddingSummaryResponse(BaseModel):
    """Statistical summary of document chunks embeddings."""

    document_id: uuid.UUID
    total_embedded: int = Field(
        description="Total count of chunks indexed with vectors."
    )
    vector_dimension: int = Field(description="Dimensionality size (e.g. 768).")
    model_used: str = Field(description="SentenceTransformers model name.")
    version: str = Field(description="Embedding pipeline schema version.")
    total_duration_ms: int = Field(description="Total cumulative duration in ms.")
