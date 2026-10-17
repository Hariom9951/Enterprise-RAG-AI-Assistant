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

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.security import _create_token, decode_token
from app.db.session import get_db
from app.main import app as fastapi_app
from app.models.refresh_token import RefreshToken
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

    async def test_refresh_token_contains_unique_jti(self, client: AsyncClient) -> None:
        """Newly issued refresh tokens include a unique, non-empty jti UUID claim."""
        await _register(client)
        login_resp = await _login(client)
        refresh_token = login_resp.json()["refresh_token"]

        payload = decode_token(refresh_token, expected_type="refresh")
        assert "jti" in payload
        assert isinstance(payload["jti"], str)
        assert len(payload["jti"]) >= 32

        # Rotate token and assert new token has a distinct jti
        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_resp.status_code == 200
        new_refresh = refresh_resp.json()["refresh_token"]
        new_payload = decode_token(new_refresh, expected_type="refresh")
        assert new_payload["jti"] != payload["jti"]

    async def test_login_persists_initial_refresh_token(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Login persists the refresh token hash, jti, and family in the database."""
        await _register(client)
        login_resp = await _login(client)
        refresh_token = login_resp.json()["refresh_token"]
        expected_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()

        stmt = select(RefreshToken).where(RefreshToken.token_hash == expected_hash)
        res = await db_session.execute(stmt)
        record = res.scalar_one_or_none()

        assert record is not None
        assert record.is_consumed is False
        assert record.is_revoked is False
        assert record.consumed_at is None
        assert record.family_id is not None

    async def test_refresh_consumes_previous_token(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Successful refresh consumes the previous token and links the new token to the same family."""
        await _register(client)
        login_resp = await _login(client)
        r1 = login_resp.json()["refresh_token"]
        r1_hash = hashlib.sha256(r1.encode("utf-8")).hexdigest()

        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": r1},
        )
        assert refresh_resp.status_code == 200
        r2 = refresh_resp.json()["refresh_token"]
        r2_hash = hashlib.sha256(r2.encode("utf-8")).hexdigest()

        # Check R1 is now consumed
        r1_record = (
            await db_session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == r1_hash)
            )
        ).scalar_one()
        assert r1_record.is_consumed is True
        assert r1_record.consumed_at is not None
        assert r1_record.is_revoked is False

        # Check R2 is active with same family_id
        r2_record = (
            await db_session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == r2_hash)
            )
        ).scalar_one()
        assert r2_record.is_consumed is False
        assert r2_record.is_revoked is False
        assert r2_record.family_id == r1_record.family_id

    async def test_reusing_consumed_token_revokes_entire_family(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Reusing a previously consumed token triggers theft detection and revokes the family."""
        await _register(client)
        login_resp = await _login(client)
        r1 = login_resp.json()["refresh_token"]

        # Rotate R1 -> R2
        ref1_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": r1},
        )
        assert ref1_resp.status_code == 200
        r2 = ref1_resp.json()["refresh_token"]

        # Attacker / replay attempt: reuse R1
        replay_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": r1},
        )
        assert replay_resp.status_code == 401
        assert "Invalid refresh token" in replay_resp.json()["error"]["message"]

        # Legitimate user subsequently tries R2: must fail because family was revoked!
        r2_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": r2},
        )
        assert r2_resp.status_code == 401

        # Verify in database that family is revoked
        r1_hash = hashlib.sha256(r1.encode("utf-8")).hexdigest()
        r1_record = (
            await db_session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == r1_hash)
            )
        ).scalar_one()
        records = (
            (
                await db_session.execute(
                    select(RefreshToken).where(
                        RefreshToken.family_id == r1_record.family_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert all(rec.is_revoked is True for rec in records)

    async def test_untracked_legacy_token_without_jti_is_rejected(
        self, client: AsyncClient
    ) -> None:
        """Legacy refresh tokens lacking the jti claim are rejected per migration policy."""
        await _register(client)
        login_resp = await _login(client)
        sub = decode_token(login_resp.json()["access_token"])["sub"]

        # Manually create legacy token without jti
        legacy_token = _create_token(
            data={"sub": sub},
            expires_delta=timedelta(days=7),
            token_type="refresh",
        )

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": legacy_token},
        )
        assert resp.status_code == 401
        assert "untracked" in resp.json()["error"]["message"].lower()

    async def test_untracked_unknown_token_is_rejected(
        self, client: AsyncClient
    ) -> None:
        """Signed refresh tokens with no corresponding database record are rejected."""
        fake_token = _create_token(
            data={"sub": str(uuid.uuid4()), "jti": str(uuid.uuid4())},
            expires_delta=timedelta(days=7),
            token_type="refresh",
        )
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": fake_token},
        )
        assert resp.status_code == 401
        assert "untracked" in resp.json()["error"]["message"].lower()

    async def test_expired_refresh_token_is_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Expired refresh tokens cannot be used to obtain new tokens."""
        await _register(client)
        login_resp = await _login(client)
        r1 = login_resp.json()["refresh_token"]
        r1_hash = hashlib.sha256(r1.encode("utf-8")).hexdigest()

        # Mark token expired in DB
        record = (
            await db_session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == r1_hash)
            )
        ).scalar_one()
        record.expires_at = datetime.now(UTC) - timedelta(days=1)
        await db_session.commit()

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": r1},
        )
        assert resp.status_code == 401
        assert "expired" in resp.json()["error"]["message"].lower()

    async def test_concurrent_refresh_requests_cannot_both_succeed(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Two concurrent refresh requests using the same token cannot both succeed."""
        await _register(client)
        login_resp = await _login(client)
        r1 = login_resp.json()["refresh_token"]

        test_engine = create_async_engine(
            str(db_session.get_bind().url),
            connect_args={"check_same_thread": False},
        )
        session_factory = async_sessionmaker(
            bind=test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

        async def _independent_get_db() -> Any:
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        fastapi_app.dependency_overrides[get_db] = _independent_get_db

        try:
            req1 = client.post("/api/v1/auth/refresh", json={"refresh_token": r1})
            req2 = client.post("/api/v1/auth/refresh", json={"refresh_token": r1})
            resps = await asyncio.gather(req1, req2)
            statuses = [r.status_code for r in resps]

            # At most one 200 OK is permitted
            assert (
                statuses.count(200) <= 1
            ), f"Both concurrent requests succeeded: {statuses}"
        finally:
            await test_engine.dispose()

            async def _restore_get_db() -> Any:
                yield db_session

            fastapi_app.dependency_overrides[get_db] = _restore_get_db

    async def test_different_users_token_families_remain_isolated(
        self, client: AsyncClient
    ) -> None:
        """Replaying a token for User A revokes User A's family without affecting User B."""
        # Register User A
        user_a = {
            "full_name": "User A",
            "email": "user.a@example.com",
            "password": "PasswordA@123",
        }
        await _register(client, user_a)
        login_a = await _login(client, user_a)
        r_a1 = login_a.json()["refresh_token"]

        # Register User B
        user_b = {
            "full_name": "User B",
            "email": "user.b@example.com",
            "password": "PasswordB@123",
        }
        await _register(client, user_b)
        login_b = await _login(client, user_b)
        r_b1 = login_b.json()["refresh_token"]

        # Rotate User A
        ref_a = await client.post("/api/v1/auth/refresh", json={"refresh_token": r_a1})
        assert ref_a.status_code == 200

        # Replay User A's old token (revokes User A's family)
        replay_a = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": r_a1}
        )
        assert replay_a.status_code == 401

        # User B should still be able to refresh normally
        ref_b = await client.post("/api/v1/auth/refresh", json={"refresh_token": r_b1})
        assert ref_b.status_code == 200, f"User B refresh failed: {ref_b.text}"


# =============================================================================
# Logout Tests
# =============================================================================


class TestLogout:
    """Tests for POST /api/v1/auth/logout"""

    async def test_logout_revokes_token_family(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Logout marks the token family as revoked and prevents further refresh."""
        await _register(client)
        login_resp = await _login(client)
        refresh_token = login_resp.json()["refresh_token"]

        logout_resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
        )
        assert logout_resp.status_code == 200
        assert logout_resp.json()["message"] == "Successfully logged out."

        # Subsequent refresh with that token must be rejected
        ref_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert ref_resp.status_code == 401

    async def test_logout_idempotent_when_already_revoked(
        self, client: AsyncClient
    ) -> None:
        """Logging out multiple times returns 200 OK without errors."""
        await _register(client)
        login_resp = await _login(client)
        refresh_token = login_resp.json()["refresh_token"]

        resp1 = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
        )
        assert resp1.status_code == 200

        resp2 = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
        )
        assert resp2.status_code == 200

    async def test_logout_safe_with_malformed_token(self, client: AsyncClient) -> None:
        """Logout with an invalid or malformed token safely returns 200 OK."""
        resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": "not-a-valid-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Successfully logged out."

    async def test_logout_safe_with_empty_payload(self, client: AsyncClient) -> None:
        """Logout with empty payload returns 200 OK."""
        resp = await client.post("/api/v1/auth/logout", json={})
        assert resp.status_code == 200
        assert resp.json()["message"] == "Successfully logged out."


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
