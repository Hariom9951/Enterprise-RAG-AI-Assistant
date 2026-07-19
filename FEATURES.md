# ✨ Features

> Complete catalogue of every implemented feature in the Enterprise RAG AI Assistant.

---

## 🔐 Authentication & Authorization

| Feature | Details |
|---|---|
| **User Registration** | Email + full name + password with 8+ char, uppercase, digit, symbol policy enforcement |
| **JWT Authentication** | Short-lived access tokens (30 min) + long-lived refresh tokens (7 days) |
| **Token Rotation** | Refresh endpoint rotates both access and refresh tokens to prevent replay attacks |
| **bcrypt Password Hashing** | Industry-standard password hashing with salt via `passlib[bcrypt]` |
| **Role-Based Access Control** | `USER` and `ADMIN` roles stored in the database — route guards in dependencies |
| **Authenticated Profile** | `GET /users/me` returns profile, role, and account metadata |
| **Rate Limiting on Auth Routes** | Redis sliding-window limiter prevents brute-force login attempts |

---

## 📄 Document Management

| Feature | Details |
|---|---|
| **Multi-format Upload** | PDF, DOCX, and TXT files up to configurable size limits |
| **SHA-256 Deduplication** | Prevents duplicate document storage by hash comparison before ingestion |
| **UUID-based Storage** | Files stored with UUID names for security — original filename preserved in DB |
| **Async Background Processing** | Upload returns immediately; Celery worker handles extraction asynchronously |
| **Processing Status Polling** | `GET /documents/{id}` tracks: `UPLOADED → QUEUED → PROCESSING → COMPLETED` |
| **Document CRUD** | List, retrieve detail, delete with cascade chunk cleanup |
| **Metadata Enrichment** | File size, MIME type, SHA-256, storage path, timestamps persisted |
| **Drag-and-Drop Frontend** | Upload page with real-time validation, progress indicators, and status polling |

---

## 🔍 Document Processing Pipeline

| Feature | Details |
|---|---|
| **Layout-Aware PDF Extraction** | PyMuPDF extracts text preserving paragraph and page boundaries |
| **DOCX Parsing** | python-docx extracts paragraphs with heading hierarchy preservation |
| **TXT Processing** | Direct text ingestion with encoding detection |
| **Recursive Semantic Chunking** | tiktoken-based chunker respects sentence boundaries up to 500-token max |
| **Chunk Metadata** | Each chunk stores: chunk index, token count, character count, word count, page number, language, section title |
| **Language Detection** | langdetect auto-identifies chunk language for multilingual support |
| **Chunk Versioning** | SHA-256 per chunk for future incremental re-embedding support |

---

## 🧮 Vector Embeddings

| Feature | Details |
|---|---|
| **Embedding Model** | `BAAI/bge-base-en-v1.5` — 768-dimensional dense vectors via SentenceTransformers |
| **L2 Normalization** | Embeddings normalized for consistent cosine similarity calculation |
| **pgvector Storage** | Native PostgreSQL vector extension stores all chunk embeddings |
| **HNSW Indexing** | Approximate nearest neighbor index for sub-linear search complexity |
| **Embedding Metadata** | Model name, version, embedding timestamp, and duration tracked per chunk |
| **CPU Inference** | No GPU required — runs efficiently on CPU in production containers |

---

## 🔎 Hybrid Search

| Feature | Details |
|---|---|
| **Semantic Vector Search** | pgvector cosine distance query against 768-dim chunk embeddings |
| **Full-Text Search (FTS)** | PostgreSQL `ts_vector` + `ts_query` for exact keyword matching |
| **Reciprocal Rank Fusion** | RRF algorithm fuses semantic and keyword rankings (k=60 smoothing) |
| **Score Normalization** | Both scores normalized 0→1 before fusion |
| **Similarity Threshold** | Configurable minimum score cutoff to filter irrelevant results |
| **Top-K Results** | Configurable result count (default 5, up to 20) |
| **Document-Scoped Search** | Search within a single document's chunk set |
| **Batch Search** | Multiple queries in a single API request |
| **Search History** | All queries persisted with latency and result count metrics |
| **Search Statistics** | Aggregated query count, avg latency, avg results per user |
| **Redis Result Cache** | 1-hour TTL cache for repeated identical queries |

---

## 🤖 RAG Pipeline

| Feature | Details |
|---|---|
| **Context Retrieval** | Top-K relevant chunks fetched and scored via hybrid search |
| **Token Budget Management** | Chunks trimmed to fit within configurable context window |
| **System Prompt Engineering** | Grounding prompt instructs LLM to: only cite provided context, write citations as `[1]`, think step-by-step |
| **Multi-Provider LLM** | Pluggable provider abstraction: Gemini and OpenAI both supported |
| **Citation Extraction** | Regex parser maps `[N]` citation markers back to source chunk metadata |
| **Source Attribution** | Response includes page numbers, section titles, and chunk indices |
| **Confidence Scoring** | Average semantic similarity score of retrieved sources |
| **Token Accounting** | Prompt tokens, completion tokens, total tokens tracked and stored |
| **Latency Tracking** | End-to-end latency recorded per RAG query |
| **Document-Scoped RAG** | RAG restricted to a single document via `POST /rag/query/document/{id}` |
| **Model Selection** | Runtime selection of `gemini-2.5-flash`, `gemini-2.5-pro`, `gpt-4o-mini` |

---

## 💬 Streaming Chat

| Feature | Details |
|---|---|
| **Server-Sent Events (SSE)** | Real-time token streaming via `text/event-stream` protocol |
| **Session Persistence** | Chat sessions stored with titles and message history |
| **Multi-turn Conversation** | Full message history included in each generation context |
| **Inline Citation Streaming** | Citations extracted mid-stream and included in response metadata |
| **Session Management** | Create, list, retrieve, delete chat sessions |
| **Message Persistence** | User and assistant messages stored with token counts and latency |
| **Live Markdown Rendering** | Frontend renders streamed markdown in real-time |
| **Typing Indicator** | Animated typing state shown during SSE stream receipt |

---

## 🕵️ ReAct AI Agent

| Feature | Details |
|---|---|
| **ReAct Loop** | Reason → Act → Observe loop with configurable max iterations |
| **Tool Registry** | `knowledge_search`, `document_lookup`, `summarize_document` tools |
| **Strict Resource Controls** | Max 5 tool calls per run, 15s per-tool timeout, exponential backoff |
| **Reasoning Extraction** | Step-by-step reasoning parsed from `<reasoning>` XML blocks |
| **Confidence Scoring** | Average retrieval score across all tool calls |
| **Run Persistence** | Full agent run stored: question, final answer, tool call log, latency |
| **Tool Call Logging** | Each tool call recorded with input, output, duration, success |
| **Session Integration** | Agent runs can be linked to chat sessions |

---

## 🖥️ Frontend Application

| Feature | Details |
|---|---|
| **Landing Page** | Hero section, feature cards, Quick Actions navigation, authenticated state |
| **Workspace Dashboard** | Total documents, chunks, conversations, searches; recent activity tables |
| **Document Manager** | Filterable list, status badges, detail view with chunk breakdown |
| **Chat Workspace** | Session sidebar, SSE stream reader, markdown display, citation cards |
| **Semantic Search UI** | Query form, filter controls, scored result cards with metadata |
| **RAG Playground** | Query console, retrieved chunks viewer, citation highlighter, token metrics |
| **AI Agent Workspace** | Query form, reasoning step trace, tool call log, confidence display |
| **Settings Panel** | Interactive form: provider, model, temperature, top-k, system prompt, chunk settings |
| **Upload Workspace** | Drag-and-drop area, file validation, upload progress, status polling |
| **Navigation** | Glassmorphic collapsible sidebar (desktop) + hamburger header (mobile) |
| **Auth Flow** | Login, register, logout with JWT storage and automatic token refresh |
| **Responsive Design** | Full mobile-to-desktop responsive layout |
| **Dark Theme** | Consistent dark UI with gradient accents and glassmorphism |

---

## 🔒 Security

| Feature | Details |
|---|---|
| **HTTPS-ready** | All CORS, CSP, and security headers pre-configured for HTTPS deployment |
| **Content Security Policy** | Strict CSP headers block XSS via script-src restrictions |
| **Security Headers** | X-Frame-Options, X-Content-Type-Options, Referrer-Policy |
| **Non-root Docker containers** | Both backend and frontend run as UID 1001 non-root users |
| **Input Validation** | All request bodies validated with Pydantic V2 strict mode |
| **SQL Injection Prevention** | SQLAlchemy ORM with parameterized queries — no raw SQL |
| **Rate Limiting** | Redis-backed sliding window on auth routes and ingestion endpoints |
| **Secret Management** | `.env` excluded from git; secrets loaded only via environment variables |

---

## ⚙️ Infrastructure & DevOps

| Feature | Details |
|---|---|
| **Multi-stage Docker Builds** | Separate builder and runtime stages for minimal image sizes |
| **Docker Compose Orchestration** | 6 services: PostgreSQL, Redis, Backend, Celery Worker, Celery Beat, Frontend |
| **Health Checks** | All services have `healthcheck` blocks with retry and timeout configuration |
| **Container Dependencies** | `depends_on` with `condition: service_healthy` for startup ordering |
| **Persistent Volumes** | Named Docker volumes for PostgreSQL data and uploaded files |
| **JSON Structured Logging** | Production log format configured for log aggregation tools |
| **Database Migrations** | Alembic version-controlled async migrations |
| **Backup Scripts** | `scripts/backup.sh` and `restore.sh` for PostgreSQL data protection |
| **Pre-commit Hooks** | Ruff linting + Mypy type checking enforced before every commit |

---

## 🧪 Testing

| Feature | Details |
|---|---|
| **Test Isolation** | In-memory aiosqlite database — no external dependencies needed for CI |
| **Async Tests** | pytest-asyncio with full async fixture support |
| **Test Client** | httpx AsyncClient for end-to-end API testing |
| **172 Tests** | Coverage across: auth, documents, chunking, embeddings, retrieval, RAG, chat, agent |
| **Fixture Sharing** | conftest.py provides reusable DB session, HTTP client, and test user fixtures |
