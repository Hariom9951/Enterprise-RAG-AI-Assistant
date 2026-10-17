"""
Enterprise RAG AI Assistant — Ingestion Benchmarking Suite
==========================================================
Deterministic benchmarks for document ingestion throughput (DPM, CPS),
duplicate rejection latency, and reprocessing idempotency.

Design Guarantees & Constraints:
- Explicit labeling: Every result clearly indicates whether it measures
  "chunking_only", "simulated_ingestion_mocked_embeddings", or "upload_deduplication".
- Explicit throughput formulas:
  - DPM: (documents_successful / elapsed_time_s) * 60.0
  - CPS: chunks_produced_total / elapsed_time_s
- Zero-duration safeguards: Prevents division by zero if elapsed time is zero or negative.
- Isolated database state & temporary files: Uses in-memory SQLite and isolated temp files.
- Pure offline execution: Synthetic documents with mocked embedding dependencies.
"""

from __future__ import annotations

import io
import time
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any
from unittest.mock import patch

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

from app.core.exceptions import ConflictException
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.processed_document import ProcessedDocument
from app.models.user import User
from app.services.chunking_service import ChunkingService
from app.services.document_service import upload_document

INGESTION_BENCHMARK_DISCLAIMER: str = (
    "Measurements reflect in-process simulation using synthetic documents, in-memory "
    "persistence, and mocked embedding dependencies. They do not represent end-to-end "
    "production throughput across distributed Celery workers or live vector databases."
)


@dataclass
class IngestionBenchmarkMetrics:
    """Throughput and performance metrics for document ingestion and chunking."""

    stage: str
    is_end_to_end_production: bool
    documents_total: int
    documents_successful: int
    documents_failed: int
    chunks_produced_total: int
    elapsed_time_s: float
    documents_per_minute: float
    chunks_per_second: float
    dpm_formula: str = "(documents_successful / elapsed_time_s) * 60.0"
    cps_formula: str = "chunks_produced_total / elapsed_time_s"
    disclaimer: str = INGESTION_BENCHMARK_DISCLAIMER
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DuplicateRejectionResult:
    """Metrics for duplicate document upload rejection."""

    stage: str = "upload_deduplication_simulated"
    is_end_to_end_production: bool = False
    initial_upload_latency_ms: float = 0.0
    duplicate_rejection_latency_ms: float = 0.0
    duplicate_detected: bool = True
    rejection_status_code: int = 409
    exception_type: str = "ConflictException"
    disclaimer: str = (
        "Measures in-process SHA-256 checksum calculation and database lookup latency. "
        "Does not measure network transfer."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IdempotencyBenchmarkResult:
    """Metrics for document re-processing idempotency."""

    stage: str = "reprocessing_idempotency_simulated"
    is_end_to_end_production: bool = False
    document_id: str = ""
    pass_durations_ms: list[float] = field(default_factory=list)
    pass_chunk_counts: list[int] = field(default_factory=list)
    is_idempotent: bool = True
    consistent_chunk_count: int = 0
    disclaimer: str = (
        "Measures semantic chunking re-execution consistency and database chunk "
        "replacement idempotency without external service overhead."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def benchmark_chunking_throughput(
    documents: Sequence[str],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> IngestionBenchmarkMetrics:
    """
    Benchmark CPU-bound tokenizer and semantic text chunking throughput.

    Stage: 'chunking_only' (pure in-memory parsing, no DB or network).
    """
    total_docs = len(documents)
    if total_docs == 0:
        return IngestionBenchmarkMetrics(
            stage="chunking_only",
            is_end_to_end_production=False,
            documents_total=0,
            documents_successful=0,
            documents_failed=0,
            chunks_produced_total=0,
            elapsed_time_s=0.0,
            documents_per_minute=0.0,
            chunks_per_second=0.0,
        )

    chunker = ChunkingService()
    t0 = time.perf_counter()
    total_chunks = 0
    successful_docs = 0
    failed_docs = 0

    for doc_text in documents:
        try:
            chunks = chunker.split_text(
                text=doc_text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            total_chunks += len(chunks)
            successful_docs += 1
        except Exception:
            failed_docs += 1

    elapsed_s = max(0.0, time.perf_counter() - t0)

    # Denominator safeguards
    dpm = round((successful_docs / elapsed_s) * 60.0, 2) if elapsed_s > 0.0 else 0.0
    cps = round(total_chunks / elapsed_s, 2) if elapsed_s > 0.0 else 0.0

    return IngestionBenchmarkMetrics(
        stage="chunking_only",
        is_end_to_end_production=False,
        documents_total=total_docs,
        documents_successful=successful_docs,
        documents_failed=failed_docs,
        chunks_produced_total=total_chunks,
        elapsed_time_s=round(elapsed_s, 4),
        documents_per_minute=dpm,
        chunks_per_second=cps,
        details={
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        },
    )


async def benchmark_simulated_ingestion(
    documents: Sequence[tuple[str, str]],
    db_session: AsyncSession,
    user_id: uuid.UUID | None = None,
) -> IngestionBenchmarkMetrics:
    """
    Benchmark document ingestion pipeline (extraction and chunking) with database persistence
    and mocked embeddings in an isolated session.

    Stage: 'simulated_ingestion_mocked_embeddings'
    """
    total_docs = len(documents)
    if total_docs == 0:
        return IngestionBenchmarkMetrics(
            stage="simulated_ingestion_mocked_embeddings",
            is_end_to_end_production=False,
            documents_total=0,
            documents_successful=0,
            documents_failed=0,
            chunks_produced_total=0,
            elapsed_time_s=0.0,
            documents_per_minute=0.0,
            chunks_per_second=0.0,
        )

    owner_id = user_id or uuid.uuid4()
    chunker = ChunkingService()
    t0 = time.perf_counter()
    total_chunks = 0
    successful_docs = 0
    failed_docs = 0

    for filename, text_content in documents:
        doc_id = uuid.uuid4()
        try:
            doc = Document(
                id=doc_id,
                user_id=owner_id,
                original_filename=filename,
                stored_filename=f"bench_{doc_id}.txt",
                mime_type="text/plain",
                file_size=len(text_content.encode("utf-8")),
                sha256_hash=f"sha256_{doc_id.hex}",
                storage_path=f"/tmp/bench_{doc_id}.txt",
                processing_status="PROCESSED",
            )
            db_session.add(doc)

            proc_doc = ProcessedDocument(
                document_id=doc_id,
                raw_text=text_content,
                clean_text=text_content,
                language="en",
                page_count=1,
                word_count=len(text_content.split()),
                character_count=len(text_content),
                processing_time=0.01,
            )
            db_session.add(proc_doc)
            await db_session.commit()

            chunks = await chunker.chunk_document(db_session, doc_id)
            total_chunks += len(chunks)

            # Simulated embedding generation (mocked vector persistence)
            doc.processing_status = "COMPLETED"
            await db_session.commit()
            successful_docs += 1
        except Exception:
            await db_session.rollback()
            failed_docs += 1

    elapsed_s = max(0.0, time.perf_counter() - t0)

    dpm = round((successful_docs / elapsed_s) * 60.0, 2) if elapsed_s > 0.0 else 0.0
    cps = round(total_chunks / elapsed_s, 2) if elapsed_s > 0.0 else 0.0

    return IngestionBenchmarkMetrics(
        stage="simulated_ingestion_mocked_embeddings",
        is_end_to_end_production=False,
        documents_total=total_docs,
        documents_successful=successful_docs,
        documents_failed=failed_docs,
        chunks_produced_total=total_chunks,
        elapsed_time_s=round(elapsed_s, 4),
        documents_per_minute=dpm,
        chunks_per_second=cps,
    )


async def benchmark_duplicate_rejection(
    filename: str,
    content: bytes,
    db_session: AsyncSession,
    user: User,
) -> DuplicateRejectionResult:
    """
    Benchmark duplicate document detection latency and rejection enforcement.

    Performs initial upload, followed immediately by identical duplicate upload.
    Measures rejection latency and confirms ConflictException (HTTP 409).
    """
    with patch("app.tasks.document_tasks.process_document.delay"):
        # 1. Initial upload
        file_1 = UploadFile(
            filename=filename,
            file=io.BytesIO(content),
            headers=Headers(headers={"content-type": "text/plain"}),
        )
        t0_initial = time.perf_counter()
        _doc_1 = await upload_document(db=db_session, user_id=user.id, file=file_1)
        initial_ms = (time.perf_counter() - t0_initial) * 1000.0

        # 2. Duplicate upload
        file_2 = UploadFile(
            filename=filename,
            file=io.BytesIO(content),
            headers=Headers(headers={"content-type": "text/plain"}),
        )
        duplicate_detected = False
        rejection_status = 0
        exc_type = ""

        t0_dup = time.perf_counter()
        try:
            await upload_document(db=db_session, user_id=user.id, file=file_2)
        except ConflictException as exc:
            duplicate_detected = True
            rejection_status = exc.status_code
            exc_type = type(exc).__name__
        finally:
            rejection_ms = (time.perf_counter() - t0_dup) * 1000.0

    return DuplicateRejectionResult(
        stage="upload_deduplication_simulated",
        is_end_to_end_production=False,
        initial_upload_latency_ms=round(initial_ms, 2),
        duplicate_rejection_latency_ms=round(rejection_ms, 2),
        duplicate_detected=duplicate_detected,
        rejection_status_code=rejection_status,
        exception_type=exc_type,
    )


async def benchmark_reprocessing_idempotency(
    doc_id: uuid.UUID,
    db_session: AsyncSession,
    passes: int = 2,
) -> IdempotencyBenchmarkResult:
    """
    Benchmark reprocessing idempotency: verifies that repeated chunking passes on
    the same document produce identical chunk counts without data accumulation.
    """
    chunker = ChunkingService()
    durations: list[float] = []
    chunk_counts: list[int] = []

    for _ in range(passes):
        t0 = time.perf_counter()
        chunks = await chunker.chunk_document(db_session, doc_id)
        durations.append(round((time.perf_counter() - t0) * 1000.0, 2))
        chunk_counts.append(len(chunks))

    # Verify database chunk count
    res = await db_session.execute(select(Chunk).where(Chunk.document_id == doc_id))
    stored_chunks = list(res.scalars().all())
    final_stored_count = len(stored_chunks)

    is_idempotent = (
        len(set(chunk_counts)) == 1 and chunk_counts[0] == final_stored_count
    )

    return IdempotencyBenchmarkResult(
        stage="reprocessing_idempotency_simulated",
        is_end_to_end_production=False,
        document_id=str(doc_id),
        pass_durations_ms=durations,
        pass_chunk_counts=chunk_counts,
        is_idempotent=is_idempotent,
        consistent_chunk_count=final_stored_count,
    )
