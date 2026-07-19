"""
Enterprise RAG AI Assistant — Dashboard API Endpoints
======================================================
Exposes user-scoped system aggregates and activity lists for the Workspace Dashboard.
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_active_user, get_db
from app.models.chat_models import ChatSession
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.rag_query import RagQuery
from app.models.search_query import SearchQuery
from app.models.agent_models import AgentRun
from app.models.user import User
from app.schemas.dashboard import DashboardStatisticsResponse

router = APIRouter()


@router.get("/statistics", response_model=DashboardStatisticsResponse)
async def get_dashboard_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Query database to compile aggregated counts, sizing metrics, averages, and recency arrays.
    """
    user_id = current_user.id

    # 1. Total Documents & Sizing
    total_docs = await db.scalar(
        select(func.count(Document.id)).where(Document.user_id == user_id)
    ) or 0

    storage_usage = await db.scalar(
        select(func.sum(Document.file_size)).where(Document.user_id == user_id)
    ) or 0

    # 2. Total Semantic Chunks & Embedded Chunks
    total_chunks = await db.scalar(
        select(func.count(Chunk.id))
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.user_id == user_id)
    ) or 0

    total_embeddings = await db.scalar(
        select(func.count(Chunk.id))
        .join(Document, Chunk.document_id == Document.id)
        .where(and_(Document.user_id == user_id, Chunk.embedding != None))
    ) or 0

    # 3. Total Chat Sessions
    total_convs = await db.scalar(
        select(func.count(ChatSession.id)).where(ChatSession.user_id == user_id)
    ) or 0

    # 4. Today's Queries Count
    today_start = datetime.now(UTC).date()
    todays_queries = await db.scalar(
        select(func.count(RagQuery.id)).where(
            and_(
                RagQuery.user_id == user_id,
                func.date(RagQuery.created_at) == today_start
            )
        )
    ) or 0

    # 5. Averages
    avg_latency = await db.scalar(
        select(func.avg(RagQuery.latency_ms)).where(RagQuery.user_id == user_id)
    ) or 0.0

    avg_similarity = await db.scalar(
        select(func.avg(RagQuery.confidence_score)).where(RagQuery.user_id == user_id)
    ) or 0.0

    # 6. Most Used Model
    llm_stmt = (
        select(RagQuery.model_name, func.count(RagQuery.id))
        .where(RagQuery.user_id == user_id)
        .group_by(RagQuery.model_name)
        .order_by(func.count(RagQuery.id).desc())
        .limit(1)
    )
    llm_res = await db.execute(llm_stmt)
    llm_row = llm_res.first()
    most_used_llm = llm_row[0] if llm_row else "None"

    # 7. Recent lists
    # Recent Uploads (last 5)
    recent_uploads_stmt = (
        select(Document)
        .where(Document.user_id == user_id)
        .order_by(Document.created_at.desc())
        .limit(5)
    )
    recent_uploads_res = await db.execute(recent_uploads_stmt)
    recent_uploads = recent_uploads_res.scalars().all()

    # Recent Conversations (last 5)
    recent_convs_stmt = (
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
        .limit(5)
    )
    recent_convs_res = await db.execute(recent_convs_stmt)
    recent_conversations = recent_convs_res.scalars().all()

    # Recent Searches (last 5)
    recent_searches_stmt = (
        select(SearchQuery)
        .where(SearchQuery.user_id == user_id)
        .order_by(SearchQuery.created_at.desc())
        .limit(5)
    )
    recent_searches_res = await db.execute(recent_searches_stmt)
    recent_searches = recent_searches_res.scalars().all()

    # Recent Agent Runs (last 5)
    recent_agent_stmt = (
        select(AgentRun)
        .where(AgentRun.user_id == user_id)
        .order_by(AgentRun.created_at.desc())
        .limit(5)
    )
    recent_agent_res = await db.execute(recent_agent_stmt)
    recent_agent_runs = recent_agent_res.scalars().all()

    return {
        "total_documents": total_docs,
        "total_chunks": total_chunks,
        "total_embeddings": total_embeddings,
        "total_conversations": total_convs,
        "todays_queries": todays_queries,
        "average_latency_ms": round(float(avg_latency), 2),
        "average_similarity": round(float(avg_similarity), 4),
        "most_used_llm": most_used_llm,
        "storage_usage_bytes": storage_usage,
        "recent_uploads": recent_uploads,
        "recent_conversations": recent_conversations,
        "recent_searches": recent_searches,
        "recent_agent_runs": recent_agent_runs,
    }
