# Coding Standards — Enterprise RAG AI Assistant

This document establishes the guidelines and styling expectations for backend (Python) and frontend (TypeScript) development.

---

## 1. Python (Backend) Guidelines

### Naming Conventions
- **Modules & Packages:** lowercase snake_case (e.g. `auth_service.py`).
- **Classes:** PascalCase (e.g. `RequestLoggingMiddleware`).
- **Functions & Methods:** lowercase snake_case (e.g. `verify_password`).
- **Variables & Parameters:** lowercase snake_case (e.g. `access_token_expire_minutes`).
- **Constants:** uppercase SNAKE_CASE (e.g. `API_V1_PREFIX`).

### Typing
- **Type Hints Required:** Every function signature must contain strict type hints for all parameters and return values (e.g., `def create_access_token(subject: str) -> str`).
- **Avoid `Any`:** Never use `Any` where a more specific type exists. If external libraries return untyped values, use `typing.cast` to declare the returned schema.
- **Future Imports:** Always declare `from __future__ import annotations` to support modern type syntax.

### Exceptions
- **Exception Hierarchy:** Inherit from `app.core.exceptions.AppException` (base) or its specialized children (e.g., `UnauthorizedException`, `NotFoundException`).
- **Fail Fast:** Validate inputs early and raise HTTP-translatable exceptions immediately.
- **No Raw Exception Leaks:** Do not allow unhandled library exceptions to bubble up. Catch them and raise a clean `AppException`.

### Logging
- **Loguru Sink:** Use `loguru`'s default `logger` for all server logs. Avoid Python standard `logging`.
- **ASCII Logs:** Ensure log messages use ASCII characters only (no emojis or fancy unicode symbols) to prevent encoding crashes on Windows console pages.
- **Structured Extras:** Use `.bind()` or passing `extra={}` parameters to attach correlation IDs and execution contexts.

### Async Guidelines
- **Non-blocking Operations:** Never use synchronous blockers (e.g., standard `time.sleep()`, synchronous `requests`, or filesystem `open()`) inside async handlers. Use `asyncio.sleep()`, `httpx.AsyncClient()`, or execute blockers inside executor threads.
- **SQLAlchemy Async:** Always execute database requests asynchronously via `await db.execute(...)`.

---

## 2. TypeScript / React (Frontend) Guidelines

### Components
- **Functional Components:** Always write components as functional components using standard `export default function ComponentName()`.
- **Destructured Props:** Explicitly declare and destructure Component props (e.g., `export default function Card({ title, children }: CardProps)`).
- **TypeScript Types:** Never use `any`. Always declare strict types for Component props.

### Hooks
- **Standard Hook Rules:** Only call hooks at the top level of React functions (no conditional hooks, no hooks inside loops).
- **Custom Hooks:** Extract complex state management or side-effects (e.g., fetching profile data, managing authorization timers) into custom hooks named with the `use` prefix.

### State Management
- **Local State:** Use `useState` for component-level UI status (e.g. `showPassword`, `isLoading`).
- **Auth Storage:** Access/Refresh tokens are managed via typed storage helpers (`localStorage` in Phase 2) and accessed via standard context hooks.

### API Layer
- **Centralized Client:** All HTTP fetch transactions must use the `request()` abstraction inside `src/lib/api.ts`.
- **Automatic Headers:** The API client automatically retrieves the access token from storage and appends the `Authorization: Bearer <token>` header if present.
- **Error Propagation:** Always wrap backend queries inside `try...catch` blocks to catch and parse type-safe `ApiError` payloads.
