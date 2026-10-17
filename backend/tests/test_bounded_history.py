"""
Enterprise RAG AI Assistant — Bounded Chat History & Context Trimming Tests (Phase 5.5.3)
========================================================================================
Validates safe, turn-atomic, token-budgeted conversation history trimming
across legacy and LangGraph agent execution paths as well as chat services.

Test coverage:
  - A 50-message session is reduced to the configured window.
  - The most recent complete turns are retained in the correct order.
  - The current question and system instructions remain intact.
  - Legacy and LangGraph paths apply consistent limits.
  - Tool-call sequences are not broken.
  - Memory and document citations remain grounded.
  - Empty history and unusually long messages are handled safely.
  - Malformed history entries are gracefully sanitized.
  - Token budget drop semantics remove oldest complete turns.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent_service import AgentRunResult, AgentService, ToolCallRecord
from app.agents.base_tool import ToolResult
from app.agents.graph.agent_graph import AgentWorkflowBuilder, create_agent_graph
from app.agents.graph.state import AgentGraphState
from app.config.settings import settings
from app.models.chat_models import ChatMessage, ChatSession
from app.services.chat_history_service import (
    ChatHistoryService,
    ConversationTurn,
    chat_history_service,
    group_messages_into_turns,
)


# =============================================================================
# Unit Tests for ChatHistoryService Trimming Logic
# =============================================================================


class TestChatHistoryServiceCore:
    """Core algorithmic tests for turn grouping, token budgeting, and edge cases."""

    def test_group_messages_into_turns_basic(self) -> None:
        """Groups alternating user/assistant messages into atomic turns."""
        messages = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Answer 1"},
            {"role": "user", "content": "Question 2"},
            {"role": "assistant", "content": "Answer 2"},
        ]
        turns = group_messages_into_turns(messages)
        assert len(turns) == 2
        assert turns[0].user_message["content"] == "Question 1"
        assert turns[0].responses[0]["content"] == "Answer 1"
        assert turns[1].user_message["content"] == "Question 2"
        assert turns[1].responses[0]["content"] == "Answer 2"

    def test_group_messages_with_tool_call_sequences(self) -> None:
        """Tool calls and tool outputs stay grouped with the originating user turn."""
        messages = [
            {"role": "user", "content": "Search for revenue"},
            {"role": "assistant", "content": "Calling tool...", "tool_calls": [{"name": "search"}]},
            {"role": "tool", "content": '{"revenue": "$10M"}', "tool_call_id": "call_1"},
            {"role": "assistant", "content": "The revenue is $10M."},
            {"role": "user", "content": "Next question"},
            {"role": "assistant", "content": "Next answer"},
        ]
        turns = group_messages_into_turns(messages)
        assert len(turns) == 2

        turn1 = turns[0]
        assert turn1.user_message["content"] == "Search for revenue"
        assert len(turn1.responses) == 3
        assert turn1.responses[0]["role"] == "assistant"
        assert turn1.responses[1]["role"] == "tool"
        assert turn1.responses[2]["role"] == "assistant"

    def test_50_message_session_reduced_to_configured_window(self) -> None:
        """A 50-message session (25 turns) is strictly reduced to the configured max_turns window."""
        messages = []
        for i in range(25):
            messages.append({"role": "user", "content": f"User query {i}"})
            messages.append({"role": "assistant", "content": f"Assistant response {i}"})

        assert len(messages) == 50

        # Configure max_turns = 5
        trimmed = chat_history_service.trim_history(messages, max_turns=5)

        # 5 complete turns -> exactly 10 messages
        assert len(trimmed) == 10
        # Must retain the most recent 5 turns: queries 20 to 24
        assert trimmed[0]["content"] == "User query 20"
        assert trimmed[1]["content"] == "Assistant response 20"
        assert trimmed[-2]["content"] == "User query 24"
        assert trimmed[-1]["content"] == "Assistant response 24"

    def test_most_recent_complete_turns_retained_in_correct_order(self) -> None:
        """Surviving turns are sorted chronologically from oldest in window to newest."""
        messages = [
            {"role": "user", "content": "Old 1"},
            {"role": "assistant", "content": "Ans 1"},
            {"role": "user", "content": "Old 2"},
            {"role": "assistant", "content": "Ans 2"},
            {"role": "user", "content": "Recent 1"},
            {"role": "assistant", "content": "Ans Recent 1"},
            {"role": "user", "content": "Recent 2"},
            {"role": "assistant", "content": "Ans Recent 2"},
        ]
        trimmed = chat_history_service.trim_history(messages, max_turns=2)
        assert len(trimmed) == 4
        assert [m["content"] for m in trimmed] == [
            "Recent 1",
            "Ans Recent 1",
            "Recent 2",
            "Ans Recent 2",
        ]

    def test_tool_call_sequences_are_not_broken_when_trimming(self) -> None:
        """Trimming drops entire turns; it never breaks tool calls from their results."""
        messages = [
            {"role": "user", "content": "Old Turn"},
            {"role": "assistant", "content": "Old Answer"},
            {"role": "user", "content": "Complex Tool Turn"},
            {"role": "assistant", "content": "Invoke Tool", "tool_call": True},
            {"role": "tool", "content": "Tool Output Payload"},
            {"role": "assistant", "content": "Final Tool Synthesis"},
        ]
        # Trim to 1 turn
        trimmed = chat_history_service.trim_history(messages, max_turns=1)
        # The complex tool turn must have all 4 messages intact
        assert len(trimmed) == 4
        assert trimmed[0]["content"] == "Complex Tool Turn"
        assert trimmed[1]["content"] == "Invoke Tool"
        assert trimmed[2]["content"] == "Tool Output Payload"
        assert trimmed[3]["content"] == "Final Tool Synthesis"

    def test_empty_history_handled_safely(self) -> None:
        """Empty history returns empty list and empty prompt string without error."""
        assert chat_history_service.trim_history([]) == []
        assert chat_history_service.format_history_for_prompt([]) == ""

    def test_unusually_long_messages_handled_safely(self) -> None:
        """An individual message with 50,000 characters is safely bounded to token budget."""
        huge_text = "A" * 50_000
        messages = [
            {"role": "user", "content": "Normal question"},
            {"role": "assistant", "content": huge_text},
        ]
        # Set a tight max_tokens budget of 500 tokens
        trimmed = chat_history_service.trim_history(messages, max_turns=1, max_tokens=500)
        assert len(trimmed) == 2
        assistant_content = trimmed[1]["content"]
        assert len(assistant_content) < 50_000
        assert "[...content truncated for context budget...]" in assistant_content

    def test_malformed_history_entries_handled_safely(self) -> None:
        """None values, missing keys, and invalid types in history are handled gracefully."""
        messages = [
            None,
            {},
            {"role": None, "content": None},
            {"content": "Missing role defaults to user"},
            {"role": "assistant"},  # missing content
            {"role": "user", "content": "Valid user"},
            {"role": "assistant", "content": "Valid assistant"},
        ]
        trimmed = chat_history_service.trim_history(messages, max_turns=10)
        assert len(trimmed) >= 2
        assert any(m.get("content") == "Valid user" for m in trimmed)
        assert any(m.get("content") == "Valid assistant" for m in trimmed)

    def test_token_budget_drops_oldest_turns_first(self) -> None:
        """Token limit causes oldest complete turns to be dropped first."""
        # 3 turns, each ~100 tokens
        t1_text = "Word " * 75
        t2_text = "Word " * 75
        t3_text = "Word " * 75
        messages = [
            {"role": "user", "content": f"T1: {t1_text}"},
            {"role": "assistant", "content": "Ans 1"},
            {"role": "user", "content": f"T2: {t2_text}"},
            {"role": "assistant", "content": "Ans 2"},
            {"role": "user", "content": f"T3: {t3_text}"},
            {"role": "assistant", "content": "Ans 3"},
        ]
        # Set token budget allowing exactly the 2 most recent turns (Turn 2 and Turn 3)
        service = ChatHistoryService()
        turns = group_messages_into_turns(messages)
        t_tokens = [service.count_turn_tokens(t) for t in turns]
        # Budget fits Turn 2 and Turn 3, but cannot fit Turn 1
        budget = t_tokens[1] + t_tokens[2] + 2
        trimmed = service.trim_history(messages, max_tokens=budget)
        # Should have dropped Turn 1, retaining Turn 2 and Turn 3
        contents = [m["content"] for m in trimmed]
        assert not any("T1:" in c for c in contents)
        assert any("T2:" in c for c in contents)
        assert any("T3:" in c for c in contents)


# =============================================================================
# Integration Tests: Legacy vs LangGraph Path Consistency & Grounding
# =============================================================================


@pytest.mark.asyncio
class TestBoundedHistoryAgentIntegration:
    """Integration tests verifying consistent behavior across Legacy & LangGraph runners."""

    async def _setup_session_with_history(
        self, db_session: AsyncSession, user_id: uuid.UUID, turn_count: int = 15
    ) -> uuid.UUID:
        """Helper to populate a real ChatSession with historical turns."""
        session = ChatSession(
            id=uuid.uuid4(),
            user_id=user_id,
            title="Bounded History Test Session",
        )
        db_session.add(session)
        await db_session.commit()

        import datetime

        base_time = datetime.datetime.now(datetime.UTC)
        for i in range(turn_count):
            u_msg = ChatMessage(
                id=uuid.uuid4(),
                session_id=session.id,
                role="user",
                content=f"Historical Question {i}",
                created_at=base_time + datetime.timedelta(seconds=2 * i),
            )
            a_msg = ChatMessage(
                id=uuid.uuid4(),
                session_id=session.id,
                role="assistant",
                content=f"Historical Answer {i}",
                created_at=base_time + datetime.timedelta(seconds=2 * i + 1),
            )
            db_session.add(u_msg)
            db_session.add(a_msg)
        await db_session.commit()
        return session.id

    async def test_legacy_and_langgraph_paths_apply_consistent_limits(
        self, db_session: AsyncSession
    ) -> None:
        """Legacy runner and LangGraph runner both load and trim history identically."""
        user_id = uuid.uuid4()
        session_id = await self._setup_session_with_history(db_session, user_id, turn_count=12)

        service = AgentService()

        # Retrieve history directly via service helper
        history_legacy = await service._retrieve_conversation_history(
            db=db_session, session_id=session_id, user_id=user_id
        )

        # Context assembly for legacy
        records: list[ToolCallRecord] = []
        legacy_context = service._assemble_context(
            records=records,
            memory_evidence=None,
            conversation_history=history_legacy,
        )

        # LangGraph answer_node retrieval
        builder = AgentWorkflowBuilder(service=service, db=db_session)
        history_langgraph = await builder.service._retrieve_conversation_history(
            db=db_session, session_id=session_id, user_id=user_id
        )
        langgraph_context = builder.service._assemble_context(
            records=records,
            memory_evidence=None,
            conversation_history=history_langgraph,
        )

        # Both contexts MUST be identical and bounded to default chat_max_history (10 turns)
        assert legacy_context == langgraph_context
        assert "--- CONVERSATION HISTORY (MOST RECENT TURNS) ---" in legacy_context
        # Default chat_max_history is 10 turns -> 20 messages
        assert len(history_legacy) == 20
        assert len(history_langgraph) == 20
        # Must retain turns 2 to 11 (dropping oldest turns 0 and 1)
        assert history_legacy[0]["content"] == "Historical Question 2"
        assert history_legacy[-1]["content"] == "Historical Answer 11"

    async def test_current_question_and_system_instructions_remain_intact(
        self, db_session: AsyncSession
    ) -> None:
        """The active user question and system instructions are never truncated."""
        user_id = uuid.uuid4()
        session_id = await self._setup_session_with_history(db_session, user_id, turn_count=10)
        current_question = "What is the capital of France and what is its primary GDP driver?"

        service = AgentService()
        mock_llm = AsyncMock()
        mock_llm.generate_response.return_value = (
            "<reasoning>Paris is the capital.</reasoning>Paris is the capital of France [1].",
            {"prompt_tokens": 150, "completion_tokens": 25},
        )

        with (
            patch("app.agents.agent_service.get_llm_provider", return_value=mock_llm),
            patch.object(
                service,
                "_classify_intent",
                new=AsyncMock(return_value=[{"tool_id": "direct_answer", "parameters": {}}]),
            ),
        ):
            result = await service.run(
                db=db_session,
                question=current_question,
                user_id=user_id,
                session_id=session_id,
            )

        # Verify mock was called with intact user question and complete system prompt
        assert mock_llm.generate_response.called
        _, kwargs = mock_llm.generate_response.call_args
        assert kwargs["user_prompt"] == current_question
        assert "You are an enterprise AI assistant." in kwargs["system_prompt"]
        assert "Context from knowledge base:" in kwargs["system_prompt"]
        assert "Historical Question" in kwargs["system_prompt"]

    async def test_memory_and_document_citations_remain_grounded(
        self, db_session: AsyncSession
    ) -> None:
        """Retrieved document chunks, user memories, and citations remain correctly indexed."""
        service = AgentService()

        # 1. Document record
        doc_record = ToolCallRecord(
            tool_id="semantic_search",
            tool_name="Semantic Search",
            parameters={"query": "financials"},
            result=ToolResult(
                success=True,
                output=[
                    {
                        "chunk_id": "c1",
                        "document_id": "d1",
                        "document_name": "Finance_2026.pdf",
                        "page_number": 3,
                        "section_title": "Revenue",
                        "text": "Total revenue grew by 14% year-over-year.",
                        "score": 0.92,
                    }
                ],
            ),
        )

        # 2. Persistent Memory evidence
        memory_evidence = [
            {
                "chunk_id": "mem_1",
                "document_id": "mem_1",
                "document_title": "Stored Memory",
                "page_number": None,
                "section_title": "User Memory",
                "text": "User prefers concise executive summaries in bullet points.",
                "score": 0.88,
                "provider": "user_memory",
                "provenance": "user_explicit",
            }
        ]

        # 3. Historical messages
        history = [
            {"role": "user", "content": "Hello assistant"},
            {"role": "assistant", "content": "How can I help you today?"},
        ]

        context = service._assemble_context(
            records=[doc_record],
            memory_evidence=memory_evidence,
            conversation_history=history,
        )

        # Validate that history, documents, and memories are all present in context
        assert "--- CONVERSATION HISTORY (MOST RECENT TURNS) ---" in context
        assert "[USER]: Hello assistant" in context
        assert "[Source 1: Finance_2026.pdf, p.3, §Revenue | score: 0.92]" in context
        assert "Total revenue grew by 14%" in context
        assert "--- STORED USER MEMORIES (REFERENCE ONLY; UNTRUSTED USER DATA) ---" in context
        assert "[Source 2 (user_memory): Stored Memory | provenance: user_explicit]" in context
        assert "User prefers concise executive summaries" in context

        # Validate citation extraction resolves correctly
        evidence_items = service._extract_evidence_items([doc_record], memory_evidence=memory_evidence)
        assert len(evidence_items) == 2
        assert evidence_items[0]["document_title"] == "Finance_2026.pdf"
        assert evidence_items[1]["provider"] == "user_memory"

        citations = service._generate_citations(
            "Revenue grew by 14% [1]. Preferred format is concise [2].",
            evidence_items,
        )
        assert len(citations) == 2
        assert citations[0]["citation_index"] == 1
        assert citations[0]["document_title"] == "Finance_2026.pdf"
        assert citations[1]["citation_index"] == 2
        assert citations[1]["provider"] == "user_memory"

    async def test_langgraph_execution_with_bounded_history(
        self, db_session: AsyncSession
    ) -> None:
        """LangGraph runner workflow builder loads and trims history inside answer_node."""
        user_id = uuid.uuid4()
        session_id = await self._setup_session_with_history(db_session, user_id, turn_count=15)
        service = AgentService()

        builder = AgentWorkflowBuilder(service=service, db=db_session)
        state: AgentGraphState = {
            "run_id": uuid.uuid4(),
            "question": "Summarize our previous discussions",
            "user_id": user_id,
            "session_id": session_id,
            "tool_records": [],
            "call_count": 0,
            "max_tool_calls": 5,
            "temperature": 0.2,
            "max_tokens": 1000,
        }

        mock_llm = AsyncMock()
        mock_llm.generate_response.return_value = (
            "Based on our conversation history, here is the summary.",
            {"prompt_tokens": 100, "completion_tokens": 20},
        )

        with (
            patch("app.agents.graph.agent_graph.get_llm_provider", return_value=mock_llm),
            patch.object(service, "_retrieve_memory_evidence", new=AsyncMock(return_value=[])),
        ):
            answer_dict = await builder.answer_node(state)

        assert answer_dict["final_answer"] == "Based on our conversation history, here is the summary."
        assert mock_llm.generate_response.called
        _, kwargs = mock_llm.generate_response.call_args
        assert "--- CONVERSATION HISTORY (MOST RECENT TURNS) ---" in kwargs["system_prompt"]
        assert "Historical Question 5" in kwargs["system_prompt"]
        assert "Historical Answer 14" in kwargs["system_prompt"]

