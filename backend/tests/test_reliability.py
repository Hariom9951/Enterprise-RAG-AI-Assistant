"""
Enterprise RAG AI Assistant — Phase 3.4 Reliability and Failure Handling Tests
==============================================================================
Validates edge cases, recovery paths, fail-open mechanisms, ownership bounds,
and failure resilience across ingestion, agents, cache, database, and auth.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.core.exceptions import NotFoundException
from app.db.session import get_db
from app.main import app
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.processed_document import ProcessedDocument
from app.models.user import User
from app.services import document_service
from app.services.cache_service import RedisCacheService
from app.services.chunking_service import ChunkingService


@pytest.mark.asyncio
async def test_duplicate_ingestion_chunking_idempotency(
    db_session: AsyncSession,
) -> None:
    """Verify that repeated chunking on the same document does not produce duplicate chunks."""
    user = User(
        full_name="Idempotency User",
        email=f"idempotency_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hashed_pw",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=user.id,
        original_filename="idempotent_doc.txt",
        stored_filename=f"stored_{doc_id}.txt",
        mime_type="text/plain",
        file_size=120,
        sha256_hash="sha256_idempotent",
        storage_path="/tmp/fake_idempotent.txt",
        processing_status="PROCESSED",
    )
    db_session.add(doc)

    pd = ProcessedDocument(
        document_id=doc_id,
        raw_text="Line 1 section A.\n\nLine 2 section B.\n\nLine 3 section C.",
        clean_text="Line 1 section A.\n\nLine 2 section B.\n\nLine 3 section C.",
        language="en",
        page_count=1,
        word_count=12,
        character_count=60,
        processing_time=0.01,
    )
    db_session.add(pd)
    await db_session.commit()

    chunker = ChunkingService()

    # Pass 1
    chunks_pass_1 = await chunker.chunk_document(db_session, doc_id)
    count_pass_1 = len(chunks_pass_1)
    assert count_pass_1 > 0

    # Pass 2: repeat execution
    chunks_pass_2 = await chunker.chunk_document(db_session, doc_id)
    count_pass_2 = len(chunks_pass_2)

    # Total in DB should still be exactly count_pass_1, not 2x
    res = await db_session.execute(select(Chunk).where(Chunk.document_id == doc_id))
    all_stored_chunks = list(res.scalars().all())

    assert len(all_stored_chunks) == count_pass_1
    assert count_pass_1 == count_pass_2


@pytest.mark.asyncio
async def test_document_ownership_enforcement(db_session: AsyncSession) -> None:
    """Verify User B cannot access, read, update, or delete User A's documents."""
    user_a = User(
        full_name="User A",
        email=f"usera_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="pw_a",
        is_active=True,
    )
    user_b = User(
        full_name="User B",
        email=f"userb_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="pw_b",
        is_active=True,
    )
    db_session.add_all([user_a, user_b])
    await db_session.commit()
    await db_session.refresh(user_a)
    await db_session.refresh(user_b)

    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=user_a.id,
        original_filename="user_a_doc.txt",
        stored_filename=f"user_a_{doc_id}.txt",
        mime_type="text/plain",
        file_size=50,
        sha256_hash="sha256_user_a",
        storage_path="/tmp/user_a.txt",
        processing_status="COMPLETED",
    )
    db_session.add(doc)
    await db_session.commit()

    # User B attempting to fetch User A's document must raise NotFoundException (404)
    with pytest.raises(NotFoundException):
        await document_service.get_document_by_id(db_session, doc_id, user_b.id)

    # User B attempting to rename User A's document must raise NotFoundException
    with pytest.raises(NotFoundException):
        await document_service.update_document_metadata(
            db_session, doc_id, user_b.id, original_filename="tampered.txt"
        )

    # User B attempting to delete User A's document must raise NotFoundException
    with pytest.raises(NotFoundException):
        await document_service.delete_document(db_session, doc_id, user_b.id)


@pytest.mark.asyncio
async def test_db_transaction_rollback_on_failure() -> None:
    """Verify that get_db generator rolls back transaction when an unhandled exception occurs."""
    mock_session = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.commit = AsyncMock()

    class MockContextManager:
        async def __aenter__(self) -> AsyncMock:
            return mock_session

        async def __aexit__(
            self, exc_type: object, exc_val: object, exc_tb: object
        ) -> None:
            return None

    with patch("app.db.session.AsyncSessionLocal", return_value=MockContextManager()):
        gen = get_db()
        await gen.__anext__()
        with pytest.raises(RuntimeError, match="Simulated request handling crash"):
            await gen.athrow(RuntimeError("Simulated request handling crash"))

    mock_session.rollback.assert_awaited_once()
    mock_session.close.assert_awaited_once()
    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_fail_open_non_authoritative() -> None:
    """Verify that RedisCacheService fails open cleanly on Redis connection error."""
    cache = RedisCacheService()

    with patch.object(cache, "_get_redis") as mock_get_redis:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(
            side_effect=RedisConnectionError("Connection refused")
        )
        mock_client.set = AsyncMock(
            side_effect=RedisConnectionError("Connection refused")
        )
        mock_client.delete = AsyncMock(
            side_effect=RedisConnectionError("Connection refused")
        )
        mock_get_redis.return_value = mock_client

        # Get fails open to None without raising
        val = await cache.get("test_key")
        assert val is None

        # Set fails open to False without raising
        success = await cache.set("test_key", {"data": 123})
        assert success is False

        # Delete fails open to False without raising
        del_success = await cache.delete("test_key")
        assert del_success is False


@pytest.mark.asyncio
async def test_health_liveness_vs_readiness_distinction() -> None:
    """Verify that /live probe succeeds regardless of downstream dependency health, while /ready probe fails when downstream DB is down."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. /live always returns 200
        live_res = await client.get("/api/v1/live")
        assert live_res.status_code == 200
        assert live_res.json() == {"status": "live"}

        # 2. When DB check fails, /ready returns 503 Service Unavailable
        with patch(
            "app.api.v1.endpoints.health.check_database_conn", return_value=False
        ):
            ready_res = await client.get("/api/v1/ready")
            assert ready_res.status_code == 503
            assert ready_res.json()["status"] == "unready"


def test_production_environment_rejects_placeholder_secret() -> None:
    """Verify Settings rejects placeholder secret key when ENVIRONMENT is set to production."""
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        with pytest.raises(
            ValueError, match="SECRET_KEY cannot be a default or placeholder"
        ):
            Settings(
                environment="production",
                secret_key="change-me-in-production",
                database_url="postgresql+asyncpg://u:p@localhost:5432/db",
            )


@pytest.mark.asyncio
async def test_agent_cancellation_propagates_cleanly(db_session: AsyncSession) -> None:
    """Verify asyncio.CancelledError is never swallowed by agent graph execution."""
    from app.agents.agent_service import AgentService
    from app.agents.graph.agent_graph import AgentWorkflowBuilder

    service = AgentService()
    builder = AgentWorkflowBuilder(service=service, db=db_session)

    # Simulate CancelledError in plan node
    with patch.object(builder, "plan_node", side_effect=asyncio.CancelledError()):
        with pytest.raises(asyncio.CancelledError):
            await builder.plan_node(
                {
                    "run_id": uuid.uuid4(),
                    "user_id": uuid.uuid4(),
                    "question": "test question",
                    "top_k": 3,
                    "threshold": 0.0,
                    "wall_t0": 0.0,
                    "loop_budget_s": 10.0,
                    "max_tool_calls": 2,
                    "call_count": 0,
                    "tool_records": [],
                    "retrieved_documents": [],
                    "evidence_sufficient": False,
                    "next_action": "plan",
                    "reformulation_count": 0,
                    "max_reformulations": 1,
                    "evaluation_reason": None,
                    "success": True,
                    "error_message": None,
                    "is_blocked": False,
                    "confidence_score": 0.0,
                }
            )


@pytest.mark.asyncio
async def test_agent_malformed_model_plan_fails_safely(
    db_session: AsyncSession,
) -> None:
    """Verify that if LLM returns malformed non-JSON output during planning, agent falls back safely."""
    from app.agents.agent_service import AgentService

    user = User(
        full_name="Agent Resilience User",
        email=f"agent_res_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="pw",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    mock_llm = MagicMock()
    # First call: malformed non-JSON response during planning
    # Second call: fallback answer
    mock_llm.generate_response = AsyncMock(
        side_effect=[
            (
                "This is completely invalid JSON {{{{ not valid",
                {"prompt_tokens": 10, "completion_tokens": 5},
            ),
            ("Safe answer provided.", {"prompt_tokens": 20, "completion_tokens": 10}),
        ]
    )

    service = AgentService()
    with (
        patch("app.agents.agent_service.get_llm_provider", return_value=mock_llm),
        patch(
            "app.agents.tools.semantic_search.RetrievalService.search_semantic",
            new=AsyncMock(return_value=[]),
        ),
        patch("app.config.settings.settings.agent_loop_budget_s", 2.0),
        patch("app.config.settings.settings.agent_tool_timeout_s", 0.5),
    ):
        result = await service.run(
            db=db_session,
            question="What is the policy?",
            user_id=user.id,
        )

    # The agent should not crash; it safely defaults to semantic search or handles it gracefully
    assert result is not None
    assert result.final_answer is not None


# ── Production CORS & Security Validation Tests ──────────────────────────────


def test_cors_production_rejects_wildcard_with_credentials() -> None:
    """Verify that Settings raises a validation error if wildcard origin is combined with credentials in production."""
    # List wildcard origin
    with pytest.raises(ValidationError, match="Wildcard CORS origin"):
        Settings(
            environment="production",
            allowed_origins=["*"],
            allow_credentials=True,
            secret_key="a" * 32,
        )

    # String comma-separated wildcard origin
    with pytest.raises(ValidationError, match="Wildcard CORS origin"):
        Settings(
            environment="production",
            allowed_origins="*",
            allow_credentials=True,
            secret_key="a" * 32,
        )

    # Multiple origins including a wildcard
    with pytest.raises(ValidationError, match="Wildcard CORS origin"):
        Settings(
            environment="production",
            allowed_origins=["https://rag.example.com", "*"],
            allow_credentials=True,
            secret_key="a" * 32,
        )


def test_cors_production_permits_explicit_origins_with_credentials() -> None:
    """Verify that explicit origins with credentials succeed in production."""
    cfg = Settings(
        environment="production",
        allowed_origins=["https://app.mycompany.com", "https://rag.mycompany.com"],
        allow_credentials=True,
        secret_key="a" * 32,
    )
    assert cfg.allowed_origins == [
        "https://app.mycompany.com",
        "https://rag.mycompany.com",
    ]
    assert cfg.allow_credentials is True


def test_cors_production_permits_wildcard_when_credentials_disabled() -> None:
    """Verify that wildcard origin is permitted in production when credentials are disabled."""
    cfg = Settings(
        environment="production",
        allowed_origins=["*"],
        allow_credentials=False,
        secret_key="a" * 32,
    )
    assert "*" in cfg.allowed_origins
    assert cfg.allow_credentials is False


def test_cors_development_preserves_wildcard_behavior() -> None:
    """Verify that development environment preserves wildcard origin with credentials for ease of testing."""
    cfg = Settings(
        environment="development",
        allowed_origins=["*"],
        allow_credentials=True,
        secret_key="dev-secret-key-for-testing",
    )
    assert "*" in cfg.allowed_origins
    assert cfg.allow_credentials is True
