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

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


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

        # Log the incoming request.
        logger.info(
            f"--> {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query": str(request.query_params) or None,
                "client_ip": request.client.host if request.client else "unknown",
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
