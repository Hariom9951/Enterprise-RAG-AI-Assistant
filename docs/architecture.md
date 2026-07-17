# Enterprise RAG AI Assistant — Architecture Documentation

## System Overview

The Enterprise RAG AI Assistant is a production-grade, API-first application
that will enable users to upload enterprise documents and query them conversationally
using Retrieval-Augmented Generation (RAG).

---

## Phase 1 Architecture (Current)

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Network                           │
│                                                                 │
│  ┌──────────────────┐          ┌──────────────────────────┐    │
│  │   Frontend       │          │       Backend            │    │
│  │   Next.js 15     │─────────▶│  FastAPI + Uvicorn       │    │
│  │   Port: 3000     │  HTTP    │  Port: 8000              │    │
│  └──────────────────┘          └──────────────────────────┘    │
│                                        │                        │
│                                        │ /api/v1/               │
│                                        │ /api/v1/health         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Backend Layers

```
app/
├── api/              ← Presentation layer (HTTP endpoints)
│   └── v1/
│       ├── router.py              # Route aggregator
│       └── endpoints/
│           ├── root.py            # GET /
│           └── health.py          # GET /health
│
├── config/           ← Configuration layer
│   ├── settings.py                # Pydantic-settings (env vars)
│   └── config.py                  # Constants & feature flags
│
├── core/             ← Cross-cutting concerns
│   ├── logging.py                 # Loguru configuration
│   └── exceptions.py              # Exception hierarchy & handlers
│
├── middleware/       ← ASGI middleware
│   ├── cors.py                    # CORS policy
│   └── logging_middleware.py      # Request/response logging
│
├── schemas/          ← Pydantic I/O schemas (API contract)
│   └── common.py                  # Shared response models
│
├── models/           ← ORM models (Phase 3)
├── services/         ← Business logic (Phase 4)
├── utils/            ← Shared helpers
├── dependencies/     ← FastAPI DI registry
└── main.py           ← Application factory + lifespan
```

---

## Planned Architecture (Phase 4 — Full RAG)

```
┌───────────────────────────────────────────────────────────────────────┐
│                           Docker Network                              │
│                                                                       │
│  ┌─────────────┐   ┌──────────────────┐   ┌────────────────────┐    │
│  │  Next.js    │   │   FastAPI         │   │  PostgreSQL +      │    │
│  │  Frontend   │──▶│   Backend         │──▶│  pgvector          │    │
│  │  Port: 3000 │   │   Port: 8000      │   │  Port: 5432        │    │
│  └─────────────┘   └──────────────────┘   └────────────────────┘    │
│                            │                                          │
│                     ┌──────┴──────┐                                  │
│                     │             │                                   │
│               ┌─────▼────┐  ┌────▼─────┐                            │
│               │  Redis    │  │  LLM API │                            │
│               │  Cache    │  │ (OpenAI) │                            │
│               │  6379     │  │ External │                            │
│               └──────────┘  └──────────┘                            │
└───────────────────────────────────────────────────────────────────────┘
```

---

## Architectural Decisions (ADRs)

### ADR-001: FastAPI over Django/Flask
**Decision**: Use FastAPI for the backend.
**Rationale**: Async-native, automatic OpenAPI generation, Pydantic integration,
high throughput for AI workloads.

### ADR-002: Pydantic Settings for Configuration
**Decision**: All configuration via `pydantic-settings` loaded from env vars.
**Rationale**: Type-safe, validated at startup, works seamlessly with Docker
env injection and Kubernetes ConfigMaps/Secrets.

### ADR-003: API Versioning from Day One
**Decision**: All endpoints prefixed with `/api/v1/`.
**Rationale**: Enables non-breaking evolution — a `/api/v2/` can be introduced
without disrupting existing integrations.

### ADR-004: Loguru over stdlib logging
**Decision**: Loguru as the sole logging backend with a stdlib bridge.
**Rationale**: Structured JSON output, automatic log rotation, cleaner API,
and a single configuration point.

### ADR-005: Multi-stage Docker builds
**Decision**: Separate builder and runtime Docker stages.
**Rationale**: Smaller runtime images, no build tools in production,
reduced attack surface.

---

## Roadmap

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Project foundation, FastAPI skeleton, Next.js shell | ✅ Complete |
| 2 | Authentication (JWT), user management | 🔜 Planned |
| 3 | Database layer (PostgreSQL + pgvector), Redis cache | 🔜 Planned |
| 4 | Document ingestion, vector embeddings, RAG pipeline | 🔜 Planned |
| 5 | Production deployment (nginx, CI/CD, monitoring) | 🔜 Planned |
