# =============================================================================
# Enterprise RAG AI Assistant — Backend Dockerfile
# =============================================================================
# Multi-stage build:
#   Stage 1 (builder): Install dependencies in an isolated layer.
#   Stage 2 (runtime): Copy only the installed packages and app code.
#
# Benefits:
#   - Smaller final image (no build tools, no cache)
#   - Non-root user for security
#   - Explicit PYTHONPATH for clean imports
# =============================================================================

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install system build dependencies (needed for some Python packages).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage Docker layer caching.
# Changing app code won't invalidate this layer.
COPY requirements.txt .

# Install dependencies into a dedicated prefix so we can copy them cleanly.
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Make installed packages visible to Python.
    PYTHONPATH=/app \
    # Default port — 7860 for Hugging Face Spaces, 8000 for local/Docker Compose.
    PORT=7860

# Install minimal runtime system libraries.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from the builder stage.
COPY --from=builder /install /usr/local

# ── Security: run as non-root ─────────────────────────────────────────────────
# UID/GID 1000 matches the default non-root user injected by Hugging Face Spaces.
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy application source code.
COPY --chown=appuser:appgroup . .

# Create logs and storage directories with correct ownership.
RUN mkdir -p /app/logs /app/storage && chown -R appuser:appgroup /app/logs /app/storage

USER appuser

# Expose the application port (7860 for HF Spaces; override PORT env var for other platforms).
EXPOSE ${PORT}

# Health check — uses PORT env var so it works on both HF Spaces and Docker Compose.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:${PORT:-7860}/api/v1/health || exit 1

# Default command — can be overridden in docker-compose.yml or HF Spaces.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1"]
