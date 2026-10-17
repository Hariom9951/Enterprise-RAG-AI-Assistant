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

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import select, update
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
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.token_revocation_service import token_revocation_service
from app.services.user_service import create_user, get_user_by_email, get_user_by_id


def _is_expired(expires_at: datetime) -> bool:
    """Check if an expiration datetime has passed, supporting both offset-aware and naive datetimes."""
    now = datetime.now(UTC)
    if expires_at.tzinfo is None:
        return expires_at < now.replace(tzinfo=None)
    return expires_at < now


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
        extra={"log_type": "audit", "user_id": str(user.id), "email": user.email},
    )
    return user


# =============================================================================
# Login
# =============================================================================


async def authenticate_user(db: AsyncSession, payload: LoginRequest) -> TokenResponse:
    """
    Authenticate a user with email and password, returning a token pair.

    Persists the newly issued refresh token in PostgreSQL for durable lifecycle
    tracking, replay detection, and revocation.

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

    # ── 4. Issue token pair with durable tracking ─────────────────────────────
    user_id_str = str(user.id)
    family_id = uuid.uuid4()
    access_token = create_access_token(
        subject=user_id_str,
        family_id=family_id,
        extra_claims={"role": user.role.value, "email": user.email},
    )

    new_jti = str(uuid.uuid4())
    refresh_token = create_refresh_token(subject=user_id_str, jti=new_jti)
    token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
    now_utc = datetime.now(UTC)
    expires_at = now_utc + timedelta(days=settings.refresh_token_expire_days)

    user_uuid = user.id if isinstance(user.id, uuid.UUID) else uuid.UUID(str(user.id))

    token_record = RefreshToken(
        id=uuid.uuid4(),
        user_id=user_uuid,
        token_hash=token_hash,
        jti=new_jti,
        family_id=family_id,
        expires_at=expires_at,
        is_revoked=False,
        is_consumed=False,
    )
    db.add(token_record)
    await db.commit()

    logger.info(
        "User login successful",
        extra={
            "log_type": "audit",
            "user_id": user_id_str,
            "email": user.email,
            "family_id": str(family_id),
        },
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


# =============================================================================
# Token Refresh (Atomic Single-Use Rotation & Theft Detection)
# =============================================================================


async def refresh_access_token(
    db: AsyncSession,
    payload: RefreshRequest,
) -> TokenResponse:
    """
    Validate a refresh token and perform atomic single-use rotation.

    Security guarantees:
      1. Validates signature, expiry, type, sub, and jti claims.
      2. Rejects legacy untracked tokens missing jti.
      3. Verifies token hash against PostgreSQL refresh_tokens table.
      4. Detects reuse/replay: if token was already consumed or revoked,
         the entire token family is revoked transactionally (RFC 6819 theft detection).
      5. Atomically consumes token using conditional update to serialize concurrency.
      6. Issues new access and refresh token pair within the same family_id.

    Args:
        db:      Active async database session.
        payload: Contains the refresh token string.

    Returns:
        A new ``TokenResponse`` with a fresh access token and child refresh token.

    Raises:
        UnauthorizedException: If token is invalid, expired, revoked, replayed,
                               or user is inactive/not found.
    """
    # ── 1. Decode and validate the refresh token ──────────────────────────────
    token_payload = decode_token(payload.refresh_token, expected_type="refresh")
    user_id_str: str = token_payload.get("sub", "")
    jti: str | None = token_payload.get("jti")

    if not jti or not user_id_str:
        logger.warning(
            "Rejected legacy untracked refresh token missing required claims",
            extra={"user_id": user_id_str},
        )
        raise UnauthorizedException(
            message="Invalid or untracked refresh token. Please log in again."
        )

    # ── 2. Look up tracked token record ───────────────────────────────────────
    token_hash = hashlib.sha256(payload.refresh_token.encode("utf-8")).hexdigest()
    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    result = await db.execute(stmt)
    tracked_token = result.scalar_one_or_none()

    if tracked_token is None:
        logger.warning(
            "Unknown refresh token presented — not tracked in database",
            extra={"user_id": user_id_str, "jti": jti},
        )
        raise UnauthorizedException(
            message="Invalid or untracked refresh token. Please log in again."
        )

    # ── 3. Validate subject match ─────────────────────────────────────────────
    if str(tracked_token.user_id) != user_id_str:
        logger.warning(
            "Token subject mismatch against tracked database record",
            extra={"token_sub": user_id_str, "db_user_id": str(tracked_token.user_id)},
        )
        raise UnauthorizedException(message="Invalid token claims.")

    # ── 4. Expiration check ───────────────────────────────────────────────────
    if _is_expired(tracked_token.expires_at):
        logger.info(
            "Expired refresh token presented",
            extra={"user_id": user_id_str, "token_id": str(tracked_token.id)},
        )
        raise UnauthorizedException(
            message="Refresh token has expired. Please log in again."
        )

    now_utc = datetime.now(UTC)

    # ── 5. Replay / Theft Detection ───────────────────────────────────────────
    if tracked_token.is_revoked or tracked_token.is_consumed:
        logger.warning(
            "Token replay or theft detected — revoking entire token family",
            extra={
                "log_type": "security_audit",
                "event": "token_replay_detected",
                "user_id": user_id_str,
                "family_id": str(tracked_token.family_id),
                "token_id": str(tracked_token.id),
                "was_consumed": tracked_token.is_consumed,
                "was_revoked": tracked_token.is_revoked,
            },
        )
        revoke_family_stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.family_id == tracked_token.family_id,
                RefreshToken.user_id == tracked_token.user_id,
            )
            .values(is_revoked=True, updated_at=now_utc)
        )
        await db.execute(revoke_family_stmt)
        await db.commit()

        # Immediate invalidation of active access tokens associated with compromised family
        await token_revocation_service.revoke_family(
            family_id=tracked_token.family_id,
            reason="replay_detected",
        )

        raise UnauthorizedException(
            message="Invalid refresh token. All sessions in this family have been revoked."
        )

    # ── 6. Atomic Single-Use Consumption (CAS / Conditional Update) ───────────
    consume_stmt = (
        update(RefreshToken)
        .where(
            RefreshToken.id == tracked_token.id,
            RefreshToken.is_consumed.is_(False),
            RefreshToken.is_revoked.is_(False),
        )
        .values(
            is_consumed=True,
            consumed_at=now_utc,
            updated_at=now_utc,
        )
    )
    consume_res = await db.execute(consume_stmt)
    if consume_res.rowcount != 1:
        # Concurrent refresh conflict: another request already consumed or revoked the row
        logger.warning(
            "Concurrent refresh race detected — token already consumed",
            extra={
                "log_type": "security_audit",
                "event": "concurrent_refresh_conflict",
                "user_id": user_id_str,
                "family_id": str(tracked_token.family_id),
            },
        )
        revoke_conflict_stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.family_id == tracked_token.family_id,
                RefreshToken.user_id == tracked_token.user_id,
            )
            .values(is_revoked=True, updated_at=now_utc)
        )
        await db.execute(revoke_conflict_stmt)
        await db.commit()

        await token_revocation_service.revoke_family(
            family_id=tracked_token.family_id,
            reason="concurrent_refresh_conflict",
        )

        raise UnauthorizedException(message="Invalid refresh token.")

    # ── 7. Check User Status ──────────────────────────────────────────────────
    user = await get_user_by_id(db, user_id_str)
    if user is None or not user.is_active:
        revoke_inactive_stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.family_id == tracked_token.family_id,
                RefreshToken.user_id == tracked_token.user_id,
            )
            .values(is_revoked=True, updated_at=now_utc)
        )
        await db.execute(revoke_inactive_stmt)
        await db.commit()

        await token_revocation_service.revoke_family(
            family_id=tracked_token.family_id,
            reason="user_inactive",
        )

        raise UnauthorizedException(
            message="User associated with this token no longer exists or is inactive."
        )

    # ── 8. Issue & Persist New Token Pair in Same Family ──────────────────────
    new_access = create_access_token(
        subject=user_id_str,
        family_id=tracked_token.family_id,
        extra_claims={"role": user.role.value, "email": user.email},
    )
    new_jti = str(uuid.uuid4())
    new_refresh = create_refresh_token(subject=user_id_str, jti=new_jti)
    new_token_hash = hashlib.sha256(new_refresh.encode("utf-8")).hexdigest()
    new_expires_at = now_utc + timedelta(days=settings.refresh_token_expire_days)

    user_uuid = user.id if isinstance(user.id, uuid.UUID) else uuid.UUID(str(user.id))

    new_tracked_token = RefreshToken(
        id=uuid.uuid4(),
        user_id=user_uuid,
        token_hash=new_token_hash,
        jti=new_jti,
        family_id=tracked_token.family_id,
        expires_at=new_expires_at,
        is_revoked=False,
        is_consumed=False,
    )
    db.add(new_tracked_token)
    await db.commit()

    logger.info(
        "Token refreshed successfully with single-use rotation",
        extra={"user_id": user_id_str, "family_id": str(tracked_token.family_id)},
    )

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


# =============================================================================
# Server-Side Logout (Revoke Token Family)
# =============================================================================


async def revoke_refresh_token(
    db: AsyncSession,
    payload: LogoutRequest,
) -> None:
    """
    Revoke a refresh token and its family on logout.

    Idempotent and safe against malformed, expired, already-revoked, or empty tokens.

    Args:
        db:      Active async database session.
        payload: Optional logout payload containing the refresh token.
    """
    if not payload.refresh_token:
        return

    try:
        token_payload = decode_token(payload.refresh_token, expected_type="refresh")
        user_id_str = token_payload.get("sub")
        token_hash = hashlib.sha256(payload.refresh_token.encode("utf-8")).hexdigest()
    except Exception as exc:
        logger.debug(f"Logout attempted with invalid or malformed token: {exc}")
        return

    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    result = await db.execute(stmt)
    tracked_token = result.scalar_one_or_none()

    if tracked_token is not None:
        now_utc = datetime.now(UTC)
        revoke_stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.family_id == tracked_token.family_id,
                RefreshToken.user_id == tracked_token.user_id,
            )
            .values(is_revoked=True, updated_at=now_utc)
        )
        await db.execute(revoke_stmt)
        await db.commit()

        # Immediate invalidation of active access tokens associated with logged-out session
        await token_revocation_service.revoke_family(
            family_id=tracked_token.family_id,
            reason="user_logout",
        )

        logger.info(
            "User session logged out — token family revoked",
            extra={
                "log_type": "security_audit",
                "event": "user_logout",
                "user_id": user_id_str,
                "family_id": str(tracked_token.family_id),
            },
        )
