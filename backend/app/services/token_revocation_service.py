"""
Enterprise RAG AI Assistant — Access Token & Family Revocation Service
======================================================================
Provides immediate invalidation of access tokens associated with compromised
or logged-out refresh-token families (RFC 6819).

Architecture & Security Properties:
1. Fast-Path (Redis):
   O(1) in-memory check against key `auth:revoked_family:{family_id}` with
   a TTL bounded by `settings.access_token_expire_minutes * 60` seconds.
2. Resilience & Safe Fallback (PostgreSQL):
   If Redis is temporarily down or unreachable, the check DOES NOT silently
   fail open for revoked sessions. Instead, it securely queries the PostgreSQL
   `refresh_tokens` table for `family_id` revocation status. Uncompromised sessions
   continue to authenticate normally, avoiding a global denial of service.
3. Bounded Storage:
   Revocation markers expire automatically after the maximum possible access-token
   TTL, preventing unbounded memory growth.
4. Privacy & Audit:
   Never stores or logs raw tokens or credentials; all markers are indexed
   strictly by UUID `family_id`.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.refresh_token import RefreshToken

REVOCATION_KEY_PREFIX = "auth:revoked_family:"


class TokenRevocationService:
    """Manages immediate access-token revocation for compromised token families."""

    def __init__(self) -> None:
        self._redis: Redis | None = None

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

    async def revoke_family(
        self,
        family_id: uuid.UUID | str,
        reason: str = "replay_detected",
        ttl_seconds: int | None = None,
    ) -> bool:
        """
        Record a revocation marker for a compromised or logged-out token family.

        TTL is capped at the maximum access-token lifetime to ensure all active
        access tokens from this family are rejected while preventing unbounded memory growth.
        """
        family_id_str = str(family_id)
        ttl = (
            ttl_seconds
            if ttl_seconds is not None
            else settings.access_token_expire_minutes * 60
        )
        key = f"{REVOCATION_KEY_PREFIX}{family_id_str}"
        payload = json.dumps(
            {
                "revoked_at": datetime.now(UTC).isoformat(),
                "reason": reason,
            }
        )

        try:
            r = self._get_redis()
            await r.set(key, payload, ex=ttl)
            logger.info(
                f"[Revocation] Recorded revocation marker for family {family_id_str}",
                extra={
                    "log_type": "security_audit",
                    "event": "family_revocation_recorded",
                    "family_id": family_id_str,
                    "reason": reason,
                    "ttl_seconds": ttl,
                },
            )
            return True
        except Exception as exc:
            logger.error(
                f"[Revocation] Failed to write revocation marker to Redis for family {family_id_str}: {exc}"
            )
            return False

    async def is_family_revoked(
        self,
        family_id: uuid.UUID | str | None,
        db: AsyncSession | None = None,
    ) -> bool:
        """
        Check if a token family has been revoked.

        Security semantics:
        1. If family_id is None or empty: returns False (handled upstream).
        2. Fast path: queries Redis. If Redis returns 1, returns True (revoked)
           immediately without querying PostgreSQL.
        3. Authoritative verification / Fallback path:
           If Redis returns 0 (marker absent) OR if Redis is unavailable:
           - If a DB session is provided, queries PostgreSQL to verify whether any
             RefreshToken row for this family has is_revoked=True.
           - If database confirms revocation, returns True and self-heals the Redis marker.
           - If database confirms active (is_revoked=False), returns False.
           - If database query fails, fails closed (returns True) to prevent compromised
             tokens from continuing to authenticate.
        4. If Redis is unavailable AND no DB session is provided:
           Fails closed (returns True).
        5. If Redis is available, marker is absent, and no DB session is provided:
           Returns False (relies on cache check).
        """
        if not family_id:
            return False

        family_id_str = str(family_id)
        key = f"{REVOCATION_KEY_PREFIX}{family_id_str}"
        redis_failed = False

        # ── 1. Redis Fast Path ────────────────────────────────────────────────
        try:
            r = self._get_redis()
            exists = await r.exists(key)
            if exists:
                return True
        except Exception as redis_exc:
            redis_failed = True
            logger.warning(
                f"[Revocation] Redis unavailable during revocation check for family {family_id_str}: {redis_exc}. "
                "Falling back to database verification."
            )

        # ── 2. Database Verification / Fallback Path ─────────────────────────
        # If Redis had the marker (exists=1), it returned True above.
        # If Redis returned 0 (absent) or failed, and a DB session is provided:
        # verify against PostgreSQL to guarantee a confirmed revoked family cannot
        # continue authenticating merely because a Redis marker write failed or raced.
        if db is not None:
            try:
                family_uuid = (
                    family_id
                    if isinstance(family_id, uuid.UUID)
                    else uuid.UUID(family_id_str)
                )
                stmt = (
                    select(RefreshToken.id)
                    .where(
                        RefreshToken.family_id == family_uuid,
                        RefreshToken.is_revoked.is_(True),
                    )
                    .limit(1)
                )
                result = await db.execute(stmt)
                is_revoked_in_db = result.scalar_one_or_none() is not None
                if is_revoked_in_db:
                    logger.warning(
                        f"[Revocation] Revoked family {family_id_str} identified via DB verification",
                        extra={"family_id": family_id_str},
                    )
                    # Self-heal Redis marker so future requests hit fast path
                    if not redis_failed:
                        try:
                            r = self._get_redis()
                            await r.set(
                                key,
                                json.dumps({"reason": "db_verification_healed"}),
                                ex=settings.access_token_expire_minutes * 60,
                            )
                        except Exception:
                            pass
                    return True
                return False
            except Exception as db_exc:
                logger.error(
                    f"[Revocation] Database verification failed for family {family_id_str}: {db_exc}"
                )
                # If database query fails, fail closed for safety
                return True

        # If no DB session is provided:
        # If Redis failed, fail closed for security.
        # If Redis succeeded and key was absent, return False.
        if redis_failed:
            return True
        return False


token_revocation_service = TokenRevocationService()
