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
    """Perform async document load, extraction, and state update — single session."""
    from app.services.processing_service import process_document_file

    async with get_async_session() as db:
        db = getattr(db, "_session", db)  # Safety mapping

        # 1. Verify document exists
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document {doc_id} not found in database.")

        if doc.processing_status == "PROCESSED":
            return {"status": "already_processed", "doc_id": str(doc_id)}

        # 2. Update status to PROCESSING
        doc.processing_status = "PROCESSING"
        await db.commit()
        logger.info(f"Transitioned document {doc_id} to PROCESSING.")

        # 3. Check if file exists on disk
        if not os.path.exists(doc.storage_path):
            doc.processing_status = "FAILED"
            await db.commit()
            raise FileNotFoundError(
                f"Physical file missing for document {doc_id} at {doc.storage_path}"
            )

        # 4. Run the full extraction pipeline within the same session
        await process_document_file(db, doc_id)

        # 5. Semantic Chunking & Metadata Enrichment
        from app.services.chunking_service import ChunkingService
        chunker = ChunkingService()
        await chunker.chunk_document(db, doc_id)

        # 6. Vector Embedding Generation
        from app.services.embedding_service import EmbeddingService
        embedder = EmbeddingService()
        await embedder.embed_document_chunks(db, doc_id)

        # Transition status to COMPLETED
        doc.processing_status = "COMPLETED"
        await db.commit()

    logger.info(f"Finished processing and embedding document {doc_id} successfully.")
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

        # Avoid retrying if file is missing (fails validation permanently)
        if isinstance(exc, FileNotFoundError | ValueError):
            run_async_in_thread(_async_handle_failure(doc_id))
            raise exc

        from celery.exceptions import Retry

        try:
            # Trigger celery task retry on temporary errors (e.g. database locks)
            self.retry(exc=exc)
            raise exc
        except Retry as retry_exc:
            raise retry_exc
        except Exception as retry_exc:
            # Mark document as FAILED only if all retry limits are fully exhausted
            run_async_in_thread(_async_handle_failure(doc_id))
            raise retry_exc


@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def embed_document(self: Task, doc_id_str: str) -> dict[str, Any]:
    """
    Background worker job to generate/regenerate embeddings for chunks of a document.
    """
    logger.info(f"Celery worker received embedding generation job: {doc_id_str}")
    doc_id = uuid.UUID(doc_id_str)

    async def progress_callback(processed: int, total: int) -> None:
        self.update_state(
            state="PROGRESS",
            meta={
                "current": processed,
                "total": total,
                "percentage": (processed / total) * 100 if total > 0 else 100,
            },
        )

    async def _async_embed() -> None:
        async with get_async_session() as db:
            db = getattr(db, "_session", db)

            # Fetch document
            result = await db.execute(select(Document).where(Document.id == doc_id))
            doc = result.scalar_one_or_none()
            if not doc:
                raise ValueError(f"Document {doc_id} not found.")

            from app.services.embedding_service import EmbeddingService
            embedder = EmbeddingService()
            await embedder.embed_document_chunks(db, doc_id, progress_callback=progress_callback)

    try:
        run_async_in_thread(_async_embed())
        return {"status": "success", "doc_id": str(doc_id)}
    except Exception as exc:
        logger.error(f"Error embedding document {doc_id_str}: {exc}")
        from celery.exceptions import Retry
        try:
            self.retry(exc=exc)
            raise exc
        except Retry as retry_exc:
            raise retry_exc
        except Exception as retry_exc:
            # We don't mark document status as FAILED for manual reruns, but we log the retry exhaust
            raise retry_exc
