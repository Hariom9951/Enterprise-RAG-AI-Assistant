"""
Enterprise RAG AI Assistant — OAuth State & PKCE Security Service
===================================================================
Manages cryptographically secure OAuth 2.0 state tokens and PKCE parameters
with atomic server-side Redis lifecycle management.

Security Guarantees:
- Cryptographically secure CSPRNG state and PKCE verifier generation (RFC 7636).
- Strict tenant binding to authenticated user_id and target provider.
- Single-use, atomic consumption via Lua GETDEL to guarantee replay prevention.
- Safe post-auth redirect URL validation preventing open redirects and CRLF attacks.
- Fail-closed error policy: Redis outage halts authorization flow rather than bypassing state.
- Zero credential exposure: tokens, keys, and client secrets are never stored in state.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final
from urllib.parse import urlparse

from loguru import logger
from redis.asyncio import Redis

from app.config.settings import settings
from app.models.oauth_models import VALID_PROVIDERS

# =============================================================================
# Constants & Exceptions
# =============================================================================

STATE_KEY_PREFIX: Final[str] = "oauth:state:"

# RFC 7636 unreserved characters: [A-Z], [a-z], [0-9], "-", ".", "_", "~"
_PKCE_UNRESERVED_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9\-._~]{43,128}$"
)

# Atomic retrieve-and-delete Lua script for single-use replay protection
LUA_GETDEL: Final[str] = """
local val = redis.call('GET', KEYS[1])
if val then
    redis.call('DEL', KEYS[1])
end
return val
"""


class OAuthSecurityError(Exception):
    """Base exception for OAuth security and state operations."""


class OAuthStateStorageError(OAuthSecurityError):
    """Raised when Redis state store is unavailable or fails (fail-closed)."""


class OAuthStateReplayOrNotFoundError(OAuthSecurityError):
    """Raised when OAuth state does not exist, expired, or was already consumed."""


class OAuthStateMismatchError(OAuthSecurityError):
    """Raised when OAuth state does not match expected user, provider, or integrity check."""


class OAuthInvalidRedirectError(OAuthSecurityError):
    """Raised when frontend redirect destination is untrusted or malformed."""


@dataclass(frozen=True)
class OAuthStateData:
    """Stored state data retrieved atomically upon callback."""

    user_id: uuid.UUID
    provider: str
    code_verifier: str
    code_challenge: str
    frontend_redirect_url: str
    created_at: str


@dataclass(frozen=True)
class OAuthStateCreationResult:
    """Public parameters generated for initiating provider authorization."""

    state: str
    code_challenge: str
    code_challenge_method: str = "S256"


# =============================================================================
# PKCE & Redirect URL Cryptographic Utilities
# =============================================================================


def generate_pkce_verifier(length: int = 64) -> str:
    """
    Generate an unreserved URL-safe PKCE code verifier (RFC 7636 Section 4.1).
    Length must be between 43 and 128 characters. Default: 64.
    """
    if length < 43 or length > 128:
        raise ValueError(
            "PKCE code_verifier length must be between 43 and 128 characters."
        )
    # Generate random bytes and base64url encode without padding
    # token_urlsafe uses [A-Za-z0-9-_], matching RFC 7636 unreserved characters
    token = secrets.token_urlsafe(length)[:length]
    if not _PKCE_UNRESERVED_PATTERN.match(token):
        raise ValueError("Generated verifier contains invalid characters.")
    return token


def compute_pkce_challenge(verifier: str) -> str:
    """
    Compute SHA-256 code challenge from verifier with base64url encoding (no padding)
    per RFC 7636 Section 4.2.
    code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
    """
    if not _PKCE_UNRESERVED_PATTERN.match(verifier):
        raise ValueError(
            "Invalid PKCE code_verifier. Must be 43-128 ASCII characters from unreserved character set."
        )
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return challenge


def validate_frontend_redirect_url(url: str | None) -> str:
    """
    Validate requested post-auth frontend redirect destination.
    Rejects open redirects, CRLF injection, and arbitrary third-party domains.

    Rules:
      1. Empty or None defaults to safe '/settings'.
      2. Relative paths starting with '/' are permitted (provided they do not start with '//' or '/\\').
      3. Absolute URLs must match an origin in settings.allowed_origins.
    """
    if not url or not url.strip():
        return "/settings"

    cleaned = url.strip()

    # Reject CRLF or null bytes
    if any(c in cleaned for c in ("\r", "\n", "\x00")):
        raise OAuthInvalidRedirectError(
            "Redirect URL contains illegal control characters."
        )

    # Reject protocol-relative URLs (e.g. '//evil.com' or '/\\evil.com')
    if cleaned.startswith("//") or cleaned.startswith("/\\"):
        raise OAuthInvalidRedirectError(
            "Protocol-relative redirect URLs are strictly forbidden."
        )

    # Safe relative paths within application
    if cleaned.startswith("/") and not cleaned.startswith("//"):
        return cleaned

    # Absolute URLs: validate origin against settings.allowed_origins
    try:
        parsed = urlparse(cleaned)
    except Exception as exc:
        raise OAuthInvalidRedirectError(f"Malformed redirect URL: {exc}") from exc

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise OAuthInvalidRedirectError(
            "Absolute redirect URL must have a valid http or https scheme and host."
        )

    origin = f"{parsed.scheme}://{parsed.netloc}".lower()
    allowed_origins = [
        o.rstrip("/").lower() for o in settings.allowed_origins if o != "*"
    ]
    if origin not in allowed_origins:
        raise OAuthInvalidRedirectError(
            f"Redirect URL origin '{origin}' is not in configured allowed origins."
        )

    return cleaned


# =============================================================================
# OAuth State & PKCE Service
# =============================================================================


class OAuthStateService:
    """
    Manages OAuth 2.0 state and PKCE parameters with server-side Redis storage.
    Enforces tenant binding, one-time consumption, expiry, and fail-closed security.
    """

    def __init__(self, redis_client: Redis | None = None) -> None:
        self._redis = redis_client

    def _get_redis(self) -> Redis:
        import asyncio

        current_loop = None
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        pool_loop = getattr(
            getattr(self._redis, "connection_pool", None), "_loop", None
        )
        if self._redis is None or (
            current_loop and pool_loop and pool_loop is not current_loop
        ):
            self._redis = Redis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def create_state(
        self,
        user_id: uuid.UUID,
        provider: str,
        frontend_redirect_url: str | None = None,
        ttl_seconds: int | None = None,
    ) -> OAuthStateCreationResult:
        """
        Generate cryptographically secure state and PKCE verifier/challenge.
        Persists state bound to user_id, provider, and verified redirect destination in Redis.
        Fails closed with OAuthStateStorageError if Redis is unavailable.
        """
        norm_provider = provider.lower().strip()
        if norm_provider not in VALID_PROVIDERS:
            raise ValueError(
                f"Unsupported OAuth provider: {provider!r}. Must be one of: {sorted(VALID_PROVIDERS)}."
            )

        safe_redirect = validate_frontend_redirect_url(frontend_redirect_url)

        # Generate 256-bit random state token
        state = secrets.token_urlsafe(32)
        code_verifier = generate_pkce_verifier(64)
        code_challenge = compute_pkce_challenge(code_verifier)

        ttl = (
            ttl_seconds
            if ttl_seconds is not None
            else settings.oauth_state_ttl_seconds
        )

        payload = {
            "user_id": str(user_id),
            "provider": norm_provider,
            "code_verifier": code_verifier,
            "code_challenge": code_challenge,
            "frontend_redirect_url": safe_redirect,
            "created_at": datetime.now(UTC).isoformat(),
        }

        redis_key = f"{STATE_KEY_PREFIX}{state}"
        try:
            r = self._get_redis()
            await r.set(redis_key, json.dumps(payload), ex=ttl)
        except Exception as exc:
            logger.error(f"[OAuthState] Failed to persist OAuth state in Redis: {exc}")
            raise OAuthStateStorageError(
                "OAuth state storage unavailable. Cannot safely initiate OAuth authorization flow."
            ) from exc

        return OAuthStateCreationResult(
            state=state,
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )

    async def consume_state(
        self,
        state: str,
        expected_provider: str,
        expected_user_id: uuid.UUID | None = None,
    ) -> OAuthStateData:
        """
        Atomically retrieve and consume state from Redis.
        Guarantees single-use replay protection.
        Validates provider and (optionally) user_id binding.
        Fails closed with OAuthStateStorageError if Redis is unavailable.
        """
        if not state or not isinstance(state, str) or len(state.strip()) < 16:
            raise OAuthStateReplayOrNotFoundError(
                "OAuth state parameter is missing or invalid."
            )

        cleaned_state = state.strip()
        redis_key = f"{STATE_KEY_PREFIX}{cleaned_state}"

        try:
            r = self._get_redis()
            raw_val = await r.eval(LUA_GETDEL, 1, redis_key)
        except Exception as exc:
            logger.error(
                f"[OAuthState] Redis failure during state consumption: {exc}"
            )
            raise OAuthStateStorageError(
                "OAuth state storage unavailable during validation. Authorization rejected."
            ) from exc

        if raw_val is None:
            raise OAuthStateReplayOrNotFoundError(
                "OAuth state is invalid, expired, or already consumed."
            )

        try:
            data = json.loads(raw_val)
        except Exception as exc:
            raise OAuthStateReplayOrNotFoundError(
                "Corrupted OAuth state record in storage."
            ) from exc

        # 1. Provider binding check
        norm_expected_provider = expected_provider.lower().strip()
        if data.get("provider") != norm_expected_provider:
            raise OAuthStateMismatchError(
                f"OAuth state provider mismatch. Expected '{norm_expected_provider}', got '{data.get('provider')}'."
            )

        # 2. User binding check (if caller provided expected user)
        if expected_user_id is not None:
            if data.get("user_id") != str(expected_user_id):
                raise OAuthStateMismatchError(
                    "OAuth state user binding mismatch. State belongs to another user session."
                )

        return OAuthStateData(
            user_id=uuid.UUID(data["user_id"]),
            provider=data["provider"],
            code_verifier=data["code_verifier"],
            code_challenge=data["code_challenge"],
            frontend_redirect_url=data.get("frontend_redirect_url", "/settings"),
            created_at=data.get("created_at", ""),
        )

    async def peek_redirect_url(
        self,
        state: str,
        expected_provider: str,
    ) -> str:
        """
        Inspect state in Redis without deleting it to recover safe frontend_redirect_url.
        Returns safe '/settings' fallback if state is missing, invalid, or provider mismatches.
        Never raises exceptions so that unauthenticated redirect handoffs fail open to '/settings'.
        """
        if not state or not isinstance(state, str) or len(state.strip()) < 16:
            return "/settings"

        cleaned_state = state.strip()
        redis_key = f"{STATE_KEY_PREFIX}{cleaned_state}"

        try:
            r = self._get_redis()
            raw_val = await r.get(redis_key)
            if not raw_val:
                return "/settings"
            data = json.loads(raw_val)
            if data.get("provider") != expected_provider.lower().strip():
                return "/settings"
            return data.get("frontend_redirect_url", "/settings")
        except Exception:
            return "/settings"


# Default singleton instance
oauth_state_service = OAuthStateService()
