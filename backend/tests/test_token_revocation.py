"""
Enterprise RAG AI Assistant — Immediate Access-Token Revocation Tests (Phase 5.5.2)
===================================================================================
Validates immediate invalidation of access tokens associated with compromised
or logged-out refresh-token families (RFC 6819).

Test coverage:
  - Access tokens embed family_id claim linking them to their session lineage.
  - Replay detection immediately revokes access tokens belonging to the compromised family.
  - Access tokens belonging to unrelated families/users remain valid.
  - Expired revocation markers in cache behave correctly.
  - Redis connection failure safely falls back to database check (no fail-open for compromised tokens, no DoS for uncompromised tokens).
  - Missing family_id claims (legacy tokens) authenticate backward-compatibly.
  - Malformed family_id claims fail safely with 401.
  - Server-side logout immediately revokes the active access token.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, decode_token
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.token_revocation_service import token_revocation_service


async def _create_user(client: AsyncClient, email: str, password: str = "SecurePass123!") -> dict:
    """Helper to register and login a test user."""
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Revocation Test User",
        },
    )
    assert reg_resp.status_code in (200, 201), reg_resp.text

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    return login_resp.json()


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.asyncio
class TestImmediateAccessTokenRevocation:
    """Test suite for immediate access-token invalidation upon family compromise."""

    async def test_access_token_includes_family_id_claim(self, client: AsyncClient) -> None:
        """Login and refresh tokens embed the family_id claim matching the tracked database record."""
        tokens = await _create_user(client, f"family_claim_{uuid.uuid4().hex[:6]}@example.com")
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]

        payload = decode_token(access_token, expected_type="access")
        assert "family_id" in payload
        assert isinstance(payload["family_id"], str)
        family_uuid = uuid.UUID(payload["family_id"])
        assert family_uuid is not None

        # Rotate token: new access token must preserve the same family_id
        ref_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert ref_resp.status_code == 200
        new_access = ref_resp.json()["access_token"]
        new_payload = decode_token(new_access, expected_type="access")
        assert new_payload["family_id"] == payload["family_id"]

    async def test_access_token_rejected_immediately_after_replay_detection(
        self, client: AsyncClient
    ) -> None:
        """An access token from a compromised family is rejected immediately once token replay is detected."""
        tokens = await _create_user(client, f"replay_revocation_{uuid.uuid4().hex[:6]}@example.com")
        a1 = tokens["access_token"]
        r1 = tokens["refresh_token"]

        # 1. Verify A1 works before replay
        me_resp = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {a1}"},
        )
        assert me_resp.status_code == 200

        # 2. Legitimate rotation R1 -> R2
        ref_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": r1},
        )
        assert ref_resp.status_code == 200
        a2 = ref_resp.json()["access_token"]
        r2 = ref_resp.json()["refresh_token"]

        # 3. Attacker replays consumed R1
        replay_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": r1},
        )
        assert replay_resp.status_code == 401
        assert "All sessions in this family have been revoked" in replay_resp.json()["error"]["message"]

        # 4. Critical Security Check: A2 (minted in the compromised family) MUST BE REJECTED IMMEDIATELY!
        me_after_replay = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {a2}"},
        )
        assert me_after_replay.status_code == 401
        assert "Session has been revoked" in me_after_replay.json()["error"]["message"]

        # 5. A1 must also be rejected
        me_a1_after_replay = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {a1}"},
        )
        assert me_a1_after_replay.status_code == 401

    async def test_access_tokens_from_unrelated_families_remain_valid(
        self, client: AsyncClient
    ) -> None:
        """Revoking one family due to replay does NOT affect unrelated users or families."""
        # Session 1 (User 1)
        tokens1 = await _create_user(client, f"victim_{uuid.uuid4().hex[:6]}@example.com")
        a1 = tokens1["access_token"]
        r1 = tokens1["refresh_token"]

        # Session 2 (User 2 - completely unrelated)
        tokens2 = await _create_user(client, f"innocent_{uuid.uuid4().hex[:6]}@example.com")
        a2 = tokens2["access_token"]

        # Rotate Session 1: R1 -> R1_child
        ref1 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": r1},
        )
        assert ref1.status_code == 200

        # Trigger replay on Session 1
        await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": r1},
        )

        # Session 1 access token must be rejected
        resp1 = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {a1}"},
        )
        assert resp1.status_code == 401

        # Session 2 access token MUST REMAIN FULLY FUNCTIONAL
        resp2 = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {a2}"},
        )
        assert resp2.status_code == 200
        assert "innocent_" in resp2.json()["email"]

    async def test_redis_failure_falls_back_to_database_safely(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """When Redis is down, revocation checks fall back to PostgreSQL: compromised tokens are rejected, uncompromised tokens succeed."""
        tokens = await _create_user(client, f"redis_fallback_{uuid.uuid4().hex[:6]}@example.com")
        access_token = tokens["access_token"]
        payload = decode_token(access_token)
        family_id = uuid.UUID(payload["family_id"])

        # Case A: Family is not revoked in DB, but Redis throws ConnectionError
        with patch.object(token_revocation_service, "_get_redis") as mock_redis_getter:
            mock_redis = AsyncMock()
            mock_redis.exists.side_effect = RedisConnectionError("Redis connection refused")
            mock_redis_getter.return_value = mock_redis

            # Request should succeed via DB fallback because family is clean
            resp_clean = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert resp_clean.status_code == 200

        # Case B: Mark family as revoked in database (as happens during replay)
        token_record = (
            await db_session.execute(
                select(RefreshToken).where(RefreshToken.family_id == family_id)
            )
        ).scalar_one()
        token_record.is_revoked = True
        await db_session.commit()

        # With Redis STILL DOWN, the compromised token MUST BE REJECTED via DB fallback
        with patch.object(token_revocation_service, "_get_redis") as mock_redis_getter:
            mock_redis = AsyncMock()
            mock_redis.exists.side_effect = RedisConnectionError("Redis connection refused")
            mock_redis_getter.return_value = mock_redis

            resp_revoked = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert resp_revoked.status_code == 401
            assert "Session has been revoked" in resp_revoked.json()["error"]["message"]

    async def test_missing_family_id_handled_backward_compatible(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Legacy access tokens without family_id authenticate backward-compatibly until natural expiry."""
        # Create user directly
        user = User(
            full_name="Legacy User",
            email=f"legacy_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password="some_hash_val",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Issue legacy token without family_id
        legacy_token = create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role.value, "email": user.email},
            family_id=None,
        )

        resp = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {legacy_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == user.email

    async def test_malformed_family_id_rejected_safely(self, client: AsyncClient) -> None:
        """Access token containing a malformed family_id claim is safely rejected with 401."""
        malformed_token = create_access_token(
            subject=str(uuid.uuid4()),
            extra_claims={"family_id": "not-a-valid-uuid-format-12345"},
        )

        resp = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {malformed_token}"},
        )
        assert resp.status_code == 401
        assert "Invalid token claims" in resp.json()["error"]["message"]

    async def test_logout_immediately_revokes_access_token(self, client: AsyncClient) -> None:
        """Calling /api/v1/auth/logout with a refresh token immediately revokes its active access token."""
        tokens = await _create_user(client, f"logout_revocation_{uuid.uuid4().hex[:6]}@example.com")
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]

        # Confirm access token is valid
        me1 = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me1.status_code == 200

        # Logout with refresh token
        logout_resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert logout_resp.status_code == 200

        # Access token must now be revoked
        me2 = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me2.status_code == 401
        assert "Session has been revoked" in me2.json()["error"]["message"]

    async def test_expired_revocation_marker_service_behavior(self) -> None:
        """TokenRevocationService writes TTL-bounded keys to Redis and expires cleanly."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.exists = AsyncMock(return_value=0)

        test_service = token_revocation_service
        with patch.object(test_service, "_get_redis", return_value=mock_redis):
            fam_id = uuid.uuid4()

            # Revoke with custom 60-second TTL
            success = await test_service.revoke_family(fam_id, reason="test_expiry", ttl_seconds=60)
            assert success is True
            mock_redis.set.assert_awaited_once()
            _, kwargs = mock_redis.set.call_args
            assert kwargs["ex"] == 60

            # When key is not found (expired), exists returns 0 -> is_family_revoked returns False
            is_revoked = await test_service.is_family_revoked(fam_id, db=None)
            assert is_revoked is False

    async def test_scenario_1_redis_marker_write_failure_still_revokes_access_token(
        self, client: AsyncClient
    ) -> None:
        """Scenario 1: PostgreSQL revocation succeeds, but writing the Redis marker fails.
        Access token MUST still be rejected on subsequent requests via database verification."""
        tokens = await _create_user(client, f"write_fail_{uuid.uuid4().hex[:6]}@example.com")
        a1 = tokens["access_token"]
        r1 = tokens["refresh_token"]

        # Rotate r1 -> r2
        ref_resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": r1})
        assert ref_resp.status_code == 200
        a2 = ref_resp.json()["access_token"]

        # Simulate Redis write failure during replay detection
        with patch.object(token_revocation_service, "revoke_family", return_value=False) as mock_revoke:
            # Trigger replay: PostgreSQL revocation succeeds, but Redis write fails
            replay_resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": r1})
            assert replay_resp.status_code == 401
            assert mock_revoke.called

        # Authenticated request with a2 MUST still be rejected because DB has family revoked!
        me_resp = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {a2}"},
        )
        assert me_resp.status_code == 401
        assert "Session has been revoked" in me_resp.json()["error"]["message"]

    async def test_scenario_2_redis_marker_absent_but_postgres_revoked_rejects_and_heals(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Scenario 2: Redis marker lookup succeeds and returns absent (exists=0),
        but PostgreSQL family is already revoked. Must reject token and heal Redis."""
        tokens = await _create_user(client, f"absent_heal_{uuid.uuid4().hex[:6]}@example.com")
        access_token = tokens["access_token"]
        payload = decode_token(access_token)
        family_id = uuid.UUID(payload["family_id"])

        # Mark family as revoked in PostgreSQL
        token_record = (
            await db_session.execute(
                select(RefreshToken).where(RefreshToken.family_id == family_id)
            )
        ).scalar_one()
        token_record.is_revoked = True
        await db_session.commit()

        # Mock Redis so exists returns 0 (absent), but set works (to test self-healing)
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=0)
        mock_redis.set = AsyncMock(return_value=True)

        with patch.object(token_revocation_service, "_get_redis", return_value=mock_redis):
            resp = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert resp.status_code == 401
            assert "Session has been revoked" in resp.json()["error"]["message"]
            # Verify self-healing write to Redis was triggered
            mock_redis.set.assert_awaited_once()

    async def test_scenario_3_redis_unavailable_during_marker_lookup(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Scenario 3: Redis raises exception during exists() lookup.
        Clean session succeeds (no global DoS), revoked session is rejected."""
        # 1. Clean session
        tokens_clean = await _create_user(client, f"clean_{uuid.uuid4().hex[:6]}@example.com")
        a_clean = tokens_clean["access_token"]

        # 2. Revoked session
        tokens_rev = await _create_user(client, f"rev_{uuid.uuid4().hex[:6]}@example.com")
        a_rev = tokens_rev["access_token"]
        payload_rev = decode_token(a_rev)
        fam_rev = uuid.UUID(payload_rev["family_id"])

        rev_record = (
            await db_session.execute(
                select(RefreshToken).where(RefreshToken.family_id == fam_rev)
            )
        ).scalar_one()
        rev_record.is_revoked = True
        await db_session.commit()

        # Redis connection error on exists
        mock_redis = AsyncMock()
        mock_redis.exists.side_effect = RedisConnectionError("Redis connection dropped during lookup")

        with patch.object(token_revocation_service, "_get_redis", return_value=mock_redis):
            # Clean session MUST authenticate successfully
            resp_clean = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {a_clean}"},
            )
            assert resp_clean.status_code == 200

            # Revoked session MUST be rejected
            resp_rev = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {a_rev}"},
            )
            assert resp_rev.status_code == 401
            assert "Session has been revoked" in resp_rev.json()["error"]["message"]

    async def test_scenario_4_and_5_race_condition_postgres_committed_before_redis_write(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Scenario 4 & 5: PostgreSQL revocation transaction commits, but the request races
        with the Redis marker write. The request must detect revocation from DB."""
        tokens = await _create_user(client, f"race_{uuid.uuid4().hex[:6]}@example.com")
        a = tokens["access_token"]
        payload = decode_token(a)
        family_id = uuid.UUID(payload["family_id"])

        # DB has committed revocation, but Redis marker has NOT been set yet
        record = (
            await db_session.execute(
                select(RefreshToken).where(RefreshToken.family_id == family_id)
            )
        ).scalar_one()
        record.is_revoked = True
        await db_session.commit()

        # Redis has not received the write yet (exists returns 0)
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=0)
        mock_redis.set = AsyncMock(return_value=True)

        with patch.object(token_revocation_service, "_get_redis", return_value=mock_redis):
            resp = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {a}"},
            )
            assert resp.status_code == 401
            assert "Session has been revoked" in resp.json()["error"]["message"]

    async def test_scenario_6_expired_redis_marker_with_revoked_postgres_family(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Scenario 6: A Redis marker expires from cache, but the access token is presented
        before its natural JWT expiration. Verification ensures it is rejected."""
        tokens = await _create_user(client, f"exp_marker_{uuid.uuid4().hex[:6]}@example.com")
        a = tokens["access_token"]
        payload = decode_token(a)
        family_id = uuid.UUID(payload["family_id"])

        # Mark family as revoked in DB
        record = (
            await db_session.execute(
                select(RefreshToken).where(RefreshToken.family_id == family_id)
            )
        ).scalar_one()
        record.is_revoked = True
        await db_session.commit()

        # Key expired in Redis (exists=0)
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=0)
        mock_redis.set = AsyncMock(return_value=True)

        with patch.object(token_revocation_service, "_get_redis", return_value=mock_redis):
            resp = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {a}"},
            )
            assert resp.status_code == 401
            assert "Session has been revoked" in resp.json()["error"]["message"]

