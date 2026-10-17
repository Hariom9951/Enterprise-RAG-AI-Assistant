"""
Enterprise RAG AI Assistant — Conversation History Tool
=========================================================
Retrieves and optionally summarizes chat history for a session.
Uses token budgeting to prevent context overflow.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_tool import BaseTool, ParameterSpec, PermissionLevel, ToolResult
from app.models.chat_models import ChatMessage, ChatSession


class ConversationHistoryTool(BaseTool):
    """
    Retrieve prior conversation messages for a chat session.

    Returns the most recent messages up to the specified limit.
    When summarize=True, a compact digest of each message is returned
    instead of the full content — useful for long histories.
    """

    id = "conversation_history"
    name = "Conversation History"
    description = (
        "Retrieve previous messages from a conversation session. "
        "Use this to recall what was already discussed, maintain context, "
        "or summarize conversation history for token-efficient prompts."
    )
    permission_level = PermissionLevel.USER
    parameters = [
        ParameterSpec(
            name="session_id",
            type="string",
            description="UUID of the conversation session to retrieve history for.",
            required=True,
        ),
        ParameterSpec(
            name="limit",
            type="integer",
            description="Maximum number of most-recent messages to return (1–50).",
            required=False,
            default=10,
            minimum=1,
            maximum=50,
        ),
        ParameterSpec(
            name="summarize",
            type="boolean",
            description=(
                "If true, returns a compact summary of each message (first 150 chars) "
                "instead of the full content."
            ),
            required=False,
            default=False,
        ),
    ]

    async def _run(
        self,
        params: dict[str, Any],
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> ToolResult:
        session_id_str: str = params["session_id"]
        limit: int = params["limit"]
        summarize: bool = params["summarize"]

        # Parse session UUID
        try:
            session_id = uuid.UUID(session_id_str)
        except ValueError:
            return ToolResult(
                success=False,
                output=None,
                error=f"Invalid session_id format: {session_id_str!r}",
            )

        # Verify session belongs to this user
        session_stmt = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
        session_res = await db.execute(session_stmt)
        session = session_res.scalar_one_or_none()

        if session is None:
            return ToolResult(
                success=True,
                output=None,
                metadata={"reason": "Session not found or access denied."},
            )

        # Retrieve bounded history using unified turn-preserving trimmer
        from app.services.chat_history_service import chat_history_service

        trimmed_messages = await chat_history_service.get_bounded_history_for_session(
            db=db,
            session_id=session_id,
            user_id=user_id,
            max_turns=limit,
        )

        output_messages = []
        for msg in trimmed_messages:
            content = msg.get("content", "")
            if summarize and len(content) > 150:
                content = content[:150].strip() + "…"

            entry: dict[str, Any] = {
                "role": msg.get("role", "user"),
                "content": content,
                "created_at": msg.get("created_at"),
            }
            if not summarize and msg.get("citations"):
                entry["citations"] = msg.get("citations")
            output_messages.append(entry)

        estimated_tokens = sum(
            chat_history_service.estimate_tokens(f"{m['role']}: {m['content']}")
            for m in output_messages
        )

        return ToolResult(
            success=True,
            output=output_messages,
            metadata={
                "session_id": session_id_str,
                "session_title": session.title,
                "message_count": len(output_messages),
                "estimated_tokens": estimated_tokens,
                "summarized": summarize,
            },
        )
