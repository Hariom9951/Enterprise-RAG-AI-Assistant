"""
Enterprise RAG AI Assistant — Phase 4.4 Consolidated Benchmark CLI & Report Tests
================================================================================
Validates the consolidated benchmark runner, CLI argument parsing, suite isolation,
schema formatting, partial failure handling, terminal summary generation,
and the safety guard preventing overwriting evaluation_report.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.evaluation.benchmark_runner import (
    SCHEMA_VERSION,
    format_terminal_summary,
    get_default_report_path,
    main,
    run_consolidated_benchmarks,
)


def test_default_report_path() -> None:
    """Default report path resolves to benchmark_report.json."""
    path = get_default_report_path()
    assert isinstance(path, Path)
    assert path.name == "benchmark_report.json"


def test_suite_normalization_and_validation() -> None:
    """Invalid suite names raise ValueError with helpful error message."""
    with pytest.raises(ValueError, match="No valid suites specified"):
        import asyncio

        asyncio.run(run_consolidated_benchmarks(suites="unknown_suite"))

    with pytest.raises(ValueError, match="No valid suites specified"):
        import asyncio

        asyncio.run(run_consolidated_benchmarks(suites=[]))


@pytest.mark.asyncio
async def test_run_single_suite_quality() -> None:
    """Running quality suite produces retrieval metrics and runner comparison without executing other suites."""
    report = await run_consolidated_benchmarks(suites="quality")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["overall_status"] == "passed"
    assert report["suites_executed"] == ["quality"]

    # Quality passed
    assert report["suite_statuses"]["quality"]["status"] == "passed"
    assert report["suite_statuses"]["quality"]["duration_s"] > 0.0

    # Other suites are skipped (not marked passed)
    assert report["suite_statuses"]["performance"]["status"] == "skipped"
    assert report["suite_statuses"]["ingestion"]["status"] == "skipped"
    assert report["suite_statuses"]["reliability"]["status"] == "skipped"

    # Measured values for quality are present
    q_data = report["measured_values"]["quality"]
    assert q_data is not None
    assert "retrieval_metrics" in q_data
    assert "evaluation_depths_k" in q_data["retrieval_metrics"]
    assert q_data["retrieval_metrics"]["evaluation_depths_k"] == [1, 3, 5, 10]
    assert "answer_quality" in q_data
    assert "runner_comparison" in q_data

    # Skipped suites have null measured values (no invented zeros)
    assert report["measured_values"]["performance"] is None
    assert report["measured_values"]["ingestion"] is None
    assert report["measured_values"]["reliability"] is None


@pytest.mark.asyncio
async def test_run_single_suite_performance() -> None:
    """Running performance suite measures concurrency latency and throughput."""
    report = await run_consolidated_benchmarks(
        suites="performance",
        concurrency_levels=(1, 2),
        requests_per_concurrency=2,
    )

    assert report["overall_status"] == "passed"
    assert report["suites_executed"] == ["performance"]
    assert report["suite_statuses"]["performance"]["status"] == "passed"

    p_data = report["measured_values"]["performance"]
    assert p_data is not None
    assert "concurrency_benchmark" in p_data
    assert "agent_concurrency_sample" in p_data
    results = p_data["concurrency_benchmark"]["results_by_concurrency"]
    assert "1" in results or 1 in results


@pytest.mark.asyncio
async def test_run_single_suite_ingestion() -> None:
    """Running ingestion suite produces DPM, CPS, duplicate rejection, and idempotency results."""
    report = await run_consolidated_benchmarks(suites="ingestion")

    assert report["overall_status"] == "passed"
    assert report["suites_executed"] == ["ingestion"]
    assert report["suite_statuses"]["ingestion"]["status"] == "passed"

    i_data = report["measured_values"]["ingestion"]
    assert i_data is not None
    assert "chunking_throughput" in i_data
    assert "simulated_ingestion" in i_data
    assert "duplicate_rejection" in i_data
    assert "reprocessing_idempotency" in i_data

    # Check stages explicitly labeled
    assert i_data["chunking_throughput"]["stage"] == "chunking_only"
    assert (
        i_data["simulated_ingestion"]["stage"]
        == "simulated_ingestion_mocked_embeddings"
    )
    assert i_data["duplicate_rejection"]["stage"] == "upload_deduplication_simulated"
    assert (
        i_data["reprocessing_idempotency"]["stage"]
        == "reprocessing_idempotency_simulated"
    )


@pytest.mark.asyncio
async def test_run_single_suite_reliability() -> None:
    """Running reliability suite executes all 6 fault-injection scenarios."""
    report = await run_consolidated_benchmarks(suites="reliability")

    assert report["overall_status"] == "passed"
    assert report["suites_executed"] == ["reliability"]
    assert report["suite_statuses"]["reliability"]["status"] == "passed"

    r_data = report["measured_values"]["reliability"]
    assert r_data is not None
    assert r_data["total_scenarios"] == 6
    assert r_data["passed_scenarios"] == 6
    assert r_data["failed_scenarios"] == 0
    assert len(r_data["results"]) == 6


@pytest.mark.asyncio
async def test_run_multiple_suites_consolidated(tmp_path: Path) -> None:
    """Running multiple suites produces full report with valid schema, estimates, and disclaimers."""
    out_file = tmp_path / "test_report.json"
    report = await run_consolidated_benchmarks(
        suites=["quality", "reliability"],
        output_path=out_file,
    )

    assert report["overall_status"] == "passed"
    assert set(report["suites_executed"]) == {"quality", "reliability"}
    assert report["suite_statuses"]["quality"]["status"] == "passed"
    assert report["suite_statuses"]["reliability"]["status"] == "passed"
    assert report["suite_statuses"]["performance"]["status"] == "skipped"
    assert report["suite_statuses"]["ingestion"]["status"] == "skipped"

    # Verify estimated values separation
    assert report["estimated_values"]["estimates_available"] is False
    assert report["estimated_values"]["projected_production_throughput"] is None
    assert report["estimated_values"]["projected_cloud_monthly_cost"] is None

    # Verify limitations and disclaimers
    assert report["limitations_and_reproducibility"]["synthetic_corpus_only"] is True
    assert "reproducibility_command" in report["limitations_and_reproducibility"]

    # Verify file was written
    assert out_file.exists()
    with open(out_file, encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["schema_version"] == SCHEMA_VERSION


@pytest.mark.asyncio
async def test_safety_guard_refuses_overwriting_evaluation_report() -> None:
    """Attempting to specify evaluation_report.json as output raises ValueError to protect baseline report."""
    with pytest.raises(
        ValueError, match="Refusing to overwrite existing evaluation_report.json"
    ):
        await run_consolidated_benchmarks(
            suites="reliability",
            output_path="evaluation_report.json",
        )

    with pytest.raises(
        ValueError, match="Refusing to overwrite existing evaluation_report.json"
    ):
        await run_consolidated_benchmarks(
            suites="reliability",
            output_path="backend/evaluation_report.json",
        )


@pytest.mark.asyncio
async def test_partial_failure_handling() -> None:
    """When one suite fails, overall_status is partial and failure details are recorded."""
    with patch(
        "app.evaluation.benchmark_runner.run_ingestion_suite",
        side_effect=RuntimeError("Simulated ingestion disk failure"),
    ):
        report = await run_consolidated_benchmarks(suites=["reliability", "ingestion"])

        assert report["overall_status"] == "partial"
        assert report["suite_statuses"]["reliability"]["status"] == "passed"
        assert report["suite_statuses"]["ingestion"]["status"] == "failed"
        assert "Simulated ingestion disk failure" in (
            report["suite_statuses"]["ingestion"]["error"] or ""
        )
        assert report["measured_values"]["ingestion"] is None
        assert report["measured_values"]["reliability"] is not None


def test_format_terminal_summary() -> None:
    """Terminal summary generator prints readable badges and metrics for passed, failed, and skipped suites."""
    mock_report = {
        "schema_version": "1.0.0",
        "run_timestamp": "2026-10-16T12:00:00Z",
        "environment": {"execution_mode": "offline_synthetic_simulation"},
        "overall_status": "partial",
        "total_elapsed_s": 3.456,
        "suite_statuses": {
            "quality": {"status": "passed", "duration_s": 1.234},
            "performance": {"status": "skipped", "duration_s": 0.0},
            "ingestion": {"status": "failed", "duration_s": 0.5, "error": "Disk full"},
            "reliability": {"status": "passed", "duration_s": 0.45},
        },
        "measured_values": {
            "quality": {
                "retrieval_metrics": {
                    "metrics": {"mrr": 0.85, "precision@3": 0.9, "recall@3": 0.8}
                }
            },
            "performance": None,
            "ingestion": None,
            "reliability": {"passed_scenarios": 6, "total_scenarios": 6},
        },
    }

    summary = format_terminal_summary(mock_report)
    assert "NexusAI Consolidated Benchmark Runner" in summary
    assert "[PASSED] Quality" in summary
    assert "MRR: 0.85" in summary
    assert "[SKIPPED] Performance" in summary
    assert "[FAILED] Ingestion" in summary
    assert "Disk full" in summary
    assert "6/6 Fault Scenarios Verified" in summary
    assert "ESTIMATED VALUES:" in summary


def test_cli_main_execution_passed(tmp_path: Path) -> None:
    """CLI execution via main() writes report and exits 0 on success."""
    out_file = tmp_path / "cli_report.json"
    test_args = [
        "benchmark_runner.py",
        "--suite",
        "reliability",
        "--output",
        str(out_file),
        "--quiet",
    ]

    with patch.object(sys, "argv", test_args):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    assert out_file.exists()
    with open(out_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["overall_status"] == "passed"


def test_cli_main_execution_failed(tmp_path: Path) -> None:
    """CLI execution via main() exits 1 when a suite fails."""
    out_file = tmp_path / "cli_failed_report.json"
    test_args = [
        "benchmark_runner.py",
        "--suite",
        "reliability",
        "--output",
        str(out_file),
        "--quiet",
    ]

    with (
        patch.object(sys, "argv", test_args),
        patch(
            "app.evaluation.benchmark_runner.run_reliability_suite",
            side_effect=RuntimeError("Forced failure"),
        ),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    assert out_file.exists()


@pytest.mark.asyncio
async def test_lexical_grounding_positive_score_and_metric_retention() -> None:
    """Phase 4.4.2 Regression: Quality suite produces positive lexical grounding and retains prior metrics."""
    report = await run_consolidated_benchmarks(suites="quality")

    assert report["overall_status"] == "passed"
    q_data = report["measured_values"]["quality"]
    assert q_data is not None

    # Finding 1: Grounding score must be positive (not 0.0) when matching fixture text is evaluated
    ans_quality = q_data["answer_quality"]
    grounding = ans_quality["lexical_grounding_heuristic"]
    assert grounding["sample_cases_evaluated"] == 7
    assert grounding["average_grounding_ratio"] > 0.0
    assert grounding["average_grounding_ratio"] == 1.0

    # Prior metrics retain their behavior
    assert ans_quality["citation_validity_rate"] == 1.0
    assert ans_quality["abstention_accuracy"] == 1.0
    ret_metrics = q_data["retrieval_metrics"]["metrics"]
    assert ret_metrics["mrr"] == 0.8
    assert ret_metrics["precision@3"] == 0.5833
    assert ret_metrics["recall@3"] == 0.735


@pytest.mark.asyncio
async def test_lexical_grounding_safety_with_missing_and_empty_fixtures() -> None:
    """Phase 4.4.2 Regression: Missing or empty targeted fixtures do not crash or fabricate grounding."""
    from app.evaluation.dataset import (
        CaseCategory,
        EvaluationCase,
        EvaluationDataset,
        SyntheticChunkFixture,
    )

    # 1. Case with expected target pointing to a non-existent fixture
    case_missing_target = EvaluationCase(
        case_id="case-missing-fixture",
        category=CaseCategory.EASY,
        query="What is the policy?",
        expected_relevant_chunk_ids=["chunk-exists-01"],
        expected_citation_targets=[
            "chunk-non-existent-99"
        ],  # Target not in reference_fixtures
        reference_fixtures=[
            SyntheticChunkFixture(
                chunk_id="chunk-exists-01",
                document_id="doc-01",
                document_title="Doc 01",
                text="Some standard policy text.",
            )
        ],
    )

    # 2. Case with empty text in the targeted fixture (alongside general reference fixtures)
    case_empty_text = EvaluationCase(
        case_id="case-empty-text",
        category=CaseCategory.EASY,
        query="What is the policy?",
        expected_relevant_chunk_ids=["chunk-empty-02"],
        expected_citation_targets=["chunk-empty-02"],
        reference_fixtures=[
            SyntheticChunkFixture(
                chunk_id="chunk-empty-02",
                document_id="doc-02",
                document_title="Doc 02",
                text="",  # Empty text in targeted fixture
            ),
            SyntheticChunkFixture(
                chunk_id="chunk-distractor-03",
                document_id="doc-03",
                document_title="Doc 03",
                text="Distractor reference text.",
            ),
        ],
    )

    custom_dataset = EvaluationDataset(
        version="custom-test-v1",
        cases=[case_missing_target, case_empty_text],
    )

    report = await run_consolidated_benchmarks(
        suites="quality",
        quality_dataset=custom_dataset,
    )

    assert report["overall_status"] == "passed"
    q_data = report["measured_values"]["quality"]
    assert q_data is not None

    # In both cases with missing/empty targeted fixtures, grounding score is 0.0 (not fabricated)
    grounding = q_data["answer_quality"]["lexical_grounding_heuristic"]
    assert grounding["sample_cases_evaluated"] == 2
    assert grounding["average_grounding_ratio"] == 0.0


def test_terminal_summary_micro_workload_label() -> None:
    """Phase 4.4.2 Regression: Terminal summary explicitly labels Concurrency 1..20 (Simulated Micro-workload)."""
    mock_report = {
        "schema_version": "1.0.0",
        "run_timestamp": "2026-10-16T12:00:00Z",
        "environment": {"execution_mode": "offline_synthetic_simulation"},
        "overall_status": "passed",
        "total_elapsed_s": 0.5,
        "suite_statuses": {
            "performance": {"status": "passed", "duration_s": 0.25},
        },
        "measured_values": {
            "performance": {
                "concurrency_benchmark": {
                    "results_by_concurrency": {
                        "1": {"p50_ms": 2.5, "requests_per_second": 400.0},
                        "5": {"p50_ms": 2.8, "requests_per_second": 1200.0},
                    }
                }
            }
        },
    }

    summary = format_terminal_summary(mock_report)
    assert "Concurrency 1..20 (Simulated Micro-workload)" in summary
    assert "Avg p50: 2.65ms" in summary
    assert "Peak RPS: 1200.0" in summary


@pytest.mark.asyncio
async def test_chunk_ids_not_inserted_as_prose() -> None:
    """Phase 4.4.2 Regression: Verify chunk IDs are never interpolated into evidence answer prose."""
    import app.evaluation.benchmark_runner

    captured_answers: list[str] = []
    real_eval_grounding = app.evaluation.benchmark_runner.evaluate_evidence_grounding

    def _spy_evaluate_grounding(
        answer: str, cited_chunks: Any = None, **kwargs: Any
    ) -> Any:
        captured_answers.append(answer)
        return real_eval_grounding(answer, cited_chunks=cited_chunks, **kwargs)

    with patch(
        "app.evaluation.benchmark_runner.evaluate_evidence_grounding",
        side_effect=_spy_evaluate_grounding,
    ):
        await run_consolidated_benchmarks(suites="quality")

    assert len(captured_answers) == 7
    for ans in captured_answers:
        # None of the answers should contain chunk- prefix or raw chunk IDs
        assert "chunk-" not in ans
        assert "chunk_id" not in ans
        assert len(ans.strip()) > 0
