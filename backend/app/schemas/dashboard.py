"""
Enterprise RAG AI Assistant — Dashboard Schemas
===================================================
Defines schemas for the system-wide workspace dashboard analytics.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RecentUploadItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    file_size: int
    processing_status: str
    created_at: datetime


class RecentConversationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    updated_at: datetime


class RecentSearchItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query_text: str
    search_type: str
    total_results: int
    created_at: datetime


class RecentAgentRunItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question: str
    success: bool
    total_latency_ms: int
    created_at: datetime


class DashboardStatisticsResponse(BaseModel):
    total_documents: int = Field(
        ..., description="Total documents uploaded by this user."
    )
    total_chunks: int = Field(
        ..., description="Total semantic chunks derived from user documents."
    )
    total_embeddings: int = Field(
        ..., description="Total chunks with generated vectors."
    )
    total_conversations: int = Field(..., description="Total active chat sessions.")
    todays_queries: int = Field(..., description="Total RAG queries executed today.")
    average_latency_ms: float = Field(
        ..., description="Average RAG latency in milliseconds."
    )
    average_similarity: float = Field(
        ..., description="Average similarity metric across queries."
    )
    most_used_llm: str = Field(
        ..., description="Name of the most frequently queried LLM model."
    )
    storage_usage_bytes: int = Field(
        ..., description="Cumulative storage bytes consumed by uploads."
    )
    recent_uploads: list[RecentUploadItem] = Field(default_factory=list)
    recent_conversations: list[RecentConversationItem] = Field(default_factory=list)
    recent_searches: list[RecentSearchItem] = Field(default_factory=list)
    recent_agent_runs: list[RecentAgentRunItem] = Field(default_factory=list)
