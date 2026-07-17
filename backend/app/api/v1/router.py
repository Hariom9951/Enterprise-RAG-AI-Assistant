"""
Enterprise RAG AI Assistant — API v1 Aggregate Router
======================================================
Collects all v1 sub-routers into a single router that is then
registered on the FastAPI app in main.py.

To add a new feature:
  1. Create a module under app/api/v1/endpoints/
  2. Import its router here and include it with an appropriate prefix and tags.
"""

from fastapi import APIRouter

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.root import router as root_router

# The top-level v1 router — all routes registered here will be mounted
# under the API_V1_PREFIX defined in settings (default: /api/v1).
api_v1_router = APIRouter()

# ── Root ──────────────────────────────────────────────────────────────────────
api_v1_router.include_router(root_router)

# ── Health ────────────────────────────────────────────────────────────────────
api_v1_router.include_router(health_router)

# ── Future routers (Phase 2+) ─────────────────────────────────────────────────
# from app.api.v1.endpoints.auth      import router as auth_router
# from app.api.v1.endpoints.documents import router as documents_router
# from app.api.v1.endpoints.chat      import router as chat_router
# from app.api.v1.endpoints.search    import router as search_router

# api_v1_router.include_router(auth_router,      prefix="/auth",      tags=["auth"])
# api_v1_router.include_router(documents_router, prefix="/documents", tags=["documents"])
# api_v1_router.include_router(chat_router,      prefix="/chat",      tags=["chat"])
# api_v1_router.include_router(search_router,    prefix="/search",    tags=["search"])
