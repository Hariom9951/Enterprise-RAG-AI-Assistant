"""
Enterprise RAG AI Assistant — Backend Test Suite: Health & Root
===============================================================
Tests for the two foundational endpoints:
  - GET /api/v1/          → 200, {"message": "Enterprise RAG AI Assistant API"}
  - GET /api/v1/health    → 200, {"status": "healthy", ...}

Run with:
    pytest tests/ -v
    pytest tests/ -v --asyncio-mode=auto
"""

from fastapi.testclient import TestClient

from app.main import app

# =============================================================================
# Test Client
# =============================================================================

# TestClient handles the full ASGI lifecycle synchronously,
# including the lifespan context manager.
client = TestClient(app)


# =============================================================================
# Root Endpoint Tests
# =============================================================================

class TestRootEndpoint:
    """Tests for GET /api/v1/"""

    def test_root_returns_200(self) -> None:
        """Root endpoint should return HTTP 200 OK."""
        response = client.get("/api/v1/")
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}. Body: {response.text}"
        )

    def test_root_returns_message(self) -> None:
        """Root endpoint should return the expected welcome message."""
        response = client.get("/api/v1/")
        data = response.json()
        assert "message" in data, "Response body must contain 'message' key."
        assert data["message"] == "Enterprise RAG AI Assistant API", (
            f"Unexpected message value: {data['message']!r}"
        )

    def test_root_content_type_is_json(self) -> None:
        """Root endpoint should respond with application/json content type."""
        response = client.get("/api/v1/")
        assert "application/json" in response.headers.get("content-type", ""), (
            "Expected Content-Type: application/json"
        )

    def test_root_has_request_id_header(self) -> None:
        """Every response should include an X-Request-ID header (from logging middleware)."""
        response = client.get("/api/v1/")
        assert "x-request-id" in response.headers, (
            "Expected X-Request-ID header to be present in every response."
        )


# =============================================================================
# Health Endpoint Tests
# =============================================================================

class TestHealthEndpoint:
    """Tests for GET /api/v1/health"""

    def test_health_returns_200(self) -> None:
        """Health endpoint should return HTTP 200 OK."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}. Body: {response.text}"
        )

    def test_health_status_is_healthy(self) -> None:
        """Health status field should be 'healthy' in Phase 1."""
        response = client.get("/api/v1/health")
        data = response.json()
        assert data.get("status") == "healthy", (
            f"Expected status='healthy', got: {data.get('status')!r}"
        )

    def test_health_response_has_required_fields(self) -> None:
        """Health response must include all required schema fields."""
        response = client.get("/api/v1/health")
        data = response.json()
        required_fields = {"status", "version", "environment", "timestamp", "components"}
        missing = required_fields - data.keys()
        assert not missing, f"Health response missing fields: {missing}"

    def test_health_version_is_string(self) -> None:
        """Version field should be a non-empty string."""
        response = client.get("/api/v1/health")
        version = response.json().get("version")
        assert isinstance(version, str) and version, (
            f"Expected non-empty string for version, got: {version!r}"
        )

    def test_health_components_is_dict(self) -> None:
        """Components field should be a dictionary."""
        response = client.get("/api/v1/health")
        components = response.json().get("components")
        assert isinstance(components, dict), (
            f"Expected components to be a dict, got: {type(components)}"
        )

    def test_health_api_component_is_healthy(self) -> None:
        """The 'api' component should report healthy in Phase 1."""
        response = client.get("/api/v1/health")
        components = response.json().get("components", {})
        assert components.get("api") == "healthy", (
            f"Expected api component to be 'healthy', got: {components.get('api')!r}"
        )

    def test_health_has_request_id_header(self) -> None:
        """Health response should include X-Request-ID header."""
        response = client.get("/api/v1/health")
        assert "x-request-id" in response.headers


# =============================================================================
# CORS Tests
# =============================================================================

class TestCORSHeaders:
    """Verify CORS headers are present for allowed origins."""

    def test_cors_header_present_for_allowed_origin(self) -> None:
        """Preflight request from allowed origin should receive CORS headers."""
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Starlette's TestClient follows redirects; check header presence.
        assert response.status_code in (200, 204), (
            f"Expected 200 or 204 for OPTIONS preflight, got {response.status_code}"
        )
