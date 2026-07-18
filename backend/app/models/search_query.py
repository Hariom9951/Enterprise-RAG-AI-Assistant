"""
Enterprise RAG AI Assistant — SearchQuery ORM Model
===================================================
Stores execution logs of semantic and hybrid retrieval queries.
Used for user search history, audit trailing, and statistics.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class SearchQuery(TimestampMixin, Base):
    """
    ORM model logging search executions.
    """

    __tablename__ = "search_queries"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Universally unique identifier for this search query log.",
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
        comment="The raw text query searched by the user.",
    )
    search_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type of search execution (e.g., SEMANTIC, HYBRID).",
    )
    top_k: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Configured top-k document search count.",
    )
    similarity_threshold: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Configured similarity distance pruning threshold.",
    )
    total_results: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of semantic chunks matched and returned.",
    )
    response_time_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Database search response latency in milliseconds.",
    )

    # Relationships
    user: Mapped[User] = relationship("User", lazy="raise")
