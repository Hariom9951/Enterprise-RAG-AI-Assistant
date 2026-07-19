# 📁 Project Structure

> Detailed map of every folder and major file in the Enterprise RAG AI Assistant repository.

---

## Root Level

```
Enterprise-RAG-AI-Assistant/
├── README.md                 # Project homepage — overview, quickstart, badges
├── DEPLOYMENT.md             # Step-by-step production deployment guide
├── PROJECT_STRUCTURE.md      # This file — codebase reference map
├── FEATURES.md               # Full implemented feature catalogue
├── API_DOCUMENTATION.md      # REST API reference with request/response examples
├── INTERVIEW_GUIDE.md        # GenAI/ML engineering interview prep guide
├── CONTRIBUTING.md           # Branch naming, commit conventions, PR checklist
├── LICENSE                   # MIT License
├── docker-compose.yml        # Multi-service Docker Compose orchestration
├── .gitignore                # Git exclusion rules
└── .pre-commit-config.yaml   # Pre-commit hooks (ruff, mypy)
```

---

## `/backend` — FastAPI Python Backend

```
backend/
├── Dockerfile                # Multi-stage Python 3.12 production build
├── requirements.txt          # All pinned Python package dependencies
├── pyproject.toml            # Ruff + Mypy tool configuration
├── pytest.ini                # pytest configuration (asyncio mode, markers)
├── alembic.ini               # Alembic database migration config
├── .env.example              # Environment variable template (safe to commit)
├── .env.production           # Production env template (do NOT commit)
│
├── app/                      # Application source code
│   ├── main.py               # FastAPI app factory, lifespan, middleware mounting
│   │
│   ├── api/v1/
│   │   ├── router.py         # Aggregates all endpoint sub-routers at /api/v1
│   │   └── endpoints/
│   │       ├── health.py     # GET /health — DB ping + service status
│   │       ├── root.py       # GET / — welcome message
│   │       ├── auth.py       # POST /auth/register, /login, /refresh
│   │       ├── users.py      # GET /users/me — authenticated profile
│   │       ├── documents.py  # Upload, list, get, delete documents
│   │       ├── chunks.py     # GET /documents/{id}/chunks — chunk viewer
│   │       ├── search.py     # POST /search — hybrid retrieval; GET /search/history
│   │       ├── rag.py        # POST /rag/query — grounded generation
│   │       ├── chat.py       # Sessions, messages, SSE streaming
│   │       ├── agent.py      # POST /agent/chat — ReAct agent
│   │       ├── jobs.py       # GET /jobs/{id} — task status polling
│   │       └── dashboard.py  # GET /dashboard/statistics — workspace stats
│   │
│   ├── agents/
│   │   └── agent_service.py  # ReAct loop: plan → tool call → observe → answer
│   │
│   ├── services/
│   │   ├── auth_service.py       # JWT creation/validation, bcrypt, token rotation
│   │   ├── user_service.py       # User CRUD, email lookup
│   │   ├── document_service.py   # File upload, storage, SHA-256 dedup
│   │   ├── processing_service.py # Orchestrates extraction → chunking → embedding
│   │   ├── chunking_service.py   # Recursive semantic chunker using tiktoken
│   │   ├── embedding_service.py  # SentenceTransformer encode + normalize
│   │   ├── retrieval_service.py  # Vector cosine search + FTS + RRF fusion
│   │   ├── rag_service.py        # Context assembly + LLM generation + citations
│   │   ├── chat_service.py       # Session management + SSE response stream
│   │   ├── llm_providers.py      # Gemini/OpenAI provider abstraction layer
│   │   └── cache_service.py      # Redis JSON caching for search results
│   │
│   ├── tasks/
│   │   ├── celery_app.py         # Celery app with Redis broker config
│   │   └── document_tasks.py     # process_document async Celery task
│   │
│   ├── processors/
│   │   └── pdf_processor.py      # PyMuPDF layout-aware extraction; DOCX/TXT support
│   │
│   ├── models/                   # SQLAlchemy 2.0 async ORM models
│   │   ├── __init__.py           # Imports all models for Alembic auto-detection
│   │   ├── enums.py              # UserRole enum (USER, ADMIN)
│   │   ├── user.py               # User table with UUID PK, role, timestamps
│   │   ├── document.py           # Document metadata, status, storage path
│   │   ├── chunk.py              # Text chunks with 768-dim pgvector embedding
│   │   ├── processed_document.py # Processing audit record
│   │   ├── chat_models.py        # ChatSession and ChatMessage tables
│   │   ├── agent_models.py       # AgentRun and AgentToolCall tables
│   │   ├── rag_query.py          # RAG query history table
│   │   └── search_query.py       # Search query history table
│   │
│   ├── schemas/                  # Pydantic V2 request/response models
│   │   ├── common.py             # PaginatedResponse, ErrorResponse, SuccessResponse
│   │   ├── auth.py               # RegisterRequest, LoginRequest, TokenResponse
│   │   ├── document.py           # DocumentResponse, DocumentListResponse
│   │   ├── chunk.py              # ChunkResponse with embedding metadata
│   │   ├── search.py             # SearchRequest, SearchResult, SearchResponse
│   │   ├── rag.py                # RAGRequest, RAGResponse, Citation, ModelList
│   │   ├── chat.py               # ChatSession, ChatMessage, StreamRequest
│   │   ├── agent.py              # AgentRequest, AgentChatResponse with reasoning
│   │   ├── dashboard.py          # DashboardStatistics, RecentItem aggregates
│   │   └── processed_document.py # ProcessingStatus response
│   │
│   ├── config/
│   │   └── settings.py           # Pydantic-settings: loads all env vars with defaults
│   │
│   ├── core/
│   │   ├── security.py           # bcrypt hash/verify, JWT encode/decode
│   │   ├── exceptions.py         # Custom exception hierarchy (RAGException tree)
│   │   └── logging.py            # Loguru configuration, JSON formatter
│   │
│   ├── db/
│   │   ├── base.py               # SQLAlchemy Base with UUID + timestamp mixins
│   │   └── session.py            # Async engine creation, request-scoped session DI
│   │
│   ├── middleware/
│   │   ├── cors.py               # CORS origin/method/header configuration
│   │   ├── security.py           # CSP, X-Frame-Options, rate limiter middleware
│   │   └── logging_middleware.py # Request/response timing and structured logging
│   │
│   └── dependencies/
│       └── auth.py               # get_current_user FastAPI dependency
│
├── alembic/
│   ├── env.py                    # Alembic async migration environment
│   ├── script.py.mako            # Migration file template
│   └── versions/                 # Timestamped migration scripts
│
├── tests/
│   ├── conftest.py               # Shared fixtures: in-memory SQLite, test client
│   ├── test_auth.py              # Registration, login, token refresh, RBAC
│   ├── test_documents.py         # Upload, list, status polling, delete
│   ├── test_chunking.py          # Chunker boundary tests
│   ├── test_embeddings.py        # Embedding dimension and normalization tests
│   ├── test_retrieval.py         # Hybrid search, RRF scoring, filter tests
│   ├── test_rag.py               # RAG pipeline, model selection, citation tests
│   ├── test_chat.py              # Session creation, message persistence, SSE
│   └── test_agent.py             # ReAct loop, tool dispatch, error handling
│
└── scripts/
    ├── benchmark_runner.py       # Automated RAG benchmark suite
    ├── eval_metrics.py           # Hit rate, MRR, NDCG evaluation
    ├── load_test.py              # Locust-style concurrent user simulation
    └── backup.sh / restore.sh   # PostgreSQL backup and restore utilities
```

---

## `/frontend` — Next.js 15 TypeScript Frontend

```
frontend/
├── Dockerfile                    # Multi-stage Node.js 20 standalone build
├── package.json                  # npm scripts and dependencies
├── next.config.ts                # Next.js configuration (standalone output)
├── tsconfig.json                 # TypeScript compiler options
├── tailwind.config.ts            # Tailwind CSS theme extensions
├── postcss.config.mjs            # PostCSS plugins
└── src/
    ├── app/                      # Next.js 15 App Router
    │   ├── layout.tsx            # Root layout with font loading and metadata
    │   ├── page.tsx              # Homepage (redirects to HomeClient)
    │   ├── HomeClient.tsx        # Landing page with hero, features, quick actions
    │   ├── globals.css           # Global CSS reset and design tokens
    │   │
    │   ├── (auth)/               # Authentication route group
    │   │   ├── layout.tsx        # Shared gradient background layout
    │   │   ├── login/page.tsx    # JWT login form with error handling
    │   │   └── register/page.tsx # Registration form with validation
    │   │
    │   ├── dashboard/page.tsx    # Workspace stats: doc count, chunks, searches
    │   ├── documents/
    │   │   ├── page.tsx          # Document list with status badges and actions
    │   │   └── [id]/page.tsx     # Document detail, chunks viewer, metadata
    │   ├── chat/page.tsx         # SSE streaming chat with session management
    │   ├── search/page.tsx       # Hybrid search with scored result cards
    │   ├── playground/page.tsx   # RAG console: query + chunks viewer + metrics
    │   ├── agent/
    │   │   ├── page.tsx          # Agent workspace shell
    │   │   └── AgentDashboardClient.tsx  # ReAct tool trace and reasoning viewer
    │   ├── settings/page.tsx     # Interactive LLM config form (localStorage)
    │   └── upload/page.tsx       # Drag-and-drop upload with progress tracking
    │
    ├── components/
    │   └── Navigation.tsx        # Glassmorphic collapsible sidebar + mobile header
    │
    └── lib/
        ├── api.ts                # Typed fetch client with JWT injection + refresh
        ├── auth.ts               # localStorage token helpers (get/set/clear)
        └── markdown.tsx          # Zero-dep React markdown renderer with citations
```

---

## `/docker` — Infrastructure Configuration

```
docker/
└── nginx.conf                   # Nginx reverse proxy configuration template
                                  # (routes /api/* → backend, /* → frontend)
```

---

## `/docs` — Developer Documentation

```
docs/
├── architecture.md              # System ADRs and component topology
├── coding-standards.md          # Python and TypeScript style guides
├── api-guidelines.md            # REST design, validation, error format
├── database-guidelines.md       # UUID keys, indexing, soft deletes
├── security-checklist.md        # OWASP, JWT, CORS, input validation
└── deployment-roadmap.md        # CI/CD pipeline stages
```

---

## `/scripts` — DevOps & Evaluation

```
scripts/
├── benchmark_runner.py          # End-to-end RAG quality benchmarks
├── eval_metrics.py              # Hit rate, MRR, precision@k evaluation
├── load_test.py                 # Basic concurrent user load simulation
├── load_test_phase13.py         # Extended 100-user load test
├── backup.sh                    # Automated PostgreSQL pg_dump backup
├── restore.sh                   # Restore from backup with validation
└── docker_test.sh               # Smoke-test Docker containers on startup
```
