# Developer Portfolio Guide: Enterprise RAG AI Assistant

This guide is curated for developers, engineers, and hiring managers. It walks through the core implementation details, architectural sequences, and source code pathways of the **Enterprise RAG AI Assistant**.

---

## 1. Architectural Workflows & Sequences

### Document Ingestion Sequence

The following diagram illustrates the sequence of asynchronous events triggered when a user uploads a document:

```mermaid
sequenceDiagram
    autonumber
    actor User as Web Client
    participant API as FastAPI Backend
    participant DB as SQLite / PostgreSQL
    participant Redis as Redis Queue
    participant Worker as Celery Worker
    participant FS as Storage Volume

    User->>API: POST /api/v1/documents/upload (Multipart File)
    API->>DB: INSERT into documents (status="PENDING")
    API->>FS: Save raw file to storage path
    API->>Redis: Publish task "process_document" (document_id)
    API-->>User: HTTP 201 Created (document_id, status="PENDING")

    Worker->>Redis: Fetch task
    Worker->>FS: Load raw file
    Worker->>Worker: Parse layout (fitz / python-docx)
    Worker->>Worker: Run semantic chunker (tiktoken)
    Worker->>Worker: Generate embeddings (SentenceTransformers)
    Worker->>DB: INSERT into chunks (embeddings, metadata)
    Worker->>DB: UPDATE documents (status="COMPLETED")
    Worker-->>User: (Optional) WebSocket / Polling status changes
```

---

## 2. Conversational RAG Query Sequence

This diagram shows how a user's question is resolved using the hybrid retrieval and streamed response pipeline:

```mermaid
sequenceDiagram
    autonumber
    actor User as Web Client
    participant API as FastAPI Backend
    participant Cache as Redis Cache
    participant DB as SQLite / PostgreSQL
    participant LLM as Google Gemini API

    User->>API: POST /api/v1/rag/query (question)
    API->>Cache: Check cached response for question hash
    alt Cache Hit
        Cache-->>API: Return cached answer & citation data
        API-->>User: Return response directly
    else Cache Miss
        API->>DB: Run Hybrid Search Query (FTS + Vector cosine distance)
        DB-->>API: Return top-K relevant text chunks with metadata
        API->>API: Assemble LLM System Context & Prompt
        API->>LLM: Stream generated response (ReAct / ground response)
        LLM-->>API: Token chunks with inline citations
        API->>API: Parse inline citation markers
        API-->>User: Stream SSE packet (text segment + parsed citations)
        API->>Cache: Save answer & citation metadata to Cache
        API->>DB: Log query to rag_queries
    end
```

---

## 3. Database Schema Blueprint

```mermaid
erDiagram
    users ||--o{ documents : owns
    users ||--o{ search_queries : searches
    users ||--o{ rag_queries : asks
    users ||--o{ chat_sessions : thread
    users ||--o{ agent_runs : executes
    documents ||--|| processed_documents : text
    documents ||--o{ chunks : contains
    chat_sessions ||--o{ chat_messages : message
    agent_runs ||--o{ agent_tool_calls : runs
```

### Table Definitions

#### 1. `users`
* `id` (UUID, PK)
* `email` (VARCHAR, Unique, Index)
* `hashed_password` (VARCHAR)
* `full_name` (VARCHAR)
* `role` (VARCHAR: admin, user)
* `is_active` (BOOLEAN)

#### 2. `documents`
* `id` (UUID, PK)
* `user_id` (UUID, FK → `users.id`)
* `original_filename` (VARCHAR)
* `stored_filename` (VARCHAR)
* `mime_type` (VARCHAR)
* `file_size` (INTEGER)
* `sha256_hash` (VARCHAR)
* `storage_path` (VARCHAR)
* `processing_status` (VARCHAR: PENDING, PROCESSING, COMPLETED, FAILED)

#### 3. `processed_documents`
* `id` (UUID, PK)
* `document_id` (UUID, FK → `documents.id`, Unique)
* `raw_text` (TEXT)
* `clean_text` (TEXT)
* `language` (VARCHAR)
* `page_count` (INTEGER)
* `word_count` (INTEGER)
* `character_count` (INTEGER)
* `processing_time` (FLOAT)

#### 4. `chunks`
* `id` (UUID, PK)
* `document_id` (UUID, FK → `documents.id`)
* `chunk_index` (INTEGER)
* `text` (TEXT)
* `token_count` (INTEGER)
* `embedding` (VECTOR 768)
* `page_number` (INTEGER)
* `metadata` (JSON)

---

## 4. Source Code Blueprint

Here are the key modules implementing our design patterns:

### Core Configurations
* [settings.py](file:///d:/Enterprise%20RAG%20AI%20Assistant/backend/app/config/settings.py): Single source of truth settings parser using `pydantic-settings`.
* [database.py](file:///d:/Enterprise%20RAG%20AI%20Assistant/backend/app/db/session.py): SQLAlchemy async session factory and engine setups.

### Document Processing Services
* [fitz_processor.py](file:///d:/Enterprise%20RAG%20AI%20Assistant/backend/app/processors/pdf_processor.py): Layout-aware PDF text parsing.
* [chunker.py](file:///d:/Enterprise%20RAG%20AI%20Assistant/backend/app/services/chunking_service.py): Semantic recursive tiktoken splitting.
* [embedder.py](file:///d:/Enterprise%20RAG%20AI%20Assistant/backend/app/services/embedding_service.py): Batch embedding execution using SentenceTransformers.

### Retrieval & Generation
* [retrieval.py](file:///d:/Enterprise%20RAG%20AI%20Assistant/backend/app/services/retrieval_service.py): Hybrid search with Reciprocal Rank Fusion.
* [rag_query.py](file:///d:/Enterprise%20RAG%20AI%20Assistant/backend/app/api/v1/endpoints/rag.py): Grounded RAG answering with SSE streams.
* [agent_service.py](file:///d:/Enterprise%20RAG%20AI%20Assistant/backend/app/agents/agent_service.py): ReAct tool-calling loop runtime and constraints.
