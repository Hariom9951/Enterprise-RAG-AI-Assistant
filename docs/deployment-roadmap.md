# Deployment Roadmap — Enterprise RAG AI Assistant

This document outlines the pipeline progression, infrastructure components, CI/CD specifications, and operational policies for the Enterprise RAG AI Assistant.

---

## 1. Environment Pipelines

The application progresses through four isolated deployment stages:

```
[Development] ──▶ [Testing (CI)] ──▶ [Staging] ──▶ [Production]
```

### A. Development (Local)
- Runs backend inside Python virtual environment or local Docker Compose containers.
- Uses SQLite for zero-config database tasks or local PostgreSQL.
- Hot-reload enabled for fast iteration.

### B. Testing (CI)
- Triggered on every pull request to `main`.
- Runs linter (`ruff`, `eslint`), static type checks (`mypy`), and backend integration tests (`pytest` running against SQLite).
- Executes Next.js compile builds.

### C. Staging (Pre-Release)
- Deployed on every push/merge to `main`.
- Mirror of production architecture using staging PostgreSQL and Redis instances.
- Used for final integration and client acceptance checks.

### D. Production
- Scaled, high-availability environment.
- Swagger docs disabled, CORS strict, SSL enforced.
- Monitored continuously for performance and errors.

---

## 2. Containerization (Docker)

Multi-container orchestration is defined in `docker-compose.yml`:
- **Postgres:** Image `pgvector/pgvector:pg16` maps persistent storage to `postgres_data` volume.
- **Backend:** Python 3.12 multi-stage builds. Port 8000 exposed, mapped logs volume.
- **Frontend:** Next.js 15 multi-stage build running Next standalone server output on port 3000.
- **Nginx (Phase 5):** Handles SSL termination and acts as reverse proxy routing `/` to frontend and `/api/` to backend.

---

## 3. CI/CD Workflow (GitHub Actions)

### Build & Test Pipeline:
1. **Checkout:** Pull code repository.
2. **Setup Runtimes:** Initialize Python 3.12 and Node.js 20.
3. **Cache Dependencies:** Cache pip packages and npm node_modules.
4. **Backend Audits:**
   - Run Ruff check.
   - Run Mypy type validation.
   - Execute pytest test suites.
5. **Frontend Audits:**
   - Run lint check.
   - Run TypeScript validation and Next production compile build.
6. **Docker Build Validation:** Execute dry-run builds on Dockerfiles.

---

## 4. Monitoring & Observability

- **Structured Log Files:** Backend logs to standard out and files in JSON format (Phase 5 aggregators, e.g., ELK / Loki).
- **Traces & Correlation:** `X-Request-ID` is injected on startup and appended to downstream query traces for easy log correlation.
- **Health Probes:** `/api/v1/health` acts as Kubernetes liveness/readiness check probe.

---

## 5. Backups Policy

- **Automated Backups:** Production PostgreSQL databases must perform automated nightly snapshot backups.
- **Offsite Storage:** Backups must be stored securely inside encrypted, isolated cloud buckets (e.g. AWS S3 with KMS).
- **Retention:** Keep daily snapshots for 7 days, weekly snapshots for 4 weeks, and monthly backups for 12 months.

---

## 6. Scaling Strategy

- **Stateless Backend Nodes:** FastAPI instances are stateless and can scale horizontally behind Nginx load balancers.
- **Database Scaling:** PostgreSQL can scale vertically, or employ read-replicas for read-heavy operations.
- **Vector DB optimization:** As vectors grow, PGVector indices (`HNSW`) must be tuned and scaled to maintain sub-second search times.
- **Caching:** Redis acts as a centralized caching tier, reducing database load and sharing session states across backend nodes.
