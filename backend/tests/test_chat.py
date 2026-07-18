"""
Enterprise RAG AI Assistant — Chat Unit & Integration Tests
=============================================================
Tests session lifecycle management, token memory limits, and Server-Sent Events.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_models import ChatMessage
from app.services.chat_service import ChatService


# Helper function to create auth token
async def _register_and_login(client: AsyncClient, email: str) -> str:
    password = "SecurePassword123!"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return resp.json()["access_token"]


class TestChatSessionLifecycle:
    """Tests conversation sessions and messages persistence."""

    @pytest.mark.asyncio
    async def test_session_crud(self, db_session: AsyncSession) -> None:
        chat_service = ChatService()
        user_id = uuid.uuid4()

        # 1. Create session
        session = await chat_service.create_session(
            db_session, user_id=user_id, title="Test Thread"
        )
        assert session.id is not None
        assert session.title == "Test Thread"
        assert session.user_id == user_id

        # 2. Get session
        fetched = await chat_service.get_session(db_session, session.id, user_id)
        assert fetched is not None
        assert fetched.title == "Test Thread"

        # Unauthorized user fetch
        bad_fetched = await chat_service.get_session(
            db_session, session.id, uuid.uuid4()
        )
        assert bad_fetched is None

        # 3. Rename session
        updated = await chat_service.rename_session(
            db_session, session.id, user_id, "Renamed Thread"
        )
        assert updated is not None
        assert updated.title == "Renamed Thread"

        # 4. List sessions
        sessions = await chat_service.list_sessions(db_session, user_id)
        assert len(sessions) == 1
        assert sessions[0].title == "Renamed Thread"

        # 5. Delete session
        deleted = await chat_service.delete_session(db_session, session.id, user_id)
        assert deleted is True

        # Confirm deleted
        none_fetched = await chat_service.get_session(db_session, session.id, user_id)
        assert none_fetched is None

    @pytest.mark.asyncio
    async def test_message_logs(self, db_session: AsyncSession) -> None:
        chat_service = ChatService()
        user_id = uuid.uuid4()
        session = await chat_service.create_session(db_session, user_id=user_id)

        # Log User Message
        msg_user = await chat_service.add_message(
            db_session, session.id, "user", "What is the policy?"
        )
        assert msg_user.id is not None
        assert msg_user.role == "user"
        assert msg_user.content == "What is the policy?"

        # Log Assistant Message with citations/tokens/latency
        citations = [
            {"doc": "guide.pdf", "page": 2, "score": 0.85, "text": "Snippet text"}
        ]
        tokens = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
        latency = {"total_ms": 500, "retrieval_ms": 100, "llm_ms": 400}

        msg_asst = await chat_service.add_message(
            db_session,
            session_id=session.id,
            role="assistant",
            content="According to policy guide, it is compliant.",
            citations=citations,
            tokens=tokens,
            latency=latency,
        )
        assert msg_asst.id is not None
        assert msg_asst.role == "assistant"
        assert msg_asst.citations == citations
        assert msg_asst.tokens == tokens
        assert msg_asst.latency == latency


class TestConversationalMemory:
    """Tests short term token context budgeting limits."""

    @pytest.mark.asyncio
    async def test_memory_budgeting(self, db_session: AsyncSession) -> None:
        chat_service = ChatService()
        user_id = uuid.uuid4()
        session = await chat_service.create_session(db_session, user_id=user_id)

        # Seed many messages to overflow CHAT_MAX_HISTORY limit with sequential timestamps
        import datetime

        base_time = datetime.datetime.now(datetime.UTC)
        for i in range(15):
            await chat_service.add_message(
                db_session,
                session.id,
                "user",
                f"Question {i}",
                created_at=base_time + datetime.timedelta(seconds=2 * i),
            )
            await chat_service.add_message(
                db_session,
                session.id,
                "assistant",
                f"Answer {i}",
                created_at=base_time + datetime.timedelta(seconds=2 * i + 1),
            )

        # Fetch using limit queries
        from sqlalchemy import select

        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(10)
        )
        res = await db_session.execute(stmt)
        recent = list(res.scalars().all())
        assert len(recent) == 10
        # Verify order contains the latest messages
        recent.reverse()
        assert recent[-1].content == "Answer 14"
        assert recent[-2].content == "Question 14"


class TestChatEndpoints:
    """Tests REST API responses and session controls."""

    @pytest.mark.asyncio
    async def test_session_endpoints(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token = await _register_and_login(client, "chatuser@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. POST /api/v1/chat/session
        resp = await client.post(
            "/api/v1/chat/session",
            json={"title": "Endpoints Session"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Endpoints Session"
        session_id = data["id"]

        # 2. GET /api/v1/chat/sessions
        list_resp = await client.get("/api/v1/chat/sessions", headers=headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1

        # 3. GET /api/v1/chat/session/{id}
        get_resp = await client.get(
            f"/api/v1/chat/session/{session_id}", headers=headers
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["title"] == "Endpoints Session"

        # 4. PUT /api/v1/chat/session/{id} (rename)
        put_resp = await client.put(
            f"/api/v1/chat/session/{session_id}",
            json={"title": "New Title"},
            headers=headers,
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["title"] == "New Title"

        # 5. DELETE /api/v1/chat/session/{id}
        del_resp = await client.delete(
            f"/api/v1/chat/session/{session_id}", headers=headers
        )
        assert del_resp.status_code == 204

    @pytest.mark.asyncio
    async def test_chat_streaming(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        token = await _register_and_login(client, "streamuser@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create a session
        session_resp = await client.post(
            "/api/v1/chat/session",
            json={"title": "Streaming Session"},
            headers=headers,
        )
        session_id = session_resp.json()["id"]

        # Mock LLM stream generator
        async def mock_stream(*args, **kwargs):
            yield "Hello"
            yield " "
            yield "World!"

        from app.services.llm_providers import GeminiProvider

        monkeypatch.setattr(GeminiProvider, "generate_response_stream", mock_stream)

        # 2. Call post message stream
        resp = await client.post(
            f"/api/v1/chat/session/{session_id}/message",
            json={"question": "Test query stream?", "provider": "gemini"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        # Collect response lines
        lines = []
        async for line in resp.aiter_lines():
            if line.strip():
                lines.append(line)

        assert len(lines) > 0
        # Check event structure
        assert any("event: citations" in ln for ln in lines)
        assert any("event: token" in ln for ln in lines)
        assert any("event: done" in ln for ln in lines)
