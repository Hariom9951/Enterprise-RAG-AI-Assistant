"""
Enterprise RAG AI Assistant — Benchmark Harness & Metrics Tests (Phase 4.2)
===========================================================================
Deterministic verification for:
1. Percentile calculations (linear interpolation, edge cases, boundaries).
2. Empty sample safety and zero-duration safeguards (division-by-zero protection).
3. Accurate error accounting (failed requests excluded from completed count).
4. Concurrency bounding via semaphore under asynchronous execution.
5. Error and timeout handling across concurrency levels.
6. Offline agent concurrency benchmark with mocked LLM and isolated database.
7. In-process simulation labeling and zero production-capacity overclaiming.
"""

from __future__ import annotations

import asyncio

import pytest

from app.evaluation.benchmark_collector import (
    IN_PROCESS_DISCLAIMER,
    BenchmarkCollector,
    BenchmarkSample,
    calculate_percentile,
)
from app.evaluation.concurrency_harness import (
    ConcurrencyBenchmarkReport,
    run_agent_concurrency_benchmark,
    run_concurrency_benchmark,
    run_concurrency_workload,
)
from app.evaluation.dataset import get_default_evaluation_dataset

# =============================================================================
# 1. Percentile Calculation Unit Tests
# =============================================================================


class TestPercentileCalculations:
    def test_empty_sequence_returns_zero(self) -> None:
        assert calculate_percentile([], 50.0) == 0.0
        assert calculate_percentile([], 99.0) == 0.0

    def test_single_value_sequence(self) -> None:
        assert calculate_percentile([42.5], 0.0) == 42.5
        assert calculate_percentile([42.5], 50.0) == 42.5
        assert calculate_percentile([42.5], 99.0) == 42.5
        assert calculate_percentile([42.5], 100.0) == 42.5

    def test_known_uniform_distribution_percentiles(self) -> None:
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        assert calculate_percentile(values, 0.0) == 10.0
        assert calculate_percentile(values, 50.0) == 30.0
        assert calculate_percentile(values, 90.0) == 46.0
        assert calculate_percentile(values, 95.0) == 48.0
        assert calculate_percentile(values, 100.0) == 50.0

    def test_unsorted_input_sequence(self) -> None:
        unsorted_vals = [50.0, 10.0, 40.0, 20.0, 30.0]
        assert calculate_percentile(unsorted_vals, 50.0) == 30.0
        assert calculate_percentile(unsorted_vals, 90.0) == 46.0

    def test_invalid_percentiles_raise_value_error(self) -> None:
        with pytest.raises(
            ValueError, match="Percentile must be between 0.0 and 100.0"
        ):
            calculate_percentile([1.0, 2.0], -0.1)
        with pytest.raises(
            ValueError, match="Percentile must be between 0.0 and 100.0"
        ):
            calculate_percentile([1.0, 2.0], 100.1)


# =============================================================================
# 2. Benchmark Collector Safety & Accounting Tests
# =============================================================================


class TestBenchmarkCollector:
    def test_empty_collector_safeguards(self) -> None:
        collector = BenchmarkCollector(name="empty_test")
        metrics = collector.compute_metrics(elapsed_time_s=0.0)

        assert metrics.total_requests == 0
        assert metrics.completed_requests == 0
        assert metrics.failed_requests == 0
        assert metrics.error_rate == 0.0
        assert metrics.requests_per_second == 0.0
        assert metrics.min_ms == 0.0
        assert metrics.p50_ms == 0.0
        assert metrics.p90_ms == 0.0
        assert metrics.p95_ms == 0.0
        assert metrics.p99_ms == 0.0
        assert metrics.max_ms == 0.0
        assert metrics.mean_ms == 0.0
        assert metrics.error_counts == {}
        assert metrics.measurement_type == "in_process_simulated"

    def test_zero_and_negative_duration_safeguards(self) -> None:
        collector = BenchmarkCollector(name="zero_duration")
        collector.record(duration_ms=10.0, success=True)
        collector.record(duration_ms=20.0, success=True)

        # Zero elapsed time safeguard: RPS must safely return 0.0 without division by zero
        metrics_zero = collector.compute_metrics(elapsed_time_s=0.0)
        assert metrics_zero.requests_per_second == 0.0
        assert metrics_zero.completed_requests == 2

        # Negative elapsed time safeguard
        metrics_neg = collector.compute_metrics(elapsed_time_s=-5.0)
        assert metrics_neg.requests_per_second == 0.0

    def test_error_accounting_excludes_failed_from_completed(self) -> None:
        collector = BenchmarkCollector(name="error_accounting")
        # 3 successful requests
        collector.record(duration_ms=10.0, success=True)
        collector.record(duration_ms=15.0, success=True)
        collector.record(duration_ms=20.0, success=True)

        # 2 failed requests (one explicit failure, one with exception message)
        collector.record(
            duration_ms=5.0,
            success=False,
            error="Connection refused",
            error_category="network_error",
        )
        collector.record(
            duration_ms=30.0,
            success=True,
            error="Provider timeout",
            error_category="timeout",
        )  # error forces success=False

        metrics = collector.compute_metrics(elapsed_time_s=1.0)
        assert metrics.total_requests == 5
        # Crucial requirement: failed requests MUST NOT be counted in completed_requests
        assert metrics.completed_requests == 3
        assert metrics.failed_requests == 2
        assert metrics.error_rate == 0.4
        assert metrics.requests_per_second == 3.0  # 3 completed / 1.0s

        # Error category breakdown
        assert metrics.error_counts["network_error"] == 1
        assert metrics.error_counts["timeout"] == 1

    def test_collector_add_sample_and_reset(self) -> None:
        collector = BenchmarkCollector(name="sample_test")
        sample = BenchmarkSample(
            request_id="custom-1",
            duration_ms=25.0,
            success=True,
            metadata={"tag": "fast"},
        )
        collector.add_sample(sample)
        assert len(collector.samples) == 1
        assert collector.samples[0].metadata["tag"] == "fast"

        collector.reset()
        assert len(collector.samples) == 0


# =============================================================================
# 3. Asynchronous Concurrency Workload Tests
# =============================================================================


class TestConcurrencyWorkload:
    @pytest.mark.asyncio
    async def test_concurrency_bounding_with_semaphore(self) -> None:
        """Verify that concurrency level strictly caps simultaneous active tasks."""
        concurrency = 3
        total_requests = 10
        active_tasks = 0
        max_seen_tasks = 0
        lock = asyncio.Lock()

        async def _test_worker(idx: int) -> bool:
            nonlocal active_tasks, max_seen_tasks
            async with lock:
                active_tasks += 1
                if active_tasks > max_seen_tasks:
                    max_seen_tasks = active_tasks

            # Brief non-blocking yield to allow other concurrent tasks to enter
            await asyncio.sleep(0.01)

            async with lock:
                active_tasks -= 1
            return True

        metrics = await run_concurrency_workload(
            worker_fn=_test_worker,
            concurrency=concurrency,
            total_requests=total_requests,
            benchmark_name="bounding_test",
        )

        assert max_seen_tasks <= concurrency
        assert metrics.total_requests == total_requests
        assert metrics.completed_requests == total_requests
        assert metrics.failed_requests == 0
        assert metrics.error_rate == 0.0

    @pytest.mark.asyncio
    async def test_timeout_and_exception_handling(self) -> None:
        """Verify that timeouts and worker exceptions are cleanly captured without crashing the harness."""

        async def _faulty_worker(idx: int) -> bool:
            if idx == 0:
                # Simulates task exceeding timeout
                await asyncio.sleep(0.2)
                return True
            elif idx == 1:
                raise RuntimeError("Simulated worker internal fault")
            elif idx == 2:
                # Unsuccessful response
                return False
            return True

        metrics = await run_concurrency_workload(
            worker_fn=_faulty_worker,
            concurrency=2,
            total_requests=4,
            timeout_s=0.05,  # Trigger timeout for idx 0
            benchmark_name="faulty_test",
        )

        assert metrics.total_requests == 4
        # Requests 0 (timeout), 1 (runtime error), 2 (False) are failures; request 3 succeeded
        assert metrics.completed_requests == 1
        assert metrics.failed_requests == 3
        assert metrics.error_rate == 0.75
        assert "timeout" in metrics.error_counts
        assert "runtimeerror" in metrics.error_counts
        assert "unsuccessful_response" in metrics.error_counts


# =============================================================================
# 4. Concurrency Benchmark Suite Tests
# =============================================================================


class TestConcurrencyBenchmarkSuite:
    @pytest.mark.asyncio
    async def test_multi_concurrency_levels_execution(self) -> None:
        """Run harness across standard levels (1, 5, 10, 20) with fast deterministic mock worker."""

        async def _fast_worker(idx: int) -> bool:
            await asyncio.sleep(0.001)
            return True

        levels = [1, 5, 10, 20]
        report = await run_concurrency_benchmark(
            worker_fn=_fast_worker,
            concurrency_levels=levels,
            requests_per_concurrency=5,
            benchmark_name="multi_level_test",
        )

        assert report.concurrency_levels == levels
        assert report.measurement_type == "in_process_simulated"
        assert report.environment_disclaimer == IN_PROCESS_DISCLAIMER
        assert set(report.results_by_concurrency.keys()) == set(levels)

        for lvl in levels:
            m = report.results_by_concurrency[lvl]
            assert m.total_requests == 5
            assert m.completed_requests == 5
            assert m.failed_requests == 0
            assert m.error_rate == 0.0
            assert m.min_ms >= 0.0
            assert m.max_ms >= m.min_ms
            assert m.p50_ms >= m.min_ms
            assert m.p95_ms >= m.p50_ms

        report_dict = report.to_dict()
        assert "results_by_concurrency" in report_dict
        assert report_dict["measurement_type"] == "in_process_simulated"

    @pytest.mark.asyncio
    async def test_agent_concurrency_benchmark_offline_simulation(self) -> None:
        """Run agent concurrency benchmark with mocked LLM and isolated database."""
        dataset = get_default_evaluation_dataset()
        # Use first 2 cases for fast, deterministic unit test execution
        subset_cases = dataset.cases[:2]

        report = await run_agent_concurrency_benchmark(
            cases=subset_cases,
            runner="langgraph",
            concurrency_levels=[1, 2],
            requests_per_concurrency=2,
            timeout_s=5.0,
        )

        assert isinstance(report, ConcurrencyBenchmarkReport)
        assert report.measurement_type == "in_process_simulated"
        assert 1 in report.results_by_concurrency
        assert 2 in report.results_by_concurrency

        for lvl in [1, 2]:
            metrics = report.results_by_concurrency[lvl]
            assert metrics.total_requests == 2
            assert metrics.completed_requests == 2
            assert metrics.failed_requests == 0
            assert metrics.error_rate == 0.0
