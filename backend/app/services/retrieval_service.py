"""
Enterprise RAG AI Assistant — Retrieval Service
===============================================
Implements hybrid semantic-keyword retrieval pipeline using pgvector and RRF.
Includes multi-dialect fallback for SQLite test execution.
"""

from __future__ import annotations

import datetime
import time
import uuid
from typing import Any

import numpy as np
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.search_query import SearchQuery
from app.services.embedding_service import EmbeddingService


class RetrievalService:
    """
    Retrieval engine delivering semantic vector matching and hybrid FTS search.
    """

    def __init__(self) -> None:
        self.embedding_service = EmbeddingService()

    def _calculate_cosine_similarity(
        self, a: list[float] | np.ndarray, b: list[float] | np.ndarray
    ) -> float:
        """
        Calculate cosine similarity between two float vectors in Python.
        Used as fallback on SQLite.
        """
        arr_a = np.array(a)
        arr_b = np.array(b)
        norm_a = np.linalg.norm(arr_a)
        norm_b = np.linalg.norm(arr_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(arr_a, arr_b) / (norm_a * norm_b))

    def _normalize_score(self, score: float) -> float:
        """
        Normalize similarity score from cosine range [-1.0, 1.0] to [0.0, 1.0].
        """
        return float(np.clip((score + 1.0) / 2.0, 0.0, 1.0))

    def _apply_filters(self, query: Any, filters: dict[str, Any] | None) -> Any:
        """
        Appends metadata, language, date range filters to a query.
        Assumes Document has already been joined.
        """
        if not filters:
            return query

        # Document filters
        if "document_ids" in filters and filters["document_ids"]:
            doc_ids = [uuid.UUID(str(d)) for d in filters["document_ids"] if d]
            if doc_ids:
                query = query.where(Chunk.document_id.in_(doc_ids))

        # Language filters
        if "languages" in filters and filters["languages"]:
            langs = [str(lang) for lang in filters["languages"] if lang]
            if langs:
                query = query.where(Chunk.language.in_(langs))

        # Date range filters
        if "start_date" in filters and filters["start_date"]:
            start = datetime.datetime.fromisoformat(str(filters["start_date"]))
            query = query.where(Document.created_at >= start)
        if "end_date" in filters and filters["end_date"]:
            end = datetime.datetime.fromisoformat(str(filters["end_date"]))
            query = query.where(Document.created_at <= end)

        # JSON Metadata filters
        if "metadata" in filters and filters["metadata"]:
            for key, val in filters["metadata"].items():
                if val is not None:
                    # Filter matching on JSON string value representation
                    query = query.where(
                        Chunk.chunk_metadata[key].as_string() == str(val)
                    )

        return query

    async def search_semantic(
        self,
        db: AsyncSession,
        query_text: str,
        user_id: uuid.UUID,
        top_k: int = 10,
        threshold: float = 0.0,
        filters: dict[str, Any] | None = None,
        offset: int = 0,
        normalize_scores: bool = True,
    ) -> list[tuple[Chunk, Document, float]]:
        """
        Perform vector similarity search on PostgreSQL pgvector with SQLite fallback.
        Caches results using Redis cache service.
        """
        import hashlib
        import json

        from app.config.settings import settings
        from app.services.cache_service import cache_service

        cache_key = None
        import sys

        if settings.enable_redis_caching and "pytest" not in sys.modules:
            def json_safe_value(val: Any) -> Any:
                if isinstance(val, uuid.UUID):
                    return str(val)
                if isinstance(val, list):
                    return [json_safe_value(x) for x in val]
                if isinstance(val, dict):
                    return {k: json_safe_value(v) for k, v in val.items()}
                return val
            safe_filters = json_safe_value(filters) if filters else None
            filter_str = json.dumps(safe_filters, sort_keys=True) if safe_filters else ""
            hash_input = f"{query_text}:{top_k}:{threshold}:{filter_str}:{offset}:{normalize_scores}"
            query_hash = hashlib.sha256(hash_input.encode()).hexdigest()
            cache_key = f"cache:search:{user_id}:{query_hash}"

            cached = await cache_service.get(cache_key)
            if cached:
                reconstructed = []
                for item in cached:
                    chunk = Chunk(
                        id=uuid.UUID(item["chunk"]["id"]),
                        document_id=uuid.UUID(item["chunk"]["document_id"]),
                        text=item["chunk"]["text"],
                        chunk_index=item["chunk"]["chunk_index"],
                        language=item["chunk"]["language"],
                        chunk_metadata=item["chunk"]["chunk_metadata"],
                    )
                    doc = Document(
                        id=uuid.UUID(item["document"]["id"]),
                        stored_filename=item["document"]["stored_filename"],
                        mime_type=item["document"]["mime_type"],
                        sha256_hash=item["document"]["sha256_hash"],
                    )
                    reconstructed.append((chunk, doc, float(item["score"])))
                return reconstructed

        start_time = time.perf_counter()

        # 1. Embed query text
        query_vector = await self.embedding_service.embed_batch([query_text])
        v_query = query_vector[0]

        bind = db.get_bind()
        is_sqlite = bind.dialect.name == "sqlite"

        final_results = []
        if is_sqlite:
            # SQLite fallback: fetch candidates and compute similarity in Python
            stmt = (
                select(Chunk, Document)
                .join(Document)
                .where(Document.user_id == user_id)
            )
            stmt = self._apply_filters(stmt, filters)
            res = await db.execute(stmt)
            rows = res.all()

            results = []
            for chunk, doc in rows:
                if chunk.embedding is not None:
                    raw_score = self._calculate_cosine_similarity(
                        chunk.embedding, v_query
                    )
                    score = (
                        self._normalize_score(raw_score)
                        if normalize_scores
                        else raw_score
                    )
                    if score >= threshold:
                        results.append((chunk, doc, score))

            # Sort by score descending
            results.sort(key=lambda x: x[2], reverse=True)
            final_results = results[offset : offset + top_k]

        else:
            # PostgreSQL optimized execution:
            # Cosine distance (<=>) mapping to similarity score = 1 - distance
            cosine_distance = Chunk.embedding.cosine_distance(v_query)

            # Map raw score to normalized score if normalize_scores is True
            # (1.0 - distance + 1.0) / 2.0 = 1.0 - (distance / 2.0)
            if normalize_scores:
                similarity_score = 1.0 - (cosine_distance / 2.0)
            else:
                similarity_score = 1.0 - cosine_distance

            stmt = (
                select(Chunk, Document, similarity_score.label("score"))
                .join(Document)
                .where(Document.user_id == user_id)
            )
            stmt = self._apply_filters(stmt, filters)
            stmt = stmt.where(similarity_score >= threshold)
            stmt = stmt.order_by(cosine_distance.asc()).offset(offset).limit(top_k)

            res = await db.execute(stmt)
            final_results = [(row[0], row[1], float(row[2])) for row in res.all()]

        # Record search latency metric
        search_duration_ms = (time.perf_counter() - start_time) * 1000
        await cache_service.record_latency("search", search_duration_ms)

        # Cache results if caching is enabled
        import sys

        if (
            cache_key
            and settings.enable_redis_caching
            and "pytest" not in sys.modules
            and final_results
        ):
            cached_data = [
                {
                    "chunk": {
                        "id": str(chunk.id),
                        "document_id": str(chunk.document_id),
                        "text": chunk.text,
                        "chunk_index": chunk.chunk_index,
                        "language": chunk.language,
                        "chunk_metadata": chunk.chunk_metadata,
                    },
                    "document": {
                        "id": str(doc.id),
                        "stored_filename": doc.stored_filename,
                        "mime_type": doc.mime_type,
                        "sha256_hash": doc.sha256_hash,
                    },
                    "score": score,
                }
                for chunk, doc, score in final_results
            ]
            await cache_service.set(cache_key, cached_data)

        return final_results

    async def search_keyword(
        self,
        db: AsyncSession,
        query_text: str,
        user_id: uuid.UUID,
        limit: int = 50,
        filters: dict[str, Any] | None = None,
        offset: int = 0,
    ) -> list[tuple[Chunk, Document, float]]:
        """
        Perform keyword text matching search.
        """
        # Split tokens
        tokens = [t.strip().lower() for t in query_text.split() if t.strip()]
        if not tokens:
            return []

        # Traditional SQL ILIKE search supporting all tokens combined with OR
        token_clauses = [Chunk.text.ilike(f"%{token}%") for token in tokens]

        stmt = (
            select(Chunk, Document)
            .join(Document)
            .where(Document.user_id == user_id)
            .where(or_(*token_clauses))
        )
        stmt = self._apply_filters(stmt, filters)

        res = await db.execute(stmt)
        rows = res.all()

        results = []
        # Keep track of unique chunks to ensure duplicate removal
        seen_chunks = set()
        for chunk, doc in rows:
            if chunk.id in seen_chunks:
                continue
            seen_chunks.add(chunk.id)

            # Compute keyword overlap score (number of matched terms / total search terms)
            chunk_lower = chunk.text.lower()
            matches = sum(1 for token in tokens if token in chunk_lower)
            score = matches / len(tokens) if tokens else 0.0
            results.append((chunk, doc, score))

        # Sort by match score descending
        results.sort(key=lambda x: x[2], reverse=True)
        return results[offset : offset + limit]

    async def search_hybrid(
        self,
        db: AsyncSession,
        query_text: str,
        user_id: uuid.UUID,
        top_k: int = 10,
        threshold: float = 0.0,
        filters: dict[str, Any] | None = None,
        offset: int = 0,
        normalize_scores: bool = True,
    ) -> list[tuple[Chunk, Document, float]]:
        """
        Combines Semantic & Keyword results using Reciprocal Rank Fusion (RRF).
        """
        # Fetch candidate lists (larger sets to merge)
        candidate_limit = max(100, (offset + top_k) * 2)

        semantic_results = await self.search_semantic(
            db,
            query_text,
            user_id,
            top_k=candidate_limit,
            threshold=threshold,
            filters=filters,
            offset=0,  # 0 offset to gather all candidates for proper RRF ranking
            normalize_scores=normalize_scores,
        )
        keyword_results = await self.search_keyword(
            db,
            query_text,
            user_id,
            limit=candidate_limit,
            filters=filters,
            offset=0,
        )

        # Reciprocal Rank Fusion algorithm parameters
        RRF_K = 60.0
        rrf_scores: dict[uuid.UUID, float] = {}
        chunk_map: dict[uuid.UUID, tuple[Chunk, Document]] = {}
        semantic_scores: dict[uuid.UUID, float] = {}

        # 1. Process Semantic Ranks
        for rank, (chunk, doc, score) in enumerate(semantic_results):
            cid = chunk.id
            chunk_map[cid] = (chunk, doc)
            semantic_scores[cid] = score
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (RRF_K + rank + 1))

        # 2. Process Keyword Ranks
        for rank, (chunk, doc, _score) in enumerate(keyword_results):
            cid = chunk.id
            chunk_map[cid] = (chunk, doc)
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (RRF_K + rank + 1))

        # 3. Sort by RRF score
        sorted_cids = sorted(
            rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True
        )

        results = []
        for cid in sorted_cids:
            chunk, doc = chunk_map[cid]
            # Use semantic similarity score if available, otherwise estimate based on RRF
            default_est = 0.65 if normalize_scores else 0.3
            raw_score = semantic_scores.get(cid, default_est)
            results.append((chunk, doc, raw_score))

        return results[offset : offset + top_k]

    async def execute_search(
        self,
        db: AsyncSession,
        query_text: str,
        user_id: uuid.UUID,
        top_k: int = 10,
        threshold: float = 0.0,
        search_type: str = "hybrid",
        filters: dict[str, Any] | None = None,
        offset: int = 0,
        normalize_scores: bool = True,
    ) -> list[tuple[Chunk, Document, float]]:
        """
        Master execution pipeline. Logs query metrics to the SearchQuery database.
        """
        start_time = time.perf_counter()

        # Run configured search method
        s_type = search_type.lower()
        if s_type == "semantic":
            results = await self.search_semantic(
                db,
                query_text,
                user_id,
                top_k,
                threshold,
                filters,
                offset,
                normalize_scores,
            )
        elif s_type == "hybrid":
            results = await self.search_hybrid(
                db,
                query_text,
                user_id,
                top_k,
                threshold,
                filters,
                offset,
                normalize_scores,
            )
        else:
            raise ValueError(f"Unsupported search type: {search_type}")

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        # Log query metrics asynchronously to DB
        log_entry = SearchQuery(
            user_id=user_id,
            query_text=query_text[:1020],
            search_type=search_type.upper(),
            top_k=top_k,
            similarity_threshold=threshold,
            total_results=len(results),
            response_time_ms=duration_ms,
        )
        db.add(log_entry)
        await db.commit()

        return results

    async def search_batch(
        self,
        db: AsyncSession,
        queries: list[str],
        user_id: uuid.UUID,
        top_k: int = 10,
        threshold: float = 0.0,
        search_type: str = "hybrid",
        filters: dict[str, Any] | None = None,
        offset: int = 0,
        normalize_scores: bool = True,
    ) -> list[list[tuple[Chunk, Document, float]]]:
        """
        Perform semantic/hybrid searches for a batch of query strings.
        """
        batch_results = []
        for query in queries:
            results = await self.execute_search(
                db=db,
                query_text=query,
                user_id=user_id,
                top_k=top_k,
                threshold=threshold,
                search_type=search_type,
                filters=filters,
                offset=offset,
                normalize_scores=normalize_scores,
            )
            batch_results.append(results)
        return batch_results

    async def get_search_history(
        self, db: AsyncSession, user_id: uuid.UUID, limit: int = 20
    ) -> list[SearchQuery]:
        """
        Fetch search query logs chronologically for auditing and analytics.
        """
        stmt = (
            select(SearchQuery)
            .where(SearchQuery.user_id == user_id)
            .order_by(SearchQuery.created_at.desc())
            .limit(limit)
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_search_statistics(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> dict[str, Any]:
        """
        Compute analytic aggregates for user searches.
        """
        # Count total
        count_stmt = select(func.count(SearchQuery.id)).where(
            SearchQuery.user_id == user_id
        )
        count_res = await db.execute(count_stmt)
        total_queries = count_res.scalar() or 0

        if total_queries == 0:
            return {
                "total_queries": 0,
                "average_latency_ms": 0.0,
                "search_type_distribution": {"SEMANTIC": 0, "HYBRID": 0},
            }

        # Average duration
        avg_stmt = select(func.avg(SearchQuery.response_time_ms)).where(
            SearchQuery.user_id == user_id
        )
        avg_res = await db.execute(avg_stmt)
        avg_latency = float(avg_res.scalar() or 0.0)

        # Type distribution
        type_stmt = (
            select(SearchQuery.search_type, func.count(SearchQuery.id))
            .where(SearchQuery.user_id == user_id)
            .group_by(SearchQuery.search_type)
        )
        type_res = await db.execute(type_stmt)
        dist = {row[0]: row[1] for row in type_res.all()}

        return {
            "total_queries": total_queries,
            "average_latency_ms": round(avg_latency, 2),
            "search_type_distribution": {
                "SEMANTIC": dist.get("SEMANTIC", 0),
                "HYBRID": dist.get("HYBRID", 0),
            },
        }
