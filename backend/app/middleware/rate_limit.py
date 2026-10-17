"""
Enterprise RAG AI Assistant — Redis-Backed Rate Limiting Middleware
===================================================================
Enforces request thresholds per client IP using Redis.
Fails open (logs warning but allows requests) if Redis is down to preserve availability.
"""

from __future__ import annotations

import ipaddress
import time

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from loguru import logger
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.config.settings import settings


def is_ip_in_trusted_proxies(ip_str: str, trusted_proxies: list[str]) -> bool:
    """Check if an IP string matches any trusted proxy IP or CIDR network."""
    if not ip_str or not trusted_proxies:
        return False
    try:
        ip = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return False

    for proxy_pattern in trusted_proxies:
        pattern = proxy_pattern.strip()
        if not pattern:
            continue
        try:
            if "/" in pattern:
                network = ipaddress.ip_network(pattern, strict=False)
                if ip in network:
                    return True
            else:
                trusted_ip = ipaddress.ip_address(pattern)
                if ip == trusted_ip:
                    return True
        except ValueError:
            continue
    return False


def get_client_ip(request: Request, trusted_proxies: list[str] | None = None) -> str:
    """
    Safely extract the real client IP address from the request.

    Security constraints:
    1. If request.client is None, returns 'unknown'.
    2. Uses request.client.host as the immediate socket peer IP.
    3. If trusted_proxies is empty or peer_ip is NOT a trusted proxy,
       returns peer_ip. X-Forwarded-For headers are strictly IGNORED to prevent
       arbitrary client IP spoofing from the public internet.
    4. If peer_ip IS a trusted proxy:
       Parses the X-Forwarded-For header and traverses IPs from right to left
       (from the closest proxy toward the client). The first IP that is NOT in
       trusted_proxies is returned as the real client IP.
    5. If all IPs in X-Forwarded-For are trusted proxies, returns the leftmost valid IP.
    6. If X-Forwarded-For is missing or contains only invalid IP strings,
       safely falls back to peer_ip.
    """
    if not request.client or not request.client.host:
        return "unknown"

    peer_ip = request.client.host.strip()
    if not trusted_proxies:
        return peer_ip

    if not is_ip_in_trusted_proxies(peer_ip, trusted_proxies):
        return peer_ip

    x_forwarded_for = request.headers.get("x-forwarded-for")
    if not x_forwarded_for:
        return peer_ip

    raw_ips = [ip.strip() for ip in x_forwarded_for.split(",") if ip.strip()]
    if not raw_ips:
        return peer_ip

    for ip in reversed(raw_ips):
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            continue

        if not is_ip_in_trusted_proxies(ip, trusted_proxies):
            return ip

    # If all entries are in trusted_proxies, fallback to the leftmost valid IP
    for ip in raw_ips:
        try:
            ipaddress.ip_address(ip)
            return ip
        except ValueError:
            continue

    return peer_ip


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

        client_ip = get_client_ip(request, settings.trusted_proxies)

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
