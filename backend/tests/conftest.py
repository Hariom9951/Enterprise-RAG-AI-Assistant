"""
Enterprise RAG AI Assistant — Shared Test Fixtures (Phase 2)
=============================================================
Provides reusable pytest fixtures for the entire test suite.

Key design decisions:
  - Uses an in-memory SQLite database (via aiosqlite) so tests run without
    a PostgreSQL instance. This is intentional — unit/integration tests should
    be environment-agnostic.
  - Overrides the ``get_db`` FastAPI dependency so every test request uses
    the in-memory DB session rather than the production connection pool.
  - Creates tables at function scope for full isolation between tests.
  - Each test gets a fresh database — all tables recreated per test.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app as fastapi_app
from app.tasks.celery_app import celery_app

# Force Celery to execute tasks synchronously in-process during tests
# without requiring a running Redis message broker.
celery_app.conf.task_always_eager = True

# =============================================================================
# Test Database — in-memory SQLite (function scoped for isolation)
# =============================================================================

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a fresh, isolated database session for a single test.

    Creates a brand-new in-memory SQLite database per test function,
    which guarantees complete isolation — no state leaks between tests.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    # Create all tables.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

    # Drop all tables and dispose engine.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(autouse=True)
def override_worker_db(db_session: AsyncSession):
    """
    Auto-inject the test's isolated SQLite database session into background tasks
    globally for all test runs (both Task units and API integration runs).
    """
    @asynccontextmanager
    async def mock_session():
        yield db_session

    with patch("app.tasks.document_tasks.get_async_session", mock_session):
        yield


@pytest_asyncio.fixture()
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Yield an async HTTP test client that uses the in-memory test database.

    Overrides the ``get_db`` FastAPI dependency so every request made
    via this client uses ``db_session`` (the isolated test session) instead
    of the production async engine.
    """

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    # Clean up overrides after the test.
    fastapi_app.dependency_overrides.clear()


# =============================================================================
# Test Data Constants
# =============================================================================

VALID_USER: dict[str, Any] = {
    "full_name": "Test User",
    "email": "testuser@example.com",
    "password": "TestPass@123",
}

ADMIN_USER: dict[str, Any] = {
    "full_name": "Admin User",
    "email": "admin@example.com",
    "password": "AdminPass@456",
}
