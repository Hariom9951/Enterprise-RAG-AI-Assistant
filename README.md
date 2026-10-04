# Aegis RAG — Enterprise Knowledge Assistant

> **A full-stack RAG system** that ingests enterprise documents, indexes them into a vector-enabled PostgreSQL database, performs hybrid retrieval with Reciprocal Rank Fusion, generates grounded answers via Google Gemini, and streams citations back to the user in real time.

---

[![CI/CD Pipeline](https://github.com/Hariom9951/Enterprise-RAG-AI-Assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/Hariom9951/Enterprise-RAG-AI-Assistant/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)
![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-336791?logo=postgresql)
![Docker](https://img.shields.io/badge/Docker-Containerised-2496ED?logo=docker)

---

## Overview

Aegis RAG is an enterprise knowledge assistant designed to eliminate the problem of institutional knowledge locked inside unstructured documents. Users upload PDF, DOCX, or TXT files; the system automatically extracts text, splits it into semantically meaningful chunks, and generates 768-dimensional vector embeddings locally using `BAAI/bge-base-en-v1.5`. Those embeddings are stored in a PostgreSQL database with the `pgvector` extension, indexed with an HNSW cosine-similarity index for sub-millisecond nearest-neighbour search at scale.

At query time the system runs two parallel retrieval passes — a dense vector search and a lexical keyword search — then fuses the ranked candidate lists using **Reciprocal Rank Fusion (RRF)** before applying a multi-factor reranker (similarity score, document freshness, metadata priority). The reranked context is assembled into a prompt and sent to **Google Gemini**, which returns a grounded, citation-annotated answer. The full response is delivered to the Next.js frontend via **Server-Sent Events (SSE)** for a progressive streaming experience.

Beyond question-answering, the system exposes a bounded **ReAct-style AI agent** that selects from a curated set of registered tools (`semantic_search`, `document_lookup`, `citation`, `conversation_history`) to answer multi-step queries. Every tool call validates user ownership before executing, and the agent enforces a hard cap of five tool calls and a 60-second wall-clock budget per run. Prompt injection patterns are detected and blocked before the agent loop begins.

The project is architected for enterprise operability: JWT authentication with refresh-token rotation, role-based access control (RBAC), per-user data isolation, asynchronous document processing via Celery + Redis, a workspace dashboard with aggregated analytics, and a three-stage GitHub Actions CI pipeline covering lint, type-checking, tests, and Docker security scanning.

---

## Table of Contents

1. [Key Features](#1-key-features)
2. [System Architecture](#2-system-architecture)
3. [RAG Pipeline](#3-rag-pipeline)
4. [AI Agent](#4-ai-agent)
5. [Tech Stack](#5-tech-stack)
6. [Project Structure](#6-project-structure)
7. [Local Development Setup](#7-local-development-setup)
8. [Run Locally](#8-run-locally)
9. [Document Ingestion](#9-document-ingestion)
10. [API Capabilities](#10-api-capabilities)
11. [Testing and Quality](#11-testing-and-quality)
12. [Security](#12-security)
13. [Environment Configuration](#13-environment-configuration)
14. [Deployment Status](#14-deployment-status)
15. [Cost-Conscious Deployment Plan](#15-cost-conscious-deployment-plan)
16. [Known Limitations](#16-known-limitations)
17. [Future Roadmap](#17-future-roadmap)
18. [Why This Project Is Technically Interesting](#18-why-this-project-is-technically-interesting)
19. [Author](#19-author)

---

## 1. Key Features

### Document Management
- **Multi-format ingestion** — PDF (via PyMuPDF), DOCX (python-docx), and TXT (with charset auto-detection)
- **SHA-256 deduplication** — duplicate documents and duplicate chunks detected at hash level before storage
- **Language detection** — ISO 639-1 language tagging per chunk via `langdetect`
- **Asynchronous processing** — uploads return immediately; Celery workers handle extraction, chunking, and embedding in the background
- **Per-user data isolation** — every document and chunk is scoped to the uploading user; no cross-user data leakage

### Retrieval and RAG
- **Dense vector retrieval** — cosine distance search via pgvector HNSW index on 768-dim embeddings
- **Lexical keyword retrieval** — SQL ILIKE token overlap scoring
- **Reciprocal Rank Fusion (RRF)** — `k=60` constant; merges ranked candidates from both retrieval passes
- **Multi-factor reranking** — similarity score (70%), document freshness via exponential decay with 30-day half-life (20%), metadata priority flags (10%)
- **Grounded generation** — Google Gemini generates answers using only retrieved context, with inline citation markers (`[1]`, `[2]`, ...)
- **SSE streaming** — answers stream token-by-token to the Next.js client via Server-Sent Events
- **Result caching** — Redis caches semantic search results keyed by query hash and user

### Chunking
- **Recursive text splitting** — hierarchy: headings → paragraphs → lines → sentences → words
- **Heading-aware splitting** — Markdown headings (`#`, `##`, ...) preserve section context in chunk metadata
- **Page-aware splitting** — form-feed characters update the active page number per chunk
- **tiktoken token counting** — `cl100k_base` encoding, 500-token target size, 50-token overlap
- **Rich metadata enrichment** — token count, word count, character count, reading time, page number, section title, heading level, language, SHA-256 hash

### AI Agent
- **Bounded ReAct-style orchestration** — intent classification → tool selection → execution → context assembly → generation
- **Registered tools**: `semantic_search`, `document_lookup`, `citation`, `conversation_history`
- **Safety constraints** — regex-based prompt injection detection blocks known jailbreak patterns before the loop starts
- **Execution limits** — max 5 tool calls per run, 60-second wall-clock budget
- **Ownership enforcement** — every tool validates `user_id` before returning data
- **Audit persistence** — every `AgentRun` and `AgentToolCall` is written to the database

### Auth and Security
- **JWT access tokens** (HS256, configurable to RS256) with 30-minute TTL
- **Refresh-token rotation** — 7-day TTL, single-use enforcement
- **bcrypt password hashing** via passlib
- **RBAC** — `user` and `admin` roles enforced at tool-registry and API level
- **Input validation** — MIME type and file size validated at upload; password strength policy at registration

### Observability
- **Health endpoints** — `/health`, `/ready`, `/live`, `/metrics` (psutil system metrics)
- **Dashboard analytics** — document count, storage usage, chunk count, query counts, agent run statistics
- **Search query logging** — every search and RAG query is persisted for analytics
- **Structured logging** — Loguru with configurable text or JSON output

### Frontend
- **Next.js 16 + React 19** with TypeScript and App Router
- **Tailwind CSS v4** with shadcn/ui component library
- **Multi-turn chat** with session management (create, rename, delete sessions)
- **Document upload** with real-time processing status polling
- **Agent interface** with tool execution trace display
- **Workspace dashboard** with live statistics

---

## 2. System Architecture

```mermaid
flowchart TD
    User["User"]

    subgraph FE["Next.js Frontend (port 3000)"]
        Chat["/chat"]
        Docs["/documents"]
        Agent["/agent"]
        Dashboard["/dashboard"]
        Search["/search"]
        Playground["/playground"]
    end

    subgraph BE["FastAPI Backend (port 8000)"]
        Auth["Auth / RBAC"]
        DocAPI["Document API"]
        ChatAPI["Chat API SSE"]
        RAGAPI["RAG API"]
        SearchAPI["Search API"]
        AgentAPI["Agent API"]
        DashAPI["Dashboard API"]
    end

    subgraph Async["Async Ingestion via Celery + Redis"]
        Redis[(Redis Broker)]
        Worker["Celery Worker"]
        Extract["Text Extraction PDF DOCX TXT"]
        Chunk["Chunking tiktoken cl100k_base 500t/50t overlap"]
        Embed["BAAI/bge-base-en-v1.5 768-dim Embeddings"]
    end

    subgraph DB["Neon PostgreSQL + pgvector"]
        PG[(PostgreSQL)]
        HNSW["HNSW cosine index vector_cosine_ops"]
    end

    subgraph Ret["Retrieval Pipeline"]
        Dense["Dense Vector Search cosine distance"]
        Lexical["Lexical Keyword Search ILIKE token overlap"]
        RRF["Reciprocal Rank Fusion k=60"]
        Rerank["Multi-factor Reranker similarity freshness metadata"]
    end

    Gemini["Google Gemini grounded generation"]
    SSE["Server-Sent Events streaming response"]

    User --> FE
    FE --> BE
    DocAPI --> Redis
    Redis --> Worker
    Worker --> Extract --> Chunk --> Embed --> PG
    PG --- HNSW
    RAGAPI --> Dense
    RAGAPI --> Lexical
    Dense --> RRF
    Lexical --> RRF
    RRF --> Rerank
    Rerank --> Gemini
    Gemini --> SSE
    SSE --> ChatAPI
    ChatAPI --> FE
```

---

## 3. RAG Pipeline

### Stage 1 — Upload and Validation
A user POSTs a file to `/api/v1/documents/upload`. The backend validates MIME type (`application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `text/plain`) and computes a SHA-256 checksum for deduplication. A document record is created with status `pending` and a Celery task is dispatched asynchronously.

### Stage 2 — Text Extraction
The Celery worker selects a processor based on MIME type: `PDFProcessor` (PyMuPDF), `DOCXProcessor` (python-docx), or `TXTProcessor` (charset-normalizer). Raw text and page metadata are extracted from the source binary.

### Stage 3 — Chunking
`ChunkingService` recursively splits extracted text using a hierarchy of separators (headings → paragraphs → lines → sentences → words). tiktoken (`cl100k_base`) counts tokens precisely. Chunks target 500 tokens with 50-token overlap to preserve semantic continuity at boundaries. Each chunk is enriched with token count, word count, character count, estimated reading time, page number, section title, heading level, language code, and a SHA-256 hash for duplicate detection.

### Stage 4 — Embedding Generation
`EmbeddingService` lazily loads `BAAI/bge-base-en-v1.5` via `sentence-transformers` on the first call, deferred to avoid cold-start memory exhaustion on constrained infrastructure. Each chunk text is encoded into a 768-dimensional float32 vector. The embedding model name, pipeline version, and generation latency are stored alongside the vector.

### Stage 5 — Vector Storage
Embeddings and chunk metadata are written to the `chunks` table in PostgreSQL. The `embedding` column is typed `Vector(768)` (pgvector). An HNSW index (`postgresql_using="hnsw"`, `vector_cosine_ops`) enables approximate nearest-neighbour search with logarithmic query time.

### Stage 6 — Dense Retrieval
At query time, `RetrievalService.search_semantic()` encodes the user question into a 768-dim vector and issues a pgvector cosine-distance query against the HNSW index. Results are filtered by `user_id` (ownership enforcement) and optional metadata filters (document IDs, language, date range). Query results are cached in Redis keyed by a SHA-256 hash of the query parameters.

### Stage 7 — Lexical Retrieval
`RetrievalService.search_keyword()` tokenises the query by whitespace and issues SQL `ILIKE` pattern matching across chunk text. Chunks are scored by the fraction of query tokens present, enabling recall for exact terminology not well captured by dense vectors alone.

### Stage 8 — Reciprocal Rank Fusion
`RetrievalService.search_hybrid()` merges the two ranked lists using RRF with `k=60`. Each candidate's fused score is `sum(1 / (k + rank))` summed across both lists. Candidates appearing in both lists receive a natural score boost. The merged list is re-sorted by RRF score.

### Stage 9 — Reranking
`Reranker` in `rag_service.py` applies a three-factor composite score: raw similarity score (70%), document freshness via exponential decay with a 30-day half-life (20%), and chunk metadata priority flags (10%). Top-k candidates after reranking form the generation context.

### Stage 10 — Context Assembly
Retrieved chunks are formatted with source indices. A token budget tracked with tiktoken ensures the context fits within the model's context window. Source document metadata (filename, page number, section) is captured for citation generation.

### Stage 11 — Gemini Generation
The assembled context and user question are sent to Google Gemini. The system prompt instructs the model to answer only from the provided context, embed citation markers (`[1]`, `[2]`...) inline, and place step-by-step reasoning inside a `<reasoning>...</reasoning>` block. The reasoning block is stripped from the final answer before delivery to the client.

### Stage 12 — Citation Generation
The `CitationTool` (also exposed as an agent tool) maps citation indices back to source chunks and formats a structured citation list with document name, page number, section title, and chunk text excerpt.

### Stage 13 — SSE Streaming
`ChatService` wraps the Gemini response in an async generator that yields `data:` events. FastAPI returns a `StreamingResponse` with `Content-Type: text/event-stream`. The Next.js frontend consumes the SSE stream and renders tokens progressively.

### Stage 14 — Persistence
The complete exchange — question, answer, citations, retrieved chunks, token counts, provider, model name, and latency — is persisted to the `rag_queries` table and linked to the active `ChatSession`.

---

## 4. AI Agent

The Aegis RAG agent is a bounded, tool-using orchestrator that answers multi-step or compound questions by selecting and executing from a fixed set of registered tools.

### Registered Tools

| Tool ID | Class | Purpose |
|---|---|---|
| `semantic_search` | `SemanticSearchTool` | Run hybrid semantic retrieval across the user's document corpus |
| `document_lookup` | `DocumentLookupTool` | Retrieve document metadata and chunk content by document ID |
| `citation` | `CitationTool` | Format structured citations from retrieved chunk references |
| `conversation_history` | `ConversationHistoryTool` | Retrieve previous messages from the active chat session |

### Execution Flow

```
User Question
    |
    +-- 1. Prompt injection scan (regex, pre-loop)
    |       Blocked patterns: [SYSTEM], "ignore previous instructions",
    |       <|im_start|>, "you are now", "disregard your", etc.
    |
    +-- 2. LLM intent classification
    |       Gemini returns a JSON array of tool call specifications
    |
    +-- 3. Sequential tool execution (max 5 calls, 60-second budget)
    |       ToolRegistry validates permissions and user_id before each call
    |
    +-- 4. Context assembly from all successful tool results
    |
    +-- 5. Gemini final-answer generation
            Grounded and citation-annotated
            AgentRun + AgentToolCall records persisted to DB
```

### Safety Design

- **No raw database access from the LLM** — the LLM can only call tool IDs registered in `ToolRegistry`; it cannot issue arbitrary SQL or access other users' data.
- **Ownership enforcement** — each tool receives `user_id` and validates it before querying the database.
- **Loop guard** — maximum 5 tool calls and a 60-second wall-clock budget prevent runaway loops.
- **Injection detection** — a regex scan blocks known prompt injection patterns before any tool is invoked.
- **RBAC at tool level** — `ToolRegistry.execute()` enforces permission levels; admin-tier tools are inaccessible to regular users.

---

## 5. Tech Stack

| Category | Technology | Purpose |
|---|---|---|
| **Frontend** | Next.js 16, React 19, TypeScript | SPA with App Router and SSE consumption |
| **UI Components** | Tailwind CSS v4, shadcn/ui, Lucide React | Design system and icon library |
| **Backend** | Python 3.12, FastAPI 0.115, Uvicorn | Async REST API and SSE server |
| **ORM** | SQLAlchemy 2.0 async | Typed async database access |
| **Database** | PostgreSQL (Neon) + pgvector 0.3 | Relational storage with vector index |
| **Vector Index** | pgvector HNSW vector_cosine_ops | Approximate nearest-neighbour search |
| **Embeddings** | BAAI/bge-base-en-v1.5, sentence-transformers 3.0 | Local 768-dim text embeddings |
| **LLM** | Google Gemini gemini-2.0-flash | Grounded answer generation and agent reasoning |
| **Background Jobs** | Celery 5.4, Redis 5 | Async document processing pipeline |
| **Caching** | Redis | Search result cache and latency metrics |
| **Authentication** | python-jose JWT HS256, passlib + bcrypt | Token issuance and password hashing |
| **PDF Extraction** | PyMuPDF 1.25 | Text and page metadata extraction from PDF |
| **DOCX Extraction** | python-docx 1.1 | Paragraph and table extraction from DOCX |
| **Tokenisation** | tiktoken 0.8, cl100k_base | Precise token counting for chunking |
| **Language Detection** | langdetect 1.0 | ISO 639-1 chunk language tagging |
| **Migrations** | Alembic 1.14 | Database schema versioning |
| **Containerisation** | Docker, Docker Compose | Service orchestration |
| **CI/CD** | GitHub Actions | Lint, type-check, test, Docker scan |
| **Linting** | Ruff 0.8, Black 24.10 | Code style and formatting |
| **Type Checking** | MyPy 1.13 | Static type safety Python 3.12 |
| **Security Scan** | Bandit | Python security static analysis |
| **Testing** | pytest 8.3, pytest-asyncio 0.24 | Backend unit and integration tests |
| **Metrics** | psutil 6.0, Loguru 0.7 | System metrics and structured logging |

---

## 6. Project Structure

```
Enterprise-RAG-AI-Assistant/
├── .github/
│   └── workflows/
│       └── ci.yml                   # 3-stage CI: backend, frontend, docker
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── agent_service.py     # ReAct orchestration loop
│   │   │   ├── base_tool.py         # BaseTool abstract class
│   │   │   ├── registry.py          # Tool registration and permission enforcement
│   │   │   └── tools/
│   │   │       ├── semantic_search.py
│   │   │       ├── document_lookup.py
│   │   │       ├── citation.py
│   │   │       └── conversation_history.py
│   │   ├── api/v1/endpoints/
│   │   │   ├── auth.py              # POST /auth/register|login|refresh
│   │   │   ├── documents.py         # Document CRUD and upload
│   │   │   ├── chat.py              # SSE streaming chat sessions
│   │   │   ├── rag.py               # RAG query endpoints
│   │   │   ├── search.py            # Hybrid search endpoints
│   │   │   ├── agent.py             # Agent chat and tool management
│   │   │   ├── dashboard.py         # Workspace statistics
│   │   │   └── health.py            # Health, readiness, liveness, metrics
│   │   ├── models/
│   │   │   ├── chunk.py             # Vector(768) column + HNSW index
│   │   │   ├── document.py
│   │   │   ├── user.py
│   │   │   ├── chat_models.py
│   │   │   ├── agent_models.py      # AgentRun, AgentToolCall
│   │   │   └── rag_query.py
│   │   ├── processors/
│   │   │   ├── pdf_processor.py     # PyMuPDF extraction
│   │   │   ├── docx_processor.py    # python-docx extraction
│   │   │   └── txt_processor.py     # charset-normalizer extraction
│   │   ├── services/
│   │   │   ├── retrieval_service.py # Dense, lexical, RRF, hybrid search
│   │   │   ├── rag_service.py       # Pipeline: retrieval, rerank, generate
│   │   │   ├── chunking_service.py  # tiktoken recursive splitter
│   │   │   ├── embedding_service.py # BAAI/bge-base-en-v1.5 lazy loading
│   │   │   ├── llm_providers.py     # Gemini API client and SSE streaming
│   │   │   ├── auth_service.py      # JWT issuance and verification
│   │   │   └── cache_service.py     # Redis search result caching
│   │   └── tasks/
│   │       ├── celery_app.py        # Celery application configuration
│   │       └── document_tasks.py    # Async extract, chunk, embed pipeline
│   ├── tests/                       # pytest test suite (13 modules)
│   ├── alembic/                     # Database migrations
│   ├── requirements.txt             # Pinned Python dependencies
│   └── pyproject.toml               # Ruff, Black, MyPy configuration
├── frontend/
│   └── src/
│       └── app/
│           ├── (auth)/              # Login and register pages
│           ├── chat/                # Multi-turn chat with SSE
│           ├── documents/           # Document manager
│           ├── agent/               # Agent interface
│           ├── dashboard/           # Analytics dashboard
│           ├── search/              # Hybrid search explorer
│           ├── playground/          # RAG query playground
│           └── settings/            # User settings
├── docs/                            # Architecture and operational guides
├── scripts/                         # Benchmarking, load testing, backup utilities
├── docker/
├── docker-compose.yml
├── Dockerfile
├── DEPLOYMENT.md
└── README.md
```

---

## 7. Local Development Setup

### Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.12 |
| Node.js | 20 |
| Git | any recent |
| Redis | 7 (Docker or local) |
| PostgreSQL | 16 with pgvector extension |

### Backend Environment

```powershell
Copy-Item backend\.env.example backend\.env
```

Key variables to configure (never commit real values):

```env
# Database
DATABASE_URL=postgresql+asyncpg://raguser:ragpassword@localhost:5432/ragdb

# Redis
REDIS_URL=redis://localhost:6379/0

# Security -- generate with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your_strong_random_secret_key

# Google Gemini
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash

# Embedding (runs locally, no API key needed)
EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
EMBEDDING_DEVICE=cpu

# App
ENVIRONMENT=development
DEBUG=false
```

### Frontend Environment

```env
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1
```

### Python Virtual Environment

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Database Migration

```powershell
# With PostgreSQL running:
alembic upgrade head
```

---

## 8. Run Locally

Four terminal sessions are required.

**Terminal 1 — Redis**
```powershell
docker run -p 6379:6379 redis:7-alpine
```

**Terminal 2 — Celery Worker**
```powershell
cd backend
.venv\Scripts\Activate.ps1
celery -A app.tasks.celery_app worker --loglevel=info
```

**Terminal 3 — FastAPI Backend**
```powershell
cd backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 4 — Next.js Frontend**
```powershell
cd frontend
npm install --legacy-peer-deps
npm run dev
```

### Service URLs

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://127.0.0.1:8000 |
| Swagger UI | http://127.0.0.1:8000/docs |
| ReDoc | http://127.0.0.1:8000/redoc |
| Health Check | http://127.0.0.1:8000/api/v1/health |

---

## 9. Document Ingestion

```
POST /api/v1/documents/upload
         |
         +-- MIME validation (PDF, DOCX, TXT)
         +-- SHA-256 checksum computed
         +-- Document record created (status: pending)
         +-- Celery task dispatched
                  |
                  +-- Text extracted by format-specific processor
                  +-- Language detected per chunk
                  +-- Text split recursively (tiktoken, 500t / 50t overlap)
                  +-- Chunk SHA-256 hashes computed (duplicate detection)
                  +-- BAAI/bge-base-en-v1.5 encodes chunks -> 768-dim vectors
                  +-- Vectors + metadata written to PostgreSQL
                           +-- HNSW index updated automatically
```

**Supported file types**: PDF, DOCX, TXT

The upload endpoint validates MIME type and file size before accepting the file. Processing is fully asynchronous — the API returns `201 Created` immediately and the document transitions from `pending` → `processing` → `processed` (or `failed`) as the Celery worker completes each stage.

---

## 10. API Capabilities

All routes are under `/api/v1` and require a valid JWT `Authorization: Bearer <token>` header.

| Feature | Endpoint | Method | Description |
|---|---|---|---|
| Register | `/auth/register` | POST | Create user account |
| Login | `/auth/login` | POST | Authenticate; receive access and refresh tokens |
| Refresh token | `/auth/refresh` | POST | Exchange refresh token for new access token |
| Upload document | `/documents/upload` | POST | Ingest PDF, DOCX, or TXT file |
| List documents | `/documents` | GET | Paginated list of user's documents |
| Get document | `/documents/{id}` | GET | Document metadata and status |
| Rename document | `/documents/{id}` | PUT | Update display name |
| Delete document | `/documents/{id}` | DELETE | Remove document and all associated chunks |
| Job status | `/jobs/{task_id}` | GET | Celery task processing status |
| Create chat session | `/chat/session` | POST | Initialise a new conversation |
| List chat sessions | `/chat/sessions` | GET | All conversations owned by the user |
| Get chat session | `/chat/session/{id}` | GET | Session with full message history |
| Rename chat session | `/chat/session/{id}` | PUT | Update session title |
| Delete chat session | `/chat/session/{id}` | DELETE | Remove session and all messages |
| Chat message SSE | `/chat/session/{id}/message` | POST | Send message; receive SSE stream |
| Global hybrid search | `/search` | POST | Semantic + keyword hybrid retrieval |
| Search history | `/search/history` | GET | Past search query log |
| Global RAG query | `/rag/query` | POST | Full RAG pipeline: retrieve, generate, cite |
| Scoped RAG query | `/rag/query/{doc_id}` | POST | RAG scoped to a single document |
| Available models | `/rag/models` | GET | List configured LLM providers and models |
| Agent chat | `/agent/chat` | POST | Run bounded ReAct agent |
| List agent tools | `/agent/tools` | GET | All registered agent tools and schemas |
| Test agent tool | `/agent/tools/test` | POST | Directly invoke a registered tool |
| Agent statistics | `/agent/statistics` | GET | Aggregate run and tool usage stats |
| Dashboard stats | `/dashboard/statistics` | GET | User-scoped system metrics |
| Health | `/health` | GET | Component health: API, DB, Redis |
| Readiness | `/ready` | GET | Container readiness probe |
| Liveness | `/live` | GET | Fast process liveness probe |
| Metrics | `/metrics` | GET | psutil system performance metrics |

---

## 11. Testing and Quality

### Backend Test Suite

```powershell
cd backend
pytest -v
# Parallel execution:
pytest -n auto
```

The test suite covers 13 modules: authentication flows, document CRUD, chunking edge cases, embedding generation, retrieval (dense, lexical, hybrid, RRF), RAG service, agent orchestration, Celery task dispatch, and health endpoints. Tests use an in-memory SQLite database via `aiosqlite` with SQLAlchemy dialect detection — no external PostgreSQL instance is required to run the full suite locally.

### Quality Gates

```powershell
cd backend
ruff check app tests           # Linter
ruff format --check app tests  # Formatter
mypy app                       # Type checker (Python 3.12)
bandit -r app/ -ll -ii         # Security scanner
```

```powershell
cd frontend
npm run lint   # ESLint
npm run build  # TypeScript compile + Next.js production bundle
```

### GitHub Actions CI Pipeline

Three-stage pipeline running on every push and pull request to `main`, `master`, and `develop`:

| Stage | Job | What Runs |
|---|---|---|
| 1 | `backend-ci` | Ruff lint, Ruff format check, MyPy, Bandit, pytest with real PostgreSQL + Redis services |
| 2 | `frontend-ci` | ESLint, Next.js production build |
| 3 | `docker-ci` (requires 1 + 2) | Docker build for backend and frontend images |

CI uses Python 3.12 and Node.js 20, matching the production targets.

---

## 12. Security

| Control | Implementation |
|---|---|
| **Authentication** | JWT HS256 access tokens with 30-minute TTL |
| **Refresh token rotation** | 7-day single-use refresh tokens |
| **Password storage** | bcrypt via passlib; plaintext is never stored |
| **Password policy** | 8+ characters, uppercase, digit, special character required |
| **RBAC** | `user` and `admin` roles enforced at API route and ToolRegistry level |
| **Data isolation** | All queries filter by `user_id`; no cross-user data access |
| **Prompt injection protection** | Regex scan blocks known jailbreak patterns before agent loop |
| **Bounded agent execution** | Max 5 tool calls, 60-second budget; no unrestricted DB access from LLM |
| **No raw LLM database access** | LLM interacts only through ToolRegistry-registered tools |
| **Secret management** | All secrets via environment variables; `.env` excluded from version control |
| **File validation** | MIME type and size validated at upload before processing begins |
| **Static security analysis** | Bandit runs on every CI push |
| **Audit trail** | Every agent run, tool call, search query, and RAG query persisted to DB |

---

## 13. Environment Configuration

All configuration is loaded by pydantic-settings from environment variables. Copy `backend/.env.example` to `backend/.env`.

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL async connection string |
| `REDIS_URL` | Redis connection string |
| `SECRET_KEY` | JWT signing secret — generate with `secrets.token_hex(32)` |
| `ALGORITHM` | JWT algorithm (`HS256` default; `RS256` for asymmetric) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token TTL (default: 30) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token TTL (default: 7) |
| `LLM_PROVIDER` | LLM backend — `gemini` (sole supported provider) |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GEMINI_MODEL` | Gemini model name (default: `gemini-2.0-flash`) |
| `EMBEDDING_MODEL` | Hugging Face model name (default: `BAAI/bge-base-en-v1.5`) |
| `EMBEDDING_DEVICE` | `cpu` or `cuda` |
| `ENVIRONMENT` | `development`, `staging`, or `production` |
| `DEBUG` | Enable debug mode |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `LOG_FORMAT` | `text` for local; `json` for production containers |
| `ALLOWED_ORIGINS` | Comma-separated CORS origin list |
| `PORT` | Server port (default: `8000` locally; `7860` for Hugging Face Spaces) |

> **Google Gemini is the sole LLM provider.** `LLM_PROVIDER` must be set to `gemini`. No other providers are currently integrated.

---

## 14. Deployment Status

| Milestone | Status |
|---|---|
| Source code on GitHub | Complete |
| GitHub Actions CI passing | Complete |
| Docker build (backend + frontend) | Complete |
| Bandit security scan passing | Complete |
| Local application verified | Complete |
| Production deployment | In progress — next phase |

> Production deployment is not yet complete. The codebase, CI pipeline, and Docker images are structurally production-ready. Cloud deployment is the active next milestone.

---

## 15. Cost-Conscious Deployment Plan

The intended deployment target is zero out-of-pocket cost using free tiers and student credits:

| Component | Planned Platform |
|---|---|
| **Frontend** | Vercel free tier (native Next.js deployment) |
| **Backend** | Hugging Face Spaces free CPU tier or student cloud credits |
| **Database** | Neon PostgreSQL free tier (includes pgvector) |
| **LLM** | Google Gemini API free tier quota |
| **Redis / Celery** | Upstash Redis free tier or student-credit infrastructure |

The `backend/.env.example` includes commented-out configuration for Neon and Upstash. The backend `PORT` defaults to `7860` to match Hugging Face Spaces expectations.

> Platform free tier terms are subject to change. Verify current availability before deploying.

---

## 16. Known Limitations

- **Gemini API quota** — All generation is subject to Google Gemini free-tier rate limits and daily quotas. When quota is exhausted, the API returns a graceful degraded response via `LLMQuotaExhaustedError`: retrieved citations are preserved; generation is skipped.
- **CPU-only embeddings** — `BAAI/bge-base-en-v1.5` runs on CPU by default. Embedding large documents is slower on free-tier infrastructure. The model is lazy-loaded to avoid cold-start memory exhaustion.
- **Lexical search** — Current keyword retrieval uses SQL `ILIKE` token matching rather than PostgreSQL `tsvector` full-text search. This is sufficient for moderate corpus sizes but does not scale as efficiently as native FTS at very high document volumes.
- **Single LLM provider** — Only Google Gemini is integrated. There is no fallback LLM if Gemini is unavailable.
- **Bounded agent tool set** — The agent is intentionally limited to four tools. Complex multi-step workflows may exceed these boundaries.

---

## 17. Future Roadmap

- [ ] Complete production deployment (Vercel + Hugging Face Spaces / Neon + Upstash)
- [ ] Frontend and backend production environment hardening (HTTPS, CORS, secrets management)
- [ ] PostgreSQL `tsvector` full-text search to replace ILIKE-based lexical retrieval
- [ ] Retrieval evaluation pipeline (precision@k, recall@k, MRR)
- [ ] Observability stack (structured JSON logs, Prometheus metrics, Grafana dashboard)
- [ ] Additional agent tools (web search, document summarisation)
- [ ] Multi-modal document support (image extraction from PDFs)
- [ ] GPU-accelerated embedding for production throughput
- [ ] Admin panel for user management and corpus-level analytics

---

## 18. Why This Project Is Technically Interesting

This section is intended for engineering interviews and technical discussions.

**Why PostgreSQL + pgvector instead of a dedicated vector database?**
pgvector collocates vectors with relational metadata (user IDs, document ownership, timestamps) in a single ACID-compliant store. This eliminates the synchronisation problem that emerges when a separate vector store must be kept consistent with a relational database under concurrent writes. For an enterprise RAG system where ownership filtering is security-critical, pushing those constraints into the database rather than application code is the correct design. The HNSW index provides competitive ANN search performance without the operational overhead of a separate vector service.

**Why BAAI/bge-base-en-v1.5 locally instead of a hosted embedding API?**
Local embeddings eliminate per-embedding API costs, reduce latency for batch ingestion, avoid sending proprietary document content to a third-party service, and make the ingestion pipeline runnable without an internet connection. The model is lazy-loaded behind an `asyncio.Lock` to prevent thundering-herd problems on cold start.

**Why hybrid retrieval (dense + lexical)?**
Dense vector retrieval excels at semantic similarity but can miss documents containing exact query terminology without semantic overlap (product codes, acronyms, proper nouns). Lexical retrieval captures exact term matches. Hybrid search achieves better recall across both dimensions.

**Why Reciprocal Rank Fusion?**
RRF is score-normalisation-free — it fuses ranked lists based on position, not raw scores, avoiding the problem of calibrating similarity scores from heterogeneous retrieval systems. With `k=60` the algorithm is robust to outlier ranks. Candidates appearing in both lists receive a natural boost approximating ensemble agreement without requiring any training.

**Why a multi-factor reranker instead of pure vector similarity?**
Vector similarity is a proximity measure, not a relevance measure. A very old document with high similarity may be less relevant than a recent document on the same topic. The 30-day exponential freshness decay and metadata priority flags allow domain knowledge to influence ranking without retraining the embedding model.

**Why Celery + Redis for document processing?**
Document ingestion involves CPU-intensive operations (PDF extraction, tokenisation, embedding generation) that can take seconds to minutes. Running these synchronously in the request/response cycle would block API workers and cause client timeouts. Celery decouples upload acknowledgement from the processing pipeline, enabling horizontal scaling of workers independently of API servers.

**Why Server-Sent Events instead of WebSockets?**
SSE is unidirectional (server to client), which exactly matches the chat use case: the user sends one message, the server streams one response. SSE works natively over HTTP/1.1, is automatically reconnected by browsers, and requires no special proxy configuration. WebSockets would add bidirectional complexity for no benefit in this interaction pattern.

**Why Gemini only?**
Constraining to a single, well-defined provider reduces integration surface area and makes testing more deterministic. The `LLMProviderError` / `LLMQuotaExhaustedError` exception hierarchy allows graceful degradation (citations returned, generation skipped) when quota is exhausted.

**How are citations grounded?**
Every retrieved chunk carries its source document ID, filename, page number, and section title through the entire pipeline. The system prompt instructs Gemini to use numeric citation markers aligned to the numbered context entries. After generation, the `CitationTool` maps those indices back to chunk metadata and assembles a structured citation list. The LLM never invents source metadata — it only cites indices from the context it was given.

**How does agent safety work?**
The agent loop has three independent safety layers: (1) regex injection detection before any LLM call; (2) tool execution routed exclusively through `ToolRegistry`, which enforces permission levels and ownership before any database access; (3) hard limits (5 tool calls, 60 seconds) preventing runaway execution. The LLM cannot issue arbitrary SQL, access other users' data, or invoke tools not in the registry.

**How does asynchronous ingestion maintain data consistency?**
The upload endpoint creates a `Document` record with `status=pending` and returns the document ID synchronously. The Celery task transitions status through `pending → processing → processed` (or `failed`) with database writes at each stage. The frontend polls `/jobs/{task_id}` for status. Chunk records are only committed after the complete chunking and embedding pipeline succeeds, preventing partial-chunk states from appearing in search results.

---

## 19. Author

**Hariom** — [@Hariom9951](https://github.com/Hariom9951)

---

## License

MIT — see [LICENSE](LICENSE) for details.
