"""
Enterprise RAG AI Assistant — Evaluation Suite Runner & CLI
============================================================
Executes the evaluation dataset across legacy and LangGraph agent runners, computes
aggregate IR and agent metrics, and outputs a sanitized machine-readable JSON report.

Usage:
------
Programmatic:
    from app.evaluation.runner import run_evaluation_suite
    report = await run_evaluation_suite()

CLI:
    python -m app.evaluation.runner --output evaluation_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.db.base import Base
from app.evaluation.dataset import EvaluationDataset, get_default_evaluation_dataset
from app.evaluation.runner_comparison import compare_case_execution

METRIC_DEFINITIONS: dict[str, str] = {
    "precision@k": "Proportion of top-K retrieved items that match ground-truth relevant IDs.",
    "recall@k": "Proportion of all ground-truth relevant items that were successfully retrieved in top-K.",
    "mrr": "Mean Reciprocal Rank (1/rank) of the first relevant item retrieved across all queries.",
    "hit_rate@k": "Binary rate of queries where at least one relevant document was retrieved in top-K.",
    "citation_validity_rate": "Fraction of bracket citations [N] that map to valid retrieved document indices.",
    "target_citation_recall": "Fraction of expected citation target chunk IDs that were cited in final answer.",
    "abstention_accuracy": "Accuracy of agent declining to answer when evidence is insufficient or query is adversarial.",
    "success_rate": "Proportion of agent runs that completed with success=True and valid structural contracts.",
}


async def run_evaluation_suite(
    dataset: EvaluationDataset | None = None,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """
    Execute the offline evaluation framework across all cases in the dataset.
    Generates a structured, privacy-preserving JSON report comparing Legacy and LangGraph.
    """
    if dataset is None:
        dataset = get_default_evaluation_dataset()

    # If no DB session is supplied, use an isolated in-memory SQLite engine
    session_to_use: AsyncSession
    engine = None
    if db is None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(
            bind=engine, class_=AsyncSession, expire_on_commit=False
        )
        session_to_use = session_factory()
    else:
        session_to_use = db

    comparison_results = []
    failed_cases = []

    try:
        for case in dataset.cases:
            try:
                comp = await compare_case_execution(case, session_to_use)
                comparison_results.append(comp)
                if not comp.legacy.success or not comp.langgraph.success:
                    failed_cases.append(
                        {
                            "case_id": case.case_id,
                            "category": case.category.value,
                            "legacy_success": comp.legacy.success,
                            "langgraph_success": comp.langgraph.success,
                            "divergences": comp.divergences,
                        }
                    )
            except Exception as exc:
                failed_cases.append(
                    {
                        "case_id": case.case_id,
                        "category": case.category.value,
                        "error": str(exc),
                    }
                )
    finally:
        if engine is not None:
            await session_to_use.close()
            await engine.dispose()

    # Compute aggregate metrics for legacy and langgraph
    total_cases = len(comparison_results)
    if total_cases == 0:
        return {"error": "No cases evaluated"}

    def _aggregate_runner_metrics(runner_key: str) -> dict[str, float]:
        metrics_list = [getattr(c, runner_key) for c in comparison_results]
        n = len(metrics_list)
        return {
            "precision@3": round(sum(m.precision_at_3 for m in metrics_list) / n, 4),
            "recall@3": round(sum(m.recall_at_3 for m in metrics_list) / n, 4),
            "hit_rate@3": round(sum(m.hit_rate_at_3 for m in metrics_list) / n, 4),
            "mrr": round(sum(m.reciprocal_rank for m in metrics_list) / n, 4),
            "citation_validity_rate": round(
                sum(m.citation_validity_rate for m in metrics_list) / n, 4
            ),
            "abstention_accuracy": round(
                sum(1.0 if m.abstention_correct else 0.0 for m in metrics_list) / n, 4
            ),
            "success_rate": round(
                sum(1.0 if m.success else 0.0 for m in metrics_list) / n, 4
            ),
            "avg_latency_ms": round(sum(m.latency_ms for m in metrics_list) / n, 2),
        }

    legacy_agg = _aggregate_runner_metrics("legacy")
    langgraph_agg = _aggregate_runner_metrics("langgraph")

    # Match summary
    matched_cases = sum(1 for c in comparison_results if c.match_status)

    report: dict[str, Any] = {
        "dataset_version": dataset.version,
        "evaluation_timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "evaluation_environment": {
            "mode": "offline_deterministic",
            "llm_mocked": True,
            "external_api_calls": False,
            "live_database_required": False,
        },
        "metric_definitions": METRIC_DEFINITIONS,
        "configuration": {
            "total_cases": total_cases,
            "retrieval_k": 3,
            "runners_evaluated": ["legacy", "langgraph"],
        },
        "aggregate_metrics": {
            "legacy": legacy_agg,
            "langgraph": langgraph_agg,
        },
        "comparison_summary": {
            "total_evaluated": total_cases,
            "identical_behavior_cases": matched_cases,
            "divergent_cases": total_cases - matched_cases,
            "divergence_details": [
                {"case_id": c.case_id, "divergences": c.divergences}
                for c in comparison_results
                if not c.match_status
            ],
        },
        "per_case_results": [
            {
                "case_id": c.case_id,
                "category": c.category,
                "query": c.query,
                "legacy": {
                    "success": c.legacy.success,
                    "retrieved_count": len(c.legacy.retrieved_chunk_ids),
                    "precision@3": c.legacy.precision_at_3,
                    "recall@3": c.legacy.recall_at_3,
                    "mrr": c.legacy.reciprocal_rank,
                    "abstention_correct": c.legacy.abstention_correct,
                    "citations_present": c.legacy.citations_present,
                    "citation_validity": c.legacy.citation_validity_rate,
                },
                "langgraph": {
                    "success": c.langgraph.success,
                    "retrieved_count": len(c.langgraph.retrieved_chunk_ids),
                    "precision@3": c.langgraph.precision_at_3,
                    "recall@3": c.langgraph.recall_at_3,
                    "mrr": c.langgraph.reciprocal_rank,
                    "abstention_correct": c.langgraph.abstention_correct,
                    "citations_present": c.langgraph.citations_present,
                    "citation_validity": c.langgraph.citation_validity_rate,
                },
                "match_status": c.match_status,
            }
            for c in comparison_results
        ],
        "failed_cases": failed_cases,
    }

    return report


def main() -> None:
    """CLI entrypoint for offline evaluation report generation."""
    parser = argparse.ArgumentParser(description="NexusAI Offline Evaluation Suite")
    parser.add_argument(
        "--output", type=str, default=None, help="Path to write JSON report"
    )
    args = parser.parse_args()

    report = asyncio.run(run_evaluation_suite())
    formatted = json.dumps(report, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(formatted)
        print(f"Evaluation report written to {args.output}")
    else:
        print(formatted)


if __name__ == "__main__":
    main()
