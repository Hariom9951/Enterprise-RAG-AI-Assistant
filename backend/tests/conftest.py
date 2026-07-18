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

import os as _os
import tempfile as _tempfile
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
# Test Database — file-based SQLite (function scoped for isolation)
# =============================================================================


_tmp_dir = _tempfile.gettempdir()


@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a fresh, isolated database session for a single test.

    Uses a file-based SQLite database (rather than in-memory) so that
    background tasks running in helper threads can connect to the same
    physical file independently without sharing the same asyncio event loop.
    """
    # Create a unique DB file per test to guarantee isolation
    db_fd, db_path = _tempfile.mkstemp(suffix=".db", dir=_tmp_dir)
    _os.close(db_fd)
    db_url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(
        db_url,
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

    # Drop all tables, dispose engine, and remove the temp file.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    _os.unlink(db_path)


@pytest.fixture(autouse=True)
def override_worker_db(db_session: AsyncSession):
    """
    Auto-inject the test's isolated SQLite database into background tasks.

    Creates an independent session factory pointing to the same DB file as
    the test's db_session. The task gets its own session, but can see state
    committed by the test and vice versa (committed changes are visible across
    connections on the same file-based SQLite).
    """
    # Extract the database URL from the existing session's engine bind
    test_engine = db_session.get_bind()
    db_url = str(test_engine.url)

    from sqlalchemy.ext.asyncio import async_sessionmaker as _asm
    from sqlalchemy.ext.asyncio import create_async_engine as _cae

    @asynccontextmanager
    async def mock_session():
        # Create a short-lived engine + session for each task call
        task_engine = _cae(
            db_url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
        task_factory = _asm(
            bind=task_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
        async with task_factory() as session:
            yield session
        await task_engine.dispose()

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
