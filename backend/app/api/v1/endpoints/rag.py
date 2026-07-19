"""
Enterprise RAG AI Assistant — RAG API Endpoints Router
======================================================
Exposes user RAG search queries, scoped searches, model choices, and stats.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.db.session import get_db
from app.dependencies import get_current_active_user
from app.models.user import User
from app.schemas.rag import (
    RAGModelItem,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGStatisticsResponse,
)
from app.schemas.search import SearchFilters
from app.services import document_service
from app.services.rag_service import RAGService

router = APIRouter()
rag_service = RAGService()


@router.post(
    "/query",
    response_model=RAGQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute global RAG query.",
    description="Query knowledge chunks across all owned documents to generate a grounded answer with citations.",
)
async def global_rag_query(
    payload: RAGQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RAGQueryResponse:
    try:
        results = await rag_service.execute_rag(
            db=db,
            question=payload.question,
            user_id=current_user.id,
            top_k=payload.top_k,
            threshold=payload.threshold,
            filters=payload.filters.model_dump() if payload.filters else None,
            use_reranker=payload.use_reranker,
            provider_name=payload.provider,
            model_name=payload.model,
        )
        return RAGQueryResponse.model_validate(results)
    except Exception as e:
        logger_msg = f"RAG Query Failed: {e!s}"
        from app.core.logging import logger

        logger.error(logger_msg)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate RAG answer: {e!s}",
        ) from e


@router.post(
    "/query/document/{document_id}",
    response_model=RAGQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute document-scoped RAG query.",
    description="Restricts the retrieval context search to a single document ID owned by the user.",
)
async def document_scoped_rag_query(
    document_id: uuid.UUID,
    payload: RAGQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RAGQueryResponse:
    # 1. Verify ownership/existence first
    await document_service.get_document_by_id(db, document_id, current_user.id)

    # 2. Coerce filters
    search_filters = payload.filters or SearchFilters()
    search_filters.document_ids = [document_id]

    try:
        results = await rag_service.execute_rag(
            db=db,
            question=payload.question,
            user_id=current_user.id,
            top_k=payload.top_k,
            threshold=payload.threshold,
            filters=search_filters.model_dump(),
            use_reranker=payload.use_reranker,
            provider_name=payload.provider,
            model_name=payload.model,
        )
        return RAGQueryResponse.model_validate(results)
    except Exception as e:
        logger_msg = f"Document-Scoped RAG Query Failed: {e!s}"
        from app.core.logging import logger

        logger.error(logger_msg)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate document RAG answer: {e!s}",
        ) from e


@router.get(
    "/models",
    response_model=list[RAGModelItem],
    status_code=status.HTTP_200_OK,
    summary="List available LLM models.",
    description="Returns metadata of all active LLM provider options.",
)
async def list_models(
    current_user: User = Depends(get_current_active_user),
) -> list[RAGModelItem]:
    default_provider = settings.llm_provider.lower()
    return [
        RAGModelItem(
            provider="GEMINI",
            model_name=settings.gemini_model,
            is_default=(default_provider == "gemini"),
        ),
        RAGModelItem(
            provider="OPENAI",
            model_name="gpt-4o-mini",
            is_default=(default_provider == "openai"),
        ),
        RAGModelItem(
            provider="OLLAMA",
            model_name="llama3",
            is_default=(default_provider == "ollama"),
        ),
    ]


@router.get(
    "/statistics",
    response_model=RAGStatisticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get RAG execution statistics.",
    description="Retrieve cumulative statistics and token accounting aggregates for active user.",
)
async def get_rag_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RAGStatisticsResponse:
    stats = await rag_service.get_rag_statistics(db, current_user.id)
    return RAGStatisticsResponse.model_validate(stats)
