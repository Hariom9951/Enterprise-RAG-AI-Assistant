# 🚢 Deployment Guide

> Step-by-step production deployment for the Enterprise RAG AI Assistant.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [Docker Deployment](#3-docker-deployment)
4. [Database Initialization](#4-database-initialization)
5. [Nginx Reverse Proxy](#5-nginx-reverse-proxy)
6. [SSL/TLS Configuration](#6-ssltls-configuration)
7. [Health Verification](#7-health-verification)
8. [Log Management](#8-log-management)
9. [Backup & Restore](#9-backup--restore)
10. [Scaling Workers](#10-scaling-workers)
11. [Environment Reference](#11-environment-reference)
12. [Common Issues](#12-common-issues)

---

## 1. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Docker | 24+ | [Install guide](https://docs.docker.com/get-docker/) |
| Docker Compose | 2.x (CLI plugin) | Bundled with Docker Desktop |
| 2+ GB RAM | — | Embedding model requires ~500MB RAM |
| 10+ GB Disk | — | For PostgreSQL data and document storage |
| Linux server | Ubuntu 22.04+ recommended | Or any Docker-compatible OS |

---

## 2. Environment Setup

### Clone Repository

```bash
git clone https://github.com/Hariom9951/Enterprise-RAG-AI-Assistant.git
cd Enterprise-RAG-AI-Assistant
```

### Configure Backend Environment

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env` and set all required values:

```bash
# Generate a strong secret key
python -c "import secrets; print(secrets.token_hex(32))"

# Required values to set:
SECRET_KEY=<generated-key>
GEMINI_API_KEY=<your-google-ai-studio-key>

# Production settings
ENVIRONMENT=production
DEBUG=false
LOG_FORMAT=json
LOG_LEVEL=INFO
WORKERS=4
```

> ⚠️ **Never commit `.env` to version control.** The `.gitignore` already excludes it.

### Optional: Configure Production DB Password

In `.env`:
```bash
DB_PASSWORD=your-strong-db-password-here
```

And update `docker-compose.yml` accordingly, or use the `${DB_PASSWORD}` substitution already in place.

---

## 3. Docker Deployment

### Build and Start All Services

```bash
# From project root — builds all images and starts 6 services
docker compose up --build -d
```

This starts:

| Container | Role | Port |
|---|---|---|
| `rag_postgres` | PostgreSQL 16 + pgvector | 5432 |
| `rag_redis` | Redis 7 cache + broker | 6379 |
| `rag_backend` | FastAPI + Uvicorn | 8000 |
| `rag_celery_worker` | Celery document processor | — |
| `rag_celery_beat` | Celery periodic scheduler | — |
| `rag_frontend` | Next.js standalone | 3000 |

### Check Service Status

```bash
docker compose ps
```

All services should show `Up (healthy)` or `Up` status.

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f celery_worker
```

---

## 4. Database Initialization

After the containers start, run Alembic migrations to create all tables:

```bash
docker compose exec backend alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade -> <hash>, initial migration
INFO  [alembic.runtime.migration] Running upgrade -> <hash>, add chat tables
...
```

Verify the database schema was created:
```bash
docker compose exec postgres psql -U raguser -d ragdb -c "\dt"
```

---

## 5. Nginx Reverse Proxy

For production, route both frontend and backend through Nginx on standard ports.

### Sample `/etc/nginx/sites-available/rag`:

```nginx
upstream backend {
    server localhost:8000;
}

upstream frontend {
    server localhost:3000;
}

server {
    listen 80;
    server_name your-domain.com;

    # Redirect all HTTP to HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;

    # Backend API
    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE streaming — disable buffering for /chat/stream endpoints
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }

    # Backend docs
    location ~ ^/(docs|redoc|openapi.json) {
        proxy_pass http://backend;
        proxy_set_header Host $host;
    }

    # Frontend
    location / {
        proxy_pass http://frontend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Increase upload size limit for document uploads
    client_max_body_size 50M;
}
```

Enable and reload:
```bash
sudo ln -s /etc/nginx/sites-available/rag /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 6. SSL/TLS Configuration

Using Let's Encrypt (free):

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal (already configured by certbot)
sudo certbot renew --dry-run
```

---

## 7. Health Verification

After deployment, verify all services:

```bash
# Backend health
curl https://your-domain.com/api/v1/health

# Expected response:
# {"status": "healthy", "database": "connected", "version": "0.2.0"}

# Frontend
curl -I https://your-domain.com
# HTTP/2 200

# Celery worker
docker compose exec celery_worker celery -A app.tasks.celery_app inspect ping
```

---

## 8. Log Management

### Configure JSON Logging

In production `.env`:
```bash
LOG_FORMAT=json
LOG_LEVEL=INFO
LOG_FILE_PATH=/app/logs/app.log
```

Logs are written to the `backend_logs` Docker volume mounted at `/app/logs`.

### View Log Files

```bash
# Access log directory
docker compose exec backend ls /app/logs/

# Tail live logs
docker compose exec backend tail -f /app/logs/app.log
```

### Log Rotation (host-level)

```bash
# /etc/logrotate.d/rag-backend
/var/lib/docker/volumes/rag_backend_logs/_data/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
}
```

---

## 9. Backup & Restore

### Database Backup

```bash
# Manual backup
bash scripts/backup.sh

# Automated daily backup via cron:
0 2 * * * /path/to/scripts/backup.sh >> /var/log/rag-backup.log 2>&1
```

The script creates a gzip-compressed SQL dump in `./backups/`.

### Database Restore

```bash
bash scripts/restore.sh backups/ragdb_2026-07-19.sql.gz
```

### Volume Backup (uploaded documents)

```bash
# Backup storage volume
docker run --rm \
  -v rag_storage:/source \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/storage_$(date +%Y%m%d).tar.gz -C /source .
```

---

## 10. Scaling Workers

### Scale Celery Workers Horizontally

```bash
# Run 3 Celery worker instances
docker compose up -d --scale celery_worker=3
```

### Scale Backend Workers (Uvicorn)

In `docker-compose.yml`, update the backend environment:
```yaml
WORKERS: "8"  # Recommended: 2 × CPU cores
```

Then rebuild:
```bash
docker compose up --build -d backend
```

---

## 11. Environment Reference

| Variable | Production Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `LOG_FORMAT` | `json` |
| `LOG_LEVEL` | `INFO` |
| `WORKERS` | `4` (or 2× CPU count) |
| `ALLOWED_ORIGINS` | Your domain (e.g. `https://rag.mycompany.com`) |
| `DOCS_URL` | `""` (disable in production) or leave as `/docs` |
| `DATABASE_URL` | `postgresql+asyncpg://raguser:<password>@postgres:5432/ragdb` |
| `REDIS_URL` | `redis://redis:6379/0` |
| `SECRET_KEY` | Strong 32-byte hex string — never a placeholder |

---

## 12. Common Issues

### Container Fails to Start

```bash
# Check detailed logs
docker compose logs backend --tail=50
```

Common causes:
- Missing `GEMINI_API_KEY` → set in `backend/.env`
- Database not ready → wait for `rag_postgres` to be `healthy`
- Port conflict → change host port in `docker-compose.yml`

### Document Stays in QUEUED State

```bash
# Check Celery worker logs
docker compose logs celery_worker --tail=50
```

Common causes:
- Redis not reachable → verify `rag_redis` is running
- Celery worker not started → `docker compose up -d celery_worker`

### pgvector Extension Missing

```bash
docker compose exec postgres psql -U raguser -d ragdb -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Alembic Migration Fails

```bash
# Check current revision
docker compose exec backend alembic current

# Show history
docker compose exec backend alembic history

# Manually apply missing migration
docker compose exec backend alembic upgrade head
```

### Reset Everything (Development Only)

```bash
# Stop all containers and remove all data volumes
docker compose down -v

# Rebuild and restart fresh
docker compose up --build -d
docker compose exec backend alembic upgrade head
```
