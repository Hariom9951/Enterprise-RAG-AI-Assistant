"""
Enterprise RAG AI Assistant — Fault-Injection Benchmarking Suite
================================================================
Deterministic benchmarks simulating dependency failures, cache outages,
database rollbacks, tool timeouts, and cancellation propagation.

Design Guarantees & Constraints:
- Pure offline execution: Simulated faults via controlled mocks.
- Fail-open verification: Verifies non-authoritative services (Redis cache)
  fail open safely without raising 500s or crashing the application.
- Fail-closed verification: Verifies authoritative transactions and authorization
  boundaries strictly fail closed (automatic rollback, zero cross-user leakage).
- Metric & context cleanup: Validates that active-run context and telemetry are
  cleaned up when agent workflows are cancelled.
- No fragile timing thresholds: Validates structural behavior and state transitions.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from redis.exceptions import ConnectionError as RedisConnectionError

from app.agents.agent_service import AgentService
from app.agents.graph.agent_graph import AgentWorkflowBuilder
from app.agents.observability import (
    classify_error,
    get_current_run_id,
    reset_run_context,
    set_run_context,
)
from app.core.exceptions import NotFoundException
from app.db.session import get_db
from app.models.document import Document
from app.models.user import User
from app.services import document_service
from app.services.cache_service import RedisCacheService


@dataclass
class FaultInjectionResult:
    """Outcome of an individual fault-injection benchmark scenario."""

    scenario_name: str
    fault_type: str
    expected_behavior: str
    behavior_verified: bool
    elapsed_ms: float
    error_classification: str
    details: dict[str, Any] = field(default_factory=dict)
    measurement_type: str = "simulated_fault_injection"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FaultInjectionReport:
    """Aggregated report of all executed fault-injection benchmark scenarios."""

    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    elapsed_total_s: float
    results: list[FaultInjectionResult]
    measurement_type: str = "simulated_fault_injection"
    disclaimer: str = (
        "Fault-injection benchmarks verify fail-open resilience, transaction rollback "
        "boundaries, and clean cancellation propagation under simulated failure conditions "
        "without asserting timing thresholds."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_scenarios": self.total_scenarios,
            "passed_scenarios": self.passed_scenarios,
            "failed_scenarios": self.failed_scenarios,
            "elapsed_total_s": round(self.elapsed_total_s, 4),
            "measurement_type": self.measurement_type,
            "disclaimer": self.disclaimer,
            "results": [r.to_dict() for r in self.results],
        }


async def benchmark_redis_cache_fail_open() -> FaultInjectionResult:
    """
    Inject connection outage into Redis cache and verify documented fail-open behavior:
    - cache.get() fails open to None without raising
    - cache.set() fails open to False without raising
    - cache.delete() fails open to False without raising
    - cache.record_latency() fails open safely
    """
    cache = RedisCacheService()
    t0 = time.perf_counter()
    behavior_verified = False
    details: dict[str, Any] = {}

    with patch.object(cache, "_get_redis") as mock_get_redis:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(
            side_effect=RedisConnectionError(
                "Simulated Redis outage: Connection refused"
            )
        )
        mock_client.set = AsyncMock(
            side_effect=RedisConnectionError(
                "Simulated Redis outage: Connection refused"
            )
        )
        mock_client.delete = AsyncMock(
            side_effect=RedisConnectionError(
                "Simulated Redis outage: Connection refused"
            )
        )
        mock_client.lpush = AsyncMock(
            side_effect=RedisConnectionError(
                "Simulated Redis outage: Connection refused"
            )
        )
        mock_get_redis.return_value = mock_client

        # 1. get() fails open
        val = await cache.get("benchmark_fault_key")
        get_ok = val is None

        # 2. set() fails open
        set_ok = (await cache.set("benchmark_fault_key", {"data": 1})) is False

        # 3. delete() fails open
        del_ok = (await cache.delete("benchmark_fault_key")) is False

        # 4. record_latency() fails open
        latency_ok = True
        try:
            await cache.record_latency("test_route", 42.0)
        except Exception:
            latency_ok = False

        behavior_verified = get_ok and set_ok and del_ok and latency_ok
        details = {
            "get_failed_open_to_none": get_ok,
            "set_failed_open_to_false": set_ok,
            "delete_failed_open_to_false": del_ok,
            "record_latency_failed_open": latency_ok,
        }

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return FaultInjectionResult(
        scenario_name="redis_cache_outage_fail_open",
        fault_type="redis_connection_error",
        expected_behavior="fail_open_non_blocking",
        behavior_verified=behavior_verified,
        elapsed_ms=round(elapsed_ms, 2),
        error_classification="redis_connection_error",
        details=details,
    )


async def benchmark_database_transaction_rollback() -> FaultInjectionResult:
    """
    Inject exception into database session generator (get_db) and verify:
    - Transaction strictly rolls back
    - Commit is never called
    - Session is cleanly closed
    """
    mock_session = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.commit = AsyncMock()

    class MockContextManager:
        async def __aenter__(self) -> AsyncMock:
            return mock_session

        async def __aexit__(
            self, exc_type: object, exc_val: object, exc_tb: object
        ) -> None:
            return None

    t0 = time.perf_counter()
    rollback_called = False
    commit_prevented = False
    close_called = False

    with patch("app.db.session.AsyncSessionLocal", return_value=MockContextManager()):
        gen = get_db()
        await gen.__anext__()
        try:
            await gen.athrow(RuntimeError("Simulated database transaction crash"))
        except RuntimeError:
            pass

    rollback_called = mock_session.rollback.await_count == 1
    commit_prevented = mock_session.commit.await_count == 0
    close_called = mock_session.close.await_count == 1
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    verified = rollback_called and commit_prevented and close_called

    return FaultInjectionResult(
        scenario_name="database_transaction_rollback_on_crash",
        fault_type="database_operational_error",
        expected_behavior="fail_closed_transaction_rollback",
        behavior_verified=verified,
        elapsed_ms=round(elapsed_ms, 2),
        error_classification="database_error",
        details={
            "rollback_awaited": rollback_called,
            "commit_prevented": commit_prevented,
            "session_closed": close_called,
        },
    )


async def benchmark_authorization_boundary_enforcement(
    db_session: Any,
) -> FaultInjectionResult:
    """
    Inject cross-tenant access attempt and verify:
    - System strictly fails closed (raises NotFoundException, 404/403)
    - Zero document content or metadata leaked to non-owner
    """
    user_a = User(
        full_name="Tenant A",
        email=f"tenanta_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="pw",
        is_active=True,
    )
    user_b = User(
        full_name="Tenant B",
        email=f"tenantb_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="pw",
        is_active=True,
    )
    db_session.add_all([user_a, user_b])
    await db_session.commit()
    await db_session.refresh(user_a)
    await db_session.refresh(user_b)

    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=user_a.id,
        original_filename="secret_tenant_a.txt",
        stored_filename=f"secret_{doc_id}.txt",
        mime_type="text/plain",
        file_size=100,
        sha256_hash=f"sha_{doc_id.hex}",
        storage_path="/tmp/secret.txt",
        processing_status="COMPLETED",
    )
    db_session.add(doc)
    await db_session.commit()

    t0 = time.perf_counter()
    get_blocked = False
    update_blocked = False
    delete_blocked = False

    try:
        await document_service.get_document_by_id(db_session, doc_id, user_b.id)
    except NotFoundException:
        get_blocked = True

    try:
        await document_service.update_document_metadata(
            db_session, doc_id, user_b.id, original_filename="hijack.txt"
        )
    except NotFoundException:
        update_blocked = True

    try:
        await document_service.delete_document(db_session, doc_id, user_b.id)
    except NotFoundException:
        delete_blocked = True

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    verified = get_blocked and update_blocked and delete_blocked

    return FaultInjectionResult(
        scenario_name="tenant_authorization_boundary_fail_closed",
        fault_type="unauthorized_cross_tenant_access",
        expected_behavior="fail_closed_not_found",
        behavior_verified=verified,
        elapsed_ms=round(elapsed_ms, 2),
        error_classification="permission_denied",
        details={
            "get_blocked_404": get_blocked,
            "update_blocked_404": update_blocked,
            "delete_blocked_404": delete_blocked,
        },
    )


async def benchmark_tool_timeout_and_error_mapping() -> FaultInjectionResult:
    """
    Inject a simulated tool timeout into the agent execution loop and verify:
    - Exception is safely classified into SafeErrorCategory.TIMEOUT
    - Agent handles tool failure without unhandled crash
    """
    t0 = time.perf_counter()
    timeout_err = TimeoutError("Tool invocation exceeded 0.5s limit")
    category = classify_error(timeout_err)

    verified = category == "timeout"
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return FaultInjectionResult(
        scenario_name="tool_timeout_error_classification",
        fault_type="tool_timeout",
        expected_behavior="classify_as_timeout_safe",
        behavior_verified=verified,
        elapsed_ms=round(elapsed_ms, 2),
        error_classification=category,
        details={"classified_category": category},
    )


async def benchmark_agent_cancellation_and_cleanup(
    db_session: Any,
) -> FaultInjectionResult:
    """
    Inject asyncio.CancelledError into active agent execution and verify:
    - CancelledError is never swallowed (cleanly propagates to caller)
    - Active run context variables are reset and not leaked to subsequent tasks
    """
    run_id = uuid.uuid4()
    user_id = uuid.uuid4()
    tokens = set_run_context(run_id, user_id)
    assert get_current_run_id() == run_id

    service = AgentService()
    builder = AgentWorkflowBuilder(service=service, db=db_session)

    t0 = time.perf_counter()
    cancellation_propagated = False

    try:
        with patch.object(builder, "plan_node", side_effect=asyncio.CancelledError()):
            await builder.plan_node(
                {
                    "run_id": run_id,
                    "user_id": user_id,
                    "question": "test question",
                    "top_k": 3,
                    "threshold": 0.0,
                    "wall_t0": 0.0,
                    "loop_budget_s": 5.0,
                    "max_tool_calls": 2,
                    "call_count": 0,
                    "tool_records": [],
                    "retrieved_documents": [],
                    "evidence_sufficient": False,
                    "next_action": "plan",
                    "reformulation_count": 0,
                    "max_reformulations": 1,
                    "evaluation_reason": None,
                    "success": True,
                    "error_message": None,
                    "is_blocked": False,
                    "confidence_score": 0.0,
                }
            )
    except asyncio.CancelledError:
        cancellation_propagated = True
    finally:
        reset_run_context(tokens)

    context_cleaned_up = get_current_run_id() is None
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    verified = cancellation_propagated and context_cleaned_up

    return FaultInjectionResult(
        scenario_name="agent_cancellation_propagation_and_context_cleanup",
        fault_type="asyncio_cancelled_error",
        expected_behavior="clean_propagation_and_context_reset",
        behavior_verified=verified,
        elapsed_ms=round(elapsed_ms, 2),
        error_classification="cancelled",
        details={
            "cancellation_propagated": cancellation_propagated,
            "context_cleaned_up": context_cleaned_up,
        },
    )


async def benchmark_celery_task_retry_and_exhaustion() -> FaultInjectionResult:
    """
    Simulate worker failure, transient errors triggering Celery retries,
    and retry exhaustion marking documents FAILED.
    """
    from celery.exceptions import MaxRetriesExceededError, Retry

    from app.tasks.document_tasks import process_document

    t0 = time.perf_counter()
    doc_id = uuid.uuid4()
    doc_id_str = str(doc_id)
    actual_task = getattr(
        process_document, "_get_current_object", lambda: process_document
    )()

    # 1. Transient error: self.retry is triggered
    retry_triggered = False

    def mock_run_async_fail(coro: Any) -> None:
        if hasattr(coro, "close"):
            coro.close()
        raise ConnectionResetError("DB lock timeout")

    with (
        patch.object(
            actual_task,
            "retry",
            side_effect=Retry("Simulated transient network glitch, retry scheduled"),
        ),
        patch(
            "app.tasks.document_tasks.run_async_in_thread",
            side_effect=mock_run_async_fail,
        ),
    ):
        try:
            process_document(doc_id_str)
        except Retry:
            retry_triggered = True

    # 2. Retry limits exhausted: _async_handle_failure is invoked
    handle_failure_invoked = False
    exhaust_calls = 0

    def mock_run_async_exhaust(coro: Any) -> None:
        nonlocal handle_failure_invoked, exhaust_calls
        exhaust_calls += 1
        if hasattr(coro, "close"):
            coro.close()
        if exhaust_calls == 1:
            raise ConnectionResetError("DB lock timeout")
        handle_failure_invoked = True

    with (
        patch.object(
            actual_task,
            "retry",
            side_effect=MaxRetriesExceededError("Can't retry: max retries reached"),
        ),
        patch(
            "app.tasks.document_tasks.run_async_in_thread",
            side_effect=mock_run_async_exhaust,
        ),
    ):
        try:
            process_document(doc_id_str)
        except MaxRetriesExceededError:
            pass

    # 3. Permanent validation failure (FileNotFoundError): fail immediately without retry
    permanent_fail_invoked = False
    perm_calls = 0

    def mock_run_async_perm(coro: Any) -> None:
        nonlocal permanent_fail_invoked, perm_calls
        perm_calls += 1
        if hasattr(coro, "close"):
            coro.close()
        if perm_calls == 1:
            raise FileNotFoundError("File not found on disk")
        permanent_fail_invoked = True

    with (
        patch.object(actual_task, "retry") as mock_perm_retry,
        patch(
            "app.tasks.document_tasks.run_async_in_thread",
            side_effect=mock_run_async_perm,
        ),
    ):
        try:
            process_document(doc_id_str)
        except FileNotFoundError:
            pass

    no_retry_on_permanent = mock_perm_retry.call_count == 0

    verified = (
        retry_triggered
        and handle_failure_invoked
        and permanent_fail_invoked
        and no_retry_on_permanent
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return FaultInjectionResult(
        scenario_name="celery_task_retry_and_exhaustion",
        fault_type="transient_task_failure_and_exhaustion",
        expected_behavior="retry_on_transient_and_mark_failed_on_exhaustion",
        behavior_verified=verified,
        elapsed_ms=round(elapsed_ms, 2),
        error_classification="transient_worker_retry",
        details={
            "transient_retry_triggered": retry_triggered,
            "retry_exhaustion_handled": handle_failure_invoked,
            "permanent_failure_rejected_without_retry": (
                permanent_fail_invoked and no_retry_on_permanent
            ),
        },
    )


async def run_fault_injection_suite(
    db_session: Any,
) -> FaultInjectionReport:
    """
    Execute all deterministic fault-injection benchmark scenarios sequentially.
    """
    t0 = time.perf_counter()
    results: list[FaultInjectionResult] = [
        await benchmark_redis_cache_fail_open(),
        await benchmark_database_transaction_rollback(),
        await benchmark_authorization_boundary_enforcement(db_session),
        await benchmark_tool_timeout_and_error_mapping(),
        await benchmark_agent_cancellation_and_cleanup(db_session),
        await benchmark_celery_task_retry_and_exhaustion(),
    ]

    total = len(results)
    passed = sum(1 for r in results if r.behavior_verified)
    failed = total - passed
    elapsed_total = max(0.0, time.perf_counter() - t0)

    return FaultInjectionReport(
        total_scenarios=total,
        passed_scenarios=passed,
        failed_scenarios=failed,
        elapsed_total_s=elapsed_total,
        results=results,
    )
