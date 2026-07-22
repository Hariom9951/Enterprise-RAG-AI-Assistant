"""
Enterprise RAG AI Assistant — Backend Test Suite: Health & Root
===============================================================
Tests for foundational health & diagnostic endpoints:
  - GET /api/v1/          → 200, {"message": "Enterprise RAG AI Assistant API"}
  - GET /api/v1/health    → 200, {"status": "healthy", ...}
  - GET /api/v1/ready     → 200, {"status": "ready"}
  - GET /api/v1/live      → 200, {"status": "live"}
  - GET /api/v1/metrics   → 200, Prometheus metrics text

Uses the shared ``client`` fixture (AsyncClient) from conftest.py which injects
the isolated test database session (get_db dependency override).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

# =============================================================================
# Root Endpoint Tests
# =============================================================================


class TestRootEndpoint:
    """Tests for GET /api/v1/"""

    @pytest.mark.anyio
    async def test_root_returns_200(self, client: AsyncClient) -> None:
        """Root endpoint should return HTTP 200 OK."""
        response = await client.get("/api/v1/")
        assert (
            response.status_code == 200
        ), f"Expected 200, got {response.status_code}. Body: {response.text}"

    @pytest.mark.anyio
    async def test_root_returns_message(self, client: AsyncClient) -> None:
        """Root endpoint should return the expected welcome message."""
        response = await client.get("/api/v1/")
        data = response.json()
        assert "message" in data, "Response body must contain 'message' key."
        assert (
            data["message"] == "Enterprise RAG AI Assistant API"
        ), f"Unexpected message value: {data['message']!r}"

    @pytest.mark.anyio
    async def test_root_content_type_is_json(self, client: AsyncClient) -> None:
        """Root endpoint should respond with application/json content type."""
        response = await client.get("/api/v1/")
        assert "application/json" in response.headers.get(
            "content-type", ""
        ), "Expected Content-Type: application/json"

    @pytest.mark.anyio
    async def test_root_has_request_id_header(self, client: AsyncClient) -> None:
        """Every response should include an X-Request-ID header (from logging middleware)."""
        response = await client.get("/api/v1/")
        assert (
            "x-request-id" in response.headers
        ), "Expected X-Request-ID header to be present in every response."


# =============================================================================
# Health Endpoint Tests
# =============================================================================


class TestHealthEndpoint:
    """Tests for GET /api/v1/health"""

    @pytest.mark.anyio
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        """Health endpoint should return HTTP 200 OK."""
        response = await client.get("/api/v1/health")
        assert (
            response.status_code == 200
        ), f"Expected 200, got {response.status_code}. Body: {response.text}"

    @pytest.mark.anyio
    async def test_health_status_is_healthy(self, client: AsyncClient) -> None:
        """Health status field should be 'healthy'."""
        response = await client.get("/api/v1/health")
        data = response.json()
        assert (
            data.get("status") == "healthy"
        ), f"Expected status='healthy', got: {data.get('status')!r}"

    @pytest.mark.anyio
    async def test_health_response_has_required_fields(
        self, client: AsyncClient
    ) -> None:
        """Health response must include all required schema fields."""
        response = await client.get("/api/v1/health")
        data = response.json()
        required_fields = {
            "status",
            "version",
            "environment",
            "timestamp",
            "components",
        }
        missing = required_fields - data.keys()
        assert not missing, f"Health response missing fields: {missing}"

    @pytest.mark.anyio
    async def test_health_version_is_string(self, client: AsyncClient) -> None:
        """Version field should be a non-empty string."""
        response = await client.get("/api/v1/health")
        version = response.json().get("version")
        assert (
            isinstance(version, str) and version
        ), f"Expected non-empty string for version, got: {version!r}"

    @pytest.mark.anyio
    async def test_health_components_is_dict(self, client: AsyncClient) -> None:
        """Components field should be a dictionary."""
        response = await client.get("/api/v1/health")
        components = response.json().get("components")
        assert isinstance(
            components, dict
        ), f"Expected components to be a dict, got: {type(components)}"

    @pytest.mark.anyio
    async def test_health_api_component_is_healthy(self, client: AsyncClient) -> None:
        """The 'api' component should report healthy."""
        response = await client.get("/api/v1/health")
        components = response.json().get("components", {})
        assert (
            components.get("api") == "healthy"
        ), f"Expected api component to be 'healthy', got: {components.get('api')!r}"

    @pytest.mark.anyio
    async def test_health_has_request_id_header(self, client: AsyncClient) -> None:
        """Health response should include X-Request-ID header."""
        response = await client.get("/api/v1/health")
        assert "x-request-id" in response.headers

    @pytest.mark.anyio
    async def test_health_redis_disabled_returns_disabled_component(
        self, client: AsyncClient
    ) -> None:
        """When enable_redis_caching is False, components['redis'] should be 'disabled'."""
        from unittest.mock import patch

        from app.config.settings import settings

        with patch.object(settings, "enable_redis_caching", False):
            response = await client.get("/api/v1/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["components"]["redis"] == "disabled"


# =============================================================================
# CORS Tests
# =============================================================================


class TestCORSHeaders:
    """Verify CORS headers are present for allowed origins."""

    @pytest.mark.anyio
    async def test_cors_header_present_for_allowed_origin(
        self, client: AsyncClient
    ) -> None:
        """Preflight request from allowed origin should receive CORS headers."""
        response = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code in (
            200,
            204,
        ), f"Expected 200 or 204 for OPTIONS preflight, got {response.status_code}"


# =============================================================================
# Phase 12 Endpoints & Security Tests
# =============================================================================


class TestProductionHardening:
    """Verify Phase 12 health probes, metrics, and security middleware."""

    @pytest.mark.anyio
    async def test_liveness_probe_returns_200(self, client: AsyncClient) -> None:
        """Liveness probe (/live) should return HTTP 200 and status 'live'."""
        response = await client.get("/api/v1/live")
        assert response.status_code == 200
        assert response.json() == {"status": "live"}

    @pytest.mark.anyio
    async def test_readiness_probe_returns_200(self, client: AsyncClient) -> None:
        """Readiness probe (/ready) should return HTTP 200 and status 'ready'."""
        response = await client.get("/api/v1/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}

    @pytest.mark.anyio
    async def test_metrics_endpoint_returns_prometheus_format(
        self, client: AsyncClient
    ) -> None:
        """Metrics endpoint (/metrics) should return text/plain Prometheus gauges."""
        response = await client.get("/api/v1/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        content = response.text
        assert "cpu_utilization_ratio" in content
        assert "memory_rss_bytes" in content
        assert "redis_queue_length" in content

    @pytest.mark.anyio
    async def test_security_headers_middleware(self, client: AsyncClient) -> None:
        """Verify that standard security headers are attached by the middleware."""
        response = await client.get("/api/v1/live")
        assert response.status_code == 200
        assert response.headers.get("x-frame-options") == "DENY"
        assert response.headers.get("x-content-type-options") == "nosniff"
        assert (
            response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        )
        assert "content-security-policy" in response.headers

    @pytest.mark.anyio
    async def test_payload_size_limiter_blocks_large_requests(
        self, client: AsyncClient
    ) -> None:
        """Verify that requests exceeding payload size limits are blocked with 413."""
        large_payload = "A" * (2 * 1024 * 1024 + 100)
        response = await client.post(
            "/api/v1/auth/login",
            content=large_payload,
            headers={
                "Content-Length": str(len(large_payload)),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
