"""
Enterprise RAG AI Assistant — Agent API Endpoints
==================================================
Exposes the enterprise AI agent via REST API.

Endpoints
---------
POST /agent/chat           — Run agent on a question.
GET  /agent/tools          — List all registered tools.
POST /agent/tools/test     — Directly test-execute a tool.
GET  /agent/statistics     — Aggregate run and tool stats.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent_service import AgentService
from app.agents.registry import get_registry
from app.dependencies import get_current_active_user, get_db
from app.models.user import User
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentStatisticsResponse,
    AgentToolCallResponse,
    ToolListItem,
    ToolListResponse,
    ToolParameterSchema,
    ToolStatItem,
    ToolTestRequest,
    ToolTestResponse,
)

router = APIRouter()
_agent_service = AgentService()


# =============================================================================
# POST /agent/chat
# =============================================================================


@router.post("/chat", response_model=AgentChatResponse, status_code=status.HTTP_200_OK)
async def agent_chat(
    payload: AgentChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Submit a question to the enterprise AI agent.

    The agent will:
      1. Detect intent and select the most relevant tools.
      2. Execute tools to retrieve grounded evidence.
      3. Generate a final answer grounded in the retrieved context.
      4. Return the answer with tool execution trace.
    """
    result = await _agent_service.run(
        db=db,
        question=payload.question,
        user_id=current_user.id,
        session_id=payload.session_id,
        provider_name=payload.provider,
        model_name=payload.model,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        top_k=payload.top_k,
        threshold=payload.threshold,
    )

    tool_call_responses: list[AgentToolCallResponse] = []
    for rec in result.tool_call_records:
        # Build a short output summary for the response
        out = rec.result.output
        if isinstance(out, list):
            summary = f"{len(out)} result(s)"
        elif isinstance(out, dict):
            summary = ", ".join(list(out.keys())[:3])
        elif out is not None:
            summary = str(out)[:100]
        else:
            summary = None

        tool_call_responses.append(
            AgentToolCallResponse(
                tool_id=rec.tool_id,
                tool_name=rec.tool_name,
                parameters=rec.parameters,
                success=rec.result.success,
                latency_ms=rec.result.latency_ms,
                retries=rec.retries,
                error=rec.result.error,
                result_summary=summary,
            )
        )

    return AgentChatResponse(
        run_id=result.run_id,
        question=result.question,
        final_answer=result.final_answer,
        tool_calls=tool_call_responses,
        total_tool_calls=len(tool_call_responses),
        total_latency_ms=result.total_latency_ms,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        provider=result.provider,
        model_name=result.model_name,
        success=result.success,
        error_message=result.error_message,
    )


# =============================================================================
# GET /agent/tools
# =============================================================================


@router.get("/tools", response_model=ToolListResponse, status_code=status.HTTP_200_OK)
async def list_tools(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Return all tools available to the authenticated user.
    Admin users see additional admin-only tools.
    """
    registry = get_registry()
    role = str(getattr(current_user, "role", "user")).lower()
    schemas = registry.list_all(role=role)

    tools = []
    for s in schemas:
        raw_params = s.get("parameters", {})
        tools.append(
            ToolListItem(
                id=s["id"],
                name=s["name"],
                description=s["description"],
                permission_level=s["permission_level"],
                parameters=ToolParameterSchema(
                    type=raw_params.get("type", "object"),
                    properties=raw_params.get("properties", {}),
                    required=raw_params.get("required", []),
                ),
            )
        )

    return ToolListResponse(tools=tools, total=len(tools))


# =============================================================================
# POST /agent/tools/test
# =============================================================================


@router.post(
    "/tools/test", response_model=ToolTestResponse, status_code=status.HTTP_200_OK
)
async def test_tool(
    payload: ToolTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Directly test-execute a specific tool with provided parameters.
    Used for debugging, validation, and integration testing.
    """
    registry = get_registry()

    try:
        registry.get(payload.tool_id)  # Validate tool exists
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{payload.tool_id}' is not registered.",
        ) from err

    result = await registry.execute(
        tool_id=payload.tool_id,
        params=payload.parameters,
        user_id=current_user.id,
        db=db,
        user=current_user,
    )

    return ToolTestResponse(
        tool_id=payload.tool_id,
        success=result.success,
        output=result.output,
        metadata=result.metadata,
        latency_ms=result.latency_ms,
        error=result.error,
    )


# =============================================================================
# GET /agent/statistics
# =============================================================================


@router.get(
    "/statistics",
    response_model=AgentStatisticsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_statistics(
    period_days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Return aggregate agent run and tool usage statistics for the current user.

    Query Parameters
    ----------------
    period_days : int, optional
        Number of days to look back. Defaults to 30.
    """
    if period_days < 1 or period_days > 365:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="period_days must be between 1 and 365.",
        )

    stats = await _agent_service.get_statistics(db, current_user.id, period_days)

    tool_stats = [
        ToolStatItem(
            tool_id=t["tool_id"],
            tool_name=t["tool_name"],
            total_calls=t["total_calls"],
            successful_calls=t["successful_calls"],
            failed_calls=t["failed_calls"],
            avg_latency_ms=t["avg_latency_ms"],
            p50_latency_ms=t["p50_latency_ms"],
            p95_latency_ms=t["p95_latency_ms"],
        )
        for t in stats["tool_stats"]
    ]

    return AgentStatisticsResponse(
        total_runs=stats["total_runs"],
        successful_runs=stats["successful_runs"],
        failed_runs=stats["failed_runs"],
        total_tool_calls=stats["total_tool_calls"],
        avg_tools_per_run=stats["avg_tools_per_run"],
        avg_run_latency_ms=stats["avg_run_latency_ms"],
        avg_prompt_tokens=stats["avg_prompt_tokens"],
        avg_completion_tokens=stats["avg_completion_tokens"],
        tool_stats=tool_stats,
        period_days=stats["period_days"],
    )
