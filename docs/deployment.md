# Enterprise RAG AI Assistant — Production Deployment Guide

This guide details the procedures for launching the Enterprise RAG AI Assistant in production using Docker Compose.

---

## 1. Prerequisites

Ensure your target servers have the following installed:
- **Docker** (v24.0.0+)
- **Docker Compose** (v2.20.0+)
- Minimum System Specifications: 2 vCPUs, 4 GB RAM, 20 GB Disk

---

## 2. Environment Setup

Copy the production configuration template and populate it with secure credentials:

```bash
cp backend/.env.production backend/.env
cp frontend/.env.production frontend/.env
```

### Critical Environment Hardening:

1. **`SECRET_KEY`**: Set a strong 32-byte hexadecimal key using:
   ```bash
   openssl rand -hex 32
   ```
2. **`DB_PASSWORD`**: Replace the default postgres password with a strong credential.
3. **`ENVIRONMENT`**: Confirm it is set to `production`. Debug mode (`DEBUG=false`) and Swagger UI/ReDoc endpoints (`DOCS_URL=`) will be deactivated automatically to prevent threat actors from mapping endpoints.
4. **`ALLOWED_ORIGINS`**: Constrain to your official application domains (e.g. `https://rag.mycompany.com`). Wildcards are forbidden when credentials/cookies are active.

---

## 3. Launching the Services

Start the production compose stack:

```bash
docker compose -f docker-compose.yml up --build -d
```

Verify that all services are online and reporting health check status:

```bash
docker compose ps
```

The output should show:
- `rag_postgres` (healthy)
- `rag_redis` (healthy)
- `rag_backend` (healthy)
- `rag_celery_worker` (healthy)
- `rag_celery_beat` (running)
- `rag_frontend` (running)

---

## 4. Database Migrations

Run database schema migrations inside the backend container to provision the production tables:

```bash
docker compose exec backend alembic upgrade head
```

---

## 5. Security & Network Topology

- **Internal Networks**: Services communicate over an isolated bridge network (`rag_network`).
- **External Exposure**: Only the `frontend` (port `3000`) and the `backend` gateway (port `8000`) should expose ports to the outside world.
- **SSL Termination**: It is highly recommended to place an Nginx/HAProxy reverse proxy or Cloudflare tunnel in front of the ports to terminate SSL/TLS.
