"""
Enterprise RAG AI Assistant — Phase 8 Semantic Retrieval Unit & Integration Tests
=============================================================================
Validates RetrievalService, RRF hybrid ranking, query metadata filters,
user ownership scope, search analytics, and REST API endpoints.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User
from app.services.retrieval_service import RetrievalService
from tests.test_documents import _register_and_login


@pytest.fixture()
def mock_vector() -> list[float]:
    return [0.1] * 768


# ── Retrieval Service Tests ───────────────────────────────────────────────────
class TestRetrievalService:
    @pytest.mark.asyncio
    async def test_semantic_retrieval_ranking_mocked(
        self,
        db_session: AsyncSession,
        mock_vector: list[float],
    ) -> None:
        """Validate vector search distance calculation and sorting on SQLite fallback."""
        user_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        # Insert test document and chunks
        doc = Document(
            id=doc_id,
            user_id=user_id,
            original_filename="search_doc.txt",
            stored_filename="search_doc.txt",
            mime_type="text/plain",
            file_size=100,
            sha256_hash="hashsearchdoc",
            storage_path="/tmp/search_doc.txt",
            processing_status="COMPLETED",
        )
        # Closer vector chunk
        c1 = Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            text="High similarity semantic text chunk.",
            token_count=5,
            character_count=35,
            word_count=5,
            reading_time_estimate=1.0,
            sha256_hash="hashc1_search",
            embedding=[0.1] * 768,  # Exactly matches query vector
        )
        # Opposing vector chunk
        c2 = Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=1,
            text="Low similarity vector chunk.",
            token_count=4,
            character_count=28,
            word_count=4,
            reading_time_estimate=1.0,
            sha256_hash="hashc2_search",
            embedding=[-0.1] * 768,  # Opposite polarity
        )
        db_session.add_all([doc, c1, c2])
        await db_session.commit()

        # Run semantic search query with patched embedding service
        service = RetrievalService()
        with patch.object(
            service.embedding_service, "embed_batch", return_value=[mock_vector]
        ) as mock_embed:
            results = await service.search_semantic(
                db=db_session,
                query_text="High similarity semantic text chunk.",
                user_id=user_id,
                top_k=2,
                threshold=-1.1,  # Set negative to avoid pruning opposing vector (-1.0 score)
                normalize_scores=False,
            )
            mock_embed.assert_called_once()

        assert len(results) == 2
        # Verify rank order (c1 must be first due to high cosine similarity)
        assert results[0][0].id == c1.id
        assert results[0][2] > 0.9  # Close to 1.0 (identical)
        assert results[1][0].id == c2.id
        assert results[1][2] < 0.0  # Opposite polarity similarity is -1.0

    @pytest.mark.asyncio
    async def test_retrieval_filtering_and_ownership(
        self,
        db_session: AsyncSession,
        mock_vector: list[float],
    ) -> None:
        """Validate document, language, and user ownership query filtering constraint scopes."""
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        doc_a = uuid.uuid4()
        doc_b = uuid.uuid4()

        # Create two documents with different users
        d_a = Document(
            id=doc_a,
            user_id=user_a,
            original_filename="user_a_doc.txt",
            stored_filename="user_a_doc.txt",
            mime_type="text/plain",
            file_size=50,
            sha256_hash="hash_a",
            storage_path="/tmp/user_a_doc.txt",
            processing_status="COMPLETED",
        )
        d_b = Document(
            id=doc_b,
            user_id=user_b,
            original_filename="user_b_doc.txt",
            stored_filename="user_b_doc.txt",
            mime_type="text/plain",
            file_size=50,
            sha256_hash="hash_b",
            storage_path="/tmp/user_b_doc.txt",
            processing_status="COMPLETED",
        )

        c_a = Chunk(
            id=uuid.uuid4(),
            document_id=doc_a,
            chunk_index=0,
            text="Secret query code segment alpha.",
            token_count=5,
            character_count=32,
            word_count=5,
            reading_time_estimate=1.0,
            sha256_hash="hash_ca",
            language="en",
            chunk_metadata={"department": "HR"},
            embedding=mock_vector,
        )
        c_b = Chunk(
            id=uuid.uuid4(),
            document_id=doc_b,
            chunk_index=0,
            text="Secret query code segment beta.",
            token_count=5,
            character_count=31,
            word_count=5,
            reading_time_estimate=1.0,
            sha256_hash="hash_cb",
            language="fr",
            chunk_metadata={"department": "finance"},
            embedding=mock_vector,
        )
        db_session.add_all([d_a, d_b, c_a, c_b])
        await db_session.commit()

        service = RetrievalService()

        # Mock the embedding generator to return query vector matching c_a/c_b
        with patch.object(
            service.embedding_service, "embed_batch", return_value=[mock_vector]
        ):
            # 1. Ownership test: User A search should NEVER return User B's chunk
            res_owner = await service.search_semantic(
                db=db_session, query_text="Secret query", user_id=user_a
            )
            assert len(res_owner) == 1
            assert res_owner[0][0].id == c_a.id

            # 2. Metadata filtering test
            res_meta = await service.search_semantic(
                db=db_session,
                query_text="Secret query",
                user_id=user_a,
                filters={
                    "metadata": {"department": "finance"}
                },  # Department mismatches
            )
            assert len(res_meta) == 0

            # 3. Language filtering test
            res_lang = await service.search_semantic(
                db=db_session,
                query_text="Secret query",
                user_id=user_a,
                filters={"languages": ["fr"]},  # French mismatch for user A's chunk
            )
            assert len(res_lang) == 0

    @pytest.mark.asyncio
    async def test_score_normalization_scaling(
        self,
        db_session: AsyncSession,
        mock_vector: list[float],
    ) -> None:
        """Verify that score normalization maps scores from raw cosine range [-1.0, 1.0] to [0.0, 1.0]."""
        user_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            user_id=user_id,
            original_filename="norm_doc.txt",
            stored_filename="norm_doc.txt",
            mime_type="text/plain",
            file_size=100,
            sha256_hash="hashnormdoc",
            storage_path="/tmp/norm_doc.txt",
            processing_status="COMPLETED",
        )
        c1 = Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            text="Identical chunk.",
            token_count=2,
            character_count=15,
            word_count=2,
            reading_time_estimate=1.0,
            sha256_hash="hashnorm1",
            embedding=[0.1] * 768,
        )
        c2 = Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=1,
            text="Opposing chunk.",
            token_count=2,
            character_count=15,
            word_count=2,
            reading_time_estimate=1.0,
            sha256_hash="hashnorm2",
            embedding=[-0.1] * 768,
        )
        db_session.add_all([doc, c1, c2])
        await db_session.commit()

        service = RetrievalService()
        with patch.object(
            service.embedding_service, "embed_batch", return_value=[mock_vector]
        ):
            results = await service.search_semantic(
                db=db_session,
                query_text="Identical chunk.",
                user_id=user_id,
                top_k=2,
                threshold=0.0,
                normalize_scores=True,
            )
        assert len(results) == 2
        # Identical vector: raw similarity = 1.0 -> normalized = 1.0
        assert abs(results[0][2] - 1.0) < 1e-5
        # Opposing vector: raw similarity = -1.0 -> normalized = 0.0
        assert abs(results[1][2] - 0.0) < 1e-5

    @pytest.mark.asyncio
    async def test_offset_pagination_sqlite(
        self,
        db_session: AsyncSession,
        mock_vector: list[float],
    ) -> None:
        """Verify that offset pagination retrieves the correct subset of chunks."""
        user_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            user_id=user_id,
            original_filename="pag_doc.txt",
            stored_filename="pag_doc.txt",
            mime_type="text/plain",
            file_size=100,
            sha256_hash="hashpagdoc",
            storage_path="/tmp/pag_doc.txt",
            processing_status="COMPLETED",
        )
        # Create 5 chunks with varying embeddings
        chunks = [
            Chunk(
                id=uuid.uuid4(),
                document_id=doc_id,
                chunk_index=i,
                text=f"Chunk number {i}",
                token_count=3,
                character_count=14,
                word_count=3,
                reading_time_estimate=1.0,
                sha256_hash=f"hashpag{i}",
                embedding=[0.1 + (i * 0.05)] * 768,
            )
            for i in range(5)
        ]
        db_session.add(doc)
        db_session.add_all(chunks)
        await db_session.commit()

        service = RetrievalService()
        with patch.object(
            service.embedding_service, "embed_batch", return_value=[mock_vector]
        ):
            # Get Page 1 (top_k=2, offset=0)
            res_p1 = await service.search_semantic(
                db=db_session,
                query_text="Query",
                user_id=user_id,
                top_k=2,
                offset=0,
                threshold=0.0,
            )
            # Get Page 2 (top_k=2, offset=2)
            res_p2 = await service.search_semantic(
                db=db_session,
                query_text="Query",
                user_id=user_id,
                top_k=2,
                offset=2,
                threshold=0.0,
            )

        assert len(res_p1) == 2
        assert len(res_p2) == 2
        # Ensure chunks in page 1 and page 2 are different (no intersection)
        p1_ids = {c[0].id for c in res_p1}
        p2_ids = {c[0].id for c in res_p2}
        assert p1_ids.isdisjoint(p2_ids)

    @pytest.mark.asyncio
    async def test_batch_query_searches(
        self,
        db_session: AsyncSession,
        mock_vector: list[float],
    ) -> None:
        """Verify that search_batch runs searches for multiple queries correctly."""
        user_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            user_id=user_id,
            original_filename="batch_doc.txt",
            stored_filename="batch_doc.txt",
            mime_type="text/plain",
            file_size=100,
            sha256_hash="hashbatchdoc",
            storage_path="/tmp/batch_doc.txt",
            processing_status="COMPLETED",
        )
        c1 = Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            text="First search term target.",
            token_count=4,
            character_count=25,
            word_count=4,
            reading_time_estimate=1.0,
            sha256_hash="hashbatchc1",
            embedding=mock_vector,
        )
        db_session.add_all([doc, c1])
        await db_session.commit()

        service = RetrievalService()
        with patch.object(
            service.embedding_service, "embed_batch", return_value=[mock_vector]
        ):
            batch_res = await service.search_batch(
                db=db_session,
                queries=["First query", "Second query"],
                user_id=user_id,
                top_k=1,
            )
        assert len(batch_res) == 2
        assert len(batch_res[0]) == 1
        assert batch_res[0][0][0].id == c1.id

    @pytest.mark.asyncio
    async def test_duplicate_removal(
        self,
        db_session: AsyncSession,
        mock_vector: list[float],
    ) -> None:
        """Verify that duplicate chunks are correctly removed from keyword and hybrid search."""
        user_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            user_id=user_id,
            original_filename="dup_doc.txt",
            stored_filename="dup_doc.txt",
            mime_type="text/plain",
            file_size=100,
            sha256_hash="hashdupdoc",
            storage_path="/tmp/dup_doc.txt",
            processing_status="COMPLETED",
        )
        c1 = Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            text="Duplicate query term keyword matching chunk text.",
            token_count=7,
            character_count=50,
            word_count=7,
            reading_time_estimate=1.0,
            sha256_hash="hashdupc1",
            embedding=mock_vector,
        )
        db_session.add_all([doc, c1])
        await db_session.commit()

        service = RetrievalService()
        with patch.object(
            service.embedding_service, "embed_batch", return_value=[mock_vector]
        ):
            # Test keyword duplicate removal: should return at most 1 item even if query matches multiple ways
            kw_results = await service.search_keyword(
                db=db_session,
                query_text="Duplicate query term keyword matching chunk text",
                user_id=user_id,
                limit=10,
            )
            # Test hybrid duplicate removal
            hybrid_results = await service.search_hybrid(
                db=db_session,
                query_text="Duplicate query term keyword matching chunk text",
                user_id=user_id,
                top_k=10,
            )
        assert len(kw_results) == 1
        assert len(hybrid_results) == 1


# ── REST API Integration Tests ────────────────────────────────────────────────
class TestRetrievalAPI:
    @pytest.mark.asyncio
    async def test_search_api_endpoints_mocked(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        mock_vector: list[float],
    ) -> None:
        """Validate global and document search, history auditing, and statistics endpoints."""
        # 1. Login
        token = await _register_and_login(client, "searchapi@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Setup user and database document
        result_user = await db_session.execute(
            select(User).where(User.email == "searchapi@example.com")
        )
        user = result_user.scalar_one()

        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            user_id=user.id,
            original_filename="api_search_doc.txt",
            stored_filename="api_search_doc.txt",
            mime_type="text/plain",
            file_size=100,
            sha256_hash="hashapisearch",
            storage_path="/tmp/api_search_doc.txt",
            processing_status="COMPLETED",
        )
        c1 = Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            text="Enterprise hybrid search logic API test.",
            token_count=6,
            character_count=40,
            word_count=6,
            reading_time_estimate=1.0,
            sha256_hash="hashapichunksearch",
            language="en",
            embedding=mock_vector,
        )
        db_session.add_all([doc, c1])
        await db_session.commit()

        # 3. Test global search endpoint POST /api/v1/search
        search_payload = {
            "query": "hybrid search logic",
            "top_k": 5,
            "threshold": 0.1,
            "search_type": "hybrid",
            "filters": {"languages": ["en"]},
        }

        # Patch the embedding service used inside endpoints
        with patch(
            "app.services.embedding_service.EmbeddingService.embed_batch",
            return_value=[mock_vector],
        ):
            resp = await client.post(
                "/api/v1/search", json=search_payload, headers=headers
            )
            assert resp.status_code == 200, resp.text
            results = resp.json()
            assert len(results) == 1
            assert results[0]["chunk"]["id"] == str(c1.id)
            assert results[0]["document"]["id"] == str(doc_id)
            assert "score" in results[0]

            # 4. Test document search endpoint POST /api/v1/documents/{id}/search
            resp_doc = await client.post(
                f"/api/v1/documents/{doc_id}/search",
                json={"query": "hybrid search logic", "top_k": 2},
                headers=headers,
            )
            assert resp_doc.status_code == 200, resp_doc.text
            doc_results = resp_doc.json()
            assert len(doc_results) == 1

        # 5. Test search history GET /api/v1/search/history
        resp_hist = await client.get("/api/v1/search/history", headers=headers)
        assert resp_hist.status_code == 200
        history = resp_hist.json()
        # Verify that the searches we ran above were logged
        assert len(history) >= 2
        assert history[0]["query_text"] == "hybrid search logic"

        # 6. Test search statistics GET /api/v1/search/statistics
        resp_stats = await client.get("/api/v1/search/statistics", headers=headers)
        assert resp_stats.status_code == 200
        stats = resp_stats.json()
        assert stats["total_queries"] >= 2
        assert stats["average_latency_ms"] >= 0.0
        assert "HYBRID" in stats["search_type_distribution"]

    @pytest.mark.asyncio
    async def test_batch_search_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        mock_vector: list[float],
    ) -> None:
        """Validate batch search execution API endpoint POST /api/v1/search/batch."""
        token = await _register_and_login(client, "batchapi@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        result_user = await db_session.execute(
            select(User).where(User.email == "batchapi@example.com")
        )
        user = result_user.scalar_one()

        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            user_id=user.id,
            original_filename="api_batch_doc.txt",
            stored_filename="api_batch_doc.txt",
            mime_type="text/plain",
            file_size=100,
            sha256_hash="hashapibatch",
            storage_path="/tmp/api_batch_doc.txt",
            processing_status="COMPLETED",
        )
        c1 = Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            text="Enterprise batch search query logic API test.",
            token_count=7,
            character_count=45,
            word_count=7,
            reading_time_estimate=1.0,
            sha256_hash="hashapichunkbatch",
            language="en",
            embedding=mock_vector,
        )
        db_session.add_all([doc, c1])
        await db_session.commit()

        batch_payload = {
            "queries": ["batch search query", "other queries"],
            "top_k": 5,
            "threshold": 0.1,
            "search_type": "hybrid",
        }

        with patch(
            "app.services.embedding_service.EmbeddingService.embed_batch",
            return_value=[mock_vector],
        ):
            resp = await client.post(
                "/api/v1/search/batch", json=batch_payload, headers=headers
            )
            assert resp.status_code == 200, resp.text
            results = resp.json()
            assert len(results) == 2
            assert len(results[0]) == 1
            assert results[0][0]["chunk"]["id"] == str(c1.id)
