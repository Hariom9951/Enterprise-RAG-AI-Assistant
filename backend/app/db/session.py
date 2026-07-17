"""
Enterprise RAG AI Assistant — Database Session & Engine
=======================================================
Creates the async SQLAlchemy engine and session factory.
Provides the ``get_db()`` FastAPI dependency for per-request sessions.

Usage in endpoints:
    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db.session import get_db

    @router.get("/example")
    async def example(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(User))
        ...
"""

from collections.abc import AsyncGenerator

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import settings

# =============================================================================
# Engine
# =============================================================================

def _build_engine() -> AsyncEngine:
    """
    Construct the async SQLAlchemy engine from the configured DATABASE_URL.

    Production tuning notes:
      - ``pool_size``: Number of persistent connections in the pool.
      - ``max_overflow``: Extra connections allowed above pool_size under load.
      - ``pool_pre_ping``: Issue a lightweight SELECT 1 before each connection
        checkout to detect stale / dropped connections.
      - ``echo``: Set to True to log every SQL statement (dev only).
    """
    is_postgres = "postgresql" in settings.database_url

    engine_kwargs: dict = {
        "pool_pre_ping": True,
        "echo": settings.debug,
    }

    # Connection pooling only applies to real databases, not SQLite.
    if is_postgres:
        engine_kwargs.update(
            {
                "pool_size": 10,
                "max_overflow": 20,
                "pool_timeout": 30,
                "pool_recycle": 1800,  # Recycle connections after 30 min
            }
        )

    return create_async_engine(settings.database_url, **engine_kwargs)


# Module-level engine singleton — created once at import time.
engine: AsyncEngine = _build_engine()

# Session factory — used to create new AsyncSession instances.
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Prevent lazy-loading after commit in async context
    autoflush=False,
    autocommit=False,
)


# =============================================================================
# FastAPI Dependency
# =============================================================================

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an ``AsyncSession`` per HTTP request.

    The session is:
      - Committed automatically if the request completes without error.
      - Rolled back automatically if an exception is raised.
      - Closed in the ``finally`` block regardless of outcome.

    Example::

        @router.post("/users")
        async def create_user(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# =============================================================================
# Startup / Shutdown Helpers (called from main.py lifespan)
# =============================================================================

async def verify_database_connection() -> None:
    """
    Issue a lightweight query to confirm the database is reachable.
    Called during application startup so the service fails fast if DB is down.
    """
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
    logger.info("[OK] Database connection verified.")


async def dispose_engine() -> None:
    """
    Gracefully close all database connections in the pool.
    Called during application shutdown.
    """
    await engine.dispose()
    logger.info("[OK] Database engine disposed.")
