"""
Enterprise RAG AI Assistant — Agent Execution Observability
===========================================================
Production-quality telemetry, structured lifecycle events, and bounded metrics
for both LangGraph and legacy agent execution pipelines.

Privacy & Safety Guarantees:
- Zero logging of raw queries, prompts, document text, tool arguments, or reasoning.
- Never swallows asyncio.CancelledError.
- Observability failures are completely safe and fail-open.
- Bounded metric labels only (no high-cardinality keys like run_id, user_id, doc_id).
- Monotonic clock for all duration measurements (time.perf_counter).
"""

from __future__ import annotations

import asyncio
import contextvars
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.core.logging import logger

# =============================================================================
# Context Correlation
# =============================================================================

_current_run_id_var: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "agent_current_run_id", default=None
)
_current_user_id_var: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "agent_current_user_id", default=None
)


def set_run_context(
    run_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> tuple[Any, Any]:
    """Bind the current execution run_id and user_id to contextvars."""
    t_run = _current_run_id_var.set(run_id)
    t_user = _current_user_id_var.set(user_id)
    return t_run, t_user


def reset_run_context(token: tuple[Any, Any]) -> None:
    """Reset contextvars using tokens acquired from set_run_context."""
    t_run, t_user = token
    _current_run_id_var.reset(t_run)
    _current_user_id_var.reset(t_user)


def get_current_run_id() -> uuid.UUID | None:
    """Retrieve the active run_id in the current async execution context."""
    return _current_run_id_var.get()


def get_current_user_id() -> uuid.UUID | None:
    """Retrieve the active user_id in the current async execution context."""
    return _current_user_id_var.get()


# =============================================================================
# Safe Error Categorization
# =============================================================================


class SafeErrorCategory(str, Enum):
    """Bounded, safe error categories that never expose sensitive error strings."""

    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"
    INJECTION_DETECTED = "injection_detected"
    VALIDATION_ERROR = "validation_error"
    PERMISSION_DENIED = "permission_denied"
    UNREGISTERED_TOOL = "unregistered_tool"
    INTERNAL_ERROR = "internal_error"
    NONE = "none"


def classify_error(
    exc: BaseException | None = None, error_str: str | None = None
) -> str:
    """Map exceptions or error messages to bounded, safe error category strings."""
    if exc is not None:
        if isinstance(exc, TimeoutError | asyncio.TimeoutError):
            return SafeErrorCategory.TIMEOUT.value
        exc_name = type(exc).__name__.lower()
        if "timeout" in exc_name:
            return SafeErrorCategory.TIMEOUT.value
        if "provider" in exc_name or "llm" in exc_name:
            return SafeErrorCategory.PROVIDER_ERROR.value
        if "validation" in exc_name or "valueerror" in exc_name:
            return SafeErrorCategory.VALIDATION_ERROR.value
        if "permission" in exc_name or "unauthorized" in exc_name:
            return SafeErrorCategory.PERMISSION_DENIED.value

    if error_str:
        err_lower = error_str.lower()
        if "timed out" in err_lower or "timeout" in err_lower:
            return SafeErrorCategory.TIMEOUT.value
        if "injection" in err_lower:
            return SafeErrorCategory.INJECTION_DETECTED.value
        if "permission" in err_lower or "admin privileges" in err_lower:
            return SafeErrorCategory.PERMISSION_DENIED.value
        if "not registered" in err_lower or "not found" in err_lower:
            return SafeErrorCategory.UNREGISTERED_TOOL.value
        if (
            "validation" in err_lower
            or "missing" in err_lower
            or "must be" in err_lower
        ):
            return SafeErrorCategory.VALIDATION_ERROR.value
        if "llm" in err_lower or "provider" in err_lower or "gemini" in err_lower:
            return SafeErrorCategory.PROVIDER_ERROR.value

    return SafeErrorCategory.INTERNAL_ERROR.value


# =============================================================================
# Bounded Internal Metrics Registry
# =============================================================================


@dataclass
class _DurationStats:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    def add(self, duration_ms: float) -> None:
        self.count += 1
        self.total_ms += duration_ms
        if duration_ms > self.max_ms:
            self.max_ms = duration_ms

    @property
    def avg_ms(self) -> float:
        return (self.total_ms / self.count) if self.count > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "total_ms": round(self.total_ms, 2),
            "avg_ms": round(self.avg_ms, 2),
            "max_ms": round(self.max_ms, 2),
        }


class AgentMetricsRegistry:
    """
    Lightweight, thread-safe metrics registry with bounded labels.
    Never uses run_id, user_id, document_id, query text, or prompts as labels.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._agent_runs: dict[tuple[str, str], int] = defaultdict(
            int
        )  # (runner, status) -> count
        self._agent_duration: dict[str, _DurationStats] = defaultdict(
            _DurationStats
        )  # runner -> stats
        self._node_executions: dict[tuple[str, str], int] = defaultdict(
            int
        )  # (node, status) -> count
        self._node_duration: dict[str, _DurationStats] = defaultdict(
            _DurationStats
        )  # node -> stats
        self._tool_calls: dict[tuple[str, str], int] = defaultdict(
            int
        )  # (tool, status) -> count
        self._tool_duration: dict[str, _DurationStats] = defaultdict(
            _DurationStats
        )  # tool -> stats
        self._reformulations_total: int = 0
        self._evidence_evaluations: dict[str, int] = defaultdict(
            int
        )  # outcome -> count

    def record_agent_run(self, runner: str, outcome: str, duration_ms: float) -> None:
        """Record an agent run completion with bounded runner and outcome labels."""
        safe_runner = "langgraph" if runner == "langgraph" else "legacy"
        safe_outcome = (
            outcome
            if outcome
            in ("success", "failure", "timeout", "blocked", "insufficient_evidence")
            else "failure"
        )
        with self._lock:
            self._agent_runs[(safe_runner, safe_outcome)] += 1
            self._agent_duration[safe_runner].add(max(0.0, duration_ms))

    def record_node_execution(
        self, node_name: str, outcome: str, duration_ms: float
    ) -> None:
        """Record a graph node execution with bounded node name and outcome labels."""
        safe_node = (
            node_name
            if node_name
            in ("plan", "execute_tool", "evaluate", "reformulate", "answer", "finalize")
            else "unknown"
        )
        safe_outcome = "success" if outcome == "success" else "failure"
        with self._lock:
            self._node_executions[(safe_node, safe_outcome)] += 1
            self._node_duration[safe_node].add(max(0.0, duration_ms))

    def record_tool_call(
        self, tool_name: str, outcome: str, duration_ms: float
    ) -> None:
        """Record a tool execution with bounded tool name and outcome labels."""
        safe_tool = (
            tool_name
            if tool_name
            in (
                "semantic_search",
                "document_lookup",
                "citation",
                "conversation_history",
                "slow_tool",
                "echo",
            )
            else "other"
        )
        safe_outcome = (
            outcome if outcome in ("success", "failure", "timeout") else "failure"
        )
        with self._lock:
            self._tool_calls[(safe_tool, safe_outcome)] += 1
            self._tool_duration[safe_tool].add(max(0.0, duration_ms))

    def record_reformulation(self) -> None:
        """Increment count of adaptive query reformulations."""
        with self._lock:
            self._reformulations_total += 1

    def record_evidence_evaluation(self, sufficient: bool) -> None:
        """Record outcome of retrieval evidence evaluation."""
        outcome = "sufficient" if sufficient else "insufficient"
        with self._lock:
            self._evidence_evaluations[outcome] += 1

    def get_snapshot(self) -> dict[str, Any]:
        """Return a structured, JSON-serializable snapshot of all recorded metrics."""
        with self._lock:
            return {
                "agent_runs_total": {
                    f"{runner}:{status}": count
                    for (runner, status), count in self._agent_runs.items()
                },
                "agent_duration_ms": {
                    runner: stats.to_dict()
                    for runner, stats in self._agent_duration.items()
                },
                "node_executions_total": {
                    f"{node}:{status}": count
                    for (node, status), count in self._node_executions.items()
                },
                "node_duration_ms": {
                    node: stats.to_dict() for node, stats in self._node_duration.items()
                },
                "tool_calls_total": {
                    f"{tool}:{status}": count
                    for (tool, status), count in self._tool_calls.items()
                },
                "tool_duration_ms": {
                    tool: stats.to_dict() for tool, stats in self._tool_duration.items()
                },
                "reformulations_total": self._reformulations_total,
                "evidence_evaluations_total": dict(self._evidence_evaluations),
            }

    def generate_prometheus_lines(self) -> list[str]:
        """Generate Prometheus exposition format lines for the metrics endpoint."""
        lines: list[str] = [
            "# HELP agent_runs_total Total agent runs by runner and status.",
            "# TYPE agent_runs_total counter",
        ]
        with self._lock:
            for (runner, status), count in sorted(self._agent_runs.items()):
                lines.append(
                    f'agent_runs_total{{runner="{runner}",status="{status}"}} {count}'
                )

            lines.extend(
                [
                    "# HELP agent_tool_calls_total Total tool calls by tool name and status.",
                    "# TYPE agent_tool_calls_total counter",
                ]
            )
            for (tool, status), count in sorted(self._tool_calls.items()):
                lines.append(
                    f'agent_tool_calls_total{{tool="{tool}",status="{status}"}} {count}'
                )

            lines.extend(
                [
                    "# HELP agent_node_executions_total Total node executions by node and status.",
                    "# TYPE agent_node_executions_total counter",
                ]
            )
            for (node, status), count in sorted(self._node_executions.items()):
                lines.append(
                    f'agent_node_executions_total{{node="{node}",status="{status}"}} {count}'
                )

            lines.extend(
                [
                    "# HELP agent_reformulations_total Total adaptive query reformulations.",
                    "# TYPE agent_reformulations_total counter",
                    f"agent_reformulations_total {self._reformulations_total}",
                    "# HELP agent_evidence_evaluations_total Total evidence evaluations by outcome.",
                    "# TYPE agent_evidence_evaluations_total counter",
                ]
            )
            for outcome, count in sorted(self._evidence_evaluations.items()):
                lines.append(
                    f'agent_evidence_evaluations_total{{outcome="{outcome}"}} {count}'
                )

        return lines

    def reset(self) -> None:
        """Reset all metrics (primarily for test isolation)."""
        with self._lock:
            self._agent_runs.clear()
            self._agent_duration.clear()
            self._node_executions.clear()
            self._node_duration.clear()
            self._tool_calls.clear()
            self._tool_duration.clear()
            self._reformulations_total = 0
            self._evidence_evaluations.clear()


# Application-wide metrics registry instance
agent_metrics = AgentMetricsRegistry()


# =============================================================================
# Structured Event Emission (Fail-Safe & Privacy Enforcing)
# =============================================================================


# Strict allowlist of permissible structured log attributes
ALLOWED_LOG_FIELDS: frozenset[str] = frozenset(
    {
        "event",
        "log_type",
        "run_id",
        "user_id",
        "runner",
        "node_name",
        "tool_name",
        "duration_ms",
        "outcome",
        "error_category",
        "call_count",
        "retry_count",
        "retries",
        "reformulation_count",
        "evidence_outcome",
        "status",
    }
)

VALID_RUNNERS: frozenset[str] = frozenset({"langgraph", "legacy"})
VALID_NODES: frozenset[str] = frozenset(
    {"plan", "execute_tool", "evaluate", "reformulate", "answer", "finalize"}
)
VALID_TOOLS: frozenset[str] = frozenset(
    {
        "semantic_search",
        "document_lookup",
        "citation",
        "conversation_history",
        "slow_tool",
        "echo",
    }
)
VALID_OUTCOMES: frozenset[str] = frozenset(
    {"success", "failure", "timeout", "blocked", "insufficient_evidence"}
)
VALID_STATUSES: frozenset[str] = frozenset({"started", "completed", "failed"})
VALID_ERROR_CATEGORIES: frozenset[str] = frozenset({e.value for e in SafeErrorCategory})


def _normalize_uuid(val: Any) -> str | None:
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, str):
        try:
            return str(uuid.UUID(val))
        except (ValueError, AttributeError):
            return None
    return None


def _normalize_int(val: Any) -> int:
    try:
        return max(0, int(val))
    except (ValueError, TypeError):
        return 0


def _normalize_duration(val: Any) -> float:
    try:
        return round(max(0.0, float(val)), 2)
    except (ValueError, TypeError):
        return 0.0


def _filter_allowed_field(key: str, val: Any) -> tuple[str, Any] | None:
    """Validate and coerce an allowed log field; return (sanitized_key, sanitized_val) or None."""
    if key not in ALLOWED_LOG_FIELDS or val is None:
        return None

    if key in ("run_id", "user_id"):
        norm_id = _normalize_uuid(val)
        return (key, norm_id) if norm_id is not None else None

    if key == "runner":
        return (key, val if val in VALID_RUNNERS else "legacy")

    if key == "node_name":
        return (key, val if val in VALID_NODES else "unknown")

    if key == "tool_name":
        return (key, val if val in VALID_TOOLS else "other")

    if key == "outcome":
        return (key, val if val in VALID_OUTCOMES else "failure")

    if key == "error_category":
        return (key, val if val in VALID_ERROR_CATEGORIES else "internal_error")

    if key == "status":
        return (key, val if val in VALID_STATUSES else "unknown")

    if key == "evidence_outcome":
        return (
            key,
            "sufficient" if str(val).lower() == "sufficient" else "insufficient",
        )

    if key == "duration_ms":
        return (key, _normalize_duration(val))

    if key in ("call_count", "reformulation_count"):
        return (key, _normalize_int(val))

    if key in ("retry_count", "retries"):
        return ("retry_count", _normalize_int(val))

    return None


def emit_agent_event(event_name: str, **kwargs: Any) -> None:
    """
    Emit a structured JSON log entry via Loguru with strict allowlist enforcement.

    Guarantees:
    - Never throws; any logging failure is silently swallowed (fail-open).
    - Preserves asyncio cancellation if interrupted.
    - Strictly drops ANY unapproved field before serialization (no blocklist reliance).
    - Bounded value validation prevents arbitrary strings from penetrating the log layer.
    """
    safe_extra: dict[str, Any] = {
        "log_type": "agent_observability",
        "event": str(event_name)[:64],
    }

    # Strict allowlist filtering and value normalization
    for k, v in kwargs.items():
        res = _filter_allowed_field(k.lower(), v)
        if res is not None:
            safe_extra[res[0]] = res[1]

    # Automatically correlate run_id from ContextVar if not present
    if "run_id" not in safe_extra:
        ctx_run_id = get_current_run_id()
        if ctx_run_id is not None:
            safe_extra["run_id"] = str(ctx_run_id)

    # Automatically correlate user_id from ContextVar if not present
    if "user_id" not in safe_extra:
        ctx_user_id = get_current_user_id()
        if ctx_user_id is not None:
            safe_extra["user_id"] = str(ctx_user_id)

    try:
        level = (
            "WARNING"
            if safe_extra.get("outcome") in ("failure", "timeout", "blocked")
            else "INFO"
        )
        logger.log(level, f"[AgentObservability] {safe_extra['event']}", **safe_extra)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.debug(f"[AgentObservability] Telemetry emit suppressed: {exc}")


# =============================================================================
# High-Level Lifecycle Hooks
# =============================================================================


def on_agent_started(
    run_id: uuid.UUID,
    runner: str,
    user_id: uuid.UUID | None = None,
) -> None:
    """Emitted when an agent execution begins."""
    try:
        emit_agent_event(
            "agent_started",
            run_id=run_id,
            runner=runner,
            user_id=user_id,
            status="started",
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


def on_agent_completed(
    run_id: uuid.UUID,
    runner: str,
    duration_ms: float,
    outcome: str = "success",
    call_count: int = 0,
    reformulation_count: int = 0,
    evidence_outcome: str = "sufficient",
    user_id: uuid.UUID | None = None,
) -> None:
    """Emitted when an agent execution finishes successfully."""
    try:
        agent_metrics.record_agent_run(
            runner=runner, outcome=outcome, duration_ms=duration_ms
        )
        emit_agent_event(
            "agent_completed",
            run_id=run_id,
            runner=runner,
            duration_ms=round(duration_ms, 2),
            outcome=outcome,
            call_count=call_count,
            reformulation_count=reformulation_count,
            evidence_outcome=evidence_outcome,
            user_id=user_id,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


def on_agent_failed(
    run_id: uuid.UUID,
    runner: str,
    duration_ms: float,
    error_category: str = "internal_error",
    outcome: str = "failure",
    user_id: uuid.UUID | None = None,
) -> None:
    """Emitted when an agent execution fails or is blocked."""
    try:
        agent_metrics.record_agent_run(
            runner=runner, outcome=outcome, duration_ms=duration_ms
        )
        emit_agent_event(
            "agent_failed",
            run_id=run_id,
            runner=runner,
            duration_ms=round(duration_ms, 2),
            outcome=outcome,
            error_category=error_category,
            user_id=user_id,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


def on_agent_timed_out(
    run_id: uuid.UUID,
    runner: str,
    duration_ms: float,
    user_id: uuid.UUID | None = None,
) -> None:
    """Emitted when overall execution budget is exhausted."""
    try:
        agent_metrics.record_agent_run(
            runner=runner, outcome="timeout", duration_ms=duration_ms
        )
        emit_agent_event(
            "agent_timed_out",
            run_id=run_id,
            runner=runner,
            duration_ms=round(duration_ms, 2),
            outcome="timeout",
            error_category="timeout",
            user_id=user_id,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


def on_node_started(run_id: uuid.UUID, node_name: str) -> None:
    """Emitted when a LangGraph node starts execution."""
    try:
        emit_agent_event(
            "graph_node_started",
            run_id=run_id,
            node_name=node_name,
            status="started",
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


def on_node_completed(
    run_id: uuid.UUID,
    node_name: str,
    duration_ms: float,
    outcome: str = "success",
) -> None:
    """Emitted when a LangGraph node successfully completes."""
    try:
        agent_metrics.record_node_execution(
            node_name=node_name, outcome=outcome, duration_ms=duration_ms
        )
        emit_agent_event(
            "graph_node_completed",
            run_id=run_id,
            node_name=node_name,
            duration_ms=round(duration_ms, 2),
            outcome=outcome,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


def on_node_failed(
    run_id: uuid.UUID,
    node_name: str,
    duration_ms: float,
    error_category: str = "internal_error",
) -> None:
    """Emitted when a LangGraph node raises an exception."""
    try:
        agent_metrics.record_node_execution(
            node_name=node_name, outcome="failure", duration_ms=duration_ms
        )
        emit_agent_event(
            "graph_node_failed",
            run_id=run_id,
            node_name=node_name,
            duration_ms=round(duration_ms, 2),
            outcome="failure",
            error_category=error_category,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


def on_tool_started(run_id: uuid.UUID, tool_name: str) -> None:
    """Emitted when a tool invocation begins."""
    try:
        emit_agent_event(
            "tool_call_started",
            run_id=run_id,
            tool_name=tool_name,
            status="started",
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


def on_tool_completed(
    run_id: uuid.UUID,
    tool_name: str,
    duration_ms: float,
    retries: int = 0,
) -> None:
    """Emitted when a tool invocation succeeds."""
    try:
        agent_metrics.record_tool_call(
            tool_name=tool_name, outcome="success", duration_ms=duration_ms
        )
        emit_agent_event(
            "tool_call_completed",
            run_id=run_id,
            tool_name=tool_name,
            duration_ms=round(duration_ms, 2),
            outcome="success",
            retries=retries,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


def on_tool_failed(
    run_id: uuid.UUID,
    tool_name: str,
    duration_ms: float,
    error_category: str = "internal_error",
    retries: int = 0,
) -> None:
    """Emitted when a tool invocation fails after retries."""
    try:
        agent_metrics.record_tool_call(
            tool_name=tool_name, outcome="failure", duration_ms=duration_ms
        )
        emit_agent_event(
            "tool_call_failed",
            run_id=run_id,
            tool_name=tool_name,
            duration_ms=round(duration_ms, 2),
            outcome="failure",
            error_category=error_category,
            retries=retries,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


def on_tool_timed_out(
    run_id: uuid.UUID,
    tool_name: str,
    duration_ms: float,
    retries: int = 0,
) -> None:
    """Emitted when a tool invocation exceeds its timeout."""
    try:
        agent_metrics.record_tool_call(
            tool_name=tool_name, outcome="timeout", duration_ms=duration_ms
        )
        emit_agent_event(
            "tool_call_timed_out",
            run_id=run_id,
            tool_name=tool_name,
            duration_ms=round(duration_ms, 2),
            outcome="timeout",
            error_category="timeout",
            retries=retries,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


def on_evidence_evaluated(
    run_id: uuid.UUID,
    evidence_sufficient: bool,
    call_count: int = 0,
    next_action: str = "",
) -> None:
    """Emitted when retrieval evidence evaluation completes."""
    try:
        agent_metrics.record_evidence_evaluation(evidence_sufficient)
        emit_agent_event(
            "evidence_evaluated",
            run_id=run_id,
            evidence_outcome="sufficient" if evidence_sufficient else "insufficient",
            outcome="sufficient" if evidence_sufficient else "insufficient",
            call_count=call_count,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


def on_query_reformulated(
    run_id: uuid.UUID,
    reformulation_count: int,
) -> None:
    """Emitted when adaptive query reformulation is executed."""
    try:
        agent_metrics.record_reformulation()
        emit_agent_event(
            "query_reformulated",
            run_id=run_id,
            reformulation_count=reformulation_count,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass
