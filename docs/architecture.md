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

## 7. Future RAG Ingestion & Query Pipeline (Phase 4)

```mermaid
flowchart TD
    subgraph Ingestion Pipeline
        Doc[Upload PDF/Doc] --> Parse[Document Parser]
        Parse --> Chunk[Text Chunking / Recursive Character]
        Chunk --> Embed[Embedding Generator / OpenAI]
        Embed --> Store[PGVector DB Store]
    end

    subgraph Query Pipeline
        Query[User Question] --> QueryEmbed[Question Embedding]
        QueryEmbed --> Search[Semantic Vector Similarity Search]
        Store -->|Similar Chunks| Search
        Search --> Prompt[Formulate Prompt Context]
        Prompt --> LLMCall[LLM Inference]
        LLMCall --> Response[Grounded Answer with Citations]
    end
```

---

## 8. Future AI Agent Architecture (Phase 4+)

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

## 9. Deployment Architecture

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
