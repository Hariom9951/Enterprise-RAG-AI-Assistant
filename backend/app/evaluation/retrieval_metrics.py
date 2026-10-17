"""
Enterprise RAG AI Assistant — Retrieval Evaluation Metrics
===========================================================
Pure offline implementation of standard Information Retrieval (IR) evaluation metrics:
Recall@K, Precision@K, Mean Reciprocal Rank (MRR), and Hit Rate@K.

Formal Definitions:
-------------------
1. Precision@K:
   Fraction of the top-K retrieved items that are in the relevant ground-truth set.
   Precision@K = |Retrieved@K ∩ Relevant| / min(K, |Retrieved@K|)

2. Recall@K:
   Fraction of all relevant ground-truth items that were successfully retrieved in the top-K.
   Recall@K = |Retrieved@K ∩ Relevant| / |Relevant|

3. Reciprocal Rank (RR@K):
   Reciprocal of the 1-based rank of the FIRST relevant item in the top-K.
   RR@K = 1 / rank_first_relevant if found else 0.0

4. Hit Rate@K:
   Binary indicator of whether at least one relevant item appears in the top-K.
   Hit@K = 1.0 if |Retrieved@K ∩ Relevant| > 0 else 0.0

Zero-Relevant Edge Case Handling:
---------------------------------
For queries where ground-truth |Relevant| == 0 (e.g., negative / unanswerable cases):
- If the system also retrieved 0 items: Precision, Recall, RR, and Hit Rate are 1.0
  (the system correctly refrained from retrieving irrelevant noise).
- If the system retrieved items: Precision, Recall, RR, and Hit Rate are 0.0
  (every retrieved item was irrelevant).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def deduplicate_rankings(ranking: Sequence[str]) -> list[str]:
    """
    Remove duplicate identifiers from a ranked list while strictly preserving
    the original relative ranking order of first appearances.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for item in ranking:
        cleaned = str(item).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            ordered.append(cleaned)
    return ordered


def calculate_precision_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str] | Sequence[str],
    k: int = 5,
) -> float:
    """
    Calculate Precision@K for a single query.

    Args:
        retrieved_ids: Ordered list of retrieved document/chunk IDs.
        relevant_ids: Set of ground-truth relevant IDs.
        k: Cutoff rank (must be >= 1).
    """
    if k < 1:
        raise ValueError(f"k must be a positive integer, got {k}")

    target_relevant = (
        set(relevant_ids) if not isinstance(relevant_ids, set) else relevant_ids
    )
    deduped = deduplicate_rankings(retrieved_ids)
    top_k = deduped[:k]

    # Edge cases when no ground-truth relevant documents exist
    if not target_relevant:
        return 1.0 if len(top_k) == 0 else 0.0

    if not top_k:
        return 0.0

    hits = sum(1 for item in top_k if item in target_relevant)
    return float(hits / len(top_k))


def calculate_recall_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str] | Sequence[str],
    k: int = 5,
) -> float:
    """
    Calculate Recall@K for a single query.

    Args:
        retrieved_ids: Ordered list of retrieved document/chunk IDs.
        relevant_ids: Set of ground-truth relevant IDs.
        k: Cutoff rank (must be >= 1).
    """
    if k < 1:
        raise ValueError(f"k must be a positive integer, got {k}")

    target_relevant = (
        set(relevant_ids) if not isinstance(relevant_ids, set) else relevant_ids
    )
    deduped = deduplicate_rankings(retrieved_ids)
    top_k = set(deduped[:k])

    if not target_relevant:
        return 1.0 if len(top_k) == 0 else 0.0

    hits = len(top_k & target_relevant)
    return float(hits / len(target_relevant))


def calculate_reciprocal_rank(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str] | Sequence[str],
    k: int | None = None,
) -> float:
    """
    Calculate Reciprocal Rank (RR) for a single query.

    Args:
        retrieved_ids: Ordered list of retrieved document/chunk IDs.
        relevant_ids: Set of ground-truth relevant IDs.
        k: Optional cutoff rank. If provided, items beyond rank k are ignored.
    """
    if k is not None and k < 1:
        raise ValueError(f"k must be a positive integer, got {k}")

    target_relevant = (
        set(relevant_ids) if not isinstance(relevant_ids, set) else relevant_ids
    )
    deduped = deduplicate_rankings(retrieved_ids)
    candidates = deduped[:k] if k is not None else deduped

    if not target_relevant:
        return 1.0 if len(candidates) == 0 else 0.0

    for rank, item in enumerate(candidates, start=1):
        if item in target_relevant:
            return float(1.0 / rank)

    return 0.0


def calculate_hit_rate_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str] | Sequence[str],
    k: int = 5,
) -> float:
    """
    Calculate Hit Rate@K for a single query.

    Returns 1.0 if at least one relevant document is retrieved within top-K, 0.0 otherwise.
    """
    if k < 1:
        raise ValueError(f"k must be a positive integer, got {k}")

    target_relevant = (
        set(relevant_ids) if not isinstance(relevant_ids, set) else relevant_ids
    )
    deduped = deduplicate_rankings(retrieved_ids)
    top_k = set(deduped[:k])

    if not target_relevant:
        return 1.0 if len(top_k) == 0 else 0.0

    return 1.0 if len(top_k & target_relevant) > 0 else 0.0


def calculate_mean_reciprocal_rank(
    query_rankings: Sequence[tuple[Sequence[str], set[str] | Sequence[str]]],
    k: int | None = None,
) -> float:
    """
    Calculate Mean Reciprocal Rank (MRR) across multiple queries.

    Args:
        query_rankings: List of (retrieved_ids, relevant_ids) tuples.
        k: Optional cutoff rank.
    """
    if not query_rankings:
        return 0.0

    total_rr = sum(
        calculate_reciprocal_rank(retrieved, relevant, k=k)
        for retrieved, relevant in query_rankings
    )
    return float(total_rr / len(query_rankings))


def calculate_retrieval_metrics_at_ks(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str] | Sequence[str],
    k_values: Sequence[int] = (1, 3, 5, 10),
) -> dict[str, float]:
    """
    Calculate retrieval metrics across multiple K cutoffs for a single query ranking.

    Supports arbitrary positive cutoff values, defaulting to standard K in {1, 3, 5, 10}.
    For each cutoff K, calculates:
      - precision@K
      - recall@K
      - hit_rate@K
      - mrr@K (reciprocal rank capped at K)

    Also includes the unbounded 'mrr' (reciprocal rank across the full ranked list).

    Args:
        retrieved_ids: Ordered list of retrieved document/chunk IDs.
        relevant_ids: Set or sequence of ground-truth relevant IDs.
        k_values: Sequence of integer cutoffs (default: 1, 3, 5, 10).
    """
    if not k_values:
        return {"mrr": calculate_reciprocal_rank(retrieved_ids, relevant_ids)}

    metrics: dict[str, float] = {}
    for k in k_values:
        if k < 1:
            raise ValueError(f"k must be a positive integer, got {k}")
        metrics[f"precision@{k}"] = calculate_precision_at_k(
            retrieved_ids, relevant_ids, k=k
        )
        metrics[f"recall@{k}"] = calculate_recall_at_k(retrieved_ids, relevant_ids, k=k)
        metrics[f"hit_rate@{k}"] = calculate_hit_rate_at_k(
            retrieved_ids, relevant_ids, k=k
        )
        metrics[f"mrr@{k}"] = calculate_reciprocal_rank(
            retrieved_ids, relevant_ids, k=k
        )

    metrics["mrr"] = calculate_reciprocal_rank(retrieved_ids, relevant_ids)
    return metrics


def calculate_aggregate_retrieval_metrics(
    eval_cases: Sequence[dict[str, Any]],
    k_values: Sequence[int] = (1, 3, 5, 10),
) -> dict[str, float]:
    """
    Compute aggregate retrieval metrics across a set of evaluated cases.

    Expected dict structure for each case:
      - "retrieved_ids": list[str]
      - "relevant_ids": list[str] | set[str]

    Default evaluation cutoffs: K in {1, 3, 5, 10}.
    """
    if not eval_cases:
        return {}

    num_cases = len(eval_cases)
    aggregates: dict[str, float] = {}

    for k in k_values:
        total_prec = sum(
            calculate_precision_at_k(c["retrieved_ids"], c["relevant_ids"], k=k)
            for c in eval_cases
        )
        total_recall = sum(
            calculate_recall_at_k(c["retrieved_ids"], c["relevant_ids"], k=k)
            for c in eval_cases
        )
        total_hit = sum(
            calculate_hit_rate_at_k(c["retrieved_ids"], c["relevant_ids"], k=k)
            for c in eval_cases
        )
        total_rr = sum(
            calculate_reciprocal_rank(c["retrieved_ids"], c["relevant_ids"], k=k)
            for c in eval_cases
        )

        aggregates[f"precision@{k}"] = round(total_prec / num_cases, 4)
        aggregates[f"recall@{k}"] = round(total_recall / num_cases, 4)
        aggregates[f"hit_rate@{k}"] = round(total_hit / num_cases, 4)
        aggregates[f"mrr@{k}"] = round(total_rr / num_cases, 4)

    # Unbounded MRR across full retrieval depth
    total_mrr = sum(
        calculate_reciprocal_rank(c["retrieved_ids"], c["relevant_ids"])
        for c in eval_cases
    )
    aggregates["mrr"] = round(total_mrr / num_cases, 4)

    return aggregates
