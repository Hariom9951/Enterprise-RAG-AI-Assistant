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
    assert doc_updated.processing_status == "PROCESSED"

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
