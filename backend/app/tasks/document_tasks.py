"""
Enterprise RAG AI Assistant — Asynchronous Document Processing Tasks
=====================================================================
Defines Celery tasks for parsing and validating documents.
Bridges Celery's synchronous runner with SQLAlchemy 2.0 asyncpg sessions.
"""

from __future__ import annotations

import asyncio
import os
import threading
import uuid
from contextlib import asynccontextmanager
from typing import Any, cast

from celery import Task
from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.document import Document
from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


# ── Thread-Safe Sync to Async Bridge ─────────────────────────────────────────
def run_async_in_thread(coro: Any) -> Any:
    """
    Execute an asynchronous coroutine inside a dedicated helper thread.
    This resolves loop conflicts when synchronous Celery task runners are invoked
    inside active event loops (such as during pytest-asyncio runs).
    """
    result: Any = None
    exception: Exception | None = None

    def worker() -> None:
        nonlocal result, exception
        try:
            result = asyncio.run(coro)
        except Exception as e:
            exception = e

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    if exception:
        raise exception
    return result


# ── Database Async Adapter Context ──────────────────────────────────────────
@asynccontextmanager
async def get_async_session() -> Any:
    """Yield an isolated async database session for worker tasks."""
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()


async def _async_process_document(doc_id: uuid.UUID) -> dict[str, Any]:
    """Perform async document load, verification, and state update."""
    async with get_async_session() as db:
        db = getattr(db, "_session", db)  # Safety mapping
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document {doc_id} not found in database.")

        if doc.processing_status == "COMPLETED":
            return {"status": "already_completed", "doc_id": str(doc_id)}

        # 1. Update status to PROCESSING
        doc.processing_status = "PROCESSING"
        await db.commit()
        await db.refresh(doc)
        logger.info(f"Transitioned document {doc_id} to PROCESSING.")

        # 2. Check if file exists on disk
        if not os.path.exists(doc.storage_path):
            doc.processing_status = "FAILED"
            await db.commit()
            raise FileNotFoundError(f"Physical file missing for document {doc_id} at {doc.storage_path}")

        # 3. Simulate work (sleep for 5 seconds to show progress)
        await asyncio.sleep(5)

        # 4. Ingestion complete
        doc.processing_status = "COMPLETED"
        await db.commit()
        logger.info(f"Finished processing document {doc_id} successfully.")
        return {"status": "success", "doc_id": str(doc_id)}


async def _async_handle_failure(doc_id: uuid.UUID) -> None:
    """Fall back status to FAILED in database after task errors."""
    async with get_async_session() as db:
        db = getattr(db, "_session", db)
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if doc:
            doc.processing_status = "FAILED"
            await db.commit()
            logger.info(f"Updated document {doc_id} status to FAILED after exception.")


# ── Celery Task Definition ───────────────────────────────────────────────────
@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def process_document(self: Task, doc_id_str: str) -> dict[str, Any]:
    """
    Background worker job processing task.

    Calculates steps asynchronously inside a synchronous Celery execution thread.
    """
    logger.info(f"Celery worker received document job: {doc_id_str}")
    doc_id = uuid.UUID(doc_id_str)

    try:
        # Execute async processing loop in helper thread
        return cast(dict[str, Any], run_async_in_thread(_async_process_document(doc_id)))
    except Exception as exc:
        logger.error(f"Error processing document {doc_id_str}: {exc}")
        # Set status to FAILED
        run_async_in_thread(_async_handle_failure(doc_id))

        # Avoid retrying if file is missing (fails validation permanently)
        if isinstance(exc, FileNotFoundError | ValueError):
            raise exc

        try:
            # Trigger celery task retry on temporary errors (e.g. database locks)
            raise self.retry(exc=exc)
        except Exception as retry_exc:
            raise retry_exc
