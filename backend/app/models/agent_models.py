"""
Enterprise RAG AI Assistant — Agent ORM Models
================================================
Persists every agent run and each individual tool call for full observability.

Tables
------
agent_runs        — One row per agent invocation.
agent_tool_calls  — One row per tool call within a run (child of agent_runs).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AgentRun(Base):
    """
    Captures a complete agent execution: question, final answer, all tools called,
    token usage, latency, and success status.
    """

    __tablename__ = "agent_runs"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique run identifier.",
    )

    # ── Ownership & Context ───────────────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Requesting user.",
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Associated chat session (optional).",
    )

    # ── Input / Output ────────────────────────────────────────────────────────
    question: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Original user question.",
    )
    final_answer: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="LLM-generated final answer.",
    )

    # ── Tool Observability ────────────────────────────────────────────────────
    tools_called: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Ordered list of tool IDs that were invoked.",
    )
    total_tool_calls: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total number of tool invocations in this run.",
    )

    # ── Performance ───────────────────────────────────────────────────────────
    total_latency_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Wall-clock time for the entire run in milliseconds.",
    )
    prompt_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Prompt tokens consumed.",
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Completion tokens generated.",
    )

    # ── LLM Metadata ─────────────────────────────────────────────────────────
    provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="LLM provider used (gemini, openai, ollama).",
    )
    model_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Specific model name.",
    )

    # ── Status ────────────────────────────────────────────────────────────────
    success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether the run completed successfully.",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error detail if success=False.",
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="UTC timestamp when the run was initiated.",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    tool_calls: Mapped[list[AgentToolCall]] = relationship(
        "AgentToolCall",
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return f"<AgentRun id={self.id!s} tools={self.total_tool_calls} success={self.success}>"


class AgentToolCall(Base):
    """
    Records a single tool invocation within an AgentRun.
    Child of AgentRun (many-to-one).
    """

    __tablename__ = "agent_tool_calls"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique tool call identifier.",
    )

    # ── Parent Run ────────────────────────────────────────────────────────────
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent AgentRun.",
    )

    # ── Tool Identity ─────────────────────────────────────────────────────────
    tool_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Registered tool identifier (e.g. 'semantic_search').",
    )
    tool_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Human-readable tool name.",
    )

    # ── Invocation Detail ─────────────────────────────────────────────────────
    parameters: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Parameters passed to the tool.",
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Serialized ToolResult (truncated if large).",
    )

    # ── Performance ───────────────────────────────────────────────────────────
    latency_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Tool execution wall-clock time in milliseconds.",
    )
    retries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of retry attempts before success or final failure.",
    )

    # ── Status ────────────────────────────────────────────────────────────────
    success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this tool call succeeded.",
    )
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if success=False.",
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    called_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="UTC timestamp when the tool was invoked.",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    run: Mapped[AgentRun] = relationship(
        "AgentRun",
        back_populates="tool_calls",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return f"<AgentToolCall tool={self.tool_id!r} latency={self.latency_ms}ms success={self.success}>"
