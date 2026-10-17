"""
Enterprise RAG AI Assistant — Runner Comparison Suite
======================================================
Executes identical evaluation cases through both the Legacy agent runner and the
LangGraph workflow builder using deterministic fixtures and controlled mock LLM responses.
Compares retrieval accuracy, tool calling, citation validity, and run stability.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent_service import AgentRunResult, AgentService
from app.agents.base_tool import ToolResult
from app.agents.registry import ToolRegistry
from app.agents.tools.semantic_search import SemanticSearchTool
from app.evaluation.answer_evaluator import (
    evaluate_abstention,
    evaluate_citations,
    evaluate_response_structure,
)
from app.evaluation.dataset import EvaluationCase
from app.evaluation.retrieval_metrics import (
    calculate_hit_rate_at_k,
    calculate_precision_at_k,
    calculate_recall_at_k,
    calculate_reciprocal_rank,
)


@dataclass
class CaseExecutionMetrics:
    """Metrics captured for a single runner executing a single evaluation case."""

    runner: str
    case_id: str
    success: bool
    final_answer: str
    retrieved_chunk_ids: list[str]
    precision_at_3: float
    recall_at_3: float
    hit_rate_at_3: float
    reciprocal_rank: float
    citations_present: bool
    citation_validity_rate: float
    target_citation_recall: float | None
    abstention_correct: bool
    latency_ms: int
    tool_calls_count: int
    tools_invoked: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComparisonReport:
    """Side-by-side comparison between legacy and LangGraph runners for an evaluation case."""

    case_id: str
    query: str
    category: str
    legacy: CaseExecutionMetrics
    langgraph: CaseExecutionMetrics
    match_status: bool
    divergences: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "query": self.query,
            "category": self.category,
            "legacy": self.legacy.to_dict(),
            "langgraph": self.langgraph.to_dict(),
            "match_status": self.match_status,
            "divergences": self.divergences,
        }


def _create_mock_tool_output(case: EvaluationCase) -> list[dict[str, Any]]:
    """Convert case reference fixtures into SemanticSearchTool output format."""
    return [
        {
            "chunk_id": f.chunk_id,
            "document_id": f.document_id,
            "document_name": f.document_title,
            "page_number": f.page_number,
            "section_title": f.section_title or "",
            "text": f.text,
            "score": f.score,
        }
        for f in case.reference_fixtures
    ]


def _build_mock_llm(case: EvaluationCase) -> AsyncMock:
    """Construct a deterministic mock LLM responding appropriately for the given evaluation case."""
    mock = AsyncMock()

    # Step 1: Intent classification response
    if case.expected_abstention and "[SYSTEM]" in case.query:
        # Prompt injection case: AgentService blocks it before calling LLM
        plan_json = json.dumps([{"tool_id": "direct_answer", "parameters": {}}])
    elif not case.reference_fixtures:
        plan_json = json.dumps([{"tool_id": "direct_answer", "parameters": {}}])
    else:
        plan_json = json.dumps(
            [
                {
                    "tool_id": "semantic_search",
                    "parameters": {"query": case.query, "top_k": 3},
                }
            ]
        )

    # Step 2: Final answer response
    if case.expected_abstention:
        answer_text = "I cannot find sufficient evidence in the enterprise knowledge base to answer this question."
    elif case.expected_citation_targets:
        # Create an answer with standard bracket citations [1], [2], etc.
        citations_str = " ".join(
            f"[{i+1}]" for i in range(len(case.expected_citation_targets))
        )
        answer_text = f"Based on enterprise policy, the answer is detailed in the documentation {citations_str}."
    else:
        answer_text = "The enterprise policy resolves this inquiry as specified."

    mock.generate_response.side_effect = [
        (plan_json, {"prompt_tokens": 40, "completion_tokens": 20}),
        (answer_text, {"prompt_tokens": 100, "completion_tokens": 30}),
        # Additional responses if LangGraph evaluation/reformulation loop queries again
        (answer_text, {"prompt_tokens": 100, "completion_tokens": 30}),
    ]
    return mock


async def execute_case_on_runner(
    case: EvaluationCase,
    runner: str,
    db: AsyncSession,
) -> CaseExecutionMetrics:
    """Execute a single evaluation case on the specified runner ('legacy' or 'langgraph')."""
    use_langgraph = runner == "langgraph"
    tool_output = _create_mock_tool_output(case)
    mock_llm = _build_mock_llm(case)
    user_id = uuid.uuid4()

    # Create an isolated SemanticSearchTool returning the fixture chunks
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

    with (
        patch("app.config.settings.settings.enable_langgraph", use_langgraph),
        patch("app.agents.agent_service.get_llm_provider", return_value=mock_llm),
        patch.object(service, "_persist_run", new_callable=AsyncMock),
        patch(
            "app.services.cache_service.cache_service.record_latency",
            new_callable=AsyncMock,
        ),
    ):
        result: AgentRunResult = await service.run(
            db=db,
            question=case.query,
            user_id=user_id,
        )

    # 1. Structure validation
    struct_eval = evaluate_response_structure(result)

    # 2. Extract retrieved IDs
    retrieved_docs = result.retrieved_documents or []
    retrieved_chunk_ids: list[str] = [
        d["chunk_id"] for d in retrieved_docs if d.get("chunk_id")
    ]

    # 3. Compute IR metrics
    prec = calculate_precision_at_k(
        retrieved_chunk_ids, case.expected_relevant_chunk_ids, k=3
    )
    rec = calculate_recall_at_k(
        retrieved_chunk_ids, case.expected_relevant_chunk_ids, k=3
    )
    hit = calculate_hit_rate_at_k(
        retrieved_chunk_ids, case.expected_relevant_chunk_ids, k=3
    )
    rr = calculate_reciprocal_rank(
        retrieved_chunk_ids, case.expected_relevant_chunk_ids, k=3
    )

    # 4. Evaluate citations
    cite_eval = evaluate_citations(
        result.final_answer,
        retrieved_docs,
        expected_targets=case.expected_citation_targets,
    )

    # 5. Evaluate abstention
    abstain_eval = evaluate_abstention(
        result.final_answer,
        expected_abstention=case.expected_abstention,
        evidence_sufficient=case.expected_evidence_sufficient,
        success=result.success,
    )

    tools_invoked = [rec.tool_id for rec in result.tool_call_records]

    case_success = (
        result.success
        if not case.expected_abstention
        else abstain_eval.abstention_decision_correct
    ) and struct_eval.outcome_consistent

    return CaseExecutionMetrics(
        runner=runner,
        case_id=case.case_id,
        success=case_success,
        final_answer=result.final_answer,
        retrieved_chunk_ids=retrieved_chunk_ids,
        precision_at_3=prec,
        recall_at_3=rec,
        hit_rate_at_3=hit,
        reciprocal_rank=rr,
        citations_present=cite_eval.citation_present,
        citation_validity_rate=cite_eval.source_grounding_rate,
        target_citation_recall=cite_eval.target_citation_recall,
        abstention_correct=abstain_eval.abstention_decision_correct,
        latency_ms=result.total_latency_ms,
        tool_calls_count=len(result.tool_call_records),
        tools_invoked=tools_invoked,
    )


async def compare_case_execution(
    case: EvaluationCase,
    db: AsyncSession,
) -> ComparisonReport:
    """Execute case on both Legacy and LangGraph runners and produce comparative analysis."""
    legacy_res = await execute_case_on_runner(case, runner="legacy", db=db)
    langgraph_res = await execute_case_on_runner(case, runner="langgraph", db=db)

    divergences: list[str] = []
    if legacy_res.success != langgraph_res.success:
        divergences.append(
            f"Success mismatch: legacy={legacy_res.success}, langgraph={langgraph_res.success}"
        )
    if legacy_res.abstention_correct != langgraph_res.abstention_correct:
        divergences.append(
            f"Abstention decision mismatch: legacy={legacy_res.abstention_correct}, "
            f"langgraph={langgraph_res.abstention_correct}"
        )
    if legacy_res.citations_present != langgraph_res.citations_present:
        divergences.append(
            f"Citation presence mismatch: legacy={legacy_res.citations_present}, "
            f"langgraph={langgraph_res.citations_present}"
        )
    if legacy_res.tool_calls_count != langgraph_res.tool_calls_count:
        divergences.append(
            f"Tool call count divergence: legacy={legacy_res.tool_calls_count}, "
            f"langgraph={langgraph_res.tool_calls_count}"
        )

    return ComparisonReport(
        case_id=case.case_id,
        query=case.query,
        category=case.category.value,
        legacy=legacy_res,
        langgraph=langgraph_res,
        match_status=len(divergences) == 0,
        divergences=divergences,
    )
