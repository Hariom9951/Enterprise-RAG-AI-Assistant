"""
Enterprise RAG AI Assistant — Phase 4.3 Ingestion & Fault-Injection Tests
========================================================================
Validates ingestion benchmarks (DPM, CPS, duplicate rejection latency,
and reprocessing idempotency) and fault-injection scenarios (Redis fail-open,
database transaction rollback, tenant boundary fail-closed, tool timeouts,
agent cancellation context cleanup, and Celery task retries).
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.fault_injection_benchmark import (
    FaultInjectionReport,
    FaultInjectionResult,
    benchmark_agent_cancellation_and_cleanup,
    benchmark_authorization_boundary_enforcement,
    benchmark_celery_task_retry_and_exhaustion,
    benchmark_database_transaction_rollback,
    benchmark_redis_cache_fail_open,
    benchmark_tool_timeout_and_error_mapping,
    run_fault_injection_suite,
)
from app.evaluation.ingestion_benchmark import (
    DuplicateRejectionResult,
    IdempotencyBenchmarkResult,
    IngestionBenchmarkMetrics,
    benchmark_chunking_throughput,
    benchmark_duplicate_rejection,
    benchmark_reprocessing_idempotency,
    benchmark_simulated_ingestion,
)
from app.models.document import Document
from app.models.processed_document import ProcessedDocument
from app.models.user import User

# =============================================================================
# Ingestion Benchmarks Tests
# =============================================================================


def test_chunking_throughput_empty_documents() -> None:
    """Benchmark with empty list returns clean zero metrics without division errors."""
    res = benchmark_chunking_throughput([])
    assert isinstance(res, IngestionBenchmarkMetrics)
    assert res.stage == "chunking_only"
    assert res.is_end_to_end_production is False
    assert res.documents_total == 0
    assert res.documents_successful == 0
    assert res.documents_failed == 0
    assert res.chunks_produced_total == 0
    assert res.documents_per_minute == 0.0
    assert res.chunks_per_second == 0.0
    assert "documents_successful / elapsed_time_s" in res.dpm_formula
    assert "chunks_produced_total / elapsed_time_s" in res.cps_formula
    d = res.to_dict()
    assert d["stage"] == "chunking_only"
    assert "disclaimer" in d


def test_chunking_throughput_synthetic_corpus() -> None:
    """Benchmark calculates DPM and CPS accurately on synthetic documents."""
    docs = [
        "Paragraph 1 contains some standard text.\n\nParagraph 2 contains more details about system.",
        "Section A provides architectural specifications.\n\nSection B outlines data flows.",
        "Overview of agent workflows.\n\nDetails on iterative reasoning and search.",
    ]
    res = benchmark_chunking_throughput(docs, chunk_size=100, chunk_overlap=10)
    assert res.stage == "chunking_only"
    assert res.is_end_to_end_production is False
    assert res.documents_total == 3
    assert res.documents_successful == 3
    assert res.documents_failed == 0
    assert res.chunks_produced_total >= 3
    assert res.elapsed_time_s >= 0.0
    assert res.documents_per_minute > 0.0
    assert res.chunks_per_second > 0.0
    assert res.details["chunk_size"] == 100
    assert res.details["chunk_overlap"] == 10


def test_chunking_throughput_handles_individual_chunking_failures() -> None:
    """Benchmark increments failed count if an individual document chunking step raises."""
    docs = ["Doc 1 text.", "Doc 2 text."]
    with patch(
        "app.services.chunking_service.ChunkingService.split_text",
        side_effect=[["chunk1", "chunk2"], RuntimeError("Tokenizer memory error")],
    ):
        res = benchmark_chunking_throughput(docs)
        assert res.documents_total == 2
        assert res.documents_successful == 1
        assert res.documents_failed == 1
        assert res.chunks_produced_total == 2


@pytest.mark.asyncio
async def test_simulated_ingestion_empty_documents(
    db_session: AsyncSession,
) -> None:
    """Simulated ingestion with empty list returns clean zero metrics."""
    res = await benchmark_simulated_ingestion([], db_session)
    assert res.stage == "simulated_ingestion_mocked_embeddings"
    assert res.is_end_to_end_production is False
    assert res.documents_total == 0
    assert res.documents_successful == 0
    assert res.documents_per_minute == 0.0
    assert res.chunks_per_second == 0.0


@pytest.mark.asyncio
async def test_simulated_ingestion_with_synthetic_documents(
    db_session: AsyncSession,
) -> None:
    """Simulated ingestion processes documents, creates records, and produces chunks."""
    user = User(
        full_name="Bench Ingest User",
        email=f"bench_ingest_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hashed_pw",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    docs = [
        (
            "report_1.txt",
            "NexusAI is an enterprise agentic RAG platform.\n\nIt indexes data safely.",
        ),
        (
            "report_2.txt",
            "Performance benchmarks assess throughput.\n\nDPM and CPS are recorded.",
        ),
    ]
    res = await benchmark_simulated_ingestion(docs, db_session, user_id=user.id)
    assert res.stage == "simulated_ingestion_mocked_embeddings"
    assert res.is_end_to_end_production is False
    assert res.documents_total == 2
    assert res.documents_successful == 2
    assert res.documents_failed == 0
    assert res.chunks_produced_total >= 2
    assert res.documents_per_minute > 0.0
    assert res.chunks_per_second > 0.0


@pytest.mark.asyncio
async def test_duplicate_rejection_benchmark(
    db_session: AsyncSession,
) -> None:
    """Duplicate document upload is rejected with 409 ConflictException and latency recorded."""
    user = User(
        full_name="Deduplication Bench User",
        email=f"dedup_bench_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hashed_pw",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    content = b"Unique document content for deduplication benchmark test."
    res = await benchmark_duplicate_rejection(
        filename="dedup_bench_file.txt",
        content=content,
        db_session=db_session,
        user=user,
    )

    assert isinstance(res, DuplicateRejectionResult)
    assert res.stage == "upload_deduplication_simulated"
    assert res.is_end_to_end_production is False
    assert res.duplicate_detected is True
    assert res.rejection_status_code == 409
    assert res.exception_type == "ConflictException"
    assert res.initial_upload_latency_ms >= 0.0
    assert res.duplicate_rejection_latency_ms >= 0.0

    d = res.to_dict()
    assert d["rejection_status_code"] == 409
    assert "disclaimer" in d


@pytest.mark.asyncio
async def test_reprocessing_idempotency_benchmark(
    db_session: AsyncSession,
) -> None:
    """Repeated chunking passes produce identical chunk counts and maintain idempotency."""
    user = User(
        full_name="Idempotency Bench User",
        email=f"idemp_bench_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hashed_pw",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=user.id,
        original_filename="idemp_bench_doc.txt",
        stored_filename=f"idemp_{doc_id}.txt",
        mime_type="text/plain",
        file_size=150,
        sha256_hash=f"sha256_{doc_id.hex}",
        storage_path=f"/tmp/idemp_{doc_id}.txt",
        processing_status="PROCESSED",
    )
    db_session.add(doc)

    pd = ProcessedDocument(
        document_id=doc_id,
        raw_text="Segment 1 details.\n\nSegment 2 details.\n\nSegment 3 details.",
        clean_text="Segment 1 details.\n\nSegment 2 details.\n\nSegment 3 details.",
        language="en",
        page_count=1,
        word_count=15,
        character_count=80,
        processing_time=0.01,
    )
    db_session.add(pd)
    await db_session.commit()

    res = await benchmark_reprocessing_idempotency(doc_id, db_session, passes=3)
    assert isinstance(res, IdempotencyBenchmarkResult)
    assert res.stage == "reprocessing_idempotency_simulated"
    assert res.is_end_to_end_production is False
    assert res.document_id == str(doc_id)
    assert len(res.pass_durations_ms) == 3
    assert len(res.pass_chunk_counts) == 3
    assert res.is_idempotent is True
    assert res.consistent_chunk_count > 0
    # Every pass produced identical count
    assert len(set(res.pass_chunk_counts)) == 1

    d = res.to_dict()
    assert d["is_idempotent"] is True
    assert "disclaimer" in d


# =============================================================================
# Fault-Injection Benchmarks Tests
# =============================================================================


@pytest.mark.asyncio
async def test_redis_cache_fail_open_benchmark() -> None:
    """Redis outage benchmark verifies non-blocking fail-open for get, set, delete, and latency."""
    res = await benchmark_redis_cache_fail_open()
    assert isinstance(res, FaultInjectionResult)
    assert res.scenario_name == "redis_cache_outage_fail_open"
    assert res.fault_type == "redis_connection_error"
    assert res.expected_behavior == "fail_open_non_blocking"
    assert res.behavior_verified is True
    assert res.error_classification == "redis_connection_error"
    assert res.details["get_failed_open_to_none"] is True
    assert res.details["set_failed_open_to_false"] is True
    assert res.details["delete_failed_open_to_false"] is True
    assert res.details["record_latency_failed_open"] is True
    assert res.elapsed_ms >= 0.0


@pytest.mark.asyncio
async def test_database_transaction_rollback_benchmark() -> None:
    """Database crash benchmark verifies rollback is called, commit is skipped, session closed."""
    res = await benchmark_database_transaction_rollback()
    assert isinstance(res, FaultInjectionResult)
    assert res.scenario_name == "database_transaction_rollback_on_crash"
    assert res.fault_type == "database_operational_error"
    assert res.expected_behavior == "fail_closed_transaction_rollback"
    assert res.behavior_verified is True
    assert res.error_classification == "database_error"
    assert res.details["rollback_awaited"] is True
    assert res.details["commit_prevented"] is True
    assert res.details["session_closed"] is True


@pytest.mark.asyncio
async def test_authorization_boundary_enforcement_benchmark(
    db_session: AsyncSession,
) -> None:
    """Cross-tenant document access benchmark verifies get, update, and delete all fail closed (404)."""
    res = await benchmark_authorization_boundary_enforcement(db_session)
    assert isinstance(res, FaultInjectionResult)
    assert res.scenario_name == "tenant_authorization_boundary_fail_closed"
    assert res.fault_type == "unauthorized_cross_tenant_access"
    assert res.expected_behavior == "fail_closed_not_found"
    assert res.behavior_verified is True
    assert res.error_classification == "permission_denied"
    assert res.details["get_blocked_404"] is True
    assert res.details["update_blocked_404"] is True
    assert res.details["delete_blocked_404"] is True


@pytest.mark.asyncio
async def test_tool_timeout_and_error_mapping_benchmark() -> None:
    """Tool timeout benchmark verifies mapping to SafeErrorCategory.TIMEOUT."""
    res = await benchmark_tool_timeout_and_error_mapping()
    assert isinstance(res, FaultInjectionResult)
    assert res.scenario_name == "tool_timeout_error_classification"
    assert res.fault_type == "tool_timeout"
    assert res.behavior_verified is True
    assert res.error_classification == "timeout"
    assert res.details["classified_category"] == "timeout"


@pytest.mark.asyncio
async def test_agent_cancellation_and_cleanup_benchmark(
    db_session: AsyncSession,
) -> None:
    """Agent cancellation benchmark verifies CancelledError propagation and contextvars cleanup."""
    res = await benchmark_agent_cancellation_and_cleanup(db_session)
    assert isinstance(res, FaultInjectionResult)
    assert res.scenario_name == "agent_cancellation_propagation_and_context_cleanup"
    assert res.fault_type == "asyncio_cancelled_error"
    assert res.behavior_verified is True
    assert res.details["cancellation_propagated"] is True
    assert res.details["context_cleaned_up"] is True


@pytest.mark.asyncio
async def test_celery_task_retry_and_exhaustion_benchmark() -> None:
    """Celery task retry benchmark verifies transient retries, exhaustion handling, and permanent rejection."""
    res = await benchmark_celery_task_retry_and_exhaustion()
    assert isinstance(res, FaultInjectionResult)
    assert res.scenario_name == "celery_task_retry_and_exhaustion"
    assert res.fault_type == "transient_task_failure_and_exhaustion"
    assert res.behavior_verified is True
    assert res.details["transient_retry_triggered"] is True
    assert res.details["retry_exhaustion_handled"] is True
    assert res.details["permanent_failure_rejected_without_retry"] is True


@pytest.mark.asyncio
async def test_run_fault_injection_suite_aggregate(
    db_session: AsyncSession,
) -> None:
    """Aggregated fault-injection suite executes all scenarios and generates structured report."""
    report = await run_fault_injection_suite(db_session)
    assert isinstance(report, FaultInjectionReport)
    assert report.total_scenarios == 6
    assert report.passed_scenarios == 6
    assert report.failed_scenarios == 0
    assert report.elapsed_total_s >= 0.0
    assert len(report.results) == 6

    d = report.to_dict()
    assert d["total_scenarios"] == 6
    assert d["passed_scenarios"] == 6
    assert d["failed_scenarios"] == 0
    assert d["measurement_type"] == "simulated_fault_injection"
    assert len(d["results"]) == 6
    assert "disclaimer" in d
