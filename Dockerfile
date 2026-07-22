# =============================================================================
# Enterprise RAG AI Assistant — Hugging Face Spaces Dockerfile
# =============================================================================
# Hugging Face Spaces Docker SDK requirements:
#   - Single container image (no compose orchestration)
#   - Must listen on port 7860
#   - Runs as a non-root user (UID 1000 by default in HF Spaces)
#
# Architecture inside the container:
#   supervisord
#   ├── uvicorn  → FastAPI backend  (port 7860)
#   └── celery   → document processing worker
#
# External services (injected via HF Spaces Secrets):
#   - Neon PostgreSQL  →  DATABASE_URL
#   - Upstash Redis    →  REDIS_URL
#   - Google Gemini    →  GEMINI_API_KEY
#
# Multi-stage build:
#   Stage 1 (builder): Install Python dependencies
#   Stage 2 (runtime): Lean runtime image with app code only
# =============================================================================

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# System build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements only for layer-cache efficiency
COPY backend/requirements.txt .

# Install all Python dependencies into /install prefix
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt && \
    # Install supervisord separately (process manager)
    pip install --prefix=/install --no-cache-dir supervisor==4.2.5


# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    # Default port for Hugging Face Spaces
    PORT=7860 \
    # Production defaults (overridable via HF Secrets)
    ENVIRONMENT=production \
    DEBUG=false \
    LOG_FORMAT=json \
    LOG_LEVEL=INFO \
    WORKERS=1

# Runtime system libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# ── Security: HF Spaces runs as UID 1000 ─────────────────────────────────────
# HF Spaces injects a non-root user with UID/GID 1000.
# We create a matching user so file ownership is consistent.
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy backend application source
COPY --chown=appuser:appgroup backend/ /app/

# Copy supervisord configuration
COPY --chown=appuser:appgroup supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create required runtime directories
RUN mkdir -p /app/logs /app/storage/uploads /app/storage/processed \
             /app/storage/failed /app/storage/temp && \
    chown -R appuser:appgroup /app/logs /app/storage

USER appuser

# Expose port 7860 — required by Hugging Face Spaces
EXPOSE 7860

# Health check — HF Spaces uses this to determine container readiness
HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:${PORT:-7860}/api/v1/health || exit 1

# Entrypoint: run Alembic migrations then start supervisord
# supervisord manages uvicorn + celery worker as supervised processes
CMD ["sh", "-c", \
     "alembic upgrade head && \
      supervisord -c /etc/supervisor/conf.d/supervisord.conf"]
