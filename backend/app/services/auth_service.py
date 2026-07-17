"""
Enterprise RAG AI Assistant — Authentication Service
=====================================================
Business logic for the authentication flow:
  - User registration (validate uniqueness, hash password, persist)
  - User login (verify credentials, issue tokens)
  - Token refresh (validate refresh token, issue new access token)

This service is intentionally thin — it delegates DB operations to
``user_service`` and crypto operations to ``core.security``.
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.core.exceptions import ConflictException, UnauthorizedException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.user_service import create_user, get_user_by_email, get_user_by_id

# =============================================================================
# Registration
# =============================================================================

async def register_user(db: AsyncSession, payload: RegisterRequest) -> User:
    """
    Register a new user account.

    Steps:
      1. Normalise and check for existing email.
      2. Hash the password with bcrypt.
      3. Persist the user record.

    Args:
        db:      Active async database session.
        payload: Validated registration request data.

    Returns:
        The newly created ``User`` ORM instance.

    Raises:
        ConflictException: If the email address is already registered.
    """
    # ── 1. Check for duplicate email ──────────────────────────────────────────
    existing = await get_user_by_email(db, payload.email)
    if existing is not None:
        raise ConflictException(
            message="An account with this email address already exists.",
            detail={"field": "email"},
        )

    # ── 2. Hash the password ──────────────────────────────────────────────────
    hashed = hash_password(payload.password)

    # ── 3. Create and persist the user ───────────────────────────────────────
    user = await create_user(
        db,
        full_name=payload.full_name,
        email=payload.email,
        hashed_password=hashed,
    )

    logger.info(
        "User registration successful",
        extra={"user_id": str(user.id), "email": user.email},
    )
    return user


# =============================================================================
# Login
# =============================================================================

async def authenticate_user(db: AsyncSession, payload: LoginRequest) -> TokenResponse:
    """
    Authenticate a user with email and password, returning a token pair.

    The same generic error message is returned whether the email is unknown
    or the password is incorrect — this prevents user enumeration attacks.

    Args:
        db:      Active async database session.
        payload: Validated login request data.

    Returns:
        A ``TokenResponse`` containing access and refresh JWTs.

    Raises:
        UnauthorizedException: If credentials are invalid or account is inactive.
    """
    _INVALID_CREDENTIALS = "Invalid email address or password."

    # ── 1. Look up user ───────────────────────────────────────────────────────
    user = await get_user_by_email(db, payload.email)
    if user is None:
        logger.debug(f"Login attempt for unknown email: {payload.email!r}")
        raise UnauthorizedException(message=_INVALID_CREDENTIALS)

    # ── 2. Verify password ────────────────────────────────────────────────────
    if not verify_password(payload.password, user.hashed_password):
        logger.warning(
            "Failed login attempt — wrong password",
            extra={"email": payload.email, "user_id": str(user.id)},
        )
        raise UnauthorizedException(message=_INVALID_CREDENTIALS)

    # ── 3. Check account is active ────────────────────────────────────────────
    if not user.is_active:
        raise UnauthorizedException(
            message="Your account has been disabled. Please contact support.",
        )

    # ── 4. Issue token pair ───────────────────────────────────────────────────
    user_id_str = str(user.id)
    access_token = create_access_token(
        subject=user_id_str,
        extra_claims={"role": user.role.value, "email": user.email},
    )
    refresh_token = create_refresh_token(subject=user_id_str)

    logger.info(
        "User login successful",
        extra={"user_id": user_id_str, "email": user.email},
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


# =============================================================================
# Token Refresh
# =============================================================================

async def refresh_access_token(
    db: AsyncSession,
    payload: RefreshRequest,
) -> TokenResponse:
    """
    Validate a refresh token and issue a new access token.

    Args:
        db:      Active async database session.
        payload: Contains the refresh token string.

    Returns:
        A new ``TokenResponse`` with a fresh access token.
        A new refresh token is also issued to implement token rotation.

    Raises:
        UnauthorizedException: If the refresh token is invalid/expired,
                               or the associated user no longer exists.
    """
    # ── 1. Decode and validate the refresh token ──────────────────────────────
    token_payload = decode_token(payload.refresh_token, expected_type="refresh")
    user_id_str: str = token_payload["sub"]

    # ── 2. Load the user ──────────────────────────────────────────────────────
    user = await get_user_by_id(db, user_id_str)
    if user is None or not user.is_active:
        raise UnauthorizedException(
            message="User associated with this token no longer exists or is inactive.",
        )

    # ── 3. Issue a new token pair (token rotation) ────────────────────────────
    new_access = create_access_token(
        subject=user_id_str,
        extra_claims={"role": user.role.value, "email": user.email},
    )
    new_refresh = create_refresh_token(subject=user_id_str)

    logger.info("Token refreshed", extra={"user_id": user_id_str})

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )
