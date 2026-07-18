"""
Enterprise RAG AI Assistant — Phase 7 Embedding Unit & Integration Tests
========================================================================
Validates vector embedding generation, pgvector storage, Celery pipelines,
and progress/summary API endpoints.
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User
from app.services.embedding_service import EmbeddingService
from app.tasks.document_tasks import process_document
from tests.test_documents import _register_and_login


@pytest.fixture()
def mock_vector() -> list[float]:
    return [0.1] * 768


# ── Chunker Splitting & Service Tests ─────────────────────────────────────────
class TestEmbeddingService:
    @pytest.mark.asyncio
    async def test_embed_batch_mocked(self, mock_vector: list[float]) -> None:
        """Validate that EmbeddingService generates batch embeddings using a mock model."""
        texts = ["Hello world", "Sentence Transformers"]

        # Instantiate service and mock internal model directly
        service = EmbeddingService()
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([mock_vector, mock_vector])

        # Inject mock model into singleton class variable
        EmbeddingService._model = mock_model

        embeddings = await service.embed_batch(texts)

        assert len(embeddings) == 2
        assert len(embeddings[0]) == 768
        np.testing.assert_allclose(embeddings[0], mock_vector)

    @pytest.mark.asyncio
    async def test_embed_document_chunks_persistence(
        self,
        db_session: AsyncSession,
        mock_vector: list[float],
    ) -> None:
        """Validate chunks database records are updated with embeddings and metadata."""
        doc_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Insert document and child chunk records
        doc = Document(
            id=doc_id,
            user_id=user_id,
            original_filename="vector_test.txt",
            stored_filename="vector_test.txt",
            mime_type="text/plain",
            file_size=100,
            sha256_hash="hashvec123",
            storage_path="/tmp/vec_test.txt",
            processing_status="PROCESSING",
        )
        c1 = Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            text="First semantic block",
            token_count=4,
            character_count=20,
            word_count=3,
            reading_time_estimate=1.0,
            sha256_hash="hashc1",
        )
        c2 = Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=1,
            text="Second semantic block",
            token_count=4,
            character_count=21,
            word_count=3,
            reading_time_estimate=1.0,
            sha256_hash="hashc2",
        )
        db_session.add_all([doc, c1, c2])
        await db_session.commit()

        # Run embedding service
        service = EmbeddingService()
        with patch.object(service, "embed_batch", return_value=[mock_vector, mock_vector]) as mock_embed:
            await service.embed_document_chunks(db_session, doc_id)
            mock_embed.assert_called_once()

        # Reset session and query updated chunks
        await db_session.close()
        result = await db_session.execute(
            select(Chunk).where(Chunk.document_id == doc_id).order_by(Chunk.chunk_index.asc())
        )
        updated_chunks = result.scalars().all()

        assert len(updated_chunks) == 2
        for chunk in updated_chunks:
            assert chunk.embedding is not None
            np.testing.assert_allclose(chunk.embedding, mock_vector)
            assert chunk.embedding_model == "BAAI/bge-base-en-v1.5"
            assert chunk.embedded_at is not None
            assert chunk.embedding_duration_ms is not None


# ── Background Celery Task & Ingestion Pipeline Tests ─────────────────────────
class TestEmbeddingCeleryIntegration:
    @pytest.mark.asyncio
    async def test_ingestion_pipeline_with_embeddings_mocked(
        self,
        db_session: AsyncSession,
        mock_vector: list[float],
    ) -> None:
        """Validate the full Upload -> Extract -> Chunk -> Embed pipeline eager run."""
        doc_id = uuid.uuid4()
        storage_path = os.path.abspath(f"storage/temp/test_{doc_id}.txt")
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)

        with open(storage_path, "w", encoding="utf-8") as f:
            f.write("Line one content.\nLine two content.")

        user_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            user_id=user_id,
            original_filename="celery_test.txt",
            stored_filename=f"test_{doc_id}.txt",
            mime_type="text/plain",
            file_size=40,
            sha256_hash="hashceleryvec",
            storage_path=storage_path,
            processing_status="UPLOADED",
        )
        db_session.add(doc)
        await db_session.commit()

        # Mock the embedding batch service method to return mock vectors
        with patch("app.services.embedding_service.EmbeddingService.embed_batch", return_value=[mock_vector, mock_vector]):
            task_res = process_document(str(doc_id))
            assert task_res["status"] == "success"

        # Verify final document status transitioned to COMPLETED
        await db_session.close()
        result_doc = await db_session.execute(select(Document).where(Document.id == doc_id))
        doc_updated = result_doc.scalar_one()
        assert doc_updated.processing_status == "COMPLETED"

        # Verify child chunks are embedded
        result_chunks = await db_session.execute(select(Chunk).where(Chunk.document_id == doc_id))
        db_chunks = result_chunks.scalars().all()
        assert len(db_chunks) > 0
        for chunk in db_chunks:
            assert chunk.embedding is not None
            np.testing.assert_allclose(chunk.embedding, mock_vector)

        # Clean up
        if os.path.exists(storage_path):
            os.remove(storage_path)


# ── API Endpoint Tests ────────────────────────────────────────────────────────
class TestEmbeddingAPI:
    @pytest.mark.asyncio
    async def test_api_endpoints_mocked(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        mock_vector: list[float],
    ) -> None:
        """Validate POST /embed, GET status, GET summary, and GET chunk/embedding APIs."""
        # 1. Login
        token = await _register_and_login(client, "embedtest@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Setup user and document
        result_user = await db_session.execute(select(User).where(User.email == "embedtest@example.com"))
        user = result_user.scalar_one()

        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            user_id=user.id,
            original_filename="api_test.txt",
            stored_filename="api_test.txt",
            mime_type="text/plain",
            file_size=100,
            sha256_hash="hashapivec",
            storage_path="/tmp/api_test.txt",
            processing_status="PROCESSED",
        )
        chunk_id = uuid.uuid4()
        chunk = Chunk(
            id=chunk_id,
            document_id=doc_id,
            chunk_index=0,
            text="API test chunk content.",
            token_count=5,
            character_count=23,
            word_count=4,
            reading_time_estimate=1.0,
            sha256_hash="hashapichunk",
            # Pre-filled mock values for some tests
            embedding=mock_vector,
            embedding_model="BAAI/bge-base-en-v1.5",
            embedding_version="1.0.0",
            embedded_at=sa.func.now(),
            embedding_duration_ms=50,
        )
        db_session.add_all([doc, chunk])
        await db_session.commit()

        # 3. Test GET /documents/{id}/embedding-status
        resp_status = await client.get(f"/api/v1/documents/{doc_id}/embedding-status", headers=headers)
        assert resp_status.status_code == 200, resp_status.text
        status_data = resp_status.json()
        assert status_data["document_id"] == str(doc_id)
        assert status_data["status"] == "COMPLETED"
        assert status_data["percentage_complete"] == 100.0
        assert status_data["processed_chunks"] == 1
        assert status_data["remaining_chunks"] == 0

        # 4. Test GET /documents/{id}/embedding-summary
        resp_summary = await client.get(f"/api/v1/documents/{doc_id}/embedding-summary", headers=headers)
        assert resp_summary.status_code == 200, resp_summary.text
        summary_data = resp_summary.json()
        assert summary_data["document_id"] == str(doc_id)
        assert summary_data["total_embedded"] == 1
        assert summary_data["model_used"] == "BAAI/bge-base-en-v1.5"

        # 5. Test GET /chunks/{id}/embedding
        resp_chunk_emb = await client.get(f"/api/v1/chunks/{chunk_id}/embedding", headers=headers)
        assert resp_chunk_emb.status_code == 200, resp_chunk_emb.text
        emb_data = resp_chunk_emb.json()
        assert emb_data["id"] == str(chunk_id)
        assert emb_data["embedding"] == mock_vector

        # 6. Test POST /documents/{id}/embed (force generation trigger)
        with patch("app.tasks.document_tasks.embed_document.delay") as mock_delay:
            resp_trigger = await client.post(f"/api/v1/documents/{doc_id}/embed", headers=headers)
            assert resp_trigger.status_code == 202
            mock_delay.assert_called_once_with(str(doc_id))
