# Architectural Blueprint — Enterprise RAG AI Assistant

This document outlines the system architecture, authentication flows, data layers, and future engineering designs for the Enterprise RAG AI Assistant.

---

## 1. System Architecture

The application is structured as a decoupled, multi-tier system designed to support secure access and low-latency document processing:

```mermaid
graph TD
    Client[Next.js Client :3000] -->|HTTP / API v1| Nginx[Nginx Reverse Proxy :80]
    Nginx -->|Route Request| FastAPI[FastAPI Backend :8000]
    FastAPI -->|Queries| Postgres[(PostgreSQL DB :5432)]
    FastAPI -->|Caching / Session| Redis[(Redis Cache :6379)]
    FastAPI -->|Semantic Search| VectorDB[(PGVector Store)]
    FastAPI -->|API Calls| LLM[LLM Provider API / OpenAI / Anthropic]
```

---

## 2. Backend Architecture

The backend is built with FastAPI following a clean service-oriented architecture:

```mermaid
sequenceDiagram
    participant User as Client
    participant Main as app/main.py
    participant Route as api/v1/endpoints
    participant Dep as app/dependencies
    participant Serv as app/services
    participant Model as app/models
    participant DB as Database (SQLAlchemy)

    User->>Main: HTTP Request
    Main->>Dep: Resolve Dependant Injections
    Dep->>DB: get_db() / Current User Verification
    DB-->>Dep: Session / User Record
    Dep-->>Route: Inject Context
    Route->>Serv: Call Business Logic
    Serv->>Model: CRUD Operations
    Model->>DB: Execute Query
    DB-->>Serv: Database Result
    Serv-->>Route: Return Service Model
    Route-->>User: Pydantic Serialised Response (JSON)
```

---

## 3. Frontend Architecture

The frontend uses Next.js 15 App Router, TypeScript, and Tailwind CSS.
- **Route Groups:** Auth views are grouped under `(auth)/` to share layout decorators and gradients.
- **API Client:** Centrally structured client (`lib/api.ts`) managing automatic bearer token injection and routing redirects to `/login` upon HTTP `401 Unauthorized` responses.
- **State Management:** Uses React 19 hooks and local state for modular form controls, relying on local storage cache configurations for JWT pairs.

---

## 4. Authentication Flow

Authentication is stateless and uses JWT (JSON Web Tokens) with a secure **Token Rotation** mechanism to mitigate token replay attacks:

```mermaid
sequenceDiagram
    actor Client
    participant AuthAPI as POST /auth/login
    participant UserSvc as User Service
    participant JWT as security.py
    
    Client->>AuthAPI: Send Credentials (email, password)
    AuthAPI->>UserSvc: Fetch user and verify bcrypt hash
    UserSvc-->>AuthAPI: User record (active=true)
    AuthAPI->>JWT: Generate JWT Token pair
    JWT-->>AuthAPI: return access_token (30m) & refresh_token (7d)
    AuthAPI-->>Client: HTTP 200 with tokens
    
    Note over Client, JWT: Token Expiration & Rotation
    
    Client->>AuthAPI: POST /auth/refresh (send refresh_token)
    AuthAPI->>JWT: Verify refresh signature & claim
    JWT-->>AuthAPI: Valid token payload
    AuthAPI->>UserSvc: Load user profile
    UserSvc-->>AuthAPI: User record (active=true)
    AuthAPI->>JWT: Generate NEW Access + NEW Refresh tokens (rotation)
    JWT-->>AuthAPI: return new token pair
    AuthAPI-->>Client: HTTP 200 with rotated tokens
```

---

## 5. Database Layer

- **SQLAlchemy 2.0 Async:** The database driver utilizes asynchronous connection factories (`async_sessionmaker[AsyncSession]`) to avoid blocking thread pools.
- **Native Types:** Restores native PostgreSQL types like `Uuid` and `Enum` for optimum index mapping, while abstracting fallbacks via SQLAlchemy column conversions on SQLite when executing tests.
- **Lifespan Integration:** Connection engine pool initialization is verified on startup and fully disposed on shutdown inside FastAPI's lifespan configuration.

---

## 6. Service Layer

The service layer contains the pure functional computations and CRUD queries of the system.
- **Separation of Concerns:** Route handlers are lightweight and perform request deserialization, dependency resolution, and response styling.
- **Transaction boundary:** Services flush data to the database session but do **NOT** commit it. Database session transactions are managed by the session generator middleware (`get_db`) to guarantee rollback safety across the request lifecycle.

---

## 7. Document Ingestion, Extraction & Semantic Chunking Pipeline

```mermaid
flowchart TD
    subgraph Ingestion & Chunking Pipeline
        Doc[Upload PDF/DOCX/TXT] --> Parser[Document Parsers / PyMuPDF & python-docx]
        Parser --> ExtractedText[Extracted Raw Text]
        ExtractedText --> CeleryTask[Celery Background Worker]
        CeleryTask --> Chunker[Semantic Chunking / ChunkingService]
        Chunker --> RecursiveSplit[Recursive Token Splitter / tiktoken]
        RecursiveSplit --> Enrich[Metadata Enrichment / Headers & Pages]
        Enrich --> Store[PostgreSQL / Chunk DB Index]
    end
```

- **Document Ingestion:** Documents are securely uploaded, metadata (original filename, sha256_hash, mime_type, file_size) saved, and stored on persistent disk storage.
- **Asynchronous Pipeline:** Celery workers manage the text extraction and semantic chunking pipeline in the background using Redis task brokers.
- **Recursive Semantic Splitting:** Text chunks are created respecting a max token count using `tiktoken` to count tokens. The text is recursively split by page breaks (`\x0c`), Markdown headings, paragraphs, sentences, and words.
- **Enrichment & Context:** Chunks inherit global document properties, track their page numbers, section headers, and reading order indexes.

---

## 8. Semantic Retrieval Engine (Phase 8)

The Retrieval Engine processes queries, generates embeddings, queries the vector database, filters metadata, and ranks results.

```mermaid
flowchart TD
    subgraph Retrieval Pipeline
        Query[User Input Query] --> EmbedService[EmbeddingService / embed_batch]
        EmbedService --> QueryVector[Query Vector 768d]
        QueryVector --> PGVector[PostgreSQL Cosine Similarity <=> Index Scan]
        QueryVector --> SQLiteFallback[SQLite Fallback / NumPy Cosine Sim]
        Query --> KeywordSearch[FTS Keyword Search / ILIKE matches]
        PGVector --> SemanticCandidates[Semantic Chunks List]
        SQLiteFallback --> SemanticCandidates
        KeywordSearch --> KeywordCandidates[Keyword Chunks List]
        SemanticCandidates & KeywordCandidates --> RRFFusion[Reciprocal Rank Fusion RRF]
        RRFFusion --> Dedup[Duplicate Removal by chunk.id]
        Dedup --> Paginate[Offset Pagination Slice]
        Paginate --> ScaleScore[Score Normalization to 0-1]
        ScaleScore --> Results[Sorted SearchResultItems]
    end
```

### Key Components

- **Cosine Similarity Search**: PostgreSQL `pgvector` calculates distance using `<=>` operator (cosine distance). The similarity score is calculated as `1.0 - distance`.
- **HNSW Indexing**: Optimizes pgvector searches with Hierarchical Navigable Small World graphs using the `vector_cosine_ops` operator class, providing sub-millisecond query execution.
- **Reciprocal Rank Fusion (RRF)**: Merges semantic results and keyword results by score rankings using:
  $$RRF(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}$$
  where $k = 60$ and $r_m(d)$ is the rank of document $d$ in system $m$.
- **Score Normalization**: Scales cosine similarities from range `[-1.0, 1.0]` to `[0.0, 1.0]` using `(score + 1.0) / 2.0`, providing a clean threshold pruning range for users.
- **Offset Pagination**: Optimized database scan using `.offset(offset).limit(top_k)` on PostgreSQL, and in-memory slicing on combined hybrid results.
- **Batch Retrieval**: Evaluates a list of input queries concurrently or sequentially to support advanced multi-hop queries.

### Performance Considerations
- **Index Scans**: Native HNSW indices in PostgreSQL ensure that search query scaling is $O(\log N)$ rather than $O(N)$ sequential table scans.
- **Deduplication**: Filters duplicate chunks at retrieval time, optimizing network overhead and context window limits.

---

---

## 9. Enterprise Retrieval-Augmented Generation Pipeline (Phase 9)

The RAG Pipeline aggregates semantic retrieval, custom reranking, token context assembly, and LLM text generation to deliver fully grounded answers with citations.

### Request Flow & Sequence

```mermaid
sequenceDiagram
    participant Client as Next.js Client
    participant API as POST /api/v1/rag/query
    participant RAG as RAGService
    participant ST as SentenceTransformers
    participant DB as PGVector DB
    participant LLM as LLMProvider (Gemini/OpenAI/Ollama)
    participant Log as RagQuery (DB)

    Client->>API: Send question + configurations
    API->>RAG: execute_rag(question)
    RAG->>ST: embed_batch(question)
    ST-->>RAG: Query vector (768d)
    RAG->>DB: Execute hybrid index scan (pgvector)
    DB-->>RAG: Matching text chunks
    RAG->>RAG: Freshness & Priority Reranking
    RAG->>RAG: Context Token Budgeting (Tiktoken)
    RAG->>LLM: POST generateContent / chat/completions
    LLM-->>RAG: Answer with citations [1], [2]
    RAG->>RAG: Regex extract & map citations
    RAG->>Log: Insert query log entry
    Log-->>RAG: Log committed
    RAG-->>API: Return grounded response payload
    API-->>Client: Display answer + cited chunks
```

### Provider Abstraction Interface

The system decouples the LLM provider from the service execution layers via an abstract base class `LLMProvider`. Concrete providers utilize direct HTTP calls to avoid heavy library dependency chains:
- **Google Gemini**: Hits `/models/gemini-1.5-flash:generateContent` using structured systemInstruction.
- **OpenAI**: Hits chat completions `/v1/chat/completions` using system role messages.
- **Local/Ollama**: Hits local endpoint `/chat/completions` via local model hosts.

### Prompt Engineering Strategy

Prompt templates enforce grounding and citation mapping:
1. **Context Passages Formatting**: Context chunks are appended with unique numeric indices:
   `--- Chunk [1] --- Document: proposal.pdf Page: 3 Content: ...`
2. **System Prompt Directives**: Instructs the model:
   - Answer **ONLY** using the supplied context passages.
   - If information is missing, clearly state that. Do not hallucinate or guess.
   - Append citation brackets `[index]` (e.g. `[1]`) at the end of sentences that use facts from that chunk.

### Citation Pipeline

1. **Generation**: The LLM outputs citation tags like `[1]` in its response.
2. **Extraction**: The RAG service executes a regular expression `\[(\d+)\]` on the response text.
3. **Lookup**: Parsed indices are mapped back to the active chunks list to extract document title, page number, section title, and raw text segment.
4. **Tooltips/Highlights**: The Next.js client renders citation tags as interactive UI badges. Clicking a badge highlights and scrolls to the source document chunk reference.

### Deployment & Environment Requirements

Configure the following variables in the deployment environment:
- `LLM_PROVIDER`: `gemini` (default), `openai`, or `ollama`.
- `GEMINI_API_KEY`: API Key for Google Gemini API.
- `OPENAI_API_KEY`: API Key for OpenAI completions.
- `RAG_TOP_K`: Number of context chunks to pull (default: `5`).
- `RAG_MAX_CONTEXT_TOKENS`: Tiktoken count limit (default: `4000`).
- `RAG_TEMPERATURE`: LLM generation randomness (default: `0.2`).
- `RAG_MAX_OUTPUT_TOKENS`: Max generated tokens (default: `1000`).

---

## 10. Future AI Agent Architecture (Phase 10)

For complex searches, the system will leverage a tool-calling AI agent loop:

```mermaid
stateDiagram-v2
    [*] --> InputQuery
    InputQuery --> EvaluateTask: Agent evaluates request
    EvaluateTask --> NeedTool: Requires facts/documents?
    NeedTool --> CallVectorDB: Query PGVector similarity tool
    CallVectorDB --> FeedContext: Returns text passages
    FeedContext --> EvaluateTask
    NeedTool --> DirectAnswer: Direct answer possible
    DirectAnswer --> [*]
```

---

## 11. Deployment Architecture

For scaling, Nginx load balances traffic across multiple stateless Docker backend nodes:

```mermaid
graph LR
    User[Web Client] -->|HTTPS| Nginx[Nginx SSL / Proxy]
    Nginx --> Backend1[FastAPI Node 1]
    Nginx --> Backend2[FastAPI Node 2]
    Backend1 --> DB[(PostgreSQL / PgVector)]
    Backend2 --> DB
    Backend1 --> Cache[(Redis Cache)]
    Backend2 --> Cache
```
