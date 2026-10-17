"""
Enterprise RAG AI Assistant — LangGraph State Definition
==========================================================
Defines the typed dictionary representing agent execution state
across nodes in the LangGraph workflow.
"""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from app.agents.agent_service import ToolCallRecord


class AgentGraphState(TypedDict, total=False):
    """
    Typed graph execution state for the LangGraph agent runner.
    """

    # Run metadata
    run_id: uuid.UUID
    question: str
    user_id: uuid.UUID
    session_id: uuid.UUID | None
    provider_name: str | None
    model_name: str | None
    temperature: float
    max_tokens: int
    top_k: int
    threshold: float

    # Resource budgets & constraints
    max_tool_calls: int
    loop_budget_s: float
    tool_timeout_s: float
    max_retries: int
    wall_t0: float

    # Adaptive loop controls
    current_query: str
    reformulation_count: int
    max_reformulations: int
    evidence_sufficient: bool
    evaluation_reason: str | None
    next_action: str  # "execute_tool", "reformulate", "answer", "finalize"
    pending_tool_call: dict[str, Any] | None

    # Execution control & plan
    is_blocked: bool
    tool_plan: list[dict[str, Any]]
    current_plan_index: int
    call_count: int
    tool_records: list[ToolCallRecord]
    context: str

    # Answer & metrics
    raw_answer: str
    final_answer: str
    reasoning_summary: str | None
    confidence_score: float
    citations: list[dict[str, Any]]
    retrieved_documents: list[dict[str, Any]]
    prompt_tokens: int
    completion_tokens: int
    total_latency_ms: int
    success: bool
    error_message: str | None
