"""
Enterprise RAG AI Assistant — Semantic Search Tool
====================================================
Searches enterprise documents using pgvector cosine similarity.
Delegates entirely to the existing RetrievalService — no raw DB access.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_tool import BaseTool, ParameterSpec, PermissionLevel, ToolResult
from app.services.retrieval_service import RetrievalService


class SemanticSearchTool(BaseTool):
    """
    Search enterprise knowledge base using semantic vector similarity.

    Returns ranked text chunks with confidence scores and document metadata.
    """

    id = "semantic_search"
    name = "Semantic Document Search"
    description = (
        "Search the enterprise document knowledge base using semantic similarity. "
        "Use this to retrieve relevant text chunks for any factual question. "
        "Returns up to top_k results ranked by confidence score."
    )
    permission_level = PermissionLevel.USER
    parameters = [
        ParameterSpec(
            name="query",
            type="string",
            description="The natural-language search query.",
            required=True,
        ),
        ParameterSpec(
            name="top_k",
            type="integer",
            description="Maximum number of results to return (1–20).",
            required=False,
            default=5,
            minimum=1,
            maximum=20,
        ),
        ParameterSpec(
            name="threshold",
            type="number",
            description="Minimum similarity score threshold (0.0–1.0).",
            required=False,
            default=0.0,
            minimum=0.0,
            maximum=1.0,
        ),
    ]

    def __init__(self) -> None:
        self._retrieval = RetrievalService()

    async def _run(
        self,
        params: dict[str, Any],
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> ToolResult:
        query: str = params["query"]
        top_k: int = params["top_k"]
        threshold: float = params["threshold"]

        results = await self._retrieval.search_semantic(
            db=db,
            query_text=query,
            user_id=user_id,
            top_k=top_k,
            threshold=threshold,
            normalize_scores=True,
        )

        chunks_out = []
        for chunk, doc, score in results:
            chunks_out.append(
                {
                    "chunk_id": str(chunk.id),
                    "document_id": str(doc.id),
                    "document_name": doc.original_filename,
                    "page_number": chunk.page_number,
                    "section_title": chunk.section_title,
                    "text": chunk.text,
                    "score": round(score, 4),
                    "language": chunk.language,
                    "chunk_index": chunk.chunk_index,
                }
            )

        return ToolResult(
            success=True,
            output=chunks_out,
            metadata={
                "query": query,
                "total_results": len(chunks_out),
                "top_k": top_k,
                "threshold": threshold,
            },
        )
