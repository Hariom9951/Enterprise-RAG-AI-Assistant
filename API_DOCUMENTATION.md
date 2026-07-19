# 📡 API Documentation

> Complete REST API reference for the Enterprise RAG AI Assistant.
>
> Base URL: `http://localhost:8000/api/v1`  
> Interactive docs: `http://localhost:8000/docs` (Swagger UI)

---

## Authentication

All protected endpoints require a Bearer token in the `Authorization` header:
```
Authorization: Bearer <access_token>
```

---

## 🔑 Auth Endpoints

### POST `/auth/register`

Create a new user account.

**Request:**
```json
{
  "full_name": "Hariom Sharma",
  "email": "hariom@example.com",
  "password": "SecurePass@123"
}
```

**Password Policy:** Minimum 8 characters, must contain uppercase, digit, and symbol.

**Response `201 Created`:**
```json
{
  "id": "57daacb91e35496fbc2737166a881ef6",
  "full_name": "Hariom Sharma",
  "email": "hariom@example.com",
  "role": "USER",
  "is_active": true,
  "created_at": "2026-07-19T05:30:00Z"
}
```

**Errors:**
- `409 Conflict` — email already registered
- `422 Unprocessable Entity` — validation failure

---

### POST `/auth/login`

Authenticate and receive JWT tokens.

**Request:**
```json
{
  "email": "hariom@example.com",
  "password": "SecurePass@123"
}
```

**Response `200 OK`:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

### POST `/auth/refresh`

Rotate expired access and refresh tokens.

**Request:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response `200 OK`:** Same structure as `/auth/login`.

---

## 👤 User Endpoints

### GET `/users/me`

Retrieve the authenticated user's profile.

**Headers:** `Authorization: Bearer <token>`

**Response `200 OK`:**
```json
{
  "id": "57daacb91e35496fbc2737166a881ef6",
  "full_name": "Hariom Sharma",
  "email": "hariom@example.com",
  "role": "USER",
  "is_active": true,
  "is_verified": true,
  "created_at": "2026-07-19T05:30:00Z",
  "updated_at": "2026-07-19T05:30:00Z"
}
```

---

## 📄 Document Endpoints

### POST `/documents/upload`

Upload a document for ingestion. Returns immediately; processing happens asynchronously.

**Headers:** `Authorization: Bearer <token>`  
**Content-Type:** `multipart/form-data`

**Form Fields:**
- `file` (required) — PDF, DOCX, or TXT file

**Response `202 Accepted`:**
```json
{
  "id": "a1b2c3d4e5f6...",
  "original_filename": "resume.pdf",
  "stored_filename": "a1b2c3d4-...-resume.pdf",
  "mime_type": "application/pdf",
  "file_size": 245760,
  "sha256_hash": "abc123...",
  "processing_status": "UPLOADED",
  "created_at": "2026-07-19T05:31:00Z"
}
```

---

### GET `/documents/`

List all documents for the authenticated user.

**Query Parameters:**
- `page` (int, default: 1)
- `page_size` (int, default: 20, max: 100)
- `status` (optional) — filter by `UPLOADED`, `QUEUED`, `PROCESSING`, `COMPLETED`, `FAILED`

**Response `200 OK`:**
```json
{
  "items": [
    {
      "id": "a1b2c3d4...",
      "original_filename": "resume.pdf",
      "processing_status": "COMPLETED",
      "file_size": 245760,
      "created_at": "2026-07-19T05:31:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

### GET `/documents/{document_id}`

Get document details including chunk count and processing metadata.

**Response `200 OK`:**
```json
{
  "id": "a1b2c3d4...",
  "original_filename": "resume.pdf",
  "processing_status": "COMPLETED",
  "file_size": 245760,
  "chunk_count": 12,
  "created_at": "2026-07-19T05:31:00Z",
  "updated_at": "2026-07-19T05:32:15Z"
}
```

---

### DELETE `/documents/{document_id}`

Delete a document and all associated chunks and vectors.

**Response `200 OK`:**
```json
{
  "message": "Document deleted successfully",
  "document_id": "a1b2c3d4..."
}
```

---

## 🔍 Search Endpoints

### POST `/search`

Execute a hybrid semantic + keyword search across all user documents.

**Request:**
```json
{
  "query": "machine learning skills and experience",
  "top_k": 5,
  "similarity_threshold": 0.3,
  "search_type": "hybrid",
  "filters": {
    "document_ids": ["a1b2c3d4..."]
  }
}
```

**Search Types:** `hybrid` (default) · `semantic` · `keyword`

**Response `200 OK`:**
```json
{
  "query": "machine learning skills and experience",
  "results": [
    {
      "chunk_id": "chunk-uuid-...",
      "document_id": "a1b2c3d4...",
      "document_name": "resume.pdf",
      "text": "Skills: Python, Scikit-learn, Pandas, NumPy, Docker, FastAPI...",
      "score": 0.847,
      "chunk_index": 2,
      "page_number": 1,
      "section_title": "Technical Skills"
    }
  ],
  "total_results": 1,
  "response_time_ms": 45,
  "search_type": "hybrid"
}
```

---

### GET `/search/history`

Retrieve search audit log for the authenticated user.

**Query Parameters:** `page`, `page_size`

**Response `200 OK`:**
```json
{
  "items": [
    {
      "id": "search-uuid...",
      "query_text": "machine learning skills",
      "search_type": "hybrid",
      "total_results": 3,
      "response_time_ms": 42,
      "created_at": "2026-07-19T05:35:00Z"
    }
  ],
  "total": 1
}
```

---

## 🤖 RAG Endpoints

### POST `/rag/query`

Execute a RAG query — retrieves context chunks and generates a grounded LLM response.

**Request:**
```json
{
  "query": "What is the CGPA and educational background of the candidate?",
  "provider": "gemini",
  "model": "gemini-2.5-flash",
  "top_k": 5,
  "temperature": 0.2,
  "max_tokens": 1000
}
```

**Response `200 OK`:**
```json
{
  "query": "What is the CGPA and educational background?",
  "answer": "Based on the resume, the candidate has a B.Tech in Information Technology from IIIT Bhopal (2023-2027) with a CGPA of 8.23 [1].",
  "citations": [
    {
      "number": 1,
      "document_name": "resume.pdf",
      "chunk_index": 0,
      "page_number": 1,
      "text_snippet": "B.Tech in Information Technology, IIIT Bhopal, 2023-2027, CGPA: 8.23",
      "score": 0.921
    }
  ],
  "provider": "gemini",
  "model": "gemini-2.5-flash",
  "prompt_tokens": 842,
  "completion_tokens": 87,
  "total_tokens": 929,
  "latency_ms": 1243,
  "confidence_score": 0.891
}
```

---

### GET `/rag/models`

List all supported LLM models.

**Response `200 OK`:**
```json
{
  "models": [
    {
      "provider": "gemini",
      "model_id": "gemini-2.5-flash",
      "display_name": "Gemini 2.5 Flash",
      "is_default": true
    },
    {
      "provider": "gemini",
      "model_id": "gemini-2.5-pro",
      "display_name": "Gemini 2.5 Pro"
    },
    {
      "provider": "openai",
      "model_id": "gpt-4o-mini",
      "display_name": "GPT-4o Mini"
    }
  ]
}
```

---

## 💬 Chat Endpoints

### GET `/chat/sessions`

List all chat sessions for the user.

**Response `200 OK`:**
```json
{
  "items": [
    {
      "id": "session-uuid...",
      "title": "Questions about resume",
      "message_count": 6,
      "created_at": "2026-07-19T05:40:00Z",
      "updated_at": "2026-07-19T05:45:00Z"
    }
  ]
}
```

---

### POST `/chat/sessions`

Create a new chat session.

**Request:**
```json
{
  "title": "Resume Analysis"
}
```

**Response `201 Created`:**
```json
{
  "id": "session-uuid...",
  "title": "Resume Analysis",
  "created_at": "2026-07-19T06:00:00Z"
}
```

---

### POST `/chat/sessions/{session_id}/stream`

Stream a chat response using Server-Sent Events.

**Headers:**
- `Authorization: Bearer <token>`
- `Accept: text/event-stream`

**Request:**
```json
{
  "message": "What programming languages does the candidate know?",
  "provider": "gemini",
  "model": "gemini-2.5-flash",
  "temperature": 0.3
}
```

**SSE Stream Format:**
```
event: token
data: {"token": "Based"}

event: token
data: {"token": " on"}

event: citation
data: {"number": 1, "document_name": "resume.pdf", "page": 1}

event: done
data: {"message_id": "msg-uuid...", "total_tokens": 124, "latency_ms": 980}
```

---

## 🕵️ Agent Endpoints

### POST `/agent/chat`

Run a ReAct agent query with tool-calling capability.

**Request:**
```json
{
  "question": "Find all the projects mentioned in the resume and summarize their technical details.",
  "provider": "gemini",
  "model": "gemini-2.5-flash"
}
```

**Response `200 OK`:**
```json
{
  "question": "Find all the projects mentioned...",
  "answer": "The resume mentions 3 projects:\n1. **Medical Diagnosis AI** — FastAPI, scikit-learn [1]\n2. **RAG Assistant** — FastAPI, pgvector [2]\n3. **MLflow Pipeline** — Docker, MLflow [1]",
  "reasoning_summary": "I searched the knowledge base for 'projects' and found 2 relevant chunks. I then retrieved document details to get complete project descriptions.",
  "citations": [...],
  "confidence_score": 0.876,
  "tool_calls": [
    {
      "tool_name": "knowledge_search",
      "input": {"query": "projects portfolio"},
      "output": "Found 3 matching chunks",
      "duration_ms": 87
    }
  ],
  "total_tool_calls": 1,
  "total_latency_ms": 2341,
  "provider": "gemini",
  "model": "gemini-2.5-flash"
}
```

---

## 📊 Dashboard Endpoints

### GET `/dashboard/statistics`

Retrieve workspace aggregated statistics.

**Response `200 OK`:**
```json
{
  "total_documents": 5,
  "total_chunks": 47,
  "total_conversations": 12,
  "total_searches": 38,
  "total_rag_queries": 22,
  "total_agent_runs": 8,
  "avg_search_latency_ms": 43.2,
  "avg_rag_latency_ms": 1320.5,
  "recent_uploads": [
    {
      "id": "a1b2c3d4...",
      "filename": "resume.pdf",
      "status": "COMPLETED",
      "uploaded_at": "2026-07-19T05:31:00Z"
    }
  ],
  "recent_searches": [
    {
      "query": "machine learning experience",
      "results": 3,
      "timestamp": "2026-07-19T05:35:00Z"
    }
  ]
}
```

---

## ❤️ Health Endpoint

### GET `/health`

System health check — verifies API, database, and service status.

**Response `200 OK`:**
```json
{
  "status": "healthy",
  "version": "0.2.0",
  "environment": "production",
  "database": "connected",
  "timestamp": "2026-07-19T06:00:00Z"
}
```

---

## Error Response Format

All errors follow a consistent structure:

```json
{
  "detail": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "Document with ID 'abc123' not found",
    "timestamp": "2026-07-19T06:00:00Z"
  }
}
```

| HTTP Status | Meaning |
|---|---|
| `200` | Success |
| `201` | Created |
| `202` | Accepted (async job queued) |
| `400` | Bad Request — invalid input |
| `401` | Unauthorized — missing or invalid token |
| `403` | Forbidden — insufficient permissions |
| `404` | Not Found |
| `409` | Conflict — duplicate resource |
| `422` | Unprocessable Entity — validation error |
| `429` | Too Many Requests — rate limited |
| `500` | Internal Server Error |
