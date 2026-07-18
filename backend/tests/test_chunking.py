"""
Enterprise RAG AI Assistant — Phase 6 Chunking Unit & Integration Tests
========================================================================
Validates semantic text splitting, metadata enrichment, duplicate detection,
API endpoints, and background Celery pipelines.
"""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User
from app.services.chunking_service import ChunkingService
from app.tasks.document_tasks import process_document
from tests.test_documents import _register_and_login


@pytest.fixture()
def chunker() -> ChunkingService:
    return ChunkingService()


# ── Chunker Splitting Tests ──────────────────────────────────────────────────
class TestChunkerSplitting:
    def test_count_tokens(self, chunker: ChunkingService) -> None:
        text = "Hello, world! This is a token counting check."
        tokens = chunker.count_tokens(text)
        assert tokens > 0
        assert chunker.count_tokens("") == 0

    def test_split_tiny_text(self, chunker: ChunkingService) -> None:
        text = "Tiny sentence."
        chunks = chunker.split_text(text, chunk_size=100, chunk_overlap=10)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].token_count > 0
        assert chunks[0].character_count == len(text)
        assert chunks[0].word_count == 2
        assert chunks[0].reading_time_estimate > 0

    def test_split_large_text(self, chunker: ChunkingService) -> None:
        # Construct long paragraphs
        paragraph = "This is a long sentence repeated multiple times to ensure we exceed size limits. " * 30
        text = "\n\n".join([paragraph] * 3)  # Three large paragraphs

        chunks = chunker.split_text(text, chunk_size=150, chunk_overlap=20)
        assert len(chunks) > 1
        # Assert each chunk is within limits
        for c in chunks:
            assert c.token_count <= 150
            assert c.character_count > 0

    def test_split_heading_aware(self, chunker: ChunkingService) -> None:
        text = (
            "# Main Title\n"
            "This is introductory text under the main H1 heading.\n\n"
            "## Subsection A\n"
            "This is text under H2 heading."
        )
        chunks = chunker.split_text(text, chunk_size=50, chunk_overlap=5)
        assert len(chunks) >= 2
        # First chunk should have section Main Title
        assert chunks[0].section_title == "Main Title"
        assert chunks[0].heading_level == 1
        # Last chunk should have section Subsection A
        assert chunks[-1].section_title == "Subsection A"
        assert chunks[-1].heading_level == 2

    def test_page_boundaries_aware(self, chunker: ChunkingService) -> None:
        text = (
            "Content on page one.\n\n"
            "\x0c"  # Form feed page boundary
            "Content on page two."
        )
        chunks = chunker.split_text(text, chunk_size=100, chunk_overlap=10)
        assert len(chunks) >= 2
        assert chunks[0].page_number == 1
        assert chunks[-1].page_number == 2

    def test_duplicate_chunk_hashing(self, chunker: ChunkingService) -> None:
        # If text is identical, its SHA-256 hash must match
        t1 = "Same text block."
        t2 = "Same text block."
        c1 = chunker.split_text(t1)[0]
        c2 = chunker.split_text(t2)[0]
        assert c1.sha256_hash == c2.sha256_hash


# ── API & Celery Integration Tests ───────────────────────────────────────────
class TestChunkingIntegration:
    @pytest.mark.asyncio
    async def test_celery_task_and_api_endpoints(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        # 1. Register and login
        token = await _register_and_login(client, "chunktest@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Setup user and document
        result_user = await db_session.execute(select(User).where(User.email == "chunktest@example.com"))
        user = result_user.scalar_one()

        doc_id = uuid.uuid4()
        storage_path = os.path.abspath(f"storage/temp/test_{doc_id}.txt")
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)

        # Write sample multi-page markdown content
        with open(storage_path, "w", encoding="utf-8") as f:
            f.write(
                "# Title Section\n"
                "This is sample text for paragraph one. It is long enough.\n\n"
                "\x0c"  # page break
                "## Subsection Title\n"
                "This is page two text content. It contains tables like | col1 | col2 |\n"
                "and other parameters."
            )

        doc = Document(
            id=doc_id,
            user_id=user.id,
            original_filename="test_chunking.txt",
            stored_filename=f"test_{doc_id}.txt",
            mime_type="text/plain",
            file_size=150,
            sha256_hash="hashchunking123",
            storage_path=storage_path,
            processing_status="UPLOADED",
        )
        db_session.add(doc)
        await db_session.commit()

        # 3. Trigger eager Celery task execution (extraction + chunking)
        task_res = process_document(str(doc_id))
        assert task_res["status"] == "success"

        # 4. Verify Document processing status moved to PROCESSED
        await db_session.close()  # Reset cache
        result_doc = await db_session.execute(select(Document).where(Document.id == doc_id))
        doc_updated = result_doc.scalar_one()
        assert doc_updated.processing_status == "PROCESSED"

        # 5. Verify Chunks were created in database
        result_chunks = await db_session.execute(select(Chunk).where(Chunk.document_id == doc_id))
        db_chunks = result_chunks.scalars().all()
        assert len(db_chunks) >= 2
        for chunk in db_chunks:
            assert chunk.token_count > 0
            assert chunk.character_count > 0
            assert chunk.word_count > 0
            assert chunk.reading_time_estimate >= 0.0
            assert chunk.chunk_metadata is not None
            assert chunk.chunk_metadata["document_id"] == str(doc_id)

        # 6. Test GET /documents/{id}/chunks
        resp_list = await client.get(f"/api/v1/documents/{doc_id}/chunks?limit=5", headers=headers)
        assert resp_list.status_code == 200, resp_list.text
        list_data = resp_list.json()
        assert len(list_data) >= 2
        assert list_data[0]["document_id"] == str(doc_id)
        assert "metadata" in list_data[0]
        assert "text" in list_data[0]

        # 7. Test GET /documents/{id}/chunk-summary
        resp_summary = await client.get(f"/api/v1/documents/{doc_id}/chunk-summary", headers=headers)
        assert resp_summary.status_code == 200
        sum_data = resp_summary.json()
        assert sum_data["total_chunks"] == len(db_chunks)
        assert sum_data["total_tokens"] > 0
        assert sum_data["min_chunk_size"] > 0
        assert sum_data["max_chunk_size"] >= sum_data["min_chunk_size"]
        assert sum_data["reading_time_estimate"] > 0.0

        # 8. Test GET /chunks/{id}
        target_chunk_id = db_chunks[0].id
        resp_detail = await client.get(f"/api/v1/chunks/{target_chunk_id}", headers=headers)
        assert resp_detail.status_code == 200
        assert resp_detail.json()["id"] == str(target_chunk_id)

        # 9. Test DELETE /chunks/{id}
        resp_del = await client.delete(f"/api/v1/chunks/{target_chunk_id}", headers=headers)
        assert resp_del.status_code == 204

        # Verify deletion
        result_del = await db_session.execute(select(Chunk).where(Chunk.id == target_chunk_id))
        assert result_del.scalar_one_or_none() is None

        # Clean up physical file
        if os.path.exists(storage_path):
            os.remove(storage_path)
