"""
Enterprise RAG AI Assistant — FastAPI Application Factory
=========================================================
This is the entry point for the backend application.

Startup sequence:
  1. Load settings from environment variables / .env file.
  2. Initialise structured logging (Loguru).
  3. Create the FastAPI app instance with OpenAPI metadata.
  4. Register middleware (CORS, request logging).
  5. Register global exception handlers.
  6. Mount versioned API routers.

Usage:
    # Development (hot-reload)
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

    # Production (via Docker / gunicorn)
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.api.v1.router import api_v1_router
from app.config.config import API_CONTACT, API_LICENSE, API_TITLE, TAGS_METADATA
from app.config.settings import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.db.session import dispose_engine, verify_database_connection
from app.middleware.cors import add_cors_middleware
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.middleware.rate_limit import RateLimitingMiddleware
from app.middleware.security import (
    RequestBodySizeLimitMiddleware,
    SecurityHeadersMiddleware,
)

# =============================================================================
# Lifespan Context Manager
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application startup and shutdown lifecycle events.

    Everything before ``yield`` runs at startup; everything after runs
    at shutdown. This is the recommended FastAPI pattern for resource
    initialisation and cleanup (replaces the deprecated on_event hooks).
    """
    # ── Startup ─────────────────────────────────────────────────────────────────────────
    logger.info(
        f"[START] Starting {settings.app_name} v{settings.app_version}",
        extra={"environment": settings.environment, "debug": settings.debug},
    )

    # Log active configuration for observability (no secrets)
    logger.info(
        f"[CONFIG] Port={settings.port} | Environment={settings.environment} "
        f"| LogFormat={settings.log_format} | Workers={settings.workers}"
    )

    if settings.gemini_api_key:
        logger.info("[CONFIG] Google Gemini API Key is configured and detected.")
    else:
        logger.warning(
            "[CONFIG] Google Gemini API Key is NOT configured. "
            "RAG and chat endpoints will fail until GEMINI_API_KEY is set "
            "(use Hugging Face Spaces Secrets UI)."
        )

    # Phase 2: Verify database connectivity.
    # Non-fatal: warns but does NOT crash if DATABASE_URL is missing or
    # unreachable at startup.  This allows the container to start and expose
    # /api/v1/health so operators can see the problem before it is corrected.
    try:
        await verify_database_connection()
    except Exception as db_exc:
        logger.warning(
            f"[CONFIG] Database connection could not be verified at startup: {db_exc}. "
            "Ensure DATABASE_URL (Neon PostgreSQL) is set via Hugging Face Spaces Secrets. "
            "The application will continue starting but DB-dependent endpoints will fail."
        )

    # Ensure local storage directories exist (idempotent).
    import os

    for folder in ["uploads", "processed", "failed", "temp"]:
        path = os.path.join(settings.storage_dir, folder)
        os.makedirs(path, exist_ok=True)
    logger.info("[OK] Document storage directories verified.")

    # Phase 3: Initialise Redis connection pool here.
    # Phase 4: Warm up vector store / LLM client here.

    logger.info("[OK] Application startup complete. Ready to serve traffic.")

    yield

    # ── Shutdown ────────────────────────────────────────────────────────────────────────
    logger.info("[STOP] Shutting down application ...")

    # Phase 2: Dispose the database connection pool.
    await dispose_engine()

    # Phase 3: Close Redis connection pool here.

    logger.info("[OK] Application shutdown complete.")


# =============================================================================
# Application Factory
# =============================================================================


def create_app() -> FastAPI:
    """
    Construct and configure the FastAPI application instance.

    Returns:
        A fully configured ``FastAPI`` instance ready to be served by Uvicorn.
    """
    # ── 1. Initialise logging first so all subsequent code is instrumented ────
    setup_logging(
        level=settings.log_level,
        fmt=settings.log_format,
        file_path=settings.log_file_path,
    )

    # ── 2. Create the FastAPI instance ────────────────────────────────────────
    application = FastAPI(
        title=API_TITLE,
        version=settings.app_version,
        description=settings.app_description,
        contact=API_CONTACT,
        license_info=API_LICENSE,
        openapi_tags=TAGS_METADATA,
        docs_url=settings.docs_url,
        redoc_url=settings.redoc_url,
        # Control openapi schema visibility based on docs path presence
        openapi_url="/openapi.json" if (settings.docs_url or settings.redoc_url) else None,
        lifespan=lifespan,
    )

    # ── 3. Register middleware (order matters — outermost registered last) ────
    add_cors_middleware(application)
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(RequestBodySizeLimitMiddleware)
    application.add_middleware(RateLimitingMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)

    # ── 4. Register global exception handlers ─────────────────────────────────
    register_exception_handlers(application)

    # ── 5. Mount versioned API routers ────────────────────────────────────────
    application.include_router(
        api_v1_router,
        prefix=settings.api_v1_prefix,
    )

    logger.debug(
        "FastAPI application configured",
        extra={"prefix": settings.api_v1_prefix, "environment": settings.environment},
    )

    return application


# =============================================================================
# Application Instance (module-level for Uvicorn)
# =============================================================================

# Uvicorn references this object when started with:
#   uvicorn app.main:app
app: FastAPI = create_app()
