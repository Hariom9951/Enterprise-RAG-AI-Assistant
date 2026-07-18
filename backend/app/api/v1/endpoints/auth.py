"""
Enterprise RAG AI Assistant — Auth Endpoints
============================================
Handles user registration, login, and token refresh.

Routes:
    POST /auth/register  — Create a new user account
    POST /auth/login     — Authenticate and receive JWT token pair
    POST /auth/refresh   — Exchange refresh token for new access token
"""

from fastapi import APIRouter, status

from app.dependencies import DBSession
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import (
    authenticate_user,
    refresh_access_token,
    register_user,
)

router = APIRouter()


# =============================================================================
# Register
# =============================================================================


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Create a new user account. "
        "Returns the created user profile. "
        "Passwords are never stored in plain text — bcrypt hashing is applied automatically."
    ),
    tags=["auth"],
)
async def register(
    payload: RegisterRequest,
    db: DBSession,
) -> UserResponse:
    """
    **Register a new user account.**

    - Email must be unique.
    - Password must meet the strength policy (8+ chars, uppercase, digit, special char).
    - Returns the user profile on success (no tokens — user must log in separately).
    """
    user = await register_user(db, payload)
    return UserResponse.model_validate(user)


# =============================================================================
# Login
# =============================================================================


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Login with email and password",
    description=(
        "Authenticate with email and password. "
        "Returns a JWT access token (short-lived) and a refresh token (long-lived). "
        "Use the access token in the ``Authorization: Bearer <token>`` header."
    ),
    tags=["auth"],
)
async def login(
    payload: LoginRequest,
    db: DBSession,
) -> TokenResponse:
    """
    **Authenticate and receive a JWT token pair.**

    - Returns the same error for unknown email or wrong password (anti-enumeration).
    - Inactive accounts receive a distinct error message.
    """
    return await authenticate_user(db, payload)


# =============================================================================
# Refresh
# =============================================================================


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description=(
        "Exchange a valid refresh token for a new access token. "
        "Token rotation is applied — a new refresh token is also issued, "
        "invalidating the previous one on next use."
    ),
    tags=["auth"],
)
async def refresh(
    payload: RefreshRequest,
    db: DBSession,
) -> TokenResponse:
    """
    **Obtain a new access token using a refresh token.**

    - Refresh tokens are long-lived but single-use (token rotation).
    - Phase 3 will add a Redis-backed blocklist for revocation.
    """
    return await refresh_access_token(db, payload)
