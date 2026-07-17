# Security Checklist & Guidelines — Enterprise RAG AI Assistant

This document outlines the security controls, authentication safeguards, data validation rules, and vulnerability checklists implemented across the system.

---

## 1. JWT (JSON Web Tokens) Safeguards
- [ ] **Short Access TTL:** Access tokens must expire within **30 minutes** maximum.
- [ ] **Long Refresh TTL:** Refresh tokens expire in **7 days** and must reside in storage rotation pools.
- [ ] **Token Rotation:** Re-issuing an access token rotates the associated refresh token. Old refresh tokens are immediately revoked.
- [ ] **Type Discriminator:** Access and refresh payloads must contain a `type` claim (`"access"` or `"refresh"`) checked during signature validation to prevent token confusion attacks.

---

## 2. RBAC (Role-Based Access Control)
- [ ] **Role Claims:** Encrypt role claims (`"user"`, `"admin"`) directly inside the access token payload.
- [ ] **Route Guards:** Protect access to user directories and system stats using FastAPI dependencies (`admin_required`).
- [ ] **Principle of Least Privilege:** Default user registrations are assigned the `"user"` role. Admin privileges require explicit database flag updates.

---

## 3. Secrets Management
- [ ] **No Hardcoded Secrets:** All credentials, encryption keys, and external API tokens are loaded from system environment files.
- [ ] **Secure Default Warnings:** Pydantic configuration settings throw visible startup alerts if default keys are loaded in staging/production.
- [ ] **Encryption Strength:** Use `HS256` or asymmetric `RS256` keys with cryptographically strong random seeds (minimum 32-byte hex hashes).

---

## 4. Rate Limiting (Phase 3 readiness)
- [ ] **Redis Backend:** Configure standard API throttling using Redis cache stores.
- [ ] **Route Limits:** General endpoint limits:
  - Login/Register: 5 requests per minute per IP.
  - Documents Query: 60 requests per minute per user.
  - Chat Queries: 30 requests per minute per user.

---

## 5. Input Validation (OWASP A03:2021)
- [ ] **Pydantic Schemas:** Explicitly filter all endpoint inputs through Pydantic schemas. Strip, clean, and validate inputs before service calls.
- [ ] **Strong Regular Expressions:** Enforce character check matching on registration usernames, emails, and passwords to prevent script execution payloads.

---

## 6. Secure File Uploads (Phase 4 readiness)
- [ ] **Size Limitations:** Reject uploaded documents exceeding **50MB** to prevent server denial-of-service.
- [ ] **MIME-Type Whitelisting:** Enforce strict checks on document types. Allow only `.pdf`, `.docx`, `.txt`, and `.md` formats.
- [ ] **Path Traversal Protection:** Sanitize filenames using secure mapping utilities (e.g., hash naming patterns) before writing files to local storage blocks.

---

## 7. SQL Injection Prevention (OWASP A03:2021)
- [ ] **Avoid Raw SQL:** Never write concatenated SQL queries. Always compile statements using SQLAlchemy's expression engine.
- [ ] **Parameter Binding:** Enable automatic parameter binding for database operations via SQLAlchemy 2.0 mapped objects.

---

## 8. XSS & CSRF Mitigation
- [ ] **Next.js Escaping:** React automatically escapes inputs, mitigating cross-site scripting vulnerabilities.
- [ ] **Secure Storage Cookies:** Move JWT refresh tokens from `localStorage` to `httpOnly` secure cookies in production (Phase 5 plan) to block client-side access.
- [ ] **CORS Restriction:** Restrict backend Allowed Origins to verified client domains in production. Avoid wildcard `*` settings.

---

## 9. OWASP Top 10 Reference Matrix

| Category | Control Implementation |
|---|---|
| **A01:2021-Broken Access Control** | FastAPI Route guards (`admin_required`), strict validation of user ownership on models. |
| **A02:2021-Cryptographic Failures** | Bcrypt password hashing, HS256 JWT signatures. |
| **A03:2021-Injection** | Parametrized SQLAlchemy 2.0 ORM queries. |
| **A04:2021-Insecure Design** | Separation of concerns, clean service architecture. |
| **A05:2021-Security Misconfiguration** | Disabling FastAPI/Swagger docs in production environments. |
| **A07:2021-Identification & Auth Failures** | Anti-enumeration error messages on credentials failure. |
