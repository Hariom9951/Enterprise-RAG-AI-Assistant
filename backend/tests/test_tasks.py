"""
Enterprise RAG AI Assistant — Celery Worker Task Tests
======================================================
Tests background worker processing logic, database status transitions,
and error fallback scenarios using mocked file storage and overridden DB session.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.processed_document import ProcessedDocument
from app.models.user import User
from app.tasks.document_tasks import process_document


# ── Integration Tests ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_process_document_task_success(db_session: AsyncSession):
    """Verify standard document ingestion task updates status to PROCESSED and creates ProcessedDocument."""
    # 1. Create a dummy user
    user = User(
        full_name="Task Worker Test",
        email="taskworker@example.com",
        hashed_password="dummyhashpassword",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # 2. Create document record with initial status UPLOADED
    doc_id = uuid.uuid4()
    storage_path = os.path.abspath(f"storage/temp/test_{doc_id}.txt")
    os.makedirs(os.path.dirname(storage_path), exist_ok=True)

    # Write a dummy content file to storage path
    with open(storage_path, "w", encoding="utf-8") as f:
        f.write("Some dummy text content to parse.")

    doc = Document(
        id=doc_id,
        user_id=user.id,
        original_filename="test_worker.txt",
        stored_filename=f"test_{doc_id}.txt",
        mime_type="text/plain",
        file_size=33,
        sha256_hash="dummysha256hash123",
        storage_path=storage_path,
        processing_status="UPLOADED",
    )
    db_session.add(doc)
    await db_session.commit()

    # 3. Trigger task execution synchronously in testing thread
    # Bypass Celery queue using direct call, which executes the task code synchronously
    result = process_document(str(doc_id))

    # Verify task result body
    assert result["status"] == "success"
    assert result["doc_id"] == str(doc_id)

    # 4. Assert database status updated to PROCESSED and ProcessedDocument created
    await db_session.close()  # Reset cache
    result_db = await db_session.execute(select(Document).where(Document.id == doc_id))
    doc_updated = result_db.scalar_one()
    assert doc_updated.processing_status == "COMPLETED"

    # Verify ProcessedDocument record was created
    pd_result = await db_session.execute(
        select(ProcessedDocument).where(ProcessedDocument.document_id == doc_id)
    )
    pd = pd_result.scalar_one_or_none()
    assert pd is not None
    assert pd.word_count >= 0

    # Clean up physical file
    if os.path.exists(storage_path):
        os.remove(storage_path)


@pytest.mark.asyncio
async def test_process_document_task_file_missing(db_session: AsyncSession):
    """Verify worker fails and marks DB status FAILED if physical file is missing."""
    # 1. Create a dummy user
    user = User(
        full_name="Task Worker Test 2",
        email="taskworker2@example.com",
        hashed_password="dummyhashpassword",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # 2. Create document record with missing storage file path
    doc_id = uuid.uuid4()
    storage_path = os.path.abspath(f"storage/temp/nonexistent_{doc_id}.txt")

    doc = Document(
        id=doc_id,
        user_id=user.id,
        original_filename="test_missing.txt",
        stored_filename=f"nonexistent_{doc_id}.txt",
        mime_type="text/plain",
        file_size=10,
        sha256_hash="dummysha256hash1234",
        storage_path=storage_path,
        processing_status="UPLOADED",
    )
    db_session.add(doc)
    await db_session.commit()

    # 3. Trigger task. It should raise FileNotFoundError
    with pytest.raises(FileNotFoundError):
        process_document(str(doc_id))

    # 4. Assert database status updated to FAILED
    await db_session.close()  # Reset cache
    result_db = await db_session.execute(select(Document).where(Document.id == doc_id))
    doc_updated = result_db.scalar_one()
    assert doc_updated.processing_status == "FAILED"


@pytest.mark.asyncio
async def test_process_document_task_nonexistent_doc(db_session: AsyncSession):
    """Verify task throws ValueError when resolving a non-existent database UUID."""
    random_id = uuid.uuid4()
    with pytest.raises(ValueError, match="not found in database"):
        process_document(str(random_id))


# ── State Machine & Ingestion Retry Regression Tests ─────────────────────────
@pytest.mark.asyncio
async def test_process_document_interrupted_after_extraction(db_session: AsyncSession):
    """
    Regression test: A document previously marked PROCESSED (text extracted but
    chunking/embedding interrupted) must NOT be skipped as already_processed.
    It must complete chunking and embedding, reaching terminal COMPLETED status.
    """
    user = User(
        full_name="Interrupted Doc Test",
        email="interrupted@example.com",
        hashed_password="dummyhashpassword",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    doc_id = uuid.uuid4()
    storage_path = os.path.abspath(f"storage/temp/interrupted_{doc_id}.txt")
    os.makedirs(os.path.dirname(storage_path), exist_ok=True)
    with open(storage_path, "w", encoding="utf-8") as f:
        f.write("Extracted text ready to be chunked and embedded.")

    # Status is PROCESSED from previous extraction, but no chunks exist yet
    doc = Document(
        id=doc_id,
        user_id=user.id,
        original_filename="interrupted.txt",
        stored_filename=f"interrupted_{doc_id}.txt",
        mime_type="text/plain",
        file_size=48,
        sha256_hash="dummysha256hash_interrupted",
        storage_path=storage_path,
        processing_status="PROCESSED",
    )
    db_session.add(doc)

    pd = ProcessedDocument(
        document_id=doc_id,
        raw_text="Extracted text ready to be chunked and embedded.",
        clean_text="Extracted text ready to be chunked and embedded.",
        language="en",
        page_count=1,
        word_count=8,
        character_count=48,
        processing_time=0.01,
    )
    db_session.add(pd)
    await db_session.commit()

    # Trigger task on partially processed document
    result = process_document(str(doc_id))
    assert result["status"] == "success"

    # Must reach COMPLETED
    await db_session.close()
    result_db = await db_session.execute(select(Document).where(Document.id == doc_id))
    doc_updated = result_db.scalar_one()
    assert doc_updated.processing_status == "COMPLETED"

    # Chunks must have been created and embedded
    from app.models.chunk import Chunk

    chunks_result = await db_session.execute(
        select(Chunk).where(Chunk.document_id == doc_id)
    )
    chunks = list(chunks_result.scalars().all())
    assert len(chunks) > 0
    assert chunks[0].embedding is not None

    if os.path.exists(storage_path):
        os.remove(storage_path)


@pytest.mark.asyncio
async def test_process_document_completed_idempotent(db_session: AsyncSession):
    """
    Verify that an already fully COMPLETED document with chunks and embeddings
    is skipped idempotently without re-extracting or re-embedding.
    """
    user = User(
        full_name="Completed Doc Test",
        email="completed@example.com",
        hashed_password="dummyhashpassword",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    doc_id = uuid.uuid4()
    storage_path = os.path.abspath(f"storage/temp/completed_{doc_id}.txt")
    os.makedirs(os.path.dirname(storage_path), exist_ok=True)
    with open(storage_path, "w", encoding="utf-8") as f:
        f.write("Finished text.")

    doc = Document(
        id=doc_id,
        user_id=user.id,
        original_filename="completed.txt",
        stored_filename=f"completed_{doc_id}.txt",
        mime_type="text/plain",
        file_size=14,
        sha256_hash="dummysha256hash_completed",
        storage_path=storage_path,
        processing_status="COMPLETED",
    )
    db_session.add(doc)

    pd = ProcessedDocument(
        document_id=doc_id,
        raw_text="Finished text.",
        clean_text="Finished text.",
        language="en",
        page_count=1,
        word_count=2,
        character_count=14,
        processing_time=0.01,
    )
    db_session.add(pd)

    from app.models.chunk import Chunk

    chunk = Chunk(
        id=uuid.uuid4(),
        document_id=doc_id,
        chunk_index=0,
        text="Finished text.",
        token_count=3,
        character_count=14,
        word_count=2,
        reading_time_estimate=0.1,
        page_number=1,
        language="en",
        sha256_hash="chunkhash_completed",
        embedding=[0.1] * 768,
    )
    db_session.add(chunk)
    await db_session.commit()

    # Re-running on truly complete document returns already_processed
    result = process_document(str(doc_id))
    assert result["status"] == "already_processed"
    assert result["doc_id"] == str(doc_id)

    if os.path.exists(storage_path):
        os.remove(storage_path)


@pytest.mark.asyncio
async def test_process_document_chunking_failure_marks_failed(db_session: AsyncSession):
    """
    Verify that an unhandled error during chunking marks the document FAILED.
    """
    from unittest.mock import patch

    user = User(
        full_name="Fail Doc Test",
        email="faildoc@example.com",
        hashed_password="dummyhashpassword",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    doc_id = uuid.uuid4()
    storage_path = os.path.abspath(f"storage/temp/fail_{doc_id}.txt")
    os.makedirs(os.path.dirname(storage_path), exist_ok=True)
    with open(storage_path, "w", encoding="utf-8") as f:
        f.write("Text that will fail during chunking.")

    doc = Document(
        id=doc_id,
        user_id=user.id,
        original_filename="fail.txt",
        stored_filename=f"fail_{doc_id}.txt",
        mime_type="text/plain",
        file_size=36,
        sha256_hash="dummysha256hash_fail",
        storage_path=storage_path,
        processing_status="UPLOADED",
    )
    db_session.add(doc)
    await db_session.commit()

    with patch(
        "app.services.chunking_service.ChunkingService.chunk_document",
        side_effect=RuntimeError("Simulated chunking failure"),
    ):
        with pytest.raises(RuntimeError, match="Simulated chunking failure"):
            process_document(str(doc_id))

    await db_session.close()
    result_db = await db_session.execute(select(Document).where(Document.id == doc_id))
    doc_updated = result_db.scalar_one()
    assert doc_updated.processing_status == "FAILED"

    if os.path.exists(storage_path):
        os.remove(storage_path)
