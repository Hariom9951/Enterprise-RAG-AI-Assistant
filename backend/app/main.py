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

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from loguru import logger

from app.api.v1.router import api_v1_router
from app.config.config import API_CONTACT, API_LICENSE, API_TITLE, TAGS_METADATA
from app.config.settings import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.middleware.cors import add_cors_middleware
from app.middleware.logging_middleware import RequestLoggingMiddleware


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
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info(
        f"🚀 Starting {settings.app_name} v{settings.app_version}",
        extra={"environment": settings.environment, "debug": settings.debug},
    )

    # Phase 3: Initialise database connection pool here.
    # Phase 3: Initialise Redis connection pool here.
    # Phase 4: Warm up vector store / LLM client here.

    logger.info("✅ Application startup complete. Ready to serve traffic.")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("🛑 Shutting down application …")

    # Phase 3: Close database connection pool here.
    # Phase 3: Close Redis connection pool here.

    logger.info("✅ Application shutdown complete.")


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
        # Disable docs in production for security — controlled via settings.
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── 3. Register middleware (order matters — outermost registered last) ────
    add_cors_middleware(application)
    application.add_middleware(RequestLoggingMiddleware)

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
