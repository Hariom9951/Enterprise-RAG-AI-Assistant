"""
Enterprise RAG AI Assistant — Evaluation Framework (Phase 3.3)
=============================================================
Reproducible, deterministic evaluation of retrieval metrics, citation validity,
abstention behavior, and agent runner execution without live API dependencies.
"""

from __future__ import annotations

from app.evaluation.answer_evaluator import (
    AbstentionEvaluationResult,
    CitationEvaluationResult,
    GroundingEvaluationResult,
    evaluate_abstention,
    evaluate_citations,
    evaluate_evidence_grounding,
    evaluate_response_structure,
)
from app.evaluation.benchmark_collector import (
    BenchmarkCollector,
    BenchmarkMetrics,
    BenchmarkSample,
    calculate_percentile,
)
from app.evaluation.benchmark_runner import (
    SCHEMA_VERSION,
    format_terminal_summary,
    get_default_report_path,
    run_consolidated_benchmarks,
)
from app.evaluation.concurrency_harness import (
    ConcurrencyBenchmarkReport,
    run_agent_concurrency_benchmark,
    run_concurrency_benchmark,
    run_concurrency_workload,
)
from app.evaluation.dataset import (
    CaseCategory,
    EvaluationCase,
    EvaluationDataset,
    get_default_evaluation_dataset,
)
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
from app.evaluation.retrieval_metrics import (
    calculate_aggregate_retrieval_metrics,
    calculate_hit_rate_at_k,
    calculate_mean_reciprocal_rank,
    calculate_precision_at_k,
    calculate_recall_at_k,
    calculate_reciprocal_rank,
    calculate_retrieval_metrics_at_ks,
)
from app.evaluation.runner import run_evaluation_suite

__all__ = [
    "AbstentionEvaluationResult",
    "BenchmarkCollector",
    "BenchmarkMetrics",
    "BenchmarkSample",
    "CaseCategory",
    "CitationEvaluationResult",
    "ConcurrencyBenchmarkReport",
    "DuplicateRejectionResult",
    "EvaluationCase",
    "EvaluationDataset",
    "FaultInjectionReport",
    "FaultInjectionResult",
    "GroundingEvaluationResult",
    "IdempotencyBenchmarkResult",
    "IngestionBenchmarkMetrics",
    "benchmark_agent_cancellation_and_cleanup",
    "benchmark_authorization_boundary_enforcement",
    "benchmark_celery_task_retry_and_exhaustion",
    "benchmark_chunking_throughput",
    "benchmark_database_transaction_rollback",
    "benchmark_duplicate_rejection",
    "benchmark_redis_cache_fail_open",
    "benchmark_reprocessing_idempotency",
    "benchmark_simulated_ingestion",
    "benchmark_tool_timeout_and_error_mapping",
    "calculate_aggregate_retrieval_metrics",
    "calculate_hit_rate_at_k",
    "calculate_mean_reciprocal_rank",
    "calculate_percentile",
    "calculate_precision_at_k",
    "calculate_recall_at_k",
    "calculate_reciprocal_rank",
    "calculate_retrieval_metrics_at_ks",
    "evaluate_abstention",
    "evaluate_citations",
    "evaluate_evidence_grounding",
    "evaluate_response_structure",
    "format_terminal_summary",
    "get_default_evaluation_dataset",
    "get_default_report_path",
    "run_agent_concurrency_benchmark",
    "run_concurrency_benchmark",
    "run_concurrency_workload",
    "run_consolidated_benchmarks",
    "run_evaluation_suite",
    "run_fault_injection_suite",
    "SCHEMA_VERSION",
]
