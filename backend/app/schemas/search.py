"""
Enterprise RAG AI Assistant — Search API Validation Schemas
===========================================================
Defines search query filter formats and serialization outputs.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.chunk import ChunkResponse
from app.schemas.document import DocumentResponse


class SearchFilters(BaseModel):
    """
    Optional filter dimensions for search scoping.
    """

    document_ids: list[uuid.UUID] | None = Field(
        default=None, description="Scope query search to specific document IDs."
    )
    languages: list[str] | None = Field(
        default=None, description="Scope search to specific ISO languages."
    )
    start_date: datetime.datetime | None = Field(
        default=None,
        description="Retrieve chunks only from documents uploaded after this timestamp.",
    )
    end_date: datetime.datetime | None = Field(
        default=None,
        description="Retrieve chunks only from documents uploaded before this timestamp.",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Retrieve chunks containing these exact key-value attributes.",
    )


class SearchRequest(BaseModel):
    """
    Search request parameters payload.
    """

    query: str = Field(..., min_length=1, description="Raw query text.")
    top_k: int = Field(
        default=10, ge=1, le=100, description="Number of results to return."
    )
    offset: int = Field(default=0, ge=0, description="Pagination offset for results.")
    threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Prune results with scores below this similarity threshold.",
    )
    search_type: str = Field(
        default="hybrid",
        description="Search algorithm type: semantic, hybrid.",
    )
    filters: SearchFilters | None = Field(
        default=None, description="Filter criteria restrictions."
    )


class SearchResultItem(BaseModel):
    """
    Matched result segment containing details and metadata.
    """

    chunk: ChunkResponse = Field(
        ..., description="Details of the matched semantic text chunk."
    )
    document: DocumentResponse = Field(
        ..., description="Details of the parent document."
    )
    score: float = Field(..., description="Vector similarity/fusion scoring metric.")


class SearchQueryResponse(BaseModel):
    """
    Previous search history log serialization schema.
    """

    id: uuid.UUID
    query_text: str
    search_type: str
    top_k: int
    similarity_threshold: float
    total_results: int
    response_time_ms: int
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class SearchStatisticsResponse(BaseModel):
    """
    Audit aggregates of user searches.
    """

    total_queries: int
    average_latency_ms: float
    search_type_distribution: dict[str, int]


class SearchBatchRequest(BaseModel):
    """
    Batch search request parameters payload.
    """

    queries: list[str] = Field(
        ..., min_length=1, description="List of raw query texts."
    )
    top_k: int = Field(
        default=10, ge=1, le=100, description="Number of results to return per query."
    )
    offset: int = Field(default=0, ge=0, description="Pagination offset for results.")
    threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Prune results with scores below this similarity threshold.",
    )
    search_type: str = Field(
        default="hybrid",
        description="Search algorithm type: semantic, hybrid.",
    )
    filters: SearchFilters | None = Field(
        default=None, description="Filter criteria restrictions."
    )
