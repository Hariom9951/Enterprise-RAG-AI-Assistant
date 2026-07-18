"""
Enterprise RAG AI Assistant — Redis-Backed Rate Limiting Middleware
===================================================================
Enforces request thresholds per client IP using Redis.
Fails open (logs warning but allows requests) if Redis is down to preserve availability.
"""

from __future__ import annotations

import time

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from loguru import logger
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.config.settings import settings


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """Global request rate limiting middleware using Redis."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        # Setup lazy redis client
        self._redis: Redis | None = None

    def _get_redis(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Bypass rate limits for health, ready, and metrics endpoints
        path = request.url.path
        is_ignored_path = any(
            p in path for p in ["/health", "/ready", "/live", "/metrics"]
        )
        if is_ignored_path or settings.is_development:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        try:
            r = self._get_redis()
            current_minute = int(time.time() / 60)
            key = f"rate_limit:{client_ip}:{current_minute}"

            requests_count = await r.incr(key)
            if requests_count == 1:
                # Expire key after 60 seconds
                await r.expire(key, 60)

            limit = settings.rate_limit_requests_per_minute
            if requests_count > limit:
                logger.warning(
                    f"[RateLimit] Rate limit exceeded for IP {client_ip}",
                    extra={
                        "client_ip": client_ip,
                        "requests": requests_count,
                        "limit": limit,
                    },
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": "Too many requests. Please try again later.",
                            "detail": {"requests_made": requests_count, "limit": limit},
                        }
                    },
                )

        except Exception as exc:
            # Fail open - do not block clients if Redis broker is temporarily down
            logger.warning(
                f"[RateLimit] Redis rate limiter error (failing open): {exc}"
            )

        return await call_next(request)
