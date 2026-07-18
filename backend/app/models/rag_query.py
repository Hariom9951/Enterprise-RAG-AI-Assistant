"""
Enterprise RAG AI Assistant — RagQuery ORM Model
===================================================
Stores execution logs of RAG queries for statistics, audit, and latency tracking.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class RagQuery(TimestampMixin, Base):
    """
    ORM model logging RAG query executions.
    """

    __tablename__ = "rag_queries"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Universally unique identifier for this RAG query log.",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User who ran this search query.",
    )
    query_text: Mapped[str] = mapped_column(
        String(1020),
        nullable=False,
        comment="The raw text query asked by the user.",
    )
    answer_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The generated RAG answer.",
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="LLM Provider used (gemini, openai, ollama).",
    )
    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Name of the model used.",
    )
    prompt_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Tokens used in the prompt context.",
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Tokens generated in completion.",
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total token usage.",
    )
    latency_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Total latency of the search + generation in milliseconds.",
    )
    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.8,
        comment="Calculated confidence score based on similarity.",
    )
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Citations associated with chunks in the answer.",
    )

    # Relationships
    user = relationship("User", lazy="raise")
