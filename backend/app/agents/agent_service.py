"""
Enterprise RAG AI Assistant — Agent Service
============================================
Orchestrates tool selection, sequential execution, context assembly,
and LLM final-answer generation for the enterprise AI agent.

Safety Model
------------
- Prompt injection: Regex scan blocks known jailbreak patterns.
- Loop guard: max 5 tool calls per run, 60-second wall-clock budget.
- Data isolation: All data access routed through ToolRegistry (no raw DB).
- Ownership enforcement: Each tool validates user_id before returning data.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_tool import ToolResult
from app.agents.registry import ToolRegistry, get_registry
from app.config.settings import settings
from app.core.logging import logger
from app.models.agent_models import AgentRun, AgentToolCall
from app.services.llm_providers import LLMProviderError, get_llm_provider

# =============================================================================
# Safety: Prompt Injection Patterns
# =============================================================================

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\[SYSTEM\]", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|endoftext\|>", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"disregard\s+your\s+", re.IGNORECASE),
    re.compile(r"act\s+as\s+.{0,30}\s+without\s+restrictions", re.IGNORECASE),
    re.compile(r"###\s*INSTRUCTIONS?", re.IGNORECASE),
]


def _check_injection(text: str) -> str | None:
    """Return matched pattern string if prompt injection is detected, else None."""
    for pat in _INJECTION_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group()
    return None


# =============================================================================
# Result Containers
# =============================================================================


@dataclass
class ToolCallRecord:
    """Captures a single tool call's execution details for reporting."""

    tool_id: str
    tool_name: str
    parameters: dict[str, Any]
    result: ToolResult
    retries: int = 0


@dataclass
class AgentRunResult:
    """Complete result of one AgentService.run() invocation."""

    run_id: uuid.UUID
    question: str
    final_answer: str
    tool_call_records: list[ToolCallRecord] = field(default_factory=list)
    total_latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    provider: str | None = None
    model_name: str | None = None
    success: bool = True
    error_message: str | None = None
    reasoning_summary: str | None = None
    confidence_score: float = 0.0
    citations: list[dict[str, Any]] | None = None
    retrieved_documents: list[dict[str, Any]] | None = None


# =============================================================================
# Agent Service
# =============================================================================


class AgentService:
    """
    Enterprise AI Agent that uses registered tools to answer questions.

    Execution Flow
    --------------
    1. Sanitize input (injection check).
    2. LLM intent classification → tool call plan (JSON).
    3. Execute each tool call (up to max_tool_calls, within loop_budget_s).
    4. Assemble context from all successful tool results.
    5. LLM generates final grounded answer.
    6. Persist AgentRun + AgentToolCall rows.
    7. Return AgentRunResult.
    """

    SYSTEM_INTENT_PROMPT = """You are an enterprise AI assistant that uses internal tools to answer questions.

Given the user's question and the list of available tools, decide which tools to call.

Respond ONLY with a valid JSON array of tool calls. Each element must have:
  - "tool_id": the exact tool ID string
  - "parameters": object with the tool's required parameters

If the question can be answered directly without tools, respond with:
  [{{"tool_id": "direct_answer", "parameters": {{}}}}]

Available tools:
{tool_schemas}

Rules:
- Never call more than {max_calls} tools total.
- Prefer semantic_search first for factual questions.
- Use citation tool AFTER retrieving chunks to format references.
- Do NOT hallucinate tool IDs — only use the exact IDs listed above.
- Respond with ONLY the JSON array, no explanation."""

    SYSTEM_ANSWER_PROMPT = """You are an enterprise AI assistant. Answer the user's question using ONLY the context provided below.

Write your step-by-step thinking process inside a `<reasoning>...</reasoning>` block.
Then, write your final answer.

Rules:
- Be precise and factual. Do not hallucinate.
- Cite sources by appending the corresponding source index number in square brackets (e.g., [1], [2]) at the end of sentences that use details from that source.
- If the context is insufficient, explain what is missing rather than flatly refusing to answer.
- Keep the answer professional and structured.

Context from knowledge base:
{context}"""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._registry = registry or get_registry()

    # ── Public Entry Point ────────────────────────────────────────────────────

    async def run(
        self,
        db: AsyncSession,
        question: str,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None = None,
        provider_name: str | None = None,
        model_name: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1000,
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> AgentRunResult:
        """
        Main agent orchestration loop.

        Parameters
        ----------
        db          : Async database session.
        question    : User's natural language question.
        user_id     : Authenticated user's UUID (for ownership enforcement).
        session_id  : Optional chat session to link the run.
        """
        run_id = uuid.uuid4()
        wall_t0 = time.perf_counter()

        # 1. Safety: Injection detection
        matched = _check_injection(question)
        if matched:
            logger.warning(f"[AgentService] Prompt injection detected: {matched!r}")
            return AgentRunResult(
                run_id=run_id,
                question=question,
                final_answer="I cannot process this request as it contains disallowed content.",
                success=False,
                error_message=f"Prompt injection detected: {matched!r}",
            )

        max_tool_calls: int = getattr(settings, "agent_max_tool_calls", 5)
        getattr(settings, "agent_tool_timeout_s", 15.0)
        loop_budget: float = getattr(settings, "agent_loop_budget_s", 60.0)

        tool_records: list[ToolCallRecord] = []
        final_answer = ""
        prompt_tokens = 0
        completion_tokens = 0
        run_success = True
        error_msg: str | None = None

        try:
            llm = get_llm_provider(provider_name, model=model_name)
        except Exception as exc:
            logger.warning(f"[AgentService] Failed to load LLM provider: {exc}")
            llm = None

        actual_provider = provider_name or settings.llm_provider
        actual_model = model_name

        # 2. Build tool plan via LLM intent classification
        if llm is not None:
            tool_plan = await self._classify_intent(
                question=question,
                llm=llm,
                max_tool_calls=max_tool_calls,
                top_k=top_k,
                threshold=threshold,
            )
        else:
            tool_plan = [
                {
                    "tool_id": "semantic_search",
                    "parameters": {
                        "query": question,
                        "top_k": top_k,
                        "threshold": threshold,
                    },
                }
            ]

        # 3. Execute tool calls sequentially
        call_count = 0
        for call_spec in tool_plan:
            if call_count >= max_tool_calls:
                logger.warning("[AgentService] Max tool calls reached, stopping loop.")
                break

            elapsed = time.perf_counter() - wall_t0
            if elapsed > loop_budget:
                logger.warning(
                    f"[AgentService] Loop budget exhausted ({elapsed:.1f}s), stopping."
                )
                break

            tool_id = call_spec.get("tool_id", "")
            if tool_id == "direct_answer":
                break

            params = dict(call_spec.get("parameters", {}))

            # Inject top_k/threshold defaults for semantic_search if not set
            if tool_id == "semantic_search":
                params.setdefault("top_k", top_k)
                params.setdefault("threshold", threshold)

            result, retries = await self._execute_with_retry(
                tool_id=tool_id,
                params=params,
                user_id=user_id,
                db=db,
                max_retries=getattr(settings, "agent_max_retries", 3),
            )

            try:
                tool_obj = self._registry.get(tool_id)
                tool_name = tool_obj.name
            except KeyError:
                tool_name = tool_id

            tool_records.append(
                ToolCallRecord(
                    tool_id=tool_id,
                    tool_name=tool_name,
                    parameters=params,
                    result=result,
                    retries=retries,
                )
            )
            call_count += 1

        # 4. Assemble context from all successful tool results
        context = self._assemble_context(tool_records)

        # 5. LLM final answer generation
        reasoning_summary = None
        final_answer = ""
        citations = []
        if llm is not None:
            try:
                system_prompt = self.SYSTEM_ANSWER_PROMPT.format(
                    context=context or "No relevant context found."
                )
                raw_answer, usage = await llm.generate_response(
                    system_prompt=system_prompt,
                    user_prompt=question,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)

                # Parse reasoning tags
                final_answer = raw_answer
                reasoning_match = re.search(r"<reasoning>(.*?)</reasoning>", raw_answer, re.DOTALL)
                if reasoning_match:
                    reasoning_summary = reasoning_match.group(1).strip()
                    final_answer = re.sub(r"<reasoning>.*?</reasoning>", "", raw_answer, flags=re.DOTALL).strip()
            except LLMProviderError as exc:
                logger.error(f"[AgentService] LLM final answer failed: {exc}")
                final_answer = self._fallback_answer(tool_records)
                run_success = False
                error_msg = str(exc)
            except Exception as exc:
                logger.error(f"[AgentService] Unexpected error in LLM call: {exc}")
                final_answer = self._fallback_answer(tool_records)
                run_success = False
                error_msg = str(exc)
        else:
            final_answer = self._fallback_answer(tool_records)
            run_success = False
            error_msg = "LLM provider not configured or failed to load."

        # Collect retrieved documents & chunks from semantic search tools
        retrieved_documents = []
        for rec in tool_records:
            if rec.tool_id == "semantic_search" and isinstance(rec.result.output, list):
                for chunk in rec.result.output:
                    retrieved_documents.append({
                        "chunk_id": str(chunk.get("chunk_id") or chunk.get("id") or ""),
                        "text": chunk.get("text", ""),
                        "page_number": chunk.get("page_number", 1),
                        "section_title": chunk.get("section_title"),
                        "document_id": str(chunk.get("document_id") or ""),
                        "document_title": chunk.get("document_name", "Unknown"),
                        "score": float(chunk.get("score", 0.0))
                    })

        scores = [d["score"] for d in retrieved_documents if d.get("score") is not None]
        confidence_score = float(sum(scores) / len(scores)) if scores else 0.0

        # Generate citations
        citations = self._generate_citations(final_answer, retrieved_documents)

        total_latency_ms = int((time.perf_counter() - wall_t0) * 1000)

        # Record agent latency metric
        from app.services.cache_service import cache_service

        await cache_service.record_latency("agent", float(total_latency_ms))

        # 6. Persist run to database
        await self._persist_run(
            db=db,
            run_id=run_id,
            user_id=user_id,
            session_id=session_id,
            question=question,
            final_answer=raw_answer if llm is not None else final_answer, # Save full answer containing reasoning block
            tool_records=tool_records,
            total_latency_ms=total_latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            provider=actual_provider,
            model_name=actual_model,
            success=run_success,
            error_message=error_msg,
        )

        return AgentRunResult(
            run_id=run_id,
            question=question,
            final_answer=final_answer,
            tool_call_records=tool_records,
            total_latency_ms=total_latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            provider=actual_provider,
            model_name=actual_model,
            success=run_success,
            error_message=error_msg,
            reasoning_summary=reasoning_summary,
            confidence_score=confidence_score,
            citations=citations,
            retrieved_documents=retrieved_documents,
        )

    # ── Intent Classification ─────────────────────────────────────────────────

    async def _classify_intent(
        self,
        question: str,
        llm: Any,
        max_tool_calls: int,
        top_k: int,
        threshold: float,
    ) -> list[dict[str, Any]]:
        """
        Call LLM to classify intent and generate a tool call plan.
        Falls back to always-run semantic_search if LLM is unavailable.
        """
        tool_schemas = json.dumps(self._registry.list_all(role="user"), indent=2)
        system_prompt = self.SYSTEM_INTENT_PROMPT.format(
            tool_schemas=tool_schemas,
            max_calls=max_tool_calls,
        )
        try:
            raw_response, _ = await llm.generate_response(
                system_prompt=system_prompt,
                user_prompt=f"Question: {question}",
                temperature=0.0,
                max_tokens=512,
            )
            # Extract JSON array from response
            plan = self._parse_json_plan(raw_response)
            if plan:
                logger.debug(f"[AgentService] Intent plan: {plan}")
                return plan
        except Exception as exc:
            logger.warning(
                f"[AgentService] Intent classification failed, using fallback: {exc}"
            )

        # Fallback: always run semantic search
        return [
            {
                "tool_id": "semantic_search",
                "parameters": {
                    "query": question,
                    "top_k": top_k,
                    "threshold": threshold,
                },
            }
        ]

    def _parse_json_plan(self, raw: str) -> list[dict[str, Any]]:
        """Extract and parse a JSON array from LLM response text."""
        # Strip markdown code fences
        raw = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
        # Find the first [...] block
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1 or end == 0:
            return []
        try:
            plan = json.loads(raw[start:end])
            if isinstance(plan, list):
                return [item for item in plan if isinstance(item, dict)]
        except json.JSONDecodeError:
            pass
        return []

    # ── Tool Execution with Retry ─────────────────────────────────────────────

    async def _execute_with_retry(
        self,
        tool_id: str,
        params: dict[str, Any],
        user_id: uuid.UUID,
        db: AsyncSession,
        max_retries: int = 3,
    ) -> tuple[ToolResult, int]:
        """Execute a tool, retrying on transient failures."""
        retries = 0
        last_result: ToolResult | None = None

        for attempt in range(max_retries):
            try:
                result = await self._registry.execute(tool_id, params, user_id, db)
                if result.success:
                    return result, retries
                last_result = result
                retries += 1
                logger.debug(
                    f"[AgentService] Tool '{tool_id}' attempt {attempt+1} failed: {result.error}"
                )
            except KeyError:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Tool '{tool_id}' is not registered.",
                ), retries
            except Exception as exc:
                last_result = ToolResult(success=False, output=None, error=str(exc))
                retries += 1

        return last_result or ToolResult(
            success=False, output=None, error="All retries exhausted."
        ), retries

    # ── Context Assembly ──────────────────────────────────────────────────────

    def _assemble_context(self, records: list[ToolCallRecord]) -> str:
        """Flatten all successful tool outputs into a LLM-ready context string."""
        parts: list[str] = []

        for rec in records:
            if not rec.result.success or rec.result.output is None:
                continue

            output = rec.result.output

            if rec.tool_id == "semantic_search" and isinstance(output, list):
                for i, chunk in enumerate(output, 1):
                    score = chunk.get("score", "?")
                    doc_name = chunk.get("document_name", "Unknown")
                    page = chunk.get("page_number", "?")
                    section = chunk.get("section_title") or ""
                    text = chunk.get("text", "")
                    header = f"[Source {i}: {doc_name}, p.{page}{', §' + section if section else ''} | score: {score}]"
                    parts.append(f"{header}\n{text}")

            elif rec.tool_id == "document_lookup" and isinstance(output, dict):
                doc = output.get("document", {})
                chunks = output.get("chunks", []) or (
                    [output.get("chunk")] if output.get("chunk") else []
                )
                if doc:
                    parts.append(f"[Document: {doc.get('filename', '')}]")
                for c in chunks:
                    if c:
                        parts.append(c.get("text", ""))

            elif rec.tool_id == "citation" and isinstance(output, list):
                for cit in output:
                    parts.append(
                        f"Citation: {cit.get('citation', '')} — {cit.get('preview', '')}"
                    )

            elif rec.tool_id == "conversation_history" and isinstance(output, list):
                for msg in output:
                    role = msg.get("role", "?").upper()
                    content = msg.get("content", "")
                    parts.append(f"[{role}]: {content}")

        return "\n\n".join(parts)

    def _fallback_answer(self, records: list[ToolCallRecord]) -> str:
        """Build a minimal answer from raw tool results when LLM is unavailable."""
        context = self._assemble_context(records)
        if context:
            return f"Based on the retrieved documents:\n\n{context[:1000]}"
        return "I was unable to find relevant information to answer your question."

    def _generate_citations(
        self,
        answer_text: str,
        retrieved_docs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Scan final answer for citation tags and resolve back to retrieved doc metadata."""
        matches = re.findall(r"\[(\d+)\]", answer_text)
        cited_indices = sorted(list(set(int(m) for m in matches)))

        citations = []
        for idx in cited_indices:
            if 0 < idx <= len(retrieved_docs):
                item = retrieved_docs[idx - 1]
                citations.append({
                    "citation_index": idx,
                    "chunk_id": item["chunk_id"],
                    "document_id": item["document_id"],
                    "document_title": item["document_title"],
                    "page_number": item["page_number"],
                    "section_title": item["section_title"],
                    "text": item["text"],
                    "score": item["score"],
                })
        return citations

    # ── Persistence ───────────────────────────────────────────────────────────

    async def _persist_run(
        self,
        db: AsyncSession,
        run_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None,
        question: str,
        final_answer: str,
        tool_records: list[ToolCallRecord],
        total_latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
        provider: str | None,
        model_name: str | None,
        success: bool,
        error_message: str | None,
    ) -> None:
        """Persist AgentRun and child AgentToolCall rows."""
        try:
            run = AgentRun(
                id=run_id,
                user_id=user_id,
                session_id=session_id,
                question=question,
                final_answer=final_answer,
                tools_called=[r.tool_id for r in tool_records],
                total_tool_calls=len(tool_records),
                total_latency_ms=total_latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                provider=provider,
                model_name=model_name,
                success=success,
                error_message=error_message,
            )
            db.add(run)
            await db.flush()  # Get the run inserted before children

            for rec in tool_records:
                # Truncate result output to avoid bloating DB (max 2KB)
                result_dict = rec.result.to_dict()
                raw_output = result_dict.get("output")
                if isinstance(raw_output, list | dict):
                    serialized = json.dumps(raw_output)
                    if len(serialized) > 2048:
                        result_dict["output"] = serialized[:2048] + "…[truncated]"
                        result_dict["truncated"] = True

                call = AgentToolCall(
                    id=uuid.uuid4(),
                    run_id=run_id,
                    tool_id=rec.tool_id,
                    tool_name=rec.tool_name,
                    parameters=rec.parameters,
                    result=result_dict,
                    latency_ms=rec.result.latency_ms,
                    retries=rec.retries,
                    success=rec.result.success,
                    error=rec.result.error,
                )
                db.add(call)

            await db.commit()
        except Exception as exc:
            logger.error(f"[AgentService] Failed to persist AgentRun: {exc}")
            await db.rollback()

    # ── Statistics ────────────────────────────────────────────────────────────

    async def get_statistics(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        period_days: int = 30,
    ) -> dict[str, Any]:
        """Compute aggregate run and tool statistics for a user."""
        from datetime import datetime, timedelta

        from app.models.agent_models import AgentToolCall

        since = datetime.now(UTC) - timedelta(days=period_days)

        # ── Run stats ─────────────────────────────────────────────────────────
        runs_stmt = select(AgentRun).where(
            AgentRun.user_id == user_id,
            AgentRun.created_at >= since,
        )
        runs_res = await db.execute(runs_stmt)
        runs = list(runs_res.scalars().all())

        total_runs = len(runs)
        successful_runs = sum(1 for r in runs if r.success)
        total_tool_calls_sum = sum(r.total_tool_calls for r in runs)
        avg_latency = sum(r.total_latency_ms for r in runs) / max(total_runs, 1)
        avg_prompt_tokens = sum(r.prompt_tokens for r in runs) / max(total_runs, 1)
        avg_completion_tokens = sum(r.completion_tokens for r in runs) / max(
            total_runs, 1
        )

        # ── Tool call stats ────────────────────────────────────────────────────
        tool_calls_stmt = (
            select(AgentToolCall)
            .join(AgentRun, AgentToolCall.run_id == AgentRun.id)
            .where(AgentRun.user_id == user_id, AgentRun.created_at >= since)
        )
        tc_res = await db.execute(tool_calls_stmt)
        all_tool_calls = list(tc_res.scalars().all())

        # Group by tool_id
        by_tool: dict[str, list[AgentToolCall]] = {}
        for tc in all_tool_calls:
            by_tool.setdefault(tc.tool_id, []).append(tc)

        tool_stats = []
        for tool_id, calls in by_tool.items():
            latencies = sorted([c.latency_ms for c in calls])
            n = len(latencies)
            p50 = latencies[n // 2] if latencies else 0
            p95 = latencies[int(n * 0.95)] if latencies else 0
            tool_stats.append(
                {
                    "tool_id": tool_id,
                    "tool_name": calls[0].tool_name,
                    "total_calls": n,
                    "successful_calls": sum(1 for c in calls if c.success),
                    "failed_calls": sum(1 for c in calls if not c.success),
                    "avg_latency_ms": sum(latencies) / max(n, 1),
                    "p50_latency_ms": p50,
                    "p95_latency_ms": p95,
                }
            )

        return {
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "failed_runs": total_runs - successful_runs,
            "total_tool_calls": total_tool_calls_sum,
            "avg_tools_per_run": total_tool_calls_sum / max(total_runs, 1),
            "avg_run_latency_ms": avg_latency,
            "avg_prompt_tokens": avg_prompt_tokens,
            "avg_completion_tokens": avg_completion_tokens,
            "tool_stats": tool_stats,
            "period_days": period_days,
        }
