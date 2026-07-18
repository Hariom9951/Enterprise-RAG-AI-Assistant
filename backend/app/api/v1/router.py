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

from app.api.v1.endpoints.agent import router as agent_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.chat import router as chat_router
from app.api.v1.endpoints.chunks import router as chunks_router
from app.api.v1.endpoints.documents import router as documents_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.jobs import router as jobs_router
from app.api.v1.endpoints.rag import router as rag_router
from app.api.v1.endpoints.root import router as root_router
from app.api.v1.endpoints.search import router as search_router
from app.api.v1.endpoints.users import router as users_router

# The top-level v1 router — all routes registered here will be mounted
# under the API_V1_PREFIX defined in settings (default: /api/v1).
api_v1_router = APIRouter()

# ── Root ──────────────────────────────────────────────────────────────────────
api_v1_router.include_router(root_router)

# ── Health ────────────────────────────────────────────────────────────────────
api_v1_router.include_router(health_router)

# ── Phase 2: Authentication ───────────────────────────────────────────────────
api_v1_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(users_router, prefix="/users", tags=["users"])

# ── Phase 3: Document Management ──────────────────────────────────────────────
api_v1_router.include_router(documents_router, prefix="/documents", tags=["documents"])

# ── Phase 4: Celery Background Jobs ───────────────────────────────────────────
api_v1_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])

# ── Phase 6: Semantic Chunking ────────────────────────────────────────────────
api_v1_router.include_router(chunks_router, prefix="/chunks", tags=["chunks"])

# ── Future routers (Phase 7+) ─────────────────────────────────────────────────

api_v1_router.include_router(chat_router, prefix="/chat", tags=["chat"])
api_v1_router.include_router(search_router, prefix="/search", tags=["search"])
api_v1_router.include_router(rag_router, prefix="/rag", tags=["rag"])

# ── Phase 11: Enterprise AI Agents ───────────────────────────────────────────
api_v1_router.include_router(agent_router, prefix="/agent", tags=["agent"])
