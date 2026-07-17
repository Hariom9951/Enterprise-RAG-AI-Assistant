# API Design Guidelines — Enterprise RAG AI Assistant

This document defines the REST conventions, validation structures, status codes, and exception boundaries for the Enterprise RAG AI Assistant APIs.

---

## 1. REST Conventions

- **Kebab-Case Paths:** All path routes must use lowercase kebab-case (e.g., `/api/v1/auth/refresh-token`).
- **Resource Pluralization:** Route resource targets must use plural nouns (e.g., `/api/v1/users` instead of `/api/v1/user`).
- **No Verb Endpoints:** Avoid verbs in CRUD paths. Prefer HTTP methods to define the action:
  - `POST /api/v1/documents` (Create document)
  - `GET /api/v1/documents/{id}` (Retrieve document)
  - `DELETE /api/v1/documents/{id}` (Delete document)

---

## 2. Request Validation

- **Pydantic Validation:** All request payloads must be defined using Pydantic v2 schemas (`BaseModel`) to validate field presence, data types, string constraints, and patterns.
- **Custom Validators:** Implement validation rules (e.g. email regex, password strength matching, string length trim checks) using `@field_validator`.
- **Automatic 422:** FastAPI automatically catches validation errors and raises a `422 Unprocessable Entity` response. We customize error structures to maintain a consistent API layout.

---

## 3. Response Models

- **Standard Return Schemas:** Endpoints must define a `response_model` parameter inside the decorator to enforce schema compliance and exclude internal attributes (like password hashes).
- **CamelCase Output:** Use snake_case internally but serialize keys to the frontend exactly matching the Pydantic field definitions (ensure consistency with frontend typescript keys).
- **Common Metadata:** Responses containing list elements should use pagination envelopes containing offset, limit, and total count keys.

---

## 4. Error Handling & Consistent Schema

Every error response returned by the API must conform to the following JSON structure:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable summary of what went wrong.",
    "detail": {
      "field_name": "Detailed information about specific fields or debug hints."
    }
  }
}
```

### Core Error Codes:
- `VALIDATION_ERROR` — Invalid request parameters or body (HTTP 422).
- `UNAUTHORIZED` — Expired or invalid authentication tokens (HTTP 401).
- `FORBIDDEN` — Insufficient role permissions (HTTP 403).
- `NOT_FOUND` — Target database record or file not found (HTTP 404).
- `CONFLICT` — Constraint violation, e.g., duplicate email address (HTTP 409).
- `INTERNAL_ERROR` — Unhandled backend exception (HTTP 500).

---

## 5. Status Codes

- `200 OK` — Successful query or record updates.
- `201 Created` — Successful resource creation (e.g., registration).
- `204 No Content` — Successful request with empty response (e.g., resource removal).
- `400 Bad Request` — General invalid input payload.
- `401 Unauthorized` — Missing or expired token (triggers frontend logout/rotation).
- `403 Forbidden` — Valid tokens but insufficient permissions (e.g., non-admin accessing user tables).
- `404 Not Found` — Resource missing.
- `409 Conflict` — Entity already exists (e.g., register duplicate email).
- `422 Unprocessable Entity` — Body parameter validation failures.

---

## 6. Versioning Policy

- **Path Versioning:** The API version is prepended directly in the URL pathway: `/api/v{major}/`.
- **Current Version:** `/api/v1/`.
- **Deprecation Workflow:** When major schema changes occur:
  1. Create `/api/v2/` under a new router module.
  2. Maintain `/api/v1/` as deprecated, forwarding requests to updated service wrappers where possible.
  3. Set a deprecation timestamp on v1 endpoint responses using HTTP headers (`Sunset`, `Deprecation`).
