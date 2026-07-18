"""
Enterprise RAG AI Assistant — Core Security Utilities
=====================================================
Provides all cryptographic primitives used by the authentication system:
  - Password hashing & verification (bcrypt via passlib)
  - JWT access token creation & verification
  - JWT refresh token creation

No business logic lives here — just pure crypto functions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from jose import JWTError, jwt
from loguru import logger
from passlib.context import CryptContext

from app.config.settings import settings
from app.core.exceptions import UnauthorizedException

# =============================================================================
# Password Hashing
# =============================================================================

# CryptContext selects bcrypt as the hashing scheme.
# ``deprecated="auto"`` automatically upgrades old hashes when users log in.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password with bcrypt.

    Args:
        plain_password: The raw password provided by the user.

    Returns:
        A bcrypt hash string suitable for database storage.

    Security note:
        bcrypt automatically incorporates a random salt, so two calls
        with the same password produce different hashes. Never store or
        log ``plain_password``.
    """
    return cast(str, _pwd_context.hash(plain_password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against a stored bcrypt hash.

    Args:
        plain_password:  Raw password provided by the user at login.
        hashed_password: Hash retrieved from the database.

    Returns:
        ``True`` if the password matches, ``False`` otherwise.
    """
    return cast(bool, _pwd_context.verify(plain_password, hashed_password))


# =============================================================================
# JWT Token Creation
# =============================================================================


def _create_token(
    data: dict[str, Any],
    expires_delta: timedelta,
    token_type: str,
) -> str:
    """
    Internal helper — encode a JWT with an expiry claim.

    Args:
        data:          Payload claims to embed (e.g. ``{"sub": user_id}``)
        expires_delta: How long the token should be valid.
        token_type:    Distinguishes ``"access"`` from ``"refresh"`` tokens.

    Returns:
        A signed JWT string.
    """
    payload = data.copy()
    now = datetime.now(UTC)
    payload.update(
        {
            "iat": now,  # Issued-at
            "exp": now + expires_delta,  # Expiry
            "type": token_type,  # Token kind discriminator
        }
    )
    return cast(
        str, jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    )


def create_access_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Create a short-lived JWT access token.

    Args:
        subject:      The ``sub`` claim — typically the user's UUID as a string.
        extra_claims: Optional additional claims (e.g. role, email).

    Returns:
        Signed JWT access token string.
    """
    data: dict[str, Any] = {"sub": subject}
    if extra_claims:
        data.update(extra_claims)

    return _create_token(
        data=data,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        token_type="access",
    )


def create_refresh_token(subject: str) -> str:
    """
    Create a long-lived JWT refresh token.

    Refresh tokens contain only the ``sub`` (user ID) and ``type`` claims
    to minimise the blast radius if one is compromised.

    Args:
        subject: The user's UUID as a string.

    Returns:
        Signed JWT refresh token string.
    """
    return _create_token(
        data={"sub": subject},
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
        token_type="refresh",
    )


# =============================================================================
# JWT Decoding & Validation
# =============================================================================


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    """
    Decode and validate a JWT, returning its payload.

    Validates:
      - Signature (using SECRET_KEY and ALGORITHM)
      - Expiry (``exp`` claim)
      - Token type discriminator (``type`` claim)

    Args:
        token:         The raw JWT string from the Authorization header.
        expected_type: ``"access"`` or ``"refresh"`` — prevents using a
                       refresh token where an access token is expected.

    Returns:
        The decoded payload dictionary.

    Raises:
        UnauthorizedException: If the token is invalid, expired, or of
                               the wrong type.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
    except JWTError as exc:
        logger.debug(f"JWT decode failed: {exc}")
        raise UnauthorizedException(
            message="Invalid or expired token.",
            detail={"hint": "Please log in again to obtain a new token."},
        ) from exc

    # Validate the token type discriminator.
    if payload.get("type") != expected_type:
        raise UnauthorizedException(
            message=f"Expected a {expected_type} token but received a {payload.get('type')} token.",
        )

    # Ensure ``sub`` is present.
    if not payload.get("sub"):
        raise UnauthorizedException(message="Token is missing the 'sub' claim.")

    return cast(dict[str, Any], payload)
