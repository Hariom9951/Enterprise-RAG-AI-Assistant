"""
Enterprise RAG AI Assistant — Chat Schemas
============================================
Defines conversational data validation schemas and JSON presentation formats.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChatSessionCreate(BaseModel):
    """Schema to instantiate a new conversation."""

    title: str | None = Field(
        default=None,
        max_length=255,
        description="Optional custom title for the session.",
    )


class ChatSessionRenameRequest(BaseModel):
    """Schema to rename a conversation thread."""

    title: str = Field(min_length=1, max_length=255, description="New display title.")


class ChatSessionResponse(BaseModel):
    """Simplified display properties of a conversation session."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessageResponse(BaseModel):
    """Properties of an individual user/assistant conversational exchange."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    citations: list[dict[str, Any]] | None = None
    tokens: dict[str, int] | None = None
    latency: dict[str, int] | None = None
    created_at: datetime


class ChatSessionDetailResponse(BaseModel):
    """Complete properties of a conversation session including message threads."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse]


class ChatMessageRequest(BaseModel):
    """Validation schema for posting a conversational question."""

    question: str = Field(min_length=1, description="The user's query question.")
    provider: str | None = Field(
        default=None, description="Active LLM provider overrides."
    )
    model: str | None = Field(default=None, description="Target LLM model overrides.")
    temperature: float | None = Field(
        default=None, ge=0.0, le=2.0, description="Generation temperature overrides."
    )
    max_tokens: int | None = Field(
        default=None, ge=1, description="Generation max output tokens overrides."
    )
    use_reranker: bool = Field(
        default=True, description="Enable metadata/priority reranking."
    )
    threshold: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum cosine similarity cutoff."
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Number of vector context documents to retrieve.",
    )
