"""
Enterprise RAG AI Assistant — Search API Routing
================================================
Exposes search execution pipeline, query history tracking, and analytics.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_active_user
from app.models.user import User
from app.schemas.search import (
    SearchBatchRequest,
    SearchQueryResponse,
    SearchRequest,
    SearchResultItem,
    SearchStatisticsResponse,
)
from app.services.retrieval_service import RetrievalService

router = APIRouter()
retrieval_service = RetrievalService()


@router.post(
    "",
    response_model=list[SearchResultItem],
    status_code=status.HTTP_200_OK,
    summary="Execute global hybrid search.",
    description="Run semantic vector cosine similarity matching combined with SQL FTS text keyword ranking.",
)
async def global_search(
    payload: SearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[SearchResultItem]:
    # Run retrieval engine
    raw_results = await retrieval_service.execute_search(
        db=db,
        query_text=payload.query,
        user_id=current_user.id,
        top_k=payload.top_k,
        threshold=payload.threshold,
        search_type=payload.search_type,
        filters=payload.filters.model_dump() if payload.filters else None,
        offset=payload.offset,
    )

    # Format output items
    from app.schemas.chunk import ChunkResponse
    from app.schemas.document import DocumentResponse

    return [
        SearchResultItem(
            chunk=ChunkResponse.model_validate(chunk),
            document=DocumentResponse.model_validate(doc),
            score=score,
        )
        for chunk, doc, score in raw_results
    ]


@router.post(
    "/batch",
    response_model=list[list[SearchResultItem]],
    status_code=status.HTTP_200_OK,
    summary="Execute batch hybrid search queries.",
    description="Run search retrieval concurrently/sequentially for a list of input query strings.",
)
async def batch_search(
    payload: SearchBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[list[SearchResultItem]]:
    raw_batch_results = await retrieval_service.search_batch(
        db=db,
        queries=payload.queries,
        user_id=current_user.id,
        top_k=payload.top_k,
        threshold=payload.threshold,
        search_type=payload.search_type,
        filters=payload.filters.model_dump() if payload.filters else None,
        offset=payload.offset,
    )

    from app.schemas.chunk import ChunkResponse
    from app.schemas.document import DocumentResponse

    return [
        [
            SearchResultItem(
                chunk=ChunkResponse.model_validate(chunk),
                document=DocumentResponse.model_validate(doc),
                score=score,
            )
            for chunk, doc, score in query_results
        ]
        for query_results in raw_batch_results
    ]


@router.get(
    "/history",
    response_model=list[SearchQueryResponse],
    status_code=status.HTTP_200_OK,
    summary="Retrieve user search log history.",
    description="Returns previous search query requests executed by the active user.",
)
async def get_search_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[SearchQueryResponse]:
    history = await retrieval_service.get_search_history(db, current_user.id)
    return [SearchQueryResponse.model_validate(item) for item in history]


@router.get(
    "/statistics",
    response_model=SearchStatisticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve user search statistics.",
    description="Returns usage aggregate analytics and performance metrics for the logged-in user.",
)
async def get_search_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SearchStatisticsResponse:
    stats = await retrieval_service.get_search_statistics(db, current_user.id)
    return SearchStatisticsResponse.model_validate(stats)
