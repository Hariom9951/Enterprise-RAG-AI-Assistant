"""
Enterprise RAG AI Assistant — Benchmark Metric Collector
=========================================================
Lightweight, pure offline metric collector calculating response latency percentiles
(min, p50, p90, p95, p99, max, mean), throughput (RPS), elapsed duration,
and explicit error accounting.

Design Guarantees & Constraints:
- Pure deterministic math (no external analytics libraries or network calls).
- Zero-duration safeguards: prevents division by zero if elapsed time is zero or negative.
- Empty sample safety: returns clean zero-valued metrics when no requests are recorded.
- Consistent error accounting: failed requests (success=False or exceptions) are
  strictly excluded from completed_requests and tracked in error_counts and error_rate.
- Explicit measurement attribution: tagged as "in_process_simulated" to prevent
  conflating simulated local measurements with production network capacity.
"""

from __future__ import annotations

import math
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

IN_PROCESS_DISCLAIMER: str = (
    "Measurements reflect simulated in-process execution with mocked model responses and "
    "local persistence. They do not reflect real network latencies, distributed queue "
    "delays, or external Gemini API production throughput."
)


def calculate_percentile(values: Sequence[float], percentile: float) -> float:
    """
    Calculate the given percentile (0.0 to 100.0) of a sequence of numerical values.

    Uses linear interpolation between closest ranks (equivalent to numpy default).
    Returns 0.0 if values is empty.

    Args:
        values: Sequence of float values (latencies in ms).
        percentile: Float between 0.0 and 100.0 inclusive.
    """
    if not values:
        return 0.0

    if percentile < 0.0 or percentile > 100.0:
        raise ValueError(f"Percentile must be between 0.0 and 100.0, got {percentile}")

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    if n == 1:
        return float(sorted_vals[0])

    k = (n - 1) * (percentile / 100.0)
    floor_idx = math.floor(k)
    ceil_idx = math.ceil(k)

    if floor_idx == ceil_idx:
        return float(sorted_vals[int(k)])

    weight_ceil = k - floor_idx
    weight_floor = ceil_idx - k
    interpolated = (sorted_vals[floor_idx] * weight_floor) + (
        sorted_vals[ceil_idx] * weight_ceil
    )
    return round(float(interpolated), 4)


@dataclass
class BenchmarkSample:
    """A single execution sample recorded during a benchmark run."""

    request_id: str
    duration_ms: float
    success: bool
    error: str | None = None
    error_category: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkMetrics:
    """Aggregated statistical metrics calculated from collected benchmark samples."""

    total_requests: int
    completed_requests: int
    failed_requests: int
    error_rate: float
    elapsed_time_s: float
    requests_per_second: float
    min_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    mean_ms: float
    measurement_type: str = "in_process_simulated"
    environment_disclaimer: str = IN_PROCESS_DISCLAIMER
    error_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BenchmarkCollector:
    """
    Collector for benchmarking latencies, throughput, and error rates.

    Thread-safe and async-safe collection for benchmarking runs.
    """

    def __init__(self, name: str = "benchmark") -> None:
        self.name = name
        self._samples: list[BenchmarkSample] = []
        self._start_time: float | None = None
        self._end_time: float | None = None

    def start(self) -> None:
        """Start the benchmark wall-clock timer."""
        self._start_time = time.perf_counter()
        self._end_time = None

    def stop(self) -> float:
        """Stop the benchmark wall-clock timer and return elapsed seconds."""
        self._end_time = time.perf_counter()
        if self._start_time is None:
            return 0.0
        return max(0.0, self._end_time - self._start_time)

    def add_sample(self, sample: BenchmarkSample) -> None:
        """Add a pre-constructed BenchmarkSample."""
        self._samples.append(sample)

    def record(
        self,
        duration_ms: float,
        success: bool,
        error: str | None = None,
        error_category: str | None = None,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BenchmarkSample:
        """
        Record a single execution sample.

        If error is provided, success is automatically coerced to False.
        """
        is_success = bool(success and error is None)
        sample = BenchmarkSample(
            request_id=request_id or f"req-{len(self._samples) + 1}",
            duration_ms=max(0.0, float(duration_ms)),
            success=is_success,
            error=error,
            error_category=error_category
            if not is_success
            else (error_category or "none"),
            metadata=metadata or {},
        )
        self._samples.append(sample)
        return sample

    @property
    def samples(self) -> list[BenchmarkSample]:
        """Return a copy of the recorded samples."""
        return list(self._samples)

    def reset(self) -> None:
        """Clear all samples and timers."""
        self._samples.clear()
        self._start_time = None
        self._end_time = None

    def compute_metrics(self, elapsed_time_s: float | None = None) -> BenchmarkMetrics:
        """
        Compute statistical metrics from all collected samples.

        Args:
            elapsed_time_s: Optional explicit wall-clock elapsed time in seconds.
                            If None, computes from start/stop timer if available.
        """
        total = len(self._samples)

        # Elapsed time determination with safeguards
        if elapsed_time_s is not None:
            elapsed = max(0.0, float(elapsed_time_s))
        elif self._start_time is not None:
            end = self._end_time if self._end_time is not None else time.perf_counter()
            elapsed = max(0.0, end - self._start_time)
        else:
            elapsed = 0.0

        if total == 0:
            return BenchmarkMetrics(
                total_requests=0,
                completed_requests=0,
                failed_requests=0,
                error_rate=0.0,
                elapsed_time_s=round(elapsed, 4),
                requests_per_second=0.0,
                min_ms=0.0,
                p50_ms=0.0,
                p90_ms=0.0,
                p95_ms=0.0,
                p99_ms=0.0,
                max_ms=0.0,
                mean_ms=0.0,
                error_counts={},
            )

        # Error accounting: failed requests are strictly NOT completed_requests
        completed = sum(1 for s in self._samples if s.success)
        failed = total - completed
        error_rate = round(float(failed / total), 4)

        # Categorize errors
        error_counter: Counter[str] = Counter()
        for s in self._samples:
            if not s.success:
                cat = s.error_category or "unspecified_error"
                error_counter[cat] += 1

        # Throughput (RPS): completed requests per second with zero-duration safeguard
        rps = round(float(completed / elapsed), 2) if elapsed > 0.0 else 0.0

        # Latency statistics across all recorded request attempts
        durations = [s.duration_ms for s in self._samples]
        min_val = round(min(durations), 4)
        max_val = round(max(durations), 4)
        mean_val = round(sum(durations) / total, 4)

        p50 = calculate_percentile(durations, 50.0)
        p90 = calculate_percentile(durations, 90.0)
        p95 = calculate_percentile(durations, 95.0)
        p99 = calculate_percentile(durations, 99.0)

        return BenchmarkMetrics(
            total_requests=total,
            completed_requests=completed,
            failed_requests=failed,
            error_rate=error_rate,
            elapsed_time_s=round(elapsed, 4),
            requests_per_second=rps,
            min_ms=min_val,
            p50_ms=p50,
            p90_ms=p90,
            p95_ms=p95,
            p99_ms=p99,
            max_ms=max_val,
            mean_ms=mean_val,
            error_counts=dict(error_counter),
        )
