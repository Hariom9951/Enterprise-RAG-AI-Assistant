"""
Enterprise RAG AI Assistant — Asynchronous Concurrency Benchmark Harness
========================================================================
Asynchronous benchmarking harness evaluating agent execution and RAG workloads
across concurrency levels 1, 5, 10, and 20.

Guarantees & Constraints:
- Pure offline execution using deterministic fixtures and mocked model responses.
- Explicit classification: clearly designated as "in_process_simulated" to avoid
  conflating local in-process concurrency with production distributed capacity.
- Accurate failure accounting: exceptions, asyncio.TimeoutError, and unsuccessful
  responses (success=False) are recorded with error categories and strictly excluded
  from completed requests.
- Monotonic timing via time.perf_counter().
- No arbitrary latency thresholds asserted in CI.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agents.agent_service import AgentService
from app.agents.base_tool import ToolResult
from app.agents.registry import ToolRegistry
from app.agents.tools.semantic_search import SemanticSearchTool
from app.db.base import Base
from app.evaluation.benchmark_collector import (
    IN_PROCESS_DISCLAIMER,
    BenchmarkCollector,
    BenchmarkMetrics,
)
from app.evaluation.dataset import EvaluationCase, get_default_evaluation_dataset
from app.evaluation.runner_comparison import _create_mock_tool_output

DEFAULT_CONCURRENCY_LEVELS: tuple[int, ...] = (1, 5, 10, 20)


def _build_concurrent_mock_llm() -> AsyncMock:
    """
    Construct a coroutine-safe mock LLM responding deterministically across concurrent calls.
    Uses dynamic functional side_effect accepting any signature (positional prompt or
    keyword system_prompt/user_prompt) to prevent StopIteration and argument mismatches.
    """
    mock = AsyncMock()

    async def _generate_response(
        *args: Any, **kwargs: Any
    ) -> tuple[str, dict[str, int]]:
        prompt_text = ""
        if args:
            prompt_text = str(args[0])
        elif "prompt" in kwargs:
            prompt_text = str(kwargs["prompt"])
        elif "user_prompt" in kwargs or "system_prompt" in kwargs:
            prompt_text = (
                f"{kwargs.get('system_prompt', '')} {kwargs.get('user_prompt', '')}"
            )

        prompt_lower = prompt_text.lower()
        if (
            "plan" in prompt_lower
            or "tool" in prompt_lower
            or "classify" in prompt_lower
            or "intent" in prompt_lower
        ):
            plan_json = json.dumps(
                [
                    {
                        "tool_id": "semantic_search",
                        "parameters": {"query": "policy query", "top_k": 3},
                    }
                ]
            )
            return plan_json, {"prompt_tokens": 40, "completion_tokens": 20}

        answer = (
            "Based on enterprise policy documentation [1] and [2], the standard "
            "compliance criteria are fulfilled as documented."
        )
        return answer, {"prompt_tokens": 100, "completion_tokens": 30}

    mock.generate_response.side_effect = _generate_response
    return mock


@dataclass
class ConcurrencyBenchmarkReport:
    """Consolidated report of benchmark results across multiple concurrency levels."""

    benchmark_name: str
    concurrency_levels: list[int]
    results_by_concurrency: dict[int, BenchmarkMetrics]
    total_elapsed_s: float
    measurement_type: str = "in_process_simulated"
    environment_disclaimer: str = IN_PROCESS_DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_name": self.benchmark_name,
            "concurrency_levels": self.concurrency_levels,
            "measurement_type": self.measurement_type,
            "environment_disclaimer": self.environment_disclaimer,
            "total_elapsed_s": round(self.total_elapsed_s, 4),
            "results_by_concurrency": {
                c: m.to_dict() for c, m in self.results_by_concurrency.items()
            },
        }


async def run_concurrency_workload(
    worker_fn: Callable[[int], Coroutine[Any, Any, bool | dict[str, Any] | None]],
    concurrency: int,
    total_requests: int,
    timeout_s: float | None = None,
    benchmark_name: str = "workload",
) -> BenchmarkMetrics:
    """
    Execute an asynchronous workload bounded by maximum concurrent in-flight tasks.

    Args:
        worker_fn: Async callable taking request index (int) and returning:
                   - bool (True for success, False for failure)
                   - dict containing {"success": bool, ...}
                   - None (treated as success)
        concurrency: Maximum number of simultaneous in-flight tasks (must be >= 1).
        total_requests: Total number of requests to execute.
        timeout_s: Optional per-request timeout in seconds.
        benchmark_name: Label for the collector run.
    """
    if concurrency < 1:
        raise ValueError(f"concurrency must be >= 1, got {concurrency}")

    collector = BenchmarkCollector(name=f"{benchmark_name}_c{concurrency}")
    if total_requests <= 0:
        return collector.compute_metrics(elapsed_time_s=0.0)

    semaphore = asyncio.Semaphore(concurrency)
    collector.start()

    async def _run_single_request(req_idx: int) -> None:
        async with semaphore:
            req_id = f"c{concurrency}-req-{req_idx}"
            t0 = time.perf_counter()
            try:
                if timeout_s is not None and timeout_s > 0:
                    result = await asyncio.wait_for(
                        worker_fn(req_idx), timeout=timeout_s
                    )
                else:
                    result = await worker_fn(req_idx)

                duration_ms = (time.perf_counter() - t0) * 1000.0

                success = True
                err_msg = None
                err_cat = None

                if isinstance(result, bool):
                    success = result
                    if not success:
                        err_cat = "unsuccessful_response"
                        err_msg = "Worker returned False"
                elif isinstance(result, dict):
                    success = bool(result.get("success", True))
                    if not success:
                        err_cat = str(
                            result.get("error_category") or "unsuccessful_response"
                        )
                        err_msg = str(
                            result.get("error")
                            or result.get("error_message")
                            or "Unsuccessful response"
                        )

                collector.record(
                    duration_ms=duration_ms,
                    success=success,
                    error=err_msg,
                    error_category=err_cat,
                    request_id=req_id,
                )
            except TimeoutError:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                collector.record(
                    duration_ms=duration_ms,
                    success=False,
                    error=f"Request timed out after {timeout_s}s",
                    error_category="timeout",
                    request_id=req_id,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                collector.record(
                    duration_ms=duration_ms,
                    success=False,
                    error=str(exc),
                    error_category=type(exc).__name__.lower(),
                    request_id=req_id,
                )

    tasks = [_run_single_request(i) for i in range(total_requests)]
    await asyncio.gather(*tasks)
    elapsed = collector.stop()
    return collector.compute_metrics(elapsed_time_s=elapsed)


async def run_concurrency_benchmark(
    worker_fn: Callable[[int], Coroutine[Any, Any, bool | dict[str, Any] | None]],
    concurrency_levels: Sequence[int] = DEFAULT_CONCURRENCY_LEVELS,
    requests_per_concurrency: int = 10,
    timeout_s: float | None = None,
    benchmark_name: str = "concurrency_benchmark",
) -> ConcurrencyBenchmarkReport:
    """
    Execute an asynchronous benchmark across multiple concurrency levels sequentially.

    Args:
        worker_fn: Async worker function to benchmark.
        concurrency_levels: Sequence of integer concurrency levels (default: 1, 5, 10, 20).
        requests_per_concurrency: Number of requests to issue at each concurrency level.
        timeout_s: Optional per-request timeout.
        benchmark_name: Name label for the benchmark suite.
    """
    levels = list(concurrency_levels)
    results: dict[int, BenchmarkMetrics] = {}
    overall_start = time.perf_counter()

    for c in levels:
        metrics = await run_concurrency_workload(
            worker_fn=worker_fn,
            concurrency=c,
            total_requests=requests_per_concurrency,
            timeout_s=timeout_s,
            benchmark_name=benchmark_name,
        )
        results[c] = metrics

    total_elapsed = max(0.0, time.perf_counter() - overall_start)

    return ConcurrencyBenchmarkReport(
        benchmark_name=benchmark_name,
        concurrency_levels=levels,
        results_by_concurrency=results,
        total_elapsed_s=total_elapsed,
    )


async def run_agent_concurrency_benchmark(
    cases: Sequence[EvaluationCase] | None = None,
    runner: str = "langgraph",
    concurrency_levels: Sequence[int] = DEFAULT_CONCURRENCY_LEVELS,
    requests_per_concurrency: int = 4,
    timeout_s: float | None = 15.0,
) -> ConcurrencyBenchmarkReport:
    """
    Benchmark agent execution throughput and latency percentiles under concurrent load
    using deterministic synthetic evaluation cases, mocked model responses, and
    isolated in-memory database sessions.

    Guarantees:
    - Zero external network access or paid Gemini API consumption.
    - Pure in-process simulated benchmark for relative pipeline comparison.
    """
    if cases is None:
        dataset = get_default_evaluation_dataset()
        eval_cases = dataset.cases
    else:
        eval_cases = list(cases)

    if not eval_cases:
        raise ValueError("Cannot run agent benchmark with empty cases sequence")

    # Set up in-memory SQLite database engine for benchmark isolation
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    # Build concurrent-safe mock LLM and mock tool returning first case fixtures
    mock_llm = _build_concurrent_mock_llm()
    tool_output = _create_mock_tool_output(eval_cases[0])
    mock_tool = SemanticSearchTool()
    mock_tool._run = AsyncMock(  # type: ignore[method-assign]
        return_value=ToolResult(
            success=True,
            output=tool_output,
            metadata={"count": len(tool_output)},
        )
    )

    registry = ToolRegistry()
    registry.register(mock_tool)
    service = AgentService(registry=registry)

    async def _agent_worker(req_idx: int) -> dict[str, Any]:
        case = eval_cases[req_idx % len(eval_cases)]
        user_id = uuid.uuid4()
        async with session_factory() as session:
            result = await service.run(
                db=session,
                question=case.query,
                user_id=user_id,
            )
            return {
                "success": result.success,
                "latency_ms": result.total_latency_ms,
                "error_category": "none" if result.success else "runner_failure",
            }

    try:
        with (
            patch(
                "app.config.settings.settings.enable_langgraph",
                runner == "langgraph",
            ),
            patch(
                "app.agents.agent_service.get_llm_provider",
                return_value=mock_llm,
            ),
            patch.object(service, "_persist_run", new_callable=AsyncMock),
            patch(
                "app.services.cache_service.cache_service.record_latency",
                new_callable=AsyncMock,
            ),
        ):
            report = await run_concurrency_benchmark(
                worker_fn=_agent_worker,
                concurrency_levels=concurrency_levels,
                requests_per_concurrency=requests_per_concurrency,
                timeout_s=timeout_s,
                benchmark_name=f"agent_{runner}_concurrency",
            )
            return report
    finally:
        await engine.dispose()
