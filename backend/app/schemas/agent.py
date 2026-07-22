"""
Enterprise RAG AI Assistant — Agent Pydantic Schemas
=====================================================
Request/response models for the /agent API endpoints.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Chat / Run
# =============================================================================


class AgentChatRequest(BaseModel):
    """Request body for POST /agent/chat."""

    question: str = Field(
        ..., min_length=1, max_length=4000, description="User question."
    )
    session_id: uuid.UUID | None = Field(
        None, description="Optional chat session to link this run to."
    )
    provider: str | None = Field(
        None, description="LLM provider override (gemini, openai, ollama)."
    )
    model: str | None = Field(None, description="Model name override.")
    temperature: float = Field(
        0.2, ge=0.0, le=2.0, description="Generation temperature."
    )
    max_tokens: int = Field(1000, ge=50, le=8192, description="Maximum output tokens.")
    top_k: int = Field(
        5, ge=1, le=20, description="Number of chunks for semantic search."
    )
    threshold: float = Field(
        0.0, ge=0.0, le=1.0, description="Minimum similarity threshold."
    )


class AgentToolCallResponse(BaseModel):
    """One tool call record within an agent run."""

    model_config = ConfigDict(from_attributes=True)

    tool_id: str
    tool_name: str
    parameters: dict[str, Any] | None = None
    success: bool
    latency_ms: int
    retries: int = 0
    error: str | None = None
    result_summary: str | None = None  # Short preview of output


class AgentChatResponse(BaseModel):
    """Response from POST /agent/chat."""

    model_config = ConfigDict(from_attributes=True)

    run_id: uuid.UUID
    question: str
    final_answer: str
    tool_calls: list[AgentToolCallResponse]
    total_tool_calls: int
    total_latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    provider: str | None = None
    model_name: str | None = None
    success: bool
    error_message: str | None = None
    citations: list[dict[str, Any]] | None = Field(
        default=None, description="Detailed citation references."
    )
    confidence_score: float | None = Field(
        default=0.0, description="Average similarity confidence index."
    )
    reasoning_summary: str | None = Field(
        default=None, description="Extracted reasoning thought process."
    )
    retrieved_documents: list[dict[str, Any]] | None = Field(
        default=None, description="All retrieved document passages."
    )


# =============================================================================
# Tool List
# =============================================================================


class ToolParameterSchema(BaseModel):
    """JSON-Schema-style parameter descriptor."""

    type: str
    properties: dict[str, Any]
    required: list[str]


class ToolListItem(BaseModel):
    """Single tool descriptor in list response."""

    id: str
    name: str
    description: str
    permission_level: str
    parameters: ToolParameterSchema


class ToolListResponse(BaseModel):
    """Response from GET /agent/tools."""

    tools: list[ToolListItem]
    total: int


# =============================================================================
# Tool Test
# =============================================================================


class ToolTestRequest(BaseModel):
    """Request body for POST /agent/tools/test."""

    tool_id: str = Field(..., description="ID of the tool to test.")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Tool parameters."
    )


class ToolTestResponse(BaseModel):
    """Response from POST /agent/tools/test."""

    tool_id: str
    success: bool
    output: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int
    error: str | None = None


# =============================================================================
# Statistics
# =============================================================================


class ToolStatItem(BaseModel):
    """Aggregate stats for a single tool."""

    tool_id: str
    tool_name: str
    total_calls: int
    successful_calls: int
    failed_calls: int
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float


class AgentStatisticsResponse(BaseModel):
    """Response from GET /agent/statistics."""

    total_runs: int
    successful_runs: int
    failed_runs: int
    total_tool_calls: int
    avg_tools_per_run: float
    avg_run_latency_ms: float
    avg_prompt_tokens: float
    avg_completion_tokens: float
    tool_stats: list[ToolStatItem]
    period_days: int
