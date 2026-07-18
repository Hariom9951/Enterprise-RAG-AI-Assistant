"""
Enterprise RAG AI Assistant — Chat ORM Models
===============================================
Defines session management and conversational history message logs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ChatSession(TimestampMixin, Base):
    """
    ORM model tracking conversation threads.
    """

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for the chat session.",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User who owns this conversation session.",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="New Conversation",
        comment="The display title of this chat session.",
    )

    # Relationships
    user = relationship("User", lazy="raise")
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ChatMessage.created_at.asc()",
    )


class ChatMessage(Base):
    """
    ORM model logging individual messages inside a conversation thread.
    """

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for the chat message.",
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        comment="The chat session this message belongs to.",
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="The role of the sender: user, assistant, system.",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The text content of the message.",
    )
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Grounded sources metadata citation matching list.",
    )
    tokens: Mapped[dict[str, int] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Token billing stats (prompt, completion, total).",
    )
    latency: Mapped[dict[str, int] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Detailed execution latencies in milliseconds.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="UTC timestamp when the message was sent.",
    )

    # Relationships
    session = relationship("ChatSession", back_populates="messages", lazy="raise")
