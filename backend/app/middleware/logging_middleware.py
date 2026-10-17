"""
Enterprise RAG AI Assistant — Request / Response Logging Middleware
===================================================================
Logs every incoming HTTP request and its corresponding response,
including method, path, status code, and duration.

This middleware is intentionally lightweight — it does NOT buffer
request/response bodies to avoid memory pressure on large payloads.

Log output example:
    INFO  | → GET /api/v1/health
    INFO  | ← GET /api/v1/health  200  3.14ms
"""

import time
import uuid
from collections.abc import Callable
from urllib.parse import parse_qsl, quote_plus

from fastapi import Request, Response
from loguru import logger
from starlette.datastructures import QueryParams
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config.settings import settings
from app.middleware.rate_limit import get_client_ip

SENSITIVE_QUERY_PARAMS = frozenset(
    {
        "code",
        "state",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "client_secret",
        "api_key",
        "apikey",
        "password",
        "q",
        "query",
    }
)

REDACTED_VALUE = "[REDACTED]"


def sanitize_query_params(query: str | QueryParams | None) -> str | None:
    """
    Sanitize query parameters by redacting sensitive values case-insensitively.

    Preserves parameter names and non-sensitive values.
    Handles repeated parameters and malformed inputs safely.
    Returns None if query is empty or contains no parameters.
    """
    if not query:
        return None

    try:
        if isinstance(query, QueryParams):
            items = query.multi_items()
        elif isinstance(query, str):
            raw = query.lstrip("?")
            if not raw.strip():
                return None
            items = parse_qsl(raw, keep_blank_values=True)
        else:
            raw = str(query).lstrip("?")
            if not raw.strip():
                return None
            items = parse_qsl(raw, keep_blank_values=True)

        if not items:
            return None

        sanitized_parts: list[str] = []
        for key, val in items:
            key_clean = key.strip()
            key_lower = key_clean.lower()

            is_sensitive = (
                key_lower in SENSITIVE_QUERY_PARAMS
                or key_lower.endswith(("_token", "_secret", "_key", "_password"))
            )

            if is_sensitive:
                sanitized_parts.append(f"{quote_plus(key_clean)}={REDACTED_VALUE}")
            else:
                sanitized_parts.append(f"{quote_plus(key_clean)}={quote_plus(val)}")

        return "&".join(sanitized_parts)

    except Exception:
        # Never leak raw query string on unexpected parsing failure
        return "[MALFORMED_QUERY]"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that logs each HTTP request/response pair.

    A unique ``X-Request-ID`` header is injected into every response so
    that distributed traces can be correlated across services.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request, log it, and log the response.

        Args:
            request:   The incoming ASGI request object.
            call_next: The next middleware / route handler in the chain.

        Returns:
            The HTTP response with an added ``X-Request-ID`` header.
        """
        # Generate a unique request identifier for tracing.
        request_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        # Sanitize query parameters and resolve client IP before log record construction
        sanitized_query = sanitize_query_params(request.query_params)
        client_ip = get_client_ip(request, settings.trusted_proxies)

        # Log the incoming request.
        logger.info(
            f"--> {request.method} {request.url.path}",
            extra={
                "log_type": "api",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query": sanitized_query,
                "client_ip": client_ip,
            },
        )

        # Pass to the next layer.
        response: Response = await call_next(request)

        # Calculate elapsed time in milliseconds.
        elapsed_ms = (time.perf_counter() - start_time) * 1_000

        # Choose log level based on status code.
        log_fn = logger.info
        if response.status_code >= 500:
            log_fn = logger.error
        elif response.status_code >= 400:
            log_fn = logger.warning

        log_fn(
            f"<-- {request.method} {request.url.path}  {response.status_code}  {elapsed_ms:.2f}ms",
            extra={
                "log_type": "api",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(elapsed_ms, 2),
            },
        )

        # Attach the request ID to the response headers for client-side tracing.
        response.headers["X-Request-ID"] = request_id

        return response
