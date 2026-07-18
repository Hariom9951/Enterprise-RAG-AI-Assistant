"""
Enterprise RAG AI Assistant — Redis Caching Service
===================================================
Provides asynchronous helper methods to cache query search responses,
session configurations, and chunks using Redis.
Gracefully fails open (bypasses cache) if Redis connection is unavailable.
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger
from redis.asyncio import Redis

from app.config.settings import settings


class RedisCacheService:
    """Enterprise Redis caching wrapper with error safety guardrails."""

    def __init__(self) -> None:
        self._redis: Redis | None = None

    def _get_redis(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def get(self, key: str) -> Any | None:
        """Retrieve deserialized data from cache."""
        if not settings.enable_redis_caching:
            return None

        try:
            r = self._get_redis()
            val = await r.get(key)
            if val:
                return json.loads(val)
        except Exception as exc:
            logger.warning(f"[Cache] Redis read failure (failing open): {exc}")
        return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Store serialized data in cache with an optional TTL."""
        if not settings.enable_redis_caching:
            return False

        try:
            r = self._get_redis()
            serialized = json.dumps(value)
            expire_ttl = ttl if ttl is not None else settings.redis_cache_ttl_seconds
            await r.set(key, serialized, ex=expire_ttl)
            return True
        except Exception as exc:
            logger.warning(f"[Cache] Redis write failure (failing open): {exc}")
        return False

    async def delete(self, key: str) -> bool:
        """Invalidate a key from the cache."""
        try:
            r = self._get_redis()
            await r.delete(key)
            return True
        except Exception as exc:
            logger.warning(f"[Cache] Redis delete failure (failing open): {exc}")
        return False

    async def clear_namespace(self, prefix: str) -> int:
        """Delete all keys matching a specific namespace prefix."""
        try:
            r = self._get_redis()
            keys = await r.keys(f"{prefix}*")
            if keys:
                await r.delete(*keys)
                return len(keys)
        except Exception as exc:
            logger.warning(
                f"[Cache] Redis clear namespace failure (failing open): {exc}"
            )
        return 0

    async def record_latency(self, metric_name: str, duration_ms: float) -> None:
        """Record rolling latency values for metrics aggregation."""
        try:
            r = self._get_redis()
            key = f"metric:latency:{metric_name}"
            # Push value to rolling list
            await r.rpush(key, duration_ms)  # type: ignore[misc]
            # Limit list size to last 100 values
            await r.ltrim(key, -100, -1)  # type: ignore[misc]
        except Exception as exc:
            logger.warning(f"[Cache] Redis record metric failure: {exc}")

    async def get_average_latency(self, metric_name: str) -> float:
        """Calculate the average latency from the rolling metrics list."""
        try:
            r = self._get_redis()
            key = f"metric:latency:{metric_name}"
            values = await r.lrange(key, 0, -1)  # type: ignore[misc]
            if values:
                float_values = [float(v) for v in values if v]
                if float_values:
                    return sum(float_values) / len(float_values)
        except Exception as exc:
            logger.warning(f"[Cache] Redis get metrics average failure: {exc}")
        return 0.0


# Singleton client for general service ingestion
cache_service = RedisCacheService()
