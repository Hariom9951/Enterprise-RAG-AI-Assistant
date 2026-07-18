"""
Enterprise RAG AI Assistant — Chat Service Layer
==================================================
Manages chat session lifecycle, memory budgeting, and token-streaming loops.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import tiktoken
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.chat_models import ChatMessage, ChatSession
from app.services.llm_providers import get_llm_provider
from app.services.rag_service import RAGService
from app.services.retrieval_service import RetrievalService


class ChatService:
    """
    Service layer coordinating conversational RAG state and streaming answers.
    """

    def __init__(self) -> None:
        self.retrieval_service = RetrievalService()
        self.rag_service = RAGService()
        try:
            self.tokenizer = tiktoken.get_encoding(settings.tokenizer_name)
        except Exception:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken encoder."""
        return len(self.tokenizer.encode(text))

    async def create_session(
        self, db: AsyncSession, user_id: uuid.UUID, title: str | None = None
    ) -> ChatSession:
        """
        Initialize a new conversational workspace session.
        """
        session = ChatSession(
            id=uuid.uuid4(),
            user_id=user_id,
            title=title or "New Conversation",
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    async def get_session(
        self, db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> ChatSession | None:
        """
        Retrieve a chat session verify ownership.
        """
        stmt = select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == user_id
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_sessions(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> list[ChatSession]:
        """
        Fetch all chat sessions owned by the user.
        """
        stmt = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def delete_session(
        self, db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """
        Delete session and cascading messages logs.
        """
        session = await self.get_session(db, session_id, user_id)
        if not session:
            return False
        await db.delete(session)
        await db.commit()
        return True

    async def rename_session(
        self, db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID, title: str
    ) -> ChatSession | None:
        """
        Rename chat session title.
        """
        session = await self.get_session(db, session_id, user_id)
        if not session:
            return None
        session.title = title
        await db.commit()
        await db.refresh(session)
        return session

    async def add_message(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
        tokens: dict[str, int] | None = None,
        latency: dict[str, int] | None = None,
        created_at: datetime | None = None,
    ) -> ChatMessage:
        """
        Create and persist a ChatMessage object inside the session.
        """
        msg = ChatMessage(
            id=uuid.uuid4(),
            session_id=session_id,
            role=role,
            content=content,
            citations=citations,
            tokens=tokens,
            latency=latency,
        )
        if created_at is not None:
            msg.created_at = created_at
        db.add(msg)
        # Update updated_at of the session
        await db.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(updated_at=func.now())
        )
        await db.commit()
        await db.refresh(msg)
        return msg

    async def execute_chat_stream(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        question: str,
        provider_name: str | None = None,
        model_name: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        use_reranker: bool = True,
        threshold: float = 0.0,
        top_k: int = 5,
    ) -> AsyncGenerator[str, None]:
        """
        SSE Generator executing contextual grounding retrieval and streaming the LLM completion tokens.
        """
        start_total = time.perf_counter()

        # 1. Ownership & existence check
        session = await self.get_session(db, session_id, user_id)
        if not session:
            yield "event: error\ndata: Session not found or unauthorized\n\n"
            return

        # Auto rename title on first message
        if session.title == "New Conversation":
            truncated_title = question[:40] + "..." if len(question) > 40 else question
            session.title = truncated_title
            await db.commit()

        # 2. Persist User Message
        user_msg = await self.add_message(db, session_id, "user", question)

        # 3. Context Retrieval
        start_retrieval = time.perf_counter()
        try:
            candidates = await self.retrieval_service.search_semantic(
                db=db,
                query_text=question,
                user_id=user_id,
                top_k=top_k * 2 if use_reranker else top_k,
                threshold=threshold or 0.0,
            )
        except Exception as e:
            yield f"event: error\ndata: Retrieval failed: {e!s}\n\n"
            return

        # Apply reranking
        if use_reranker and candidates:
            candidates = self.rag_service.reranker.rerank(question, candidates)[:top_k]

        # Token budgeted context assembly
        context_str, included_chunks = self.rag_service._assemble_context(
            candidates, max_tokens=settings.rag_max_context_tokens
        )
        retrieval_ms = int((time.perf_counter() - start_retrieval) * 1000)

        # Format citations payload list
        citations = []
        for _idx, (chunk, doc, score, c_idx) in enumerate(included_chunks):
            citations.append(
                {
                    "citation_index": c_idx,
                    "chunk_id": str(chunk.id),
                    "document_id": str(doc.id),
                    "document_title": doc.original_filename,
                    "page_number": chunk.page_number,
                    "section_title": chunk.section_title,
                    "score": float(score),
                    "text": chunk.text,
                }
            )

        # Yield citations first
        import json

        yield f"event: citations\ndata: {json.dumps(citations)}\n\n"

        # 4. Fetch Message history for context memory budgeting
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id, ChatMessage.id != user_msg.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(settings.chat_max_history)
        )
        history_res = await db.execute(stmt)
        past_messages = list(history_res.scalars().all())
        past_messages.reverse()  # chronological order

        # Assemble and budget history string
        # Limit token count of history segment dynamically
        history_items: list[str] = []
        history_tokens = 0
        max_history_tokens = (
            settings.chat_max_tokens
            - self._count_tokens(question)
            - self._count_tokens(context_str)
            - 200
        )

        for msg in reversed(past_messages):
            msg_str = f"{msg.role.capitalize()}: {msg.content}\n"
            msg_tok = self._count_tokens(msg_str)
            if history_tokens + msg_tok > max_history_tokens:
                break
            history_items.insert(0, msg_str)
            history_tokens += msg_tok

        history_str = "".join(history_items)

        # 5. Prompt assembly
        system_prompt = (
            "You are a helpful, professional Enterprise AI assistant. "
            "Use the provided context passages below to answer the user's question, taking the conversation history into account. "
            "Follow these strict directives:\n"
            "1. Base your answer ONLY on the provided context passages. Do not use external knowledge.\n"
            "2. If the context does not contain the answer, state: 'I am sorry, but I do not have that information in my documents.'\n"
            "3. Cite your sources using bracketed indices (e.g., [1], [2]) at the end of statements where the facts are used.\n\n"
            f"--- Context ---\n{context_str}"
        )

        user_prompt = ""
        if history_str:
            user_prompt += f"--- Conversation History ---\n{history_str}\n"
        user_prompt += f"--- Current Question ---\nUser: {question}"

        # 6. Stream LLM answer
        prov_name = provider_name or settings.llm_provider
        mod_name = model_name or (
            "gemini-1.5-flash"
            if prov_name == "gemini"
            else "gpt-4o-mini"
            if prov_name == "openai"
            else "llama3"
        )
        temp = temperature if temperature is not None else settings.rag_temperature
        max_out = (
            max_tokens if max_tokens is not None else settings.rag_max_output_tokens
        )

        start_llm = time.perf_counter()
        full_answer_list = []
        try:
            provider = get_llm_provider(prov_name, model=mod_name)
            async for token in provider.generate_response_stream(
                system_prompt, user_prompt, temperature=temp, max_tokens=max_out
            ):
                full_answer_list.append(token)
                # Escaping token strings to be safe for SSE data: tags
                yield f"event: token\ndata: {json.dumps(token)}\n\n"
        except Exception as e:
            yield f"event: error\ndata: LLM Streaming generation failed: {e!s}\n\n"
            return

        llm_ms = int((time.perf_counter() - start_llm) * 1000)
        full_answer = "".join(full_answer_list)

        # 7. Aggregate Token Billing & latency details and persist assistant message
        prompt_tok = self._count_tokens(system_prompt) + self._count_tokens(user_prompt)
        comp_tok = self._count_tokens(full_answer)
        tokens_log = {
            "prompt_tokens": prompt_tok,
            "completion_tokens": comp_tok,
            "total_tokens": prompt_tok + comp_tok,
        }
        total_ms = int((time.perf_counter() - start_total) * 1000)
        latency_log = {
            "total_ms": total_ms,
            "retrieval_ms": retrieval_ms,
            "llm_ms": llm_ms,
        }

        asst_msg = await self.add_message(
            db,
            session_id,
            "assistant",
            full_answer,
            citations=citations,
            tokens=tokens_log,
            latency=latency_log,
        )

        done_payload = {
            "message_id": str(asst_msg.id),
            "session_id": str(session_id),
            "latency": latency_log,
            "tokens": tokens_log,
        }
        yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"
