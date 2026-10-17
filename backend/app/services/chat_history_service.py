"""
Enterprise RAG AI Assistant — Bounded Chat History & Context Trimming Service
=============================================================================
Provides safe, configurable, turn-aware conversation history trimming for
LLM prompts across legacy and LangGraph agent execution paths as well as
streaming conversational RAG.

Key Invariants:
1. Turn-Atomicity: Preserves complete conversational turns (User -> Assistant / Tools)
   rather than slicing arbitrary individual messages. Never splits tool-call and tool-result sequences.
2. Question & System Protection: The current user query and required system prompts are
   never truncated to accommodate past history.
3. Safe Token Budgeting: Uses tiktoken when available with conservative approximation fallback;
   drops oldest complete turns first when exceeding token budget.
4. Privacy & Audit: Never logs private message content; logs only sanitized turn/token metrics.
5. Storage Immutability: Trims only the runtime LLM prompt payload; never modifies or deletes
   stored historical messages in PostgreSQL.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.chat_models import ChatMessage, ChatSession

try:
    import tiktoken
except ImportError:
    tiktoken = None  # type: ignore[assignment]


# =============================================================================
# Turn Representation
# =============================================================================


@dataclass
class ConversationTurn:
    """Represents a complete conversational interaction (user prompt + assistant/tool responses)."""

    user_message: dict[str, Any] | None
    responses: list[dict[str, Any]] = field(default_factory=list)

    @property
    def all_messages(self) -> list[dict[str, Any]]:
        """Return all messages belonging to this turn in chronological order."""
        msgs: list[dict[str, Any]] = []
        if self.user_message is not None:
            msgs.append(self.user_message)
        msgs.extend(self.responses)
        return msgs


def _extract_msg_fields(msg: Any) -> tuple[str, str, dict[str, Any]]:
    """Extract (role, content, metadata) safely from a ChatMessage ORM model or a dict."""
    if isinstance(msg, dict):
        role = str(msg.get("role") or "user").strip().lower()
        content = str(msg.get("content") or "")
        meta = {k: v for k, v in msg.items() if k not in ("role", "content")}
        return role, content, meta

    # ChatMessage ORM instance or duck-typed object
    role = str(getattr(msg, "role", "user") or "user").strip().lower()
    content = str(getattr(msg, "content", "") or "")
    meta = {}
    if hasattr(msg, "id") and getattr(msg, "id"):
        meta["id"] = str(getattr(msg, "id"))
    if hasattr(msg, "citations") and getattr(msg, "citations"):
        meta["citations"] = getattr(msg, "citations")
    if hasattr(msg, "created_at") and getattr(msg, "created_at"):
        meta["created_at"] = getattr(msg, "created_at").isoformat()
    return role, content, meta


def group_messages_into_turns(messages: list[Any]) -> list[ConversationTurn]:
    """
    Group a flat sequence of chronological messages into atomic conversational turns.

    Rules:
    - A turn starts with a 'user' message.
    - All subsequent non-user messages ('assistant', 'tool', 'function', 'system')
      belong to that turn's responses until the next 'user' message.
    - Any leading non-user messages before the first user message form a turn 0.
    """
    turns: list[ConversationTurn] = []
    current_turn: ConversationTurn | None = None

    for msg in messages:
        if msg is None:
            continue
        try:
            role, content, meta = _extract_msg_fields(msg)
        except Exception as exc:
            logger.debug(f"[ChatHistoryService] Skipping unparseable history entry: {exc}")
            continue

        msg_dict = {"role": role, "content": content, **meta}

        if role == "user":
            if current_turn is not None and (current_turn.user_message or current_turn.responses):
                turns.append(current_turn)
            current_turn = ConversationTurn(user_message=msg_dict, responses=[])
        else:
            if current_turn is None:
                # Leading message (e.g. system greeting before any user question)
                current_turn = ConversationTurn(user_message=None, responses=[msg_dict])
            else:
                current_turn.responses.append(msg_dict)

    if current_turn is not None and (current_turn.user_message or current_turn.responses):
        turns.append(current_turn)

    return turns


# =============================================================================
# Service Implementation
# =============================================================================


class ChatHistoryService:
    """Manages bounded conversation history extraction, turn preservation, and context trimming."""

    def __init__(self, tokenizer: Any = None) -> None:
        self._tokenizer = tokenizer
        if self._tokenizer is None and tiktoken is not None:
            try:
                tokenizer_name = getattr(settings, "tokenizer_name", "cl100k_base")
                self._tokenizer = tiktoken.get_encoding(tokenizer_name)
            except Exception:
                try:
                    self._tokenizer = tiktoken.get_encoding("cl100k_base")
                except Exception:
                    self._tokenizer = None

    def estimate_tokens(self, text: str) -> int:
        """
        Count tokens using tiktoken when available, with a documented conservative
        fallback (len(text) / 3.5 + 4) when tokenizer is unavailable.
        """
        if not text:
            return 0
        if self._tokenizer is not None:
            try:
                return len(self._tokenizer.encode(text))
            except Exception:
                pass
        # Conservative token estimation: ~3.5 chars per token + fixed overhead
        return math.ceil(len(text) / 3.5) + 4

    def count_turn_tokens(self, turn: ConversationTurn) -> int:
        """Compute the total estimated tokens for all messages within a turn."""
        tokens = 0
        for msg in turn.all_messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            tokens += self.estimate_tokens(f"{role}: {content}\n")
        return tokens

    def trim_history(
        self,
        messages: list[Any],
        max_turns: int | None = None,
        max_tokens: int | None = None,
        reserved_tokens: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Trim conversation history to fit both turn-window and token-budget limits.

        Guarantees:
        - Atomic turns: complete user/assistant/tool-call sequences are kept together.
        - Oldest turns dropped first: the most recent turns are always preserved.
        - Token budgeting: drops oldest complete turns until history fits within budget.
        - Single-turn protection: if an individual turn exceeds budget, its message content
          is safely bounded with an explicit truncation notice without dropping the turn.
        """
        if not messages:
            return []

        # 1. Group into atomic conversation turns
        turns = group_messages_into_turns(messages)
        if not turns:
            return []

        # 2. Window constraint: retain at most max_turns complete turns
        limit_turns = (
            max_turns
            if max_turns is not None
            else getattr(settings, "chat_max_history_turns", None)
            or getattr(settings, "chat_max_history", 10)
        )
        if len(turns) > limit_turns:
            turns = turns[-limit_turns:]

        # 3. Token budget constraint
        configured_token_budget = (
            max_tokens
            if max_tokens is not None
            else getattr(settings, "chat_max_tokens", 4000)
        )
        effective_budget = max(100, configured_token_budget - reserved_tokens)

        # Calculate total tokens for currently selected turns
        total_tokens = sum(self.count_turn_tokens(t) for t in turns)

        # Drop oldest complete turns while exceeding budget
        while total_tokens > effective_budget and len(turns) > 1:
            dropped = turns.pop(0)
            total_tokens -= self.count_turn_tokens(dropped)

        # 4. Handle edge case: single surviving turn exceeds token budget (e.g. 50k-char message)
        if len(turns) == 1 and total_tokens > effective_budget:
            single_turn = turns[0]
            max_chars_per_msg = max(200, int(effective_budget * 3.5))
            for msg in single_turn.all_messages:
                content = msg.get("content", "")
                if len(content) > max_chars_per_msg:
                    msg["content"] = (
                        content[:max_chars_per_msg].rstrip()
                        + "\n[...content truncated for context budget...]"
                    )

        # 5. Flatten surviving complete turns in chronological order
        result: list[dict[str, Any]] = []
        for turn in turns:
            result.extend(turn.all_messages)

        logger.debug(
            f"[ChatHistoryService] Bounded history: {len(messages)} raw messages -> "
            f"{len(turns)} complete turns ({len(result)} messages, ~{total_tokens} tokens)."
        )
        return result

    def format_history_for_prompt(
        self,
        trimmed_messages: list[dict[str, Any]],
        style: str = "agent",
    ) -> str:
        """
        Format a list of trimmed message dictionaries into a prompt-ready string.

        Styles:
          - "agent": '[USER]: ...\\n[ASSISTANT]: ...'
          - "chat":  'User: ...\\nAssistant: ...\\n'
        """
        if not trimmed_messages:
            return ""

        if style == "chat":
            return "".join(
                f"{msg.get('role', 'user').capitalize()}: {msg.get('content', '')}\n"
                for msg in trimmed_messages
            )

        # "agent" style with bracketed roles
        lines = []
        for msg in trimmed_messages:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            lines.append(f"[{role}]: {content}")
        return "\n".join(lines)

    async def get_bounded_history_for_session(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        exclude_message_id: uuid.UUID | None = None,
        max_turns: int | None = None,
        max_tokens: int | None = None,
        reserved_tokens: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Retrieve and trim conversation history for an authenticated session from the database.
        Verifies session ownership before querying messages.
        """
        # 1. Ownership & existence check
        session_stmt = select(ChatSession.id).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
        session_res = await db.execute(session_stmt)
        if session_res.scalar_one_or_none() is None:
            return []

        # 2. Fetch messages in chronological order
        query = select(ChatMessage).where(ChatMessage.session_id == session_id)
        if exclude_message_id is not None:
            query = query.where(ChatMessage.id != exclude_message_id)
        query = query.order_by(ChatMessage.created_at.asc())

        res = await db.execute(query)
        messages = list(res.scalars().all())

        # 3. Apply bounded turn and token trimming
        return self.trim_history(
            messages=messages,
            max_turns=max_turns,
            max_tokens=max_tokens,
            reserved_tokens=reserved_tokens,
        )


chat_history_service = ChatHistoryService()
