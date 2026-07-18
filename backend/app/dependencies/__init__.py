"""
Enterprise RAG AI Assistant — Dependency Injection Registry
============================================================
FastAPI reusable dependencies resolved automatically per-request.

Phase 2 implements:
  - get_db()                — async SQLAlchemy session
  - get_current_user()      — decode JWT + load user from DB
  - get_current_active_user() — assert account is active
  - admin_required()        — assert role == ADMIN

Usage in endpoints:
    from app.dependencies import get_current_active_user

    @router.get("/protected")
    async def protected(user: User = Depends(get_current_active_user)):
        return {"id": user.id, "email": user.email}
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import decode_token
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.services.user_service import get_user_by_id

# =============================================================================
# Bearer Token Scheme
# =============================================================================

# ``auto_error=False`` lets us provide our own structured error response
# instead of FastAPI's default plain-text 403.
_bearer_scheme = HTTPBearer(auto_error=False)

BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(_bearer_scheme),
]

# Convenience type aliases for clean endpoint signatures.
DBSession = Annotated[AsyncSession, Depends(get_db)]


# =============================================================================
# Core Auth Dependencies
# =============================================================================


async def get_current_user(
    credentials: BearerCredentials,
    db: DBSession,
) -> User:
    """
    Decode the JWT from the Authorization header and return the authenticated user.

    Steps:
      1. Extract Bearer token from the ``Authorization`` header.
      2. Decode and validate the JWT (signature + expiry + type).
      3. Load the user from the database by the ``sub`` (UUID) claim.

    Raises:
        UnauthorizedException: If the token is missing, invalid, or the
                               user no longer exists in the database.
    """
    if credentials is None:
        raise UnauthorizedException(
            message="Authentication required. Please provide a Bearer token.",
            detail={"hint": "Set the Authorization header to 'Bearer <your_token>'."},
        )

    # Decode and validate the JWT.
    payload = decode_token(credentials.credentials, expected_type="access")

    # Load the user from the database.
    try:
        user_id_str = payload["sub"]
    except KeyError as exc:
        raise UnauthorizedException(
            message="Token contains an invalid user identifier."
        ) from exc

    user = await get_user_by_id(db, user_id_str)
    if user is None:
        raise UnauthorizedException(
            message="The user associated with this token no longer exists.",
        )

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Assert the authenticated user's account is active.

    Raises:
        ForbiddenException: If the account has been suspended (``is_active=False``).
    """
    if not current_user.is_active:
        raise ForbiddenException(
            message="Your account has been suspended. Contact support for assistance.",
        )
    return current_user


async def admin_required(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """
    Assert the authenticated user holds the ADMIN role.

    Raises:
        ForbiddenException: If the user's role is not ADMIN.
    """
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenException(
            message="You do not have permission to access this resource.",
            detail={
                "required_role": UserRole.ADMIN.value,
                "your_role": current_user.role.value,
            },
        )
    return current_user


# =============================================================================
# Convenience Type Aliases (for clean endpoint signatures)
# =============================================================================

CurrentUser = Annotated[User, Depends(get_current_user)]
ActiveUser = Annotated[User, Depends(get_current_active_user)]
AdminUser = Annotated[User, Depends(admin_required)]


__all__ = [
    "get_db",
    "get_current_user",
    "get_current_active_user",
    "admin_required",
    "DBSession",
    "CurrentUser",
    "ActiveUser",
    "AdminUser",
]
