"""
Enterprise RAG AI Assistant — User Service
==========================================
Data-access layer for user records.
Provides async functions for querying and creating users.

All database interaction is done here — endpoint handlers and auth services
call these functions instead of writing raw queries.
"""

from __future__ import annotations

import uuid

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID | str) -> User | None:
    """
    Retrieve a user by their UUID primary key.

    Accepts both ``uuid.UUID`` objects and string representations
    for cross-database compatibility (PostgreSQL uses UUID, SQLite uses String).

    Args:
        db:      Active database session.
        user_id: UUID of the user to retrieve (as UUID object or string).

    Returns:
        The ``User`` ORM instance, or ``None`` if not found.
    """
    uuid_obj = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
    result = await db.execute(select(User).where(User.id == uuid_obj))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """
    Retrieve a user by their email address (case-insensitive).

    Args:
        db:    Active database session.
        email: Email address to search for.

    Returns:
        The ``User`` ORM instance, or ``None`` if not found.
    """
    result = await db.execute(
        select(User).where(User.email == email.lower().strip())
    )
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    *,
    full_name: str,
    email: str,
    hashed_password: str,
) -> User:
    """
    Persist a new user record to the database.

    Args:
        db:              Active database session.
        full_name:       User's display name.
        email:           Unique email address (normalised to lowercase).
        hashed_password: bcrypt hash of the user's password.

    Returns:
        The newly created and persisted ``User`` instance.

    Note:
        The session is NOT committed here — the caller (typically ``get_db``
        via FastAPI DI) handles the commit so the session can be rolled back
        if a subsequent operation in the same request fails.
    """
    user = User(
        full_name=full_name.strip(),
        email=email.lower().strip(),
        hashed_password=hashed_password,
        is_verified=True,   # Phase 5: set False and send verification email
    )
    db.add(user)
    await db.flush()   # Assigns the generated UUID without committing
    await db.refresh(user)

    logger.info(
        "New user created",
        extra={"user_id": str(user.id), "email": user.email},
    )
    return user
