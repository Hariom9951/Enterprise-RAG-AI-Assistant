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
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.common import MessageResponse
from app.services.auth_service import (
    authenticate_user,
    refresh_access_token,
    register_user,
    revoke_refresh_token,
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
        "Atomic single-use token rotation is applied — the previous refresh token is "
        "consumed and invalidated immediately."
    ),
    tags=["auth"],
)
async def refresh(
    payload: RefreshRequest,
    db: DBSession,
) -> TokenResponse:
    """
    **Obtain a new access token using a refresh token.**

    - Refresh tokens are single-use (atomic token rotation).
    - Replay of an already-consumed token triggers token-theft revocation of the entire family.
    """
    return await refresh_access_token(db, payload)


# =============================================================================
# Logout
# =============================================================================


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Logout user session",
    description=(
        "Revoke the supplied refresh token and invalidate its session family server-side. "
        "Safe and idempotent against already-revoked, expired, or malformed tokens."
    ),
    tags=["auth"],
)
async def logout(
    payload: LogoutRequest,
    db: DBSession,
) -> MessageResponse:
    """
    **Logout user session and revoke refresh tokens.**

    - Marks the session's token family as revoked in PostgreSQL.
    - Subsequent refresh attempts with the token will fail.
    - Always returns 200 OK to allow clean client-side logout.
    """
    await revoke_refresh_token(db, payload)
    return MessageResponse(message="Successfully logged out.")
