"""
Enterprise RAG AI Assistant — Production Security Middleware
============================================================
Includes:
  1. SecurityHeadersMiddleware - HTTP headers (CSP, HSTS, X-Frame-Options, etc.)
  2. RequestBodySizeLimitMiddleware - Enforce strict JSON payload size limits
"""

from __future__ import annotations

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.config.settings import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to every response to protect against web vulnerabilities."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response: Response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Strict Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # HSTS (Strict Transport Security) - enforced only in production
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        # Basic Content Security Policy (CSP)
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' *; "
            "frame-ancestors 'none'; "
            "object-src 'none'"
        )
        response.headers["Content-Security-Policy"] = csp_policy

        # Permissions policy
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )

        return response


class RequestBodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Restricts the maximum allowed HTTP request payload size to prevent DoS."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Exclude file upload path which is independently checked and limited in the service layer
        is_upload_path = "/documents/upload" in request.url.path

        if not is_upload_path:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    size = int(content_length)
                    max_size = settings.max_request_body_size_bytes
                    if size > max_size:
                        return JSONResponse(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            content={
                                "error": {
                                    "code": "PAYLOAD_TOO_LARGE",
                                    "message": f"Request payload size exceeds the limit of {max_size} bytes.",
                                }
                            },
                        )
                except ValueError:
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={
                            "error": {
                                "code": "BAD_REQUEST",
                                "message": "Invalid Content-Length header.",
                            }
                        },
                    )

        return await call_next(request)
