"""
Alembic Environment Script — Enterprise RAG AI Assistant
=========================================================
Configures the migration environment for both offline (SQL generation)
and online (live database) migration modes.

Key design decisions:
  - Uses SQLAlchemy's *async* engine with ``run_sync`` for compatibility.
  - Reads DATABASE_URL from the application's pydantic-settings so there
    is a single source of truth for the connection string.
  - All ORM models are imported so Alembic can detect schema changes via
    ``--autogenerate``.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# =============================================================================
# Alembic Config Object
# =============================================================================
# ``config`` is the Alembic ``Config`` object that grants access to
# the values in ``alembic.ini``.
config = context.config

# Interpret the alembic.ini logging configuration (if present).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# =============================================================================
# Model Registration — MUST import all models before autogenerate
# =============================================================================
# The wildcard import ensures every model class is registered with Base.metadata.
from app.db.base import Base  # noqa: E402 — must come after sys.path setup
from app.models import *  # noqa: F401,F403,E402

target_metadata = Base.metadata

# =============================================================================
# Database URL — sourced from application settings
# =============================================================================
from app.config.settings import settings  # noqa: E402

# Override alembic.ini's sqlalchemy.url with the value from pydantic-settings.
config.set_main_option("sqlalchemy.url", settings.database_url)


# =============================================================================
# Offline Mode (generate SQL without connecting to DB)
# =============================================================================

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    In this mode Alembic emits SQL to stdout instead of executing it.
    Useful for generating a migration script to review before applying.

    Usage:
        alembic upgrade head --sql > migration.sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,         # Detect column type changes
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# =============================================================================
# Online Mode (connect to DB and apply migrations)
# =============================================================================

def do_run_migrations(connection: Connection) -> None:
    """Run migrations using a synchronous connection (required by Alembic)."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode using an async engine.

    Because Alembic's core migration API is synchronous, we use
    ``run_sync`` to bridge the async engine with the sync migration runner.
    """
    connectable = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,   # Never pool connections during migrations
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


# =============================================================================
# Entry Point
# =============================================================================

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
