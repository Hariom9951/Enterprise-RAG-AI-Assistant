# 🚢 Enterprise RAG AI Assistant — Production Deployment Guide

> Step-by-step production deployment and operations manual for the Enterprise RAG AI Assistant.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Production Environment Variables](#2-production-environment-variables)
3. [Database Migration Command](#3-database-migration-command)
4. [Redis Setup & Message Broker](#4-redis-setup--message-broker)
5. [Celery Worker & Scheduler Setup](#5-celery-worker--scheduler-setup)
6. [Backend Service Startup](#6-backend-service-startup)
7. [Frontend Production Startup](#7-frontend-production-startup)
8. [Docker & Containerized Deployment](#8-docker--containerized-deployment)
9. [Health-Check & Readiness URLs](#9-health-check--readiness-urls)
10. [Production Security Notes](#10-production-security-notes)
11. [Troubleshooting & Runbook](#11-troubleshooting--runbook)

---

## 1. Prerequisites

| Component | Minimum Version | Production Specification |
|---|---|---|
| **Python** | 3.12+ | CPython 64-bit |
| **Node.js** | 20+ LTS | Node.js with npm 10+ |
| **PostgreSQL** | 16+ | PostgreSQL with `pgvector` (`v0.5.0+`) extension enabled |
| **Redis** | 7.0+ | In-memory cache & Celery broker (Upstash Redis TLS supported) |
| **Docker** | 24+ | Engine with Docker Compose v2 (optional for containerized deploys) |
| **CPU / RAM** | 2 vCPU / 4 GB RAM | Embedding model (`BAAI/bge-base-en-v1.5`) requires ~500MB RAM |
| **Storage** | 20+ GB SSD | Persistent storage for document uploads (`storage/uploads/`) |

---

## 2. Production Environment Variables

### Backend Configuration (`backend/.env` or Container Environment)

The backend strictly validates environment variables on startup. In production (`ENVIRONMENT=production`), the system rejects insecure defaults and placeholders.

```bash
# Core Environment
APP_NAME="Enterprise RAG AI Assistant"
ENVIRONMENT=production
DEBUG=false

# Networking & Bind
HOST=0.0.0.0
PORT=8000
WORKERS=4
RELOAD=false

# Security & CORS (REQUIRED: non-wildcard in production)
# Format: comma-separated list of exact allowed browser origins
ALLOWED_ORIGINS=https://app.yourcompany.com,https://rag.yourcompany.com
ALLOW_CREDENTIALS=true

# JWT Signing Secret (REQUIRED: >= 32 characters, no placeholders)
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=replace_with_cryptographically_secure_hex_token_at_least_32_chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Database Connection (REQUIRED: PostgreSQL + pgvector)
# Format: postgresql+asyncpg://<user>:<password>@<host>:<port>/<dbname>
DATABASE_URL=postgresql+asyncpg://raguser:<password>@postgres-host:5432/ragdb?sslmode=require

# Redis & Broker Connection (REQUIRED: Redis 7+)
# Format: redis://[:password@]host:port/db or rediss:// for TLS
REDIS_URL=redis://redis-host:6379/0
ENABLE_REDIS_CACHING=true
REDIS_CACHE_TTL_SECONDS=3600

# Google Gemini LLM (REQUIRED: Verified Runtime Model)
GEMINI_API_KEY=AIzaSy...your_google_ai_studio_api_key
GEMINI_MODEL=gemini-3.5-flash
LLM_PROVIDER=gemini

# RAG & Embedding Hyperparameters
EMBEDDING_MODEL_NAME=BAAI/bge-base-en-v1.5
EMBEDDING_DIMENSION=768
RAG_TOP_K=10
RAG_SIMILARITY_THRESHOLD=0.0
RAG_MAX_CONTEXT_TOKENS=3000

# Storage Directories
STORAGE_DIR=/app/storage
```

### Frontend Configuration (`frontend/.env.production`)

```bash
NODE_ENV=production
NEXT_TELEMETRY_DISABLED=1

# Public API Gateway URL accessed from client browsers
NEXT_PUBLIC_API_URL=https://rag.yourcompany.com/api/v1

# Internal Docker / SSR API Gateway URL (Server-to-Server)
API_INTERNAL_URL=http://backend:8000/api/v1

PORT=3000
HOSTNAME=0.0.0.0
```

---

## 3. Database Migration Command

The schema uses SQLAlchemy 2.0 with Alembic. The `vector` extension and all tables (`users`, `documents`, `processed_documents`, `chunks`, `search_queries`, `rag_queries`, `chat_sessions`, `chat_messages`, `agent_runs`, `agent_tool_calls`) are applied via Alembic:

```bash
# From backend directory:
cd backend
alembic upgrade head
```

### Verify Migration Status:
```bash
alembic current
# Verify vector extension in PostgreSQL:
psql -U raguser -d ragdb -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
```

---

## 4. Redis Setup & Message Broker

Redis is used simultaneously as the Celery asynchronous task broker and as the API caching/rate-limiting layer.

### Standalone Linux:
```bash
sudo apt update && sudo apt install -y redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server
redis-cli ping
# Output: PONG
```

### Managed Redis (Upstash / AWS ElastiCache):
Provide TLS URL with `rediss://` protocol in `REDIS_URL`:
```bash
REDIS_URL=rediss://default:token@cluster-name.upstash.io:6379
```

---

## 5. Celery Worker & Scheduler Setup

Asynchronous document parsing (PDF, DOCX, TXT), semantic chunking, and BAAI dense embedding generation are handled by Celery workers.

### Start Celery Worker (Production Linux):
```bash
cd backend
celery -A app.tasks.celery_app worker \
  --loglevel=info \
  --concurrency=4 \
  --max-tasks-per-child=100
```

*Note for Windows development:* Use `--pool=solo` on Windows hosts:
```powershell
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
```

### Start Celery Beat (Scheduled Tasks / Daily Cleanup):
```bash
cd backend
celery -A app.tasks.celery_app beat \
  --loglevel=info \
  --schedule=/tmp/celerybeat-schedule
```

### Verify Celery Cluster Health:
```bash
celery -A app.tasks.celery_app inspect ping
celery -A app.tasks.celery_app inspect active
```

---

## 6. Backend Service Startup

### Production Command (Uvicorn / FastAPI):
```bash
cd backend
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --no-access-log \
  --proxy-headers \
  --forwarded-allow-ips="*"
```

### Systemd Service Template (`/etc/systemd/system/rag-backend.service`):
```ini
[Unit]
Description=Enterprise RAG AI Assistant Backend
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=raguser
WorkingDirectory=/opt/enterprise-rag/backend
EnvironmentFile=/opt/enterprise-rag/backend/.env
ExecStart=/opt/enterprise-rag/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## 7. Frontend Production Startup

The Next.js 16 frontend is compiled into an optimized standalone Node.js server.

### Build the Standalone Bundle:
```bash
cd frontend
npm ci --legacy-peer-deps
npm run build
```

### Start the Production Frontend Server:
```bash
# Option A: Standalone output mode (recommended, minimal footprint)
cd frontend/.next/standalone
PORT=3000 HOSTNAME=0.0.0.0 node server.js

# Option B: Standard Next.js runner
cd frontend
npm run start -- -p 3000 -H 0.0.0.0
```

---

## 8. Docker & Containerized Deployment

A production multi-container setup is orchestrated via `docker-compose.yml`:

```bash
# Build and start all 6 services (postgres, redis, backend, celery_worker, celery_beat, frontend):
docker compose up --build -d

# Execute database migrations:
docker compose exec backend alembic upgrade head

# View running container status:
docker compose ps

# Tail logs:
docker compose logs -f backend
docker compose logs -f celery_worker
```

---

## 9. Health-Check & Readiness URLs

The backend exposes automated endpoints for container orchestration, load balancers, and monitoring systems:

| Endpoint | Method | Purpose | Expected Status |
|---|---|---|---|
| `/api/v1/health` | `GET` | Overall system health (checks DB, Redis, App state) | `200 OK`, `{"status": "healthy"}` |
| `/api/v1/health/live` | `GET` | Kubernetes liveness probe (checks process responsiveness) | `200 OK`, `{"status": "live"}` |
| `/api/v1/health/ready` | `GET` | Kubernetes readiness probe (checks DB pool & model readiness) | `200 OK`, `{"status": "ready"}` |
| `/api/v1/health/metrics` | `GET` | Prometheus-compatible metrics endpoint | `200 OK`, text/plain metrics |

### Health Probe Verification:
```bash
curl -f http://localhost:8000/api/v1/health
curl -f http://localhost:8000/api/v1/health/ready
```

---

## 10. Production Security Notes

1. **Secret Key Hardening**:
   - `SECRET_KEY` must be at least 32 characters in length.
   - Pydantic startup validator automatically rejects common placeholder strings (`change-me`, `changeme`, `placeholder`, `secret`, `default`).
   - If an insecure key is detected with `ENVIRONMENT=production`, the application immediately raises `ValueError` and halts execution.
2. **CORS Isolation**:
   - Wildcard `ALLOWED_ORIGINS=*` is strictly disallowed in production when `ALLOW_CREDENTIALS=true`.
   - Specify only verified production domains to prevent cross-origin credential exfiltration.
3. **Container Privileges**:
   - Docker containers run under dedicated non-root users (`appuser:appgroup` UID 1000 in backend; `nextjs:nodejs` UID 1001 in frontend).
4. **LLM Chain-of-Thought Isolation**:
   - The ReAct agent service filters internal reasoning blocks (`<reasoning>...</reasoning>`) prior to persisting or transmitting answers.

---

## 11. Troubleshooting & Runbook

### Issue: Gemini HTTP 429 (`RESOURCE_EXHAUSTED`)
- **Symptom**: `LLM Streaming generation failed: Gemini stream failed with HTTP 429: Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash`.
- **Cause**: Google AI Studio free tier enforces a strict limit of 20 requests per project per day for `gemini-3.5-flash`.
- **Remediation**:
  1. Link a billing account in Google Cloud Console / Google AI Studio to enable Pay-As-You-Go pricing.
  2. Request a quota increase for `generate_content_requests` under the Google Cloud Quotas dashboard.

### Issue: Document Upload Stays in `PENDING`
- **Check**: Verify Celery worker is active and connected to the same Redis instance:
  ```bash
  celery -A app.tasks.celery_app inspect ping
  ```
- **Check**: Verify document storage directory permissions:
  ```bash
  ls -la backend/storage/uploads/
  ```

### Issue: PostgreSQL pgvector Cosine Distance Operator `<=>` Error
- **Symptom**: `operator does not exist: vector <=> unknown`.
- **Remediation**: Ensure the `pgvector` extension is active in the target database:
  ```sql
  CREATE EXTENSION IF NOT EXISTS vector;
  ```

### Issue: Next.js Frontend Cannot Connect to Backend
- **Check**: Verify `NEXT_PUBLIC_API_URL` baked into client bundles matches the public reverse proxy URL (e.g. `https://rag.yourcompany.com/api/v1`).
- **Check**: Verify browser console does not show CORS rejection errors.
