"""
Enterprise RAG AI Assistant — RAG Service
==========================================
Implements the core RAG pipeline: retrieval, context budgeting, reranking,
prompt template construction, LLM generation, citation generation, and DB logging.
"""

from __future__ import annotations

import datetime
import re
import time
import uuid
from typing import Any

import numpy as np
import tiktoken
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.core.logging import logger
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.rag_query import RagQuery
from app.services.llm_providers import LLMProviderError, get_llm_provider
from app.services.retrieval_service import RetrievalService


class Reranker:
    """
    Optional reranking layer that scores chunk candidates using:
      - Raw vector similarity score (70%)
      - Document freshness (20%) via exponential time decay
      - Metadata priority weighting (10%)
    """

    def rerank(
        self,
        query: str,
        results: list[tuple[Chunk, Document, float]],
    ) -> list[tuple[Chunk, Document, float]]:
        if not results:
            return []

        reranked_results = []
        now = datetime.datetime.now(datetime.UTC)

        for chunk, doc, score in results:
            # 1. Document Freshness (20%)
            # Calculate hours since the document was uploaded.
            # Convert doc.created_at to timezone-aware UTC if needed.
            doc_created = doc.created_at
            if doc_created.tzinfo is None:
                doc_created = doc_created.replace(tzinfo=datetime.UTC)

            hours_old = (now - doc_created).total_seconds() / 3600.0
            # Decay factor with a half-life of ~30 days (720 hours)
            freshness_weight = float(np.exp(-hours_old / 720.0))

            # 2. Metadata Weighting (10%)
            meta_weight = 0.0
            if chunk.chunk_metadata:
                verified = chunk.chunk_metadata.get("verified")
                priority = chunk.chunk_metadata.get("priority")
                importance = chunk.chunk_metadata.get("importance")

                if verified is True or str(verified).lower() == "true":
                    meta_weight = 1.0
                elif str(priority).lower() == "high":
                    meta_weight = 1.0
                elif str(importance).lower() == "critical":
                    meta_weight = 1.0

            # Combined score calculation
            reranked_score = (
                (score * 0.7) + (freshness_weight * 0.2) + (meta_weight * 0.1)
            )
            reranked_results.append((chunk, doc, float(reranked_score)))

        # Sort descending by the calculated reranked score
        reranked_results.sort(key=lambda x: x[2], reverse=True)
        return reranked_results


class RAGService:
    """
    Main RAG pipeline service orchestration class.
    """

    SYSTEM_PROMPT_TEMPLATE = (
        "You are a professional, helpful Enterprise AI Assistant.\n"
        "Analyze the user's question using ONLY the context passages below.\n"
        "Directives:\n"
        "1. Answer naturally, summarizing and reasoning over the retrieved context.\n"
        "2. Avoid hallucinations and do not use outside knowledge.\n"
        "3. If the context only partially supports the answer, clearly state what is supported and what is not, but answer to the best extent possible using the context. Do NOT simply say 'I don't have enough information' or refuse to answer.\n"
        "4. Always cite sources by appending the corresponding chunk index in brackets (e.g., [1], [2]) at the end of sentences where facts are drawn from that chunk.\n\n"
        "Context Passages:\n"
        "{context_str}\n"
    )

    USER_PROMPT_TEMPLATE = "User Question: {question}\n" "Answer:"

    def __init__(self) -> None:
        self.retrieval_service = RetrievalService()
        self.reranker = Reranker()
        try:
            self.tokenizer = tiktoken.get_encoding(settings.tokenizer_name)
        except Exception:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(self, text: str) -> int:
        """Count tokens in a string using tiktoken."""
        return len(self.tokenizer.encode(text))

    def _assemble_context(
        self,
        chunks: list[tuple[Chunk, Document, float]],
        max_tokens: int,
    ) -> tuple[str, list[tuple[Chunk, Document, float, int]]]:
        """
        Builds a token-budgeted context string while tracking indices for citation lookup.
        """
        current_tokens = 0
        context_blocks = []
        included_chunks = []

        for idx, (chunk, doc, score) in enumerate(chunks):
            # Format block text for LLM
            block = (
                f"--- Chunk [{idx + 1}] ---\n"
                f"Document: {doc.original_filename} (ID: {doc.id})\n"
                f"Page: {chunk.page_number}\n"
            )
            if chunk.section_title:
                block += f"Section: {chunk.section_title}\n"
            block += f"Content: {chunk.text}\n\n"

            # Check token counts
            block_tokens = self._count_tokens(block)
            if current_tokens + block_tokens > max_tokens:
                # Token budget reached, skip remaining chunks
                break

            current_tokens += block_tokens
            context_blocks.append(block)
            # Store chunk with its 1-indexed RAG index
            included_chunks.append((chunk, doc, score, idx + 1))

        context_str = "".join(context_blocks)
        return context_str, included_chunks

    def _generate_citations(
        self,
        answer_text: str,
        included_chunks: list[tuple[Chunk, Document, float, int]],
    ) -> list[dict[str, Any]]:
        """
        Parses chunk citation brackets (e.g. [1], [2]) from LLM response text
        and maps them to document metadata references.
        """
        # Find all brackets containing digits, e.g. [1]
        matches = re.findall(r"\[(\d+)\]", answer_text)
        cited_indices = sorted(list(set(int(m) for m in matches)))

        citations = []
        for idx in cited_indices:
            # Match 1-indexed citation pointer back to the chunk tuple
            match = next((item for item in included_chunks if item[3] == idx), None)
            if match:
                chunk, doc, score, _ = match
                citations.append(
                    {
                        "citation_index": idx,
                        "chunk_id": str(chunk.id),
                        "document_id": str(doc.id),
                        "document_title": doc.original_filename,
                        "page_number": chunk.page_number,
                        "section_title": chunk.section_title,
                        "text": chunk.text,
                        "score": score,
                    }
                )
        return citations

    async def execute_rag(
        self,
        db: AsyncSession,
        question: str,
        user_id: uuid.UUID,
        top_k: int | None = None,
        threshold: float = 0.0,
        filters: dict[str, Any] | None = None,
        use_reranker: bool = True,
        provider_name: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Orchestrate retrieval, context budget slicing, LLM call, citation lookup, and metric logging.
        """
        start_time = time.perf_counter()
        t_k = top_k or settings.rag_top_k
        p_name = provider_name or settings.llm_provider
        m_name = model_name or (
            settings.gemini_model
            if p_name.lower() == "gemini"
            else "gpt-4o-mini"
            if p_name.lower() == "openai"
            else "llama3"
        )

        # 1. Retrieval (Semantic/Hybrid search)
        retrieval_start = time.perf_counter()
        # Retrieve slightly more than top-k if reranking is enabled
        fetch_limit = t_k * 2 if use_reranker else t_k
        raw_chunks = await self.retrieval_service.execute_search(
            db=db,
            query_text=question,
            user_id=user_id,
            top_k=fetch_limit,
            threshold=threshold,
            search_type="hybrid",
            filters=filters,
            normalize_scores=True,
        )
        retrieval_latency = int((time.perf_counter() - retrieval_start) * 1000)

        # 2. Reranking (optional)
        if use_reranker and raw_chunks:
            chunks = self.reranker.rerank(question, raw_chunks)[:t_k]
        else:
            chunks = raw_chunks[:t_k]

        # Calculate average similarity as confidence indicator
        confidence_score = float(np.mean([c[2] for c in chunks])) if chunks else 0.0

        # 3. Context Assembly
        context_str, included_chunks = self._assemble_context(
            chunks=chunks,
            max_tokens=settings.rag_max_context_tokens,
        )

        # 4. Prompt Construction
        system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(context_str=context_str)
        user_prompt = self.USER_PROMPT_TEMPLATE.format(question=question)

        # 5. LLM Invocation
        llm_start = time.perf_counter()
        llm_provider = get_llm_provider(p_name, model=m_name)

        try:
            answer_text, token_usage = await llm_provider.generate_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=settings.rag_temperature,
                max_tokens=settings.rag_max_output_tokens,
            )
        except LLMProviderError as lpe:
            logger.error(f"RAG LLM execution failed: {lpe!s}")
            # Re-raise to let API exception handlers format correctly
            raise

        llm_latency = int((time.perf_counter() - llm_start) * 1000)

        # Record LLM latency metric
        from app.services.cache_service import cache_service

        await cache_service.record_latency("llm", float(llm_latency))

        # 6. Citation Generation
        citations = self._generate_citations(answer_text, included_chunks)
        total_latency = int((time.perf_counter() - start_time) * 1000)

        # 7. Persist metrics and query log to DB
        log_entry = RagQuery(
            user_id=user_id,
            query_text=question[:1020],
            answer_text=answer_text,
            provider=p_name.upper(),
            model_name=m_name,
            prompt_tokens=token_usage.get("prompt_tokens", 0),
            completion_tokens=token_usage.get("completion_tokens", 0),
            total_tokens=token_usage.get("total_tokens", 0),
            latency_ms=total_latency,
            confidence_score=confidence_score,
            citations=citations,
        )
        db.add(log_entry)
        await db.commit()

        # Format retrieved chunks schema output
        formatted_chunks = [
            {
                "chunk_id": str(c[0].id),
                "text": c[0].text,
                "page_number": c[0].page_number,
                "section_title": c[0].section_title,
                "document_id": str(c[1].id),
                "document_title": c[1].original_filename,
                "score": c[2],
            }
            for c in chunks
        ]

        return {
            "answer": answer_text,
            "citations": citations,
            "retrieved_chunks": formatted_chunks,
            "confidence_score": confidence_score,
            "latency": {
                "total_ms": total_latency,
                "retrieval_ms": retrieval_latency,
                "llm_ms": llm_latency,
            },
            "tokens_used": {
                "prompt_tokens": token_usage.get("prompt_tokens", 0),
                "completion_tokens": token_usage.get("completion_tokens", 0),
                "total_tokens": token_usage.get("total_tokens", 0),
            },
            "model_name": m_name,
            "provider": p_name.upper(),
        }

    async def get_rag_statistics(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> dict[str, Any]:
        """
        Compute analytic aggregates for user RAG executions.
        """
        # Count total
        count_stmt = select(func.count(RagQuery.id)).where(RagQuery.user_id == user_id)
        count_res = await db.execute(count_stmt)
        total_queries = count_res.scalar() or 0

        if total_queries == 0:
            return {
                "total_queries": 0,
                "average_latency_ms": 0.0,
                "total_tokens_used": 0,
                "provider_distribution": {"GEMINI": 0, "OPENAI": 0, "OLLAMA": 0},
            }

        # Average latency
        avg_stmt = select(func.avg(RagQuery.latency_ms)).where(
            RagQuery.user_id == user_id
        )
        avg_res = await db.execute(avg_stmt)
        avg_latency = float(avg_res.scalar() or 0.0)

        # Total tokens
        tokens_stmt = select(func.sum(RagQuery.total_tokens)).where(
            RagQuery.user_id == user_id
        )
        tokens_res = await db.execute(tokens_stmt)
        total_tokens = int(tokens_res.scalar() or 0)

        # Provider distribution
        provider_stmt = (
            select(RagQuery.provider, func.count(RagQuery.id))
            .where(RagQuery.user_id == user_id)
            .group_by(RagQuery.provider)
        )
        provider_res = await db.execute(provider_stmt)
        dist = {row[0]: row[1] for row in provider_res.all()}

        return {
            "total_queries": total_queries,
            "average_latency_ms": round(avg_latency, 2),
            "total_tokens_used": total_tokens,
            "provider_distribution": {
                "GEMINI": dist.get("GEMINI", 0),
                "OPENAI": dist.get("OPENAI", 0),
                "OLLAMA": dist.get("OLLAMA", 0),
            },
        }
