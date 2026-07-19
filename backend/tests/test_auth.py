"""
Enterprise RAG AI Assistant — Auth Endpoint Tests (Phase 2)
============================================================
Integration tests for:
  - POST /api/v1/auth/register
  - POST /api/v1/auth/login
  - POST /api/v1/auth/refresh
  - GET  /api/v1/users/me

Uses the in-memory SQLite test database configured in conftest.py.
Each test is fully isolated — no data persists between tests.

Run with:
    pytest tests/test_auth.py -v
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from tests.conftest import VALID_USER

# All tests in this module are async
pytestmark = pytest.mark.asyncio


# =============================================================================
# Helpers
# =============================================================================


async def _register(client: AsyncClient, data: dict[str, Any] | None = None) -> Any:
    """Register a user and return the HTTP response."""
    payload = data or VALID_USER.copy()
    return await client.post("/api/v1/auth/register", json=payload)


async def _login(client: AsyncClient, data: dict[str, Any] | None = None) -> Any:
    """Login and return the HTTP response."""
    payload = {
        "email": (data or VALID_USER)["email"],
        "password": (data or VALID_USER)["password"],
    }
    return await client.post("/api/v1/auth/login", json=payload)


async def _register_and_login(client: AsyncClient) -> str:
    """Register a user and return a valid access token."""
    await _register(client)
    resp = await _login(client)
    return resp.json()["access_token"]


# =============================================================================
# Registration Tests
# =============================================================================


class TestRegister:
    """Tests for POST /api/v1/auth/register"""

    async def test_register_success_returns_201(self, client: AsyncClient) -> None:
        """A valid registration payload returns HTTP 201 Created."""
        response = await _register(client)
        assert response.status_code == 201, response.text

    async def test_register_success_response_shape(self, client: AsyncClient) -> None:
        """Registration response contains expected user fields."""
        response = await _register(client)
        data = response.json()
        assert "id" in data
        assert data["email"] == VALID_USER["email"]
        assert data["full_name"] == VALID_USER["full_name"]
        assert data["role"] == "USER"
        assert data["is_active"] is True
        # hashed_password must never appear in the response
        assert "hashed_password" not in data
        assert "password" not in data

    async def test_register_duplicate_email_returns_409(
        self, client: AsyncClient
    ) -> None:
        """Registering with an already-used email returns HTTP 409 Conflict."""
        await _register(client)
        response = await _register(client)  # Same email again
        assert response.status_code == 409, response.text
        error = response.json()["error"]
        assert error["code"] == "CONFLICT"

    async def test_register_weak_password_returns_422(
        self, client: AsyncClient
    ) -> None:
        """A password that fails the strength policy returns HTTP 422."""
        payload = {**VALID_USER, "password": "weakpass"}
        response = await _register(client, payload)
        assert response.status_code == 422, response.text

    async def test_register_invalid_email_returns_422(
        self, client: AsyncClient
    ) -> None:
        """An invalid email format returns HTTP 422."""
        payload = {**VALID_USER, "email": "not-an-email"}
        response = await _register(client, payload)
        assert response.status_code == 422, response.text

    async def test_register_missing_fields_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Missing required fields return HTTP 422."""
        response = await client.post("/api/v1/auth/register", json={"email": "x@x.com"})
        assert response.status_code == 422, response.text

    async def test_register_blank_full_name_returns_422(
        self, client: AsyncClient
    ) -> None:
        """A whitespace-only full_name returns HTTP 422."""
        payload = {**VALID_USER, "email": "unique@example.com", "full_name": "   "}
        response = await _register(client, payload)
        assert response.status_code == 422, response.text


# =============================================================================
# Login Tests
# =============================================================================


class TestLogin:
    """Tests for POST /api/v1/auth/login"""

    async def test_login_success_returns_200(self, client: AsyncClient) -> None:
        """Valid credentials return HTTP 200 OK."""
        await _register(client)
        response = await _login(client)
        assert response.status_code == 200, response.text

    async def test_login_success_returns_token_pair(self, client: AsyncClient) -> None:
        """Successful login response contains access_token and refresh_token."""
        await _register(client)
        response = await _login(client)
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert isinstance(data["expires_in"], int)
        assert data["expires_in"] > 0

    async def test_login_wrong_password_returns_401(self, client: AsyncClient) -> None:
        """Wrong password returns HTTP 401 Unauthorized."""
        await _register(client)
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": VALID_USER["email"], "password": "WrongPass@999"},
        )
        assert response.status_code == 401, response.text

    async def test_login_unknown_email_returns_401(self, client: AsyncClient) -> None:
        """Login with an unregistered email returns HTTP 401 (not 404 — anti-enumeration)."""
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "Test@1234"},
        )
        assert response.status_code == 401, response.text

    async def test_login_error_message_is_generic(self, client: AsyncClient) -> None:
        """The error message is identical for unknown email and wrong password (anti-enumeration)."""
        await _register(client)
        resp_bad_pw = await client.post(
            "/api/v1/auth/login",
            json={"email": VALID_USER["email"], "password": "Wrong@999"},
        )
        resp_bad_email = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": VALID_USER["password"]},
        )
        assert (
            resp_bad_pw.json()["error"]["message"]
            == resp_bad_email.json()["error"]["message"]
        )


# =============================================================================
# Refresh Token Tests
# =============================================================================


class TestRefresh:
    """Tests for POST /api/v1/auth/refresh"""

    async def test_refresh_returns_new_access_token(self, client: AsyncClient) -> None:
        """A valid refresh token produces a new access token."""
        await _register(client)
        login_resp = await _login(client)
        tokens = login_resp.json()

        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert refresh_resp.status_code == 200, refresh_resp.text
        new_tokens = refresh_resp.json()
        assert "access_token" in new_tokens
        # Token rotation: new refresh token must also be issued
        assert "refresh_token" in new_tokens

    async def test_refresh_with_access_token_fails(self, client: AsyncClient) -> None:
        """Using an access token as a refresh token must be rejected."""
        await _register(client)
        login_resp = await _login(client)
        access_token = login_resp.json()["access_token"]

        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access_token},  # Wrong token type
        )
        assert refresh_resp.status_code == 401, refresh_resp.text

    async def test_refresh_with_invalid_token_returns_401(
        self, client: AsyncClient
    ) -> None:
        """A tampered or malformed refresh token returns HTTP 401."""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "this.is.not.a.jwt"},
        )
        assert response.status_code == 401, response.text


# =============================================================================
# Protected Route Tests
# =============================================================================


class TestGetMe:
    """Tests for GET /api/v1/users/me"""

    async def test_get_me_authenticated_returns_200(self, client: AsyncClient) -> None:
        """An authenticated request to /users/me returns HTTP 200."""
        token = await _register_and_login(client)
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text

    async def test_get_me_returns_correct_user(self, client: AsyncClient) -> None:
        """The response contains the authenticated user's data."""
        token = await _register_and_login(client)
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = response.json()
        assert data["email"] == VALID_USER["email"]
        assert data["full_name"] == VALID_USER["full_name"]
        assert "hashed_password" not in data

    async def test_get_me_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        """A request without an Authorization header returns HTTP 401."""
        response = await client.get("/api/v1/users/me")
        assert response.status_code == 401, response.text

    async def test_get_me_with_invalid_token_returns_401(
        self, client: AsyncClient
    ) -> None:
        """A request with a malformed token returns HTTP 401."""
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer this.is.invalid"},
        )
        assert response.status_code == 401, response.text

    async def test_get_me_with_refresh_token_returns_401(
        self, client: AsyncClient
    ) -> None:
        """Using a refresh token in the Authorization header must fail (wrong token type)."""
        await _register(client)
        login_resp = await _login(client)
        refresh_token = login_resp.json()["refresh_token"]

        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        assert response.status_code == 401, response.text
