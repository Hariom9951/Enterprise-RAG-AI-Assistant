"""
Enterprise RAG AI Assistant — Evaluation Suite Tests (Phase 3.3)
================================================================
Comprehensive tests for:
1. Retrieval metrics (Recall@K, MRR, Precision@K, Hit Rate@K, deduplication, edge cases).
2. Answer & citation evaluation (validity, source grounding, target recall/precision).
3. Abstention and rejection correctness.
4. Response structure and outcome consistency.
5. Versioned evaluation dataset integrity.
6. Runner comparison and deterministic offline report generation.
7. Privacy and zero-leakage guarantees on generated evaluation reports.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent_service import AgentRunResult
from app.evaluation.answer_evaluator import (
    GroundingEvaluationResult,
    evaluate_abstention,
    evaluate_citations,
    evaluate_evidence_grounding,
    evaluate_response_structure,
)
from app.evaluation.dataset import (
    CaseCategory,
    get_default_evaluation_dataset,
)
from app.evaluation.retrieval_metrics import (
    calculate_aggregate_retrieval_metrics,
    calculate_hit_rate_at_k,
    calculate_mean_reciprocal_rank,
    calculate_precision_at_k,
    calculate_recall_at_k,
    calculate_reciprocal_rank,
    calculate_retrieval_metrics_at_ks,
    deduplicate_rankings,
)
from app.evaluation.runner import run_evaluation_suite
from app.evaluation.runner_comparison import compare_case_execution

# =============================================================================
# 1. Retrieval Metrics Tests
# =============================================================================


class TestRetrievalMetrics:
    def test_precision_at_k(self) -> None:
        retrieved = ["doc1", "doc2", "doc3", "doc4", "doc5"]
        relevant = {"doc1", "doc3", "doc7"}

        # At k=1: 1 hit out of 1
        assert calculate_precision_at_k(retrieved, relevant, k=1) == 1.0
        # At k=2: 1 hit out of 2 (doc1)
        assert calculate_precision_at_k(retrieved, relevant, k=2) == 0.5
        # At k=3: 2 hits out of 3 (doc1, doc3)
        assert round(calculate_precision_at_k(retrieved, relevant, k=3), 4) == round(
            2 / 3, 4
        )
        # At k=5: 2 hits out of 5
        assert calculate_precision_at_k(retrieved, relevant, k=5) == 0.4

    def test_recall_at_k(self) -> None:
        retrieved = ["doc1", "doc2", "doc3", "doc4", "doc5"]
        relevant = {"doc1", "doc3", "doc7"}  # 3 total relevant items

        # At k=1: 1 of 3 found -> 1/3
        assert round(calculate_recall_at_k(retrieved, relevant, k=1), 4) == round(
            1 / 3, 4
        )
        # At k=3: 2 of 3 found -> 2/3
        assert round(calculate_recall_at_k(retrieved, relevant, k=3), 4) == round(
            2 / 3, 4
        )
        # If all relevant are in top-k
        relevant_subset = {"doc1", "doc2"}
        assert calculate_recall_at_k(retrieved, relevant_subset, k=2) == 1.0

    def test_reciprocal_rank(self) -> None:
        # First relevant at rank 1 -> 1.0
        assert calculate_reciprocal_rank(["doc1", "doc2"], {"doc1"}) == 1.0
        # First relevant at rank 2 -> 0.5
        assert calculate_reciprocal_rank(["doc1", "doc2"], {"doc2"}) == 0.5
        # First relevant at rank 3 -> 1/3
        assert round(
            calculate_reciprocal_rank(["doc1", "doc2", "doc3"], {"doc3"}), 4
        ) == round(1 / 3, 4)
        # No relevant item -> 0.0
        assert calculate_reciprocal_rank(["doc1", "doc2"], {"doc9"}) == 0.0
        # With k cutoff: relevant item at rank 3 is ignored if k=2
        assert calculate_reciprocal_rank(["doc1", "doc2", "doc3"], {"doc3"}, k=2) == 0.0

    def test_hit_rate_at_k(self) -> None:
        retrieved = ["doc1", "doc2", "doc3"]
        assert calculate_hit_rate_at_k(retrieved, {"doc1"}, k=1) == 1.0
        assert calculate_hit_rate_at_k(retrieved, {"doc2"}, k=1) == 0.0
        assert calculate_hit_rate_at_k(retrieved, {"doc2"}, k=2) == 1.0
        assert calculate_hit_rate_at_k(retrieved, {"doc9"}, k=3) == 0.0

    def test_deduplicate_rankings(self) -> None:
        raw = ["doc1", "doc2", "doc1", "doc3", "doc2", "doc4"]
        deduped = deduplicate_rankings(raw)
        assert deduped == ["doc1", "doc2", "doc3", "doc4"]

    def test_empty_retrieved_and_relevant_edge_cases(self) -> None:
        # Both empty: correctly retrieved nothing when nothing is relevant
        assert calculate_precision_at_k([], set(), k=3) == 1.0
        assert calculate_recall_at_k([], set(), k=3) == 1.0
        assert calculate_reciprocal_rank([], set(), k=3) == 1.0
        assert calculate_hit_rate_at_k([], set(), k=3) == 1.0

        # Retrieved items when relevant is empty: all false positives
        assert calculate_precision_at_k(["doc1"], set(), k=3) == 0.0
        assert calculate_recall_at_k(["doc1"], set(), k=3) == 0.0
        assert calculate_reciprocal_rank(["doc1"], set(), k=3) == 0.0
        assert calculate_hit_rate_at_k(["doc1"], set(), k=3) == 0.0

        # Empty retrieved when relevant is non-empty: missed everything
        assert calculate_precision_at_k([], {"doc1"}, k=3) == 0.0
        assert calculate_recall_at_k([], {"doc1"}, k=3) == 0.0
        assert calculate_reciprocal_rank([], {"doc1"}, k=3) == 0.0
        assert calculate_hit_rate_at_k([], {"doc1"}, k=3) == 0.0

    def test_invalid_k_raises_error(self) -> None:
        with pytest.raises(ValueError, match="k must be a positive integer"):
            calculate_precision_at_k(["doc1"], {"doc1"}, k=0)
        with pytest.raises(ValueError, match="k must be a positive integer"):
            calculate_recall_at_k(["doc1"], {"doc1"}, k=-1)
        with pytest.raises(ValueError, match="k must be a positive integer"):
            calculate_reciprocal_rank(["doc1"], {"doc1"}, k=0)
        with pytest.raises(ValueError, match="k must be a positive integer"):
            calculate_hit_rate_at_k(["doc1"], {"doc1"}, k=-5)

    def test_mean_reciprocal_rank(self) -> None:
        cases = [
            (["doc1", "doc2"], {"doc1"}),  # RR = 1.0
            (["doc1", "doc2"], {"doc2"}),  # RR = 0.5
            (["doc1", "doc2"], {"doc9"}),  # RR = 0.0
        ]
        # MRR = (1.0 + 0.5 + 0.0) / 3 = 0.5
        assert calculate_mean_reciprocal_rank(cases) == 0.5
        assert calculate_mean_reciprocal_rank([]) == 0.0

    def test_aggregate_retrieval_metrics(self) -> None:
        cases = [
            {"retrieved_ids": ["d1", "d2"], "relevant_ids": {"d1"}},
            {"retrieved_ids": ["d1", "d2"], "relevant_ids": {"d2"}},
        ]
        agg = calculate_aggregate_retrieval_metrics(cases, k_values=[1, 3])
        assert "precision@1" in agg
        assert "recall@1" in agg
        assert "hit_rate@1" in agg
        assert "mrr@1" in agg
        assert "mrr" in agg
        assert agg["mrr"] == 0.75  # (1.0 + 0.5) / 2

    def test_k_larger_than_ranking(self) -> None:
        """When K exceeds the number of retrieved items, precision and recall calculate safely."""
        retrieved = ["doc1", "doc2"]
        relevant = {"doc1", "doc3"}
        for k in (3, 5, 10, 50):
            # top_k has 2 items, 1 hit -> precision = 1/2 = 0.5
            assert calculate_precision_at_k(retrieved, relevant, k=k) == 0.5
            # 1 of 2 relevant retrieved -> recall = 0.5
            assert calculate_recall_at_k(retrieved, relevant, k=k) == 0.5
            assert calculate_hit_rate_at_k(retrieved, relevant, k=k) == 1.0
            assert calculate_reciprocal_rank(retrieved, relevant, k=k) == 1.0

    def test_duplicate_retrieval_ranking_deduplication(self) -> None:
        """Duplicate document IDs in retrieved list are deduplicated while preserving first-seen rank."""
        raw = ["doc1", "doc1", "doc2", "doc2", "doc1", "doc3"]
        relevant = {"doc1", "doc2"}
        # Deduped ranking is ["doc1", "doc2", "doc3"]
        assert calculate_precision_at_k(raw, relevant, k=1) == 1.0
        assert calculate_recall_at_k(raw, relevant, k=1) == 0.5
        assert calculate_precision_at_k(raw, relevant, k=2) == 1.0
        assert calculate_recall_at_k(raw, relevant, k=2) == 1.0
        # At k=5: 2 hits out of 3 unique retrieved
        assert round(calculate_precision_at_k(raw, relevant, k=5), 4) == round(2 / 3, 4)
        assert calculate_recall_at_k(raw, relevant, k=5) == 1.0

    def test_no_relevant_documents_at_multi_k(self) -> None:
        """Handling queries where no ground truth relevant documents exist."""
        retrieved = ["doc1", "doc2", "doc3"]
        for k in (1, 3, 5, 10):
            # When ground truth is empty, any retrieved document is a false positive
            assert calculate_precision_at_k(retrieved, set(), k=k) == 0.0
            assert calculate_recall_at_k(retrieved, set(), k=k) == 0.0
            assert calculate_hit_rate_at_k(retrieved, set(), k=k) == 0.0
            assert calculate_reciprocal_rank(retrieved, set(), k=k) == 0.0
            # When relevant documents exist elsewhere but not in retrieved
            assert calculate_precision_at_k(retrieved, {"unrelated"}, k=k) == 0.0
            assert calculate_recall_at_k(retrieved, {"unrelated"}, k=k) == 0.0
            assert calculate_hit_rate_at_k(retrieved, {"unrelated"}, k=k) == 0.0
            assert calculate_reciprocal_rank(retrieved, {"unrelated"}, k=k) == 0.0

    def test_calculate_retrieval_metrics_at_ks_single_query(self) -> None:
        """Single-query multi-K retrieval metrics calculation across standard K in {1, 3, 5, 10}."""
        retrieved = ["doc1", "doc2", "doc3", "doc4", "doc5"]
        relevant = {"doc1", "doc3", "doc5", "doc7"}
        metrics = calculate_retrieval_metrics_at_ks(retrieved, relevant)

        for k in (1, 3, 5, 10):
            assert f"precision@{k}" in metrics
            assert f"recall@{k}" in metrics
            assert f"hit_rate@{k}" in metrics
            assert f"mrr@{k}" in metrics
        assert "mrr" in metrics

        assert metrics["precision@1"] == 1.0
        assert metrics["recall@1"] == 0.25  # 1 of 4
        assert round(metrics["precision@3"], 4) == round(2 / 3, 4)
        assert metrics["recall@3"] == 0.5  # 2 of 4
        assert metrics["precision@5"] == 0.6  # 3 of 5
        assert metrics["recall@5"] == 0.75  # 3 of 4
        assert metrics["precision@10"] == 0.6  # 3 hits out of 5 unique retrieved items
        assert metrics["recall@10"] == 0.75

        # Custom cutoffs
        custom = calculate_retrieval_metrics_at_ks(retrieved, relevant, k_values=[2, 4])
        assert "precision@2" in custom
        assert "precision@4" in custom
        assert "precision@1" not in custom

        # Invalid cutoff raises ValueError
        with pytest.raises(ValueError, match="k must be a positive integer"):
            calculate_retrieval_metrics_at_ks(retrieved, relevant, k_values=[0])

    def test_aggregate_retrieval_metrics_default_multi_k(self) -> None:
        """Default aggregate metrics computation supports K in {1, 3, 5, 10}."""
        cases = [
            {"retrieved_ids": ["d1", "d2", "d3"], "relevant_ids": {"d1"}},
            {"retrieved_ids": ["d1", "d2", "d3"], "relevant_ids": {"d3"}},
        ]
        agg = calculate_aggregate_retrieval_metrics(cases)
        for k in (1, 3, 5, 10):
            assert f"precision@{k}" in agg
            assert f"recall@{k}" in agg
            assert f"hit_rate@{k}" in agg
            assert f"mrr@{k}" in agg
        assert "mrr" in agg


# =============================================================================
# 2. Answer & Citation Evaluation Tests
# =============================================================================


class TestAnswerAndCitationEvaluation:
    def test_citation_evaluation_valid_references(self) -> None:
        answer = (
            "The SLA resolution time is 4 hours [1], according to company policies [2]."
        )
        retrieved_docs = [
            {"chunk_id": "chunk-1", "document_title": "SLA Policy"},
            {"chunk_id": "chunk-2", "document_title": "Company Policy"},
        ]
        expected_targets = ["chunk-1", "chunk-2"]

        res = evaluate_citations(answer, retrieved_docs, expected_targets)
        assert res.citation_present is True
        assert res.all_indices_valid is True
        assert res.cited_indices == [1, 2]
        assert res.cited_chunk_ids == ["chunk-1", "chunk-2"]
        assert res.source_grounding_rate == 1.0
        assert res.target_citation_recall == 1.0
        assert res.target_citation_precision == 1.0

    def test_citation_evaluation_invalid_hallucinated_index(self) -> None:
        answer = "The policy states that retention is 90 days [1] and [99]."
        retrieved_docs = [{"chunk_id": "chunk-1"}]  # Only 1 document retrieved

        res = evaluate_citations(answer, retrieved_docs, expected_targets=["chunk-1"])
        assert res.citation_present is True
        assert res.all_indices_valid is False
        assert 99 in res.invalid_indices
        assert res.cited_chunk_ids == ["chunk-1"]
        # Grounding rate: 1 valid out of 2 parsed citations = 0.5
        assert res.source_grounding_rate == 0.5

    def test_citation_evaluation_no_citations(self) -> None:
        answer = "General statement without any citations."
        res = evaluate_citations(answer, [{"chunk_id": "chunk-1"}])
        assert res.citation_present is False
        assert res.all_indices_valid is True
        assert res.cited_chunk_ids == []
        assert res.source_grounding_rate == 1.0

    def test_abstention_evaluation_detected(self) -> None:
        answer = "I cannot find sufficient evidence in the enterprise knowledge base."
        res = evaluate_abstention(answer, expected_abstention=True)
        assert res.abstention_detected is True
        assert res.expected_abstention is True
        assert res.abstention_decision_correct is True
        assert res.detected_phrase is not None

    def test_abstention_evaluation_false_rejection(self) -> None:
        # Falsely abstaining when not expected
        answer = "There is no information available to answer this inquiry."
        res = evaluate_abstention(answer, expected_abstention=False)
        assert res.abstention_detected is True
        assert res.expected_abstention is False
        assert res.abstention_decision_correct is False

    def test_abstention_evaluation_proper_answer(self) -> None:
        answer = "The standard retention period is 90 days [1]."
        res = evaluate_abstention(answer, expected_abstention=False)
        assert res.abstention_detected is False
        assert res.expected_abstention is False
        assert res.abstention_decision_correct is True

    def test_response_structure_evaluation(self) -> None:
        valid_result = AgentRunResult(
            run_id=uuid.uuid4(),
            question="What is the policy?",
            final_answer="The policy is X [1].",
            tool_call_records=[],
            total_latency_ms=120,
            prompt_tokens=10,
            completion_tokens=20,
            provider="mock",
            model_name="mock-model",
            success=True,
        )
        res = evaluate_response_structure(valid_result)
        assert res.valid_run_id is True
        assert res.valid_latency is True
        assert res.valid_final_answer is True
        assert res.outcome_consistent is True
        assert len(res.errors) == 0

    def test_response_structure_detects_inconsistencies(self) -> None:
        # Inconsistent result: success=False but error_message is empty
        bad_result = AgentRunResult(
            run_id="invalid-uuid",
            question="What is the policy?",
            final_answer="",
            tool_call_records=[],
            total_latency_ms=-10,
            prompt_tokens=0,
            completion_tokens=0,
            provider="mock",
            model_name="mock-model",
            success=False,
            error_message="",
        )
        res = evaluate_response_structure(bad_result)
        assert res.valid_run_id is False
        assert res.valid_latency is False
        assert res.valid_final_answer is False
        assert res.outcome_consistent is False
        assert len(res.errors) >= 3

    def test_citation_mapping_boundary_and_duplicate_indices(self) -> None:
        """Citation extraction correctly handles duplicate brackets and out-of-bounds boundary indices."""
        answer = "First statement [1], second statement [1], third [2], invalid [0], out-of-bounds [5]."
        retrieved_docs = [{"chunk_id": "c1"}, {"chunk_id": "c2"}]
        res = evaluate_citations(answer, retrieved_docs, expected_targets=["c1", "c2"])
        assert res.citation_present is True
        assert res.all_indices_valid is False
        assert res.cited_indices == [0, 1, 2, 5]
        assert set(res.invalid_indices) == {0, 5}
        assert res.cited_chunk_ids == ["c1", "c2"]
        # 2 valid unique indices out of 4 parsed unique indices = 0.5
        assert res.source_grounding_rate == 0.5
        assert res.target_citation_recall == 1.0
        assert res.target_citation_precision == 1.0

    def test_evidence_grounding_exact_match(self) -> None:
        """Evidence grounding heuristic yields high overlap when answer closely tracks source text."""
        chunk_text = (
            "Enterprise laptops must enable Full Disk Encryption using AES-256 and lock "
            "automatically after 5 minutes of inactivity."
        )
        answer = (
            "Enterprise laptops must enable full disk encryption using AES-256 and lock "
            "automatically after 5 minutes of inactivity [1]."
        )
        res = evaluate_evidence_grounding(answer, cited_chunks=[{"text": chunk_text}])
        assert res.grounding_score == 1.0
        assert res.sentence_grounding_rate == 1.0
        assert res.grounded_sentences_count == 1
        assert res.total_sentences_count == 1
        assert len(res.unsupported_sentences) == 0

        # Lexical divergence test: paraphrase with synonyms lowers lexical score
        paraphrase = (
            "Corporate laptops require full disk encryption with AES-256 and automatic lock "
            "after 5 minutes [1]."
        )
        res_para = evaluate_evidence_grounding(
            paraphrase, cited_chunks=[{"text": chunk_text}]
        )
        assert 0.60 <= res_para.grounding_score <= 0.85
        assert res_para.sentence_grounding_rate == 1.0

    def test_evidence_grounding_completely_ungrounded(self) -> None:
        """Evidence grounding heuristic identifies completely fabricated / ungrounded answers."""
        chunk_text = (
            "The cafeteria serves fresh fruit and coffee from Monday through Friday."
        )
        answer = (
            "Quantum cryptography utilizes entangled photon pairs to negotiate keys."
        )
        res = evaluate_evidence_grounding(answer, cited_chunks=[chunk_text])
        assert res.grounding_score == 0.0
        assert res.sentence_grounding_rate == 0.0
        assert res.grounded_sentences_count == 0
        assert res.total_sentences_count == 1
        assert len(res.unsupported_sentences) == 1

    def test_evidence_grounding_partial_sentences(self) -> None:
        """Evidence grounding heuristic accurately flags unsupported sentences in mixed answers."""
        evidence = [
            {"text": "Data retention window is ninety days for all audit trails."},
        ]
        answer = (
            "Audit trails are retained for ninety days [1]. "
            "Employees are also awarded monthly space exploration bonuses."
        )
        res = evaluate_evidence_grounding(answer, cited_chunks=evidence)
        assert 0.0 < res.grounding_score < 1.0
        assert res.total_sentences_count == 2
        assert res.grounded_sentences_count == 1
        assert res.sentence_grounding_rate == 0.5
        assert len(res.supported_sentences) == 1
        assert len(res.unsupported_sentences) == 1
        assert "bonuses" in res.unsupported_sentences[0]

    def test_evidence_grounding_empty_edge_cases(self) -> None:
        """Boundary handling for empty answer, empty evidence, and combined empty inputs."""
        # 1. Both empty
        res_both_empty = evaluate_evidence_grounding("", [])
        assert res_both_empty.grounding_score == 1.0
        assert res_both_empty.sentence_grounding_rate == 1.0
        assert res_both_empty.total_sentences_count == 0

        # 2. Empty answer with evidence
        res_empty_ans = evaluate_evidence_grounding("", ["Some evidence text"])
        assert res_empty_ans.grounding_score == 0.0
        assert res_empty_ans.total_sentences_count == 0

        # 3. Non-empty answer with empty evidence
        res_empty_ev = evaluate_evidence_grounding("Answer with claims.", [])
        assert res_empty_ev.grounding_score == 0.0
        assert res_empty_ev.sentence_grounding_rate == 0.0
        assert len(res_empty_ev.unsupported_sentences) == 1

    def test_evidence_grounding_heuristic_disclaimer(self) -> None:
        """Grounding heuristic result and documentation strictly disclaim proof of factual correctness."""
        doc = evaluate_evidence_grounding.__doc__ or ""
        assert "DOES NOT" in doc
        assert "factual correctness" in doc.lower()
        res = evaluate_evidence_grounding("Valid answer [1].", ["Valid answer."])
        assert isinstance(res, GroundingEvaluationResult)
        assert hasattr(res, "grounding_score")
        assert hasattr(res, "sentence_grounding_rate")


# =============================================================================
# 3. Dataset Integrity & Filtering Tests
# =============================================================================


class TestEvaluationDataset:
    def test_default_dataset_version_and_categories(self) -> None:
        dataset = get_default_evaluation_dataset()
        assert dataset.version == "v1.0.0"
        assert len(dataset.cases) >= 8

        categories = {c.category for c in dataset.cases}
        assert CaseCategory.EASY in categories
        assert CaseCategory.KEYWORD_HEAVY in categories
        assert CaseCategory.SEMANTIC_MATCH in categories
        assert CaseCategory.AMBIGUOUS in categories
        assert CaseCategory.INSUFFICIENT_EVIDENCE in categories
        assert CaseCategory.CITATION_ORIENTED in categories

    def test_filter_by_category(self) -> None:
        dataset = get_default_evaluation_dataset()
        easy_cases = dataset.filter_by_category(CaseCategory.EASY)
        assert len(easy_cases) >= 1
        assert all(c.category == CaseCategory.EASY for c in easy_cases)

    def test_get_case_by_id(self) -> None:
        dataset = get_default_evaluation_dataset()
        case = dataset.get_case("case-001-easy-semantic")
        assert case is not None
        assert case.case_id == "case-001-easy-semantic"
        assert dataset.get_case("non-existent-case-id") is None

    def test_dataset_serialization(self) -> None:
        dataset = get_default_evaluation_dataset()
        data = dataset.to_dict()
        assert data["version"] == "v1.0.0"
        assert data["case_count"] == len(dataset.cases)
        assert isinstance(data["cases"], list)
        assert len(data["cases"]) > 0

    def test_dataset_multi_k_cases(self) -> None:
        """Extended dataset includes multi-K ground truth cases evaluating depth-dependent retrieval."""
        dataset = get_default_evaluation_dataset()
        case_009 = dataset.get_case("case-009-multi-k-incident-escalation")
        case_010 = dataset.get_case("case-010-multi-k-retention-matrix")

        assert case_009 is not None
        assert len(case_009.expected_relevant_chunk_ids) == 5
        assert case_010 is not None
        assert len(case_010.expected_relevant_chunk_ids) == 4

        # Verify retrieval metric variations across K cutoffs on case 009
        retrieved_ids = [f.chunk_id for f in case_009.reference_fixtures]
        metrics = calculate_retrieval_metrics_at_ks(
            retrieved_ids,
            case_009.expected_relevant_chunk_ids,
            k_values=[1, 3, 5, 10],
        )
        assert metrics["recall@1"] == 0.20  # 1 / 5
        assert metrics["recall@3"] == 0.60  # 3 / 5
        assert metrics["recall@5"] == 1.00  # 5 / 5
        assert metrics["hit_rate@1"] == 1.0
        assert metrics["hit_rate@5"] == 1.0


# =============================================================================
# 4. Runner Comparison & Evaluation Suite Tests
# =============================================================================


class TestRunnerComparisonAndEvaluation:
    @pytest.mark.asyncio
    async def test_single_case_execution_legacy_and_langgraph(
        self, db_session: AsyncSession
    ) -> None:
        """Execute a single test case on both legacy and langgraph and compare results."""
        dataset = get_default_evaluation_dataset()
        case = dataset.get_case("case-001-easy-semantic")
        assert case is not None

        comp = await compare_case_execution(case, db=db_session)
        assert comp.case_id == "case-001-easy-semantic"
        assert comp.legacy.success is True
        assert comp.langgraph.success is True
        assert comp.legacy.precision_at_3 == 0.5
        assert comp.langgraph.precision_at_3 == 0.5
        assert comp.legacy.citations_present is True
        assert comp.langgraph.citations_present is True

    @pytest.mark.asyncio
    async def test_full_evaluation_suite_report(self, db_session: AsyncSession) -> None:
        """Run full evaluation suite and verify schema, aggregate metrics, and zero leakage."""
        dataset = get_default_evaluation_dataset()
        report = await run_evaluation_suite(dataset=dataset, db=db_session)

        # 1. Structure check
        assert report["dataset_version"] == "v1.0.0"
        assert "evaluation_timestamp" in report
        assert "metric_definitions" in report
        assert "aggregate_metrics" in report
        assert "comparison_summary" in report
        assert "per_case_results" in report
        assert "failed_cases" in report

        # 2. Aggregates check
        legacy_agg = report["aggregate_metrics"]["legacy"]
        langgraph_agg = report["aggregate_metrics"]["langgraph"]
        assert "precision@3" in legacy_agg
        assert "recall@3" in legacy_agg
        assert "hit_rate@3" in legacy_agg
        assert "mrr" in legacy_agg
        assert "citation_validity_rate" in legacy_agg
        assert "abstention_accuracy" in legacy_agg
        assert "success_rate" in legacy_agg

        assert legacy_agg["success_rate"] == 1.0
        assert langgraph_agg["success_rate"] == 1.0

        # 3. Privacy & Zero-leakage check on serialized report
        serialized = json.dumps(report)
        assert "secret_key" not in serialized.lower()
        assert "api_key" not in serialized.lower()
        assert "authorization" not in serialized.lower()
        assert "eyjhbgcioi" not in serialized.lower()  # No JWT headers
        # Password token only present in known synthetic prompt queries
        queries = [c["query"] for c in report["per_case_results"]]
        assert any("password" in q.lower() for q in queries)
