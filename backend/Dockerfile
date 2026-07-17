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
    PYTHONPATH=/app

# Install minimal runtime system libraries.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from the builder stage.
COPY --from=builder /install /usr/local

# ── Security: run as non-root ─────────────────────────────────────────────────
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy application source code.
COPY --chown=appuser:appgroup . .

# Create logs directory with correct ownership.
RUN mkdir -p /app/logs && chown -R appuser:appgroup /app/logs

USER appuser

# Expose the application port.
EXPOSE 8000

# Health check used by Docker / Kubernetes.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Default command — can be overridden in docker-compose.yml.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
