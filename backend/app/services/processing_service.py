"""
Enterprise RAG AI Assistant — Document Processing Service
==========================================================
Orchestrates the full text extraction pipeline for a single document.

Responsibilities:
  1. Load the ``Document`` record from the database.
  2. Resolve the correct processor via ``ProcessorFactory``.
  3. Run the processor's ``extract()`` method.
  4. Persist the result in ``ProcessedDocument`` (upsert on document_id).
  5. Update ``Document.processing_status`` to ``PROCESSED`` or ``FAILED``.

This service is designed to be called from the Celery worker thread via
``run_async_in_thread``, so it uses an async SQLAlchemy session.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.processed_document import ProcessedDocument
from app.processors.processor_factory import ProcessorFactory
from app.schemas.processed_document import ProcessedDocumentResponse

# Module-level factory instance (cached processors)
_factory = ProcessorFactory()


async def process_document_file(
    db: AsyncSession,
    document_id: uuid.UUID,
) -> ProcessedDocumentResponse:
    """
    Run the full extraction pipeline for the document identified by
    ``document_id``.

    Args:
        db:          Active async database session.
        document_id: UUID of the ``Document`` to process.

    Returns:
        ``ProcessedDocumentResponse`` with all extraction statistics.

    Raises:
        ValueError:              If the document does not exist in the database.
        FileNotFoundError:       If the physical file is missing from disk.
        UnsupportedFormatError:  If no processor supports the document's MIME type.
        RuntimeError:            On extraction failures inside a processor.
    """
    # ── 1. Load document ──────────────────────────────────────────────────────
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise ValueError(f"Document {document_id} not found.")

    # ── 2. Validate file path ─────────────────────────────────────────────────
    file_path = Path(doc.storage_path)
    if not file_path.exists():
        raise FileNotFoundError(
            f"Physical file missing for document {document_id}: {file_path}"
        )

    # ── 3. Resolve processor ──────────────────────────────────────────────────
    processor = _factory.get_processor(doc.mime_type)
    logger.info(
        f"Processing document {document_id} "
        f"({doc.mime_type}, {doc.file_size} bytes) "
        f"with {type(processor).__name__}."
    )

    # ── 4. Extract ────────────────────────────────────────────────────────────
    extraction = processor.extract(file_path)
    logger.info(
        f"Extracted document {document_id}: "
        f"{extraction.word_count} words, "
        f"{extraction.page_count} pages, "
        f"lang={extraction.language!r}, "
        f"time={extraction.processing_time:.3f}s"
    )

    # ── 5. Upsert ProcessedDocument ───────────────────────────────────────────
    pd_result = await db.execute(
        select(ProcessedDocument).where(ProcessedDocument.document_id == document_id)
    )
    pd_record = pd_result.scalar_one_or_none()

    if pd_record is None:
        pd_record = ProcessedDocument(document_id=document_id)
        db.add(pd_record)

    pd_record.raw_text = extraction.raw_text
    pd_record.clean_text = extraction.clean_text
    pd_record.language = extraction.language
    pd_record.page_count = extraction.page_count
    pd_record.word_count = extraction.word_count
    pd_record.character_count = extraction.character_count
    pd_record.processing_time = extraction.processing_time

    # ── 6. Update document status to PROCESSED ────────────────────────────────
    doc.processing_status = "PROCESSED"
    await db.commit()
    await db.refresh(pd_record)

    logger.info(f"Document {document_id} successfully PROCESSED.")
    return ProcessedDocumentResponse.model_validate(pd_record)
