"""
Enterprise RAG AI Assistant — RAG Validation Schemas
======================================================
Defines input payloads and output structures for the RAG endpoint.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.schemas.search import SearchFilters


class RAGQueryRequest(BaseModel):
    """
    RAG query input parameters payload.
    """

    question: str = Field(
        ..., min_length=1, description="The natural language question to ask."
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Optional override for chunk context count.",
    )
    threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Prune context chunks below this threshold.",
    )
    filters: SearchFilters | None = Field(
        default=None, description="Optional metadata/document filters."
    )
    use_reranker: bool = Field(
        default=True, description="Enable metadata, freshness, similarity reranking."
    )
    provider: str | None = Field(
        default=None, description="Optional provider override (gemini, openai, ollama)."
    )
    model: str | None = Field(default=None, description="Optional model name override.")


class CitationItem(BaseModel):
    """
    Metadata citation indicating which text segment backed a statement.
    """

    citation_index: int = Field(
        ..., description="The citation pointer index, e.g. 1 matches [1] in text."
    )
    chunk_id: uuid.UUID = Field(..., description="Source chunk ID.")
    document_id: uuid.UUID = Field(..., description="Parent document ID.")
    document_title: str = Field(..., description="Filename of parent document.")
    page_number: int = Field(..., description="Physical page number in source file.")
    section_title: str | None = Field(
        None, description="Heading/section title context."
    )
    text: str = Field(..., description="Raw text segment of the chunk.")
    score: float = Field(..., description="Relevance similarity/RRF score.")


class RAGChunkItem(BaseModel):
    """
    Individual chunk candidate retrieved for generation.
    """

    chunk_id: uuid.UUID
    text: str
    page_number: int
    section_title: str | None
    document_id: uuid.UUID
    document_title: str
    score: float


class RAGLatencyInfo(BaseModel):
    """
    Detailed latency metrics.
    """

    total_ms: int
    retrieval_ms: int
    llm_ms: int


class RAGTokenUsageInfo(BaseModel):
    """
    Usage tokens billing accounting metrics.
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class RAGQueryResponse(BaseModel):
    """
    Complete grounded RAG query output response.
    """

    answer: str = Field(
        ..., description="The model's generated response text, grounded by citations."
    )
    citations: list[CitationItem] = Field(
        ..., description="Metadata citation map list mapping back to sources."
    )
    retrieved_chunks: list[RAGChunkItem] = Field(
        ..., description="The sorted list of context chunks used."
    )
    confidence_score: float = Field(
        ..., description="Overall confidence indicator percentage score."
    )
    latency: RAGLatencyInfo = Field(
        ..., description="Latency statistics in milliseconds."
    )
    tokens_used: RAGTokenUsageInfo = Field(
        ..., description="Tokens consumed during retrieval + execution."
    )
    model_name: str = Field(..., description="Active LLM model used.")
    provider: str = Field(..., description="Active LLM provider used.")


class RAGStatisticsResponse(BaseModel):
    """
    User aggregate analytics metrics.
    """

    total_queries: int
    average_latency_ms: float
    total_tokens_used: int
    provider_distribution: dict[str, int]


class RAGModelItem(BaseModel):
    """
    Individual model option metadata block.
    """

    provider: str
    model_name: str
    is_default: bool
