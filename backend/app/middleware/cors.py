"""
Enterprise RAG AI Assistant — CORS Middleware Configuration
===========================================================
Configures Cross-Origin Resource Sharing (CORS) to allow the
Next.js frontend (and any other approved client) to make requests
to the FastAPI backend from a different origin.

Production checklist:
  - Replace wildcard ALLOWED_ORIGINS with the exact frontend domain.
  - Set ALLOW_CREDENTIALS=true only if cookies/auth headers are used.
  - Remove DEBUG origins before deploying.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config.settings import settings


def add_cors_middleware(app: FastAPI) -> None:
    """
    Attach the CORSMiddleware to the FastAPI application.

    Configuration values are sourced from ``settings`` so they can be
    overridden per-environment via environment variables.

    Args:
        app: The FastAPI application instance.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=settings.allow_credentials,
        allow_methods=settings.allowed_methods,
        allow_headers=settings.allowed_headers,
    )

    logger.debug(
        "CORS middleware attached",
        extra={
            "allow_origins": settings.allowed_origins,
            "allow_credentials": settings.allow_credentials,
            "allow_methods": settings.allowed_methods,
        },
    )
