"""
Enterprise RAG AI Assistant — Phase 5.6.1 OAuth Foundation & Security Tests
=============================================================================
Validates:
1. PKCE verifier generation and SHA-256 S256 challenge (RFC 7636 Appendix B test vector).
2. Frontend redirect URL safety (rejection of open redirects, protocol-relative URLs, CRLF).
3. OAuth state generation, entropy, and user/provider binding.
4. Single-use atomic consumption and replay rejection (Lua GETDEL).
5. State expiry and tampering rejection.
6. Fail-closed behavior on Redis outages (OAuthStateStorageError).
7. Production ENCRYPTION_MASTER_KEY enforcement (missing, wrong length, non-hex, placeholder).
8. Provider secret protection (SecretStr masking, exclusion from logs/serialization).
9. OAuth router endpoints (connections, disconnect, and 501 stubs).
"""

from __future__ import annotations

import json
import secrets
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr, ValidationError
from redis.asyncio import Redis

from app.config.settings import Settings, settings
from app.main import app
from app.models.user import User, UserRole
from app.services.oauth_state_service import (
    OAuthInvalidRedirectError,
    OAuthSecurityError,
    OAuthStateMismatchError,
    OAuthStateReplayOrNotFoundError,
    OAuthStateService,
    OAuthStateStorageError,
    compute_pkce_challenge,
    generate_pkce_verifier,
    validate_frontend_redirect_url,
)

# A standard valid 64-hex key for production config testing
VALID_HEX_KEY = "b4f8d9a2c1e67890abcdef1234567890b4f8d9a2c1e67890abcdef1234567890"
VALID_SECRET_KEY = "a" * 32


# =============================================================================
# 1. PKCE RFC 7636 Cryptographic Correctness Tests
# =============================================================================


class TestPKCECryptographicCorrectness:
    """Validate RFC 7636 compliance and exact test vector verification."""

    def test_rfc7636_appendix_b_test_vector(self) -> None:
        """
        Verify that compute_pkce_challenge exactly produces the RFC 7636 Appendix B test vector.
        Verifier: dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
        Expected: E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
        """
        rfc_verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        expected_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

        computed_challenge = compute_pkce_challenge(rfc_verifier)
        assert computed_challenge == expected_challenge

    def test_verifier_length_and_character_set(self) -> None:
        """Generated verifiers must use RFC 7636 unreserved characters and requested length."""
        for length in (43, 64, 96, 128):
            verifier = generate_pkce_verifier(length=length)
            assert len(verifier) == length
            # All chars must be in unreserved set: [A-Za-z0-9-._~]
            for c in verifier:
                assert (
                    c.isalnum() or c in "-._~"
                ), f"Invalid character '{c}' in verifier"

    def test_invalid_verifier_lengths_rejected(self) -> None:
        """Lengths outside 43..128 must be rejected with ValueError."""
        with pytest.raises(ValueError, match="between 43 and 128"):
            generate_pkce_verifier(length=42)

        with pytest.raises(ValueError, match="between 43 and 128"):
            generate_pkce_verifier(length=129)

    def test_invalid_characters_rejected_in_computation(self) -> None:
        """Invalid characters (spaces, symbols) in verifier must be rejected."""
        with pytest.raises(ValueError, match="Invalid PKCE code_verifier"):
            compute_pkce_challenge("too short")

        with pytest.raises(ValueError, match="Invalid PKCE code_verifier"):
            compute_pkce_challenge("a" * 50 + " " + "b" * 10)


# =============================================================================
# 2. Redirect URL Validation & Open Redirect Protection
# =============================================================================


class TestRedirectUrlValidation:
    """Validate strict whitelist and format rules for frontend redirect destinations."""

    def test_default_redirect_path(self) -> None:
        """None or empty string must default to '/settings'."""
        assert validate_frontend_redirect_url(None) == "/settings"
        assert validate_frontend_redirect_url("") == "/settings"
        assert validate_frontend_redirect_url("   ") == "/settings"

    def test_valid_relative_paths(self) -> None:
        """Safe relative paths must be accepted."""
        assert validate_frontend_redirect_url("/settings") == "/settings"
        assert (
            validate_frontend_redirect_url("/settings/connections")
            == "/settings/connections"
        )
        assert (
            validate_frontend_redirect_url("/dashboard?app=github")
            == "/dashboard?app=github"
        )

    def test_rejection_of_protocol_relative_urls(self) -> None:
        """Protocol-relative URLs (e.g. '//attacker.com') must be rejected."""
        with pytest.raises(OAuthInvalidRedirectError, match="Protocol-relative"):
            validate_frontend_redirect_url("//attacker.com/steal")

        with pytest.raises(OAuthInvalidRedirectError, match="Protocol-relative"):
            validate_frontend_redirect_url("/\\attacker.com/steal")

    def test_rejection_of_crlf_injection(self) -> None:
        """Control characters must be rejected."""
        with pytest.raises(OAuthInvalidRedirectError, match="control characters"):
            validate_frontend_redirect_url("/settings\r\nSet-Cookie: evil=1")

        with pytest.raises(OAuthInvalidRedirectError, match="control characters"):
            validate_frontend_redirect_url("/settings\x00")

    def test_rejection_of_arbitrary_external_domains(self) -> None:
        """External URLs not in settings.allowed_origins must be rejected."""
        with pytest.raises(OAuthInvalidRedirectError, match="not in configured"):
            validate_frontend_redirect_url("https://malicious.com/oauth/steal")

    def test_allowed_origins_permitted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Absolute URLs whose origin is in allowed_origins must be accepted."""
        monkeypatch.setattr(
            settings,
            "allowed_origins",
            ["http://localhost:3000", "https://app.nexusai.com"],
        )
        assert (
            validate_frontend_redirect_url("http://localhost:3000/settings")
            == "http://localhost:3000/settings"
        )
        assert (
            validate_frontend_redirect_url("https://app.nexusai.com/connections")
            == "https://app.nexusai.com/connections"
        )


# =============================================================================
# 3. OAuth State Lifecycle, Expiry, and Atomic Replay Protection
# =============================================================================


class TestOAuthStateLifecycle:
    """Test state creation, Redis storage, user/provider binding, and one-time consumption."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        client = AsyncMock(spec=Redis)
        client._storage = {}

        async def fake_set(key: str, value: str, ex: int | None = None) -> bool:
            client._storage[key] = value
            return True

        async def fake_eval(script: str, numkeys: int, key: str) -> str | None:
            # Simulate Lua GETDEL atomically
            return client._storage.pop(key, None)

        client.set.side_effect = fake_set
        client.eval.side_effect = fake_eval
        return client

    @pytest.mark.asyncio
    async def test_state_creation_and_binding(self, mock_redis: AsyncMock) -> None:
        """Creating a state must store bound user_id, provider, verifier, and challenge."""
        service = OAuthStateService(redis_client=mock_redis)
        user_id = uuid.uuid4()

        result = await service.create_state(
            user_id=user_id,
            provider="github",
            frontend_redirect_url="/settings/connections",
            ttl_seconds=300,
        )

        assert len(result.state) >= 40
        assert result.code_challenge_method == "S256"
        assert len(result.code_challenge) >= 40

        # Check Redis storage
        redis_key = f"oauth:state:{result.state}"
        assert redis_key in mock_redis._storage
        stored = json.loads(mock_redis._storage[redis_key])
        assert stored["user_id"] == str(user_id)
        assert stored["provider"] == "github"
        assert stored["frontend_redirect_url"] == "/settings/connections"
        assert stored["code_challenge"] == result.code_challenge

    @pytest.mark.asyncio
    async def test_state_randomness_across_generations(
        self, mock_redis: AsyncMock
    ) -> None:
        """Subsequent state calls must produce distinct, high-entropy tokens."""
        service = OAuthStateService(redis_client=mock_redis)
        user_id = uuid.uuid4()

        states = set()
        for _ in range(50):
            res = await service.create_state(user_id=user_id, provider="gmail")
            states.add(res.state)
        assert len(states) == 50

    @pytest.mark.asyncio
    async def test_atomic_single_use_and_replay_rejection(
        self, mock_redis: AsyncMock
    ) -> None:
        """State must be consumed once atomically. A second call with same state must be rejected."""
        service = OAuthStateService(redis_client=mock_redis)
        user_id = uuid.uuid4()

        create_res = await service.create_state(
            user_id=user_id,
            provider="linkedin",
        )

        # 1. First consumption succeeds
        state_data = await service.consume_state(
            state=create_res.state,
            expected_provider="linkedin",
            expected_user_id=user_id,
        )
        assert state_data.user_id == user_id
        assert state_data.provider == "linkedin"
        assert len(state_data.code_verifier) >= 43

        # 2. Second consumption (replay attack) fails closed
        with pytest.raises(OAuthStateReplayOrNotFoundError, match="invalid, expired"):
            await service.consume_state(
                state=create_res.state,
                expected_provider="linkedin",
                expected_user_id=user_id,
            )

    @pytest.mark.asyncio
    async def test_provider_mismatch_rejected(self, mock_redis: AsyncMock) -> None:
        """State issued for provider A cannot be consumed for provider B."""
        service = OAuthStateService(redis_client=mock_redis)
        user_id = uuid.uuid4()

        create_res = await service.create_state(
            user_id=user_id,
            provider="github",
        )

        with pytest.raises(OAuthStateMismatchError, match="provider mismatch"):
            await service.consume_state(
                state=create_res.state,
                expected_provider="gmail",
                expected_user_id=user_id,
            )

    @pytest.mark.asyncio
    async def test_user_mismatch_rejected(self, mock_redis: AsyncMock) -> None:
        """State issued for User A cannot be consumed by User B (account linking prevention)."""
        service = OAuthStateService(redis_client=mock_redis)
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()

        create_res = await service.create_state(
            user_id=user_a,
            provider="google_drive",
        )

        with pytest.raises(OAuthStateMismatchError, match="user binding mismatch"):
            await service.consume_state(
                state=create_res.state,
                expected_provider="google_drive",
                expected_user_id=user_b,
            )

    @pytest.mark.asyncio
    async def test_unsupported_provider_rejected(self, mock_redis: AsyncMock) -> None:
        """Inactive or unsupported providers must be rejected at initiation."""
        service = OAuthStateService(redis_client=mock_redis)
        user_id = uuid.uuid4()

        for bad in ("notion", "jira", "slack", "dropbox", ""):
            with pytest.raises(ValueError, match="Unsupported OAuth provider"):
                await service.create_state(user_id=user_id, provider=bad)


# =============================================================================
# 4. Redis Failure Resilience & Fail-Closed Behavior
# =============================================================================


class TestOAuthStateRedisFailClosed:
    """Ensure state creation and consumption strictly fail closed if Redis is down."""

    @pytest.mark.asyncio
    async def test_create_state_fails_closed_when_redis_down(self) -> None:
        """If Redis throws during set, create_state raises OAuthStateStorageError."""
        failing_redis = AsyncMock(spec=Redis)
        failing_redis.set.side_effect = ConnectionError("Redis server unreachable")

        service = OAuthStateService(redis_client=failing_redis)
        with pytest.raises(
            OAuthStateStorageError, match="OAuth state storage unavailable"
        ):
            await service.create_state(user_id=uuid.uuid4(), provider="github")

    @pytest.mark.asyncio
    async def test_consume_state_fails_closed_when_redis_down(self) -> None:
        """If Redis throws during eval/GETDEL, consume_state raises OAuthStateStorageError."""
        failing_redis = AsyncMock(spec=Redis)
        failing_redis.eval.side_effect = ConnectionError("Redis server unreachable")

        service = OAuthStateService(redis_client=failing_redis)
        with pytest.raises(
            OAuthStateStorageError, match="OAuth state storage unavailable"
        ):
            await service.consume_state(
                state="some-valid-looking-state-token-12345",
                expected_provider="github",
            )


# =============================================================================
# 5. Production ENCRYPTION_MASTER_KEY Validation Tests
# =============================================================================


class TestProductionEncryptionKeyValidation:
    """Validate ENCRYPTION_MASTER_KEY enforcement in production Settings."""

    def test_production_fails_when_key_missing(self) -> None:
        """Production startup must fail if ENCRYPTION_MASTER_KEY is None or empty."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                secret_key=VALID_SECRET_KEY,
                encryption_master_key=None,
                allowed_origins=["https://rag.company.com"],
            )
        assert any(
            "ENCRYPTION_MASTER_KEY must be set in production" in str(e)
            for e in exc_info.value.errors()
        )

        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                secret_key=VALID_SECRET_KEY,
                encryption_master_key="   ",
                allowed_origins=["https://rag.company.com"],
            )
        assert any(
            "ENCRYPTION_MASTER_KEY must be set in production" in str(e)
            for e in exc_info.value.errors()
        )

    def test_production_fails_when_key_wrong_length(self) -> None:
        """Production startup must fail if key is not exactly 64 characters (32 bytes)."""
        for bad_len_key in (
            "a" * 32,
            "b" * 63,
            "c" * 65,
            secrets.token_hex(16),  # 32 chars
        ):
            with pytest.raises(ValidationError) as exc_info:
                Settings(
                    environment="production",
                    secret_key=VALID_SECRET_KEY,
                    encryption_master_key=bad_len_key,
                    allowed_origins=["https://rag.company.com"],
                )
            assert any(
                "exactly 64 hexadecimal characters" in str(e)
                for e in exc_info.value.errors()
            )

    def test_production_fails_when_key_invalid_hex(self) -> None:
        """Production startup must fail if 64-char string contains non-hex characters."""
        for non_hex_key in (
            "Z" * 64,
            "change-me" + "0" * 55,
            "placeholder" + "a" * 53,
        ):
            with pytest.raises(ValidationError) as exc_info:
                Settings(
                    environment="production",
                    secret_key=VALID_SECRET_KEY,
                    encryption_master_key=non_hex_key,
                    allowed_origins=["https://rag.company.com"],
                )
            assert any(
                "valid hex-encoded string" in str(e) for e in exc_info.value.errors()
            )

    @pytest.mark.parametrize(
        "placeholder",
        [
            "0" * 64,
            "f" * 64,
            "a" * 64,
            "1" * 64,
        ],
    )
    def test_production_fails_on_placeholders(self, placeholder: str) -> None:
        """Trivial or placeholder keys must be rejected in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                secret_key=VALID_SECRET_KEY,
                encryption_master_key=placeholder,
                allowed_origins=["https://rag.company.com"],
            )
        assert any(
            "cannot be a default or placeholder" in str(e)
            for e in exc_info.value.errors()
        )
        # Ensure key material is never printed in error message
        for err in exc_info.value.errors():
            assert placeholder not in err["msg"]

    def test_production_succeeds_with_valid_key(self) -> None:
        """Production startup succeeds when valid 64-char hex key is provided."""
        cfg = Settings(
            environment="production",
            secret_key=VALID_SECRET_KEY,
            encryption_master_key=VALID_HEX_KEY,
            allowed_origins=["https://rag.company.com"],
        )
        assert cfg.environment == "production"
        assert cfg.encryption_master_key == VALID_HEX_KEY

    def test_development_permits_none_key(self) -> None:
        """Development and test environments permit missing encryption key at startup."""
        cfg = Settings(
            environment="development",
            encryption_master_key=None,
        )
        assert cfg.encryption_master_key is None
        assert cfg.environment == "development"


# =============================================================================
# 6. Provider Configuration & Secret Masking Tests
# =============================================================================


class TestProviderConfiguration:
    """Validate typed provider settings and secret string masking."""

    def test_provider_secrets_typed_as_secretstr(self) -> None:
        """Client secrets must be SecretStr instances."""
        raw_google_secret = "google-top-secret-value-12345"
        raw_github_secret = "github-top-secret-value-67890"

        cfg = Settings(
            google_client_id="google-id.apps.googleusercontent.com",
            google_client_secret=SecretStr(raw_google_secret),
            github_client_id="gh-client-id",
            github_client_secret=SecretStr(raw_github_secret),
        )

        assert isinstance(cfg.google_client_secret, SecretStr)
        assert isinstance(cfg.github_client_secret, SecretStr)

        # str() and repr() must NEVER expose the plaintext secret
        assert raw_google_secret not in str(cfg.google_client_secret)
        assert raw_google_secret not in repr(cfg.google_client_secret)
        assert str(cfg.google_client_secret) == "**********"

        # Explicit retrieval via get_secret_value() works
        assert cfg.google_client_secret.get_secret_value() == raw_google_secret

    def test_model_dump_masks_secrets(self) -> None:
        """model_dump must not leak plaintext secrets."""
        raw_secret = "linkedin-secret-xyz"
        cfg = Settings(
            linkedin_client_id="linkedin-id",
            linkedin_client_secret=SecretStr(raw_secret),
        )
        dumped = cfg.model_dump()
        assert raw_secret not in str(dumped)

    def test_get_oauth_callback_url(self) -> None:
        """get_oauth_callback_url produces canonical path."""
        cfg = Settings(
            oauth_redirect_base_url="https://api.nexusai.example.com",
            api_v1_prefix="/api/v1",
        )
        assert (
            cfg.get_oauth_callback_url("google_drive")
            == "https://api.nexusai.example.com/api/v1/oauth/google_drive/callback"
        )
        assert (
            cfg.get_oauth_callback_url("GITHUB")
            == "https://api.nexusai.example.com/api/v1/oauth/github/callback"
        )


# =============================================================================
# 7. OAuth Router Endpoints Tests
# =============================================================================


class TestOAuthRouterEndpoints:
    """Validate the OAuth router endpoints and 501 stub behavior."""

    @pytest.mark.asyncio
    async def test_connections_endpoint_requires_auth(self) -> None:
        """Unauthenticated GET /api/v1/oauth/connections returns 401."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.get("/api/v1/oauth/connections")
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_disconnect_endpoint_requires_auth(self) -> None:
        """Unauthenticated POST /api/v1/oauth/{provider}/disconnect returns 401."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.post("/api/v1/oauth/github/disconnect")
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_authorize_stub_returns_501(self) -> None:
        """GET /api/v1/oauth/{provider}/authorize returns 501 Not Implemented for inactive providers."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.get("/api/v1/oauth/gmail/authorize")
        assert res.status_code == 501
        payload = res.json()
        msg = (
            payload.get("error", {}).get("message")
            or payload.get("message")
            or payload.get("detail")
        )
        assert "Phase" in str(msg)

    @pytest.mark.asyncio
    async def test_callback_stub_returns_501(self) -> None:
        """GET /api/v1/oauth/{provider}/callback returns 501 Not Implemented for inactive providers."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.get("/api/v1/oauth/gmail/callback")
        assert res.status_code == 501
        payload = res.json()
        msg = (
            payload.get("error", {}).get("message")
            or payload.get("message")
            or payload.get("detail")
        )
        assert "Phase" in str(msg)

