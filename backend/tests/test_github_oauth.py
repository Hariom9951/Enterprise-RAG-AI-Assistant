"""
Enterprise RAG AI Assistant — GitHub OAuth 2.0 Integration Security Tests (Phase 5.6.2)
======================================================================================
Validates GitHub OAuth 2.0 authorization-code flow, PKCE/state integration,
token exchange, encrypted vault storage, connection status, disconnect, and fail-closed security.

Mocked infrastructure only — zero live network requests to GitHub or external endpoints.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.github_tool import GitHubSearchTool
from app.config.settings import Settings, settings
from app.core.security import create_access_token, hash_password
from app.models.oauth_models import VALID_PROVIDERS, UserConnectedApp
from app.models.user import User
from app.schemas.oauth import OAuthConnectionStatus
from app.services.github_oauth_service import (
    GITHUB_ACCESS_TOKEN_URL,
    GITHUB_AUTHORIZE_URL,
    GitHubOAuthConfigurationError,
    GitHubOAuthExchangeError,
    GitHubOAuthInsufficientScopeError,
    GitHubOAuthNetworkError,
    GitHubOAuthResponseError,
    GitHubOAuthService,
    github_oauth_service,
)
from app.services.oauth_state_service import (
    OAuthStateCreationResult,
    OAuthStateData,
    OAuthStateMismatchError,
    OAuthStateReplayOrNotFoundError,
    OAuthStateService,
    OAuthStateStorageError,
    oauth_state_service,
)
from app.services.oauth_vault_service import InactiveConnectionError, OAuthVaultService


# =============================================================================
# Test Helpers & Fixtures
# =============================================================================


async def _create_test_user(
    db: AsyncSession,
    email: str = "gh_user@example.com",
) -> User:
    """Helper to create and persist an active test user."""
    user = User(
        id=uuid.uuid4(),
        email=email,
        full_name="GitHub Test User",
        hashed_password=hash_password("SecurePassword@123"),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _auth_headers(user: User) -> dict[str, str]:
    """Helper to generate JWT Bearer authorization headers."""
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


class MockRedisStateStore:
    """In-memory Redis mock replicating single-use Lua GETDEL semantics and TTL."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(
        self, key: str, value: str, ex: int | None = None
    ) -> None:
        self._store[key] = value

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def eval(
        self, script: str, numkeys: int, key: str
    ) -> str | None:
        # Atomic GETDEL
        return self._store.pop(key, None)


# =============================================================================
# 1. Configuration & Authorization URL Tests
# =============================================================================


class TestGitHubConfigurationAndAuthUrl:
    """Tests for GitHub OAuth configuration validation and URL generation."""

    def test_missing_client_id_raises_configuration_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_authorization_url raises error if client ID is unconfigured."""
        monkeypatch.setattr(settings, "github_client_id", None)
        svc = GitHubOAuthService()
        with pytest.raises(GitHubOAuthConfigurationError) as exc_info:
            svc.get_authorization_url(
                state="test_state_12345",
                redirect_uri="http://localhost:8000/api/v1/oauth/github/callback",
            )
        assert "GITHUB_CLIENT_ID" in str(exc_info.value)

    def test_missing_client_secret_raises_configuration_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_authorization_url raises error if client secret is unconfigured."""
        monkeypatch.setattr(settings, "github_client_id", "test_client_id")
        monkeypatch.setattr(settings, "github_client_secret", None)
        svc = GitHubOAuthService()
        with pytest.raises(GitHubOAuthConfigurationError) as exc_info:
            svc.get_authorization_url(
                state="test_state_12345",
                redirect_uri="http://localhost:8000/api/v1/oauth/github/callback",
            )
        assert "GITHUB_CLIENT_SECRET" in str(exc_info.value)

    def test_successful_authorization_url_generation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Correctly constructs GitHub authorization URL with required parameters."""
        monkeypatch.setattr(settings, "github_client_id", "gh_mock_client_id")
        monkeypatch.setattr(
            settings, "github_client_secret", SecretStr("gh_mock_secret")
        )

        svc = GitHubOAuthService()
        redirect_uri = "http://localhost:8000/api/v1/oauth/github/callback"
        state = "secure_random_state_token_12345"

        url = svc.get_authorization_url(
            state=state,
            redirect_uri=redirect_uri,
            scopes=["repo"],
        )

        assert url.startswith(GITHUB_AUTHORIZE_URL)
        assert "client_id=gh_mock_client_id" in url
        assert f"redirect_uri={httpx.URL(redirect_uri)}" or "redirect_uri=http" in url
        assert "scope=repo" in url
        assert f"state={state}" in url

    @pytest.mark.asyncio
    async def test_unauthenticated_authorize_endpoint_returns_401(
        self, client: AsyncClient
    ) -> None:
        """GET /api/v1/oauth/github/authorize requires authentication."""
        res = await client.get("/api/v1/oauth/github/authorize")
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_authorize_endpoint_missing_credentials_returns_503(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET /api/v1/oauth/github/authorize returns 503 if GitHub credentials not set."""
        user = await _create_test_user(db_session, "gh_noconfig@example.com")
        monkeypatch.setattr(settings, "github_client_id", None)

        res = await client.get(
            "/api/v1/oauth/github/authorize",
            headers=_auth_headers(user),
        )
        assert res.status_code == 503
        payload = res.json()
        msg = (
            payload.get("error", {}).get("message")
            or payload.get("message")
            or payload.get("detail")
        )
        assert "GITHUB_CLIENT_ID" in str(msg)

    @pytest.mark.asyncio
    async def test_authorize_endpoint_success_returns_url_and_state(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET /api/v1/oauth/github/authorize returns 200 with authorization URL and state."""
        user = await _create_test_user(db_session, "gh_auth_ok@example.com")
        monkeypatch.setattr(settings, "github_client_id", "gh_test_id")
        monkeypatch.setattr(
            settings, "github_client_secret", SecretStr("gh_test_secret")
        )

        mock_redis = MockRedisStateStore()
        monkeypatch.setattr(oauth_state_service, "_redis", mock_redis)

        res = await client.get(
            "/api/v1/oauth/github/authorize?frontend_redirect_url=/settings",
            headers=_auth_headers(user),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["provider"] == "github"
        assert "authorization_url" in data
        assert "state" in data
        assert "github.com/login/oauth/authorize" in data["authorization_url"]
        assert f"state={data['state']}" in data["authorization_url"]

    @pytest.mark.asyncio
    async def test_authorize_endpoint_redirect_mode_returns_307(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET /api/v1/oauth/github/authorize?redirect=true returns 307 Temporary Redirect."""
        user = await _create_test_user(db_session, "gh_redir_mode@example.com")
        monkeypatch.setattr(settings, "github_client_id", "gh_test_id")
        monkeypatch.setattr(
            settings, "github_client_secret", SecretStr("gh_test_secret")
        )

        mock_redis = MockRedisStateStore()
        monkeypatch.setattr(oauth_state_service, "_redis", mock_redis)

        res = await client.get(
            "/api/v1/oauth/github/authorize?redirect=true",
            headers=_auth_headers(user),
            follow_redirects=False,
        )
        assert res.status_code == 307
        assert "location" in res.headers
        assert res.headers["location"].startswith(GITHUB_AUTHORIZE_URL)

    @pytest.mark.asyncio
    async def test_authorize_endpoint_untrusted_redirect_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET /api/v1/oauth/github/authorize rejects untrusted third-party redirect URLs."""
        user = await _create_test_user(db_session, "gh_bad_redir@example.com")
        monkeypatch.setattr(settings, "github_client_id", "gh_test_id")
        monkeypatch.setattr(
            settings, "github_client_secret", SecretStr("gh_test_secret")
        )

        res = await client.get(
            "/api/v1/oauth/github/authorize?frontend_redirect_url=https://attacker.example.com",
            headers=_auth_headers(user),
        )
        assert res.status_code == 400


# =============================================================================
# 2. Token Exchange Unit & Error Handling Tests
# =============================================================================


class TestGitHubTokenExchangeUnit:
    """Unit tests for GitHub code exchange, network timeout, scope checks, and response parsing."""

    @pytest.mark.asyncio
    async def test_token_exchange_success_standard_non_expiring(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Standard GitHub token response without expires_in sets expires_at=None."""
        monkeypatch.setattr(settings, "github_client_id", "gh_cid")
        monkeypatch.setattr(settings, "github_client_secret", SecretStr("gh_sec"))

        mock_response = httpx.Response(
            status_code=200,
            json={
                "access_token": "gho_validaccesstoken12345",
                "scope": "repo,read:user",
                "token_type": "bearer",
            },
            request=httpx.Request("POST", GITHUB_ACCESS_TOKEN_URL),
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        svc = GitHubOAuthService()
        result = await svc.exchange_code_for_token(
            code="mock_code_abc",
            redirect_uri="http://localhost:8000/callback",
            required_scopes=["repo"],
            client=mock_client,
        )

        assert result["access_token"] == "gho_validaccesstoken12345"
        assert result["refresh_token"] is None
        assert result["expires_at"] is None
        assert "repo" in result["scopes"]
        assert "read:user" in result["scopes"]

    @pytest.mark.asyncio
    async def test_token_exchange_with_expiring_tokens(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GitHub App tokens with expires_in calculate accurate UTC expires_at."""
        monkeypatch.setattr(settings, "github_client_id", "gh_cid")
        monkeypatch.setattr(settings, "github_client_secret", SecretStr("gh_sec"))

        mock_response = httpx.Response(
            status_code=200,
            json={
                "access_token": "ghu_expiringtoken123",
                "expires_in": 28800,  # 8 hours
                "refresh_token": "ghr_refreshtoken123",
                "refresh_token_expires_in": 15811200,
                "scope": "repo",
                "token_type": "bearer",
            },
            request=httpx.Request("POST", GITHUB_ACCESS_TOKEN_URL),
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        svc = GitHubOAuthService()
        before = datetime.now(UTC)
        result = await svc.exchange_code_for_token(
            code="mock_code_abc",
            redirect_uri="http://localhost:8000/callback",
            required_scopes=["repo"],
            client=mock_client,
        )

        assert result["access_token"] == "ghu_expiringtoken123"
        assert result["refresh_token"] == "ghr_refreshtoken123"
        assert result["expires_at"] is not None
        # Should be roughly 8 hours in the future
        diff = (result["expires_at"] - before).total_seconds()
        assert 28790 <= diff <= 28810

    @pytest.mark.asyncio
    async def test_token_exchange_timeout_raises_network_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Network timeout during token exchange raises GitHubOAuthNetworkError."""
        monkeypatch.setattr(settings, "github_client_id", "gh_cid")
        monkeypatch.setattr(settings, "github_client_secret", SecretStr("gh_sec"))

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.TimeoutException("Read timed out")

        svc = GitHubOAuthService()
        with pytest.raises(GitHubOAuthNetworkError) as exc_info:
            await svc.exchange_code_for_token(
                code="code123",
                redirect_uri="http://callback",
                client=mock_client,
            )
        assert "Failed to communicate" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_token_exchange_non_2xx_raises_response_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Upstream HTTP 500 error raises GitHubOAuthResponseError."""
        monkeypatch.setattr(settings, "github_client_id", "gh_cid")
        monkeypatch.setattr(settings, "github_client_secret", SecretStr("gh_sec"))

        mock_response = httpx.Response(
            status_code=500,
            text="Internal Server Error",
            request=httpx.Request("POST", GITHUB_ACCESS_TOKEN_URL),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        svc = GitHubOAuthService()
        with pytest.raises(GitHubOAuthResponseError) as exc_info:
            await svc.exchange_code_for_token(
                code="code123",
                redirect_uri="http://callback",
                client=mock_client,
            )
        assert "HTTP 500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_token_exchange_malformed_json_raises_response_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Malformed JSON from provider raises GitHubOAuthResponseError."""
        monkeypatch.setattr(settings, "github_client_id", "gh_cid")
        monkeypatch.setattr(settings, "github_client_secret", SecretStr("gh_sec"))

        mock_response = httpx.Response(
            status_code=200,
            content=b"<html>Bad Gateway</html>",
            headers={"Content-Type": "text/html"},
            request=httpx.Request("POST", GITHUB_ACCESS_TOKEN_URL),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        svc = GitHubOAuthService()
        with pytest.raises(GitHubOAuthResponseError) as exc_info:
            await svc.exchange_code_for_token(
                code="code123",
                redirect_uri="http://callback",
                client=mock_client,
            )
        assert "Invalid JSON" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_token_exchange_provider_rejection_raises_exchange_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Provider returning error field (e.g. bad_verification_code) raises GitHubOAuthExchangeError."""
        monkeypatch.setattr(settings, "github_client_id", "gh_cid")
        monkeypatch.setattr(settings, "github_client_secret", SecretStr("gh_sec"))

        mock_response = httpx.Response(
            status_code=200,
            json={
                "error": "bad_verification_code",
                "error_description": "The code passed is incorrect or has expired.",
                "error_uri": "https://docs.github.com/...",
            },
            request=httpx.Request("POST", GITHUB_ACCESS_TOKEN_URL),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        svc = GitHubOAuthService()
        with pytest.raises(GitHubOAuthExchangeError) as exc_info:
            await svc.exchange_code_for_token(
                code="expired_code",
                redirect_uri="http://callback",
                client=mock_client,
            )
        assert exc_info.value.error_code == "bad_verification_code"
        assert "incorrect or has expired" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_token_exchange_missing_access_token_raises_response_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Response lacking access_token field raises GitHubOAuthResponseError."""
        monkeypatch.setattr(settings, "github_client_id", "gh_cid")
        monkeypatch.setattr(settings, "github_client_secret", SecretStr("gh_sec"))

        mock_response = httpx.Response(
            status_code=200,
            json={"token_type": "bearer", "scope": "repo"},
            request=httpx.Request("POST", GITHUB_ACCESS_TOKEN_URL),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        svc = GitHubOAuthService()
        with pytest.raises(GitHubOAuthResponseError) as exc_info:
            await svc.exchange_code_for_token(
                code="code123",
                redirect_uri="http://callback",
                client=mock_client,
            )
        assert "did not contain an access_token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_token_exchange_insufficient_scope_raises_scope_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User granting only 'read:user' when 'repo' is required raises GitHubOAuthInsufficientScopeError."""
        monkeypatch.setattr(settings, "github_client_id", "gh_cid")
        monkeypatch.setattr(settings, "github_client_secret", SecretStr("gh_sec"))

        mock_response = httpx.Response(
            status_code=200,
            json={
                "access_token": "gho_valid_token_but_wrong_scope",
                "scope": "read:user,gist",
                "token_type": "bearer",
            },
            request=httpx.Request("POST", GITHUB_ACCESS_TOKEN_URL),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        svc = GitHubOAuthService()
        with pytest.raises(GitHubOAuthInsufficientScopeError) as exc_info:
            await svc.exchange_code_for_token(
                code="code123",
                redirect_uri="http://callback",
                required_scopes=["repo"],
                client=mock_client,
            )
        assert "repo" in exc_info.value.required_scopes
        assert "read:user" in exc_info.value.granted_scopes


# =============================================================================
# 3. Callback Endpoint & Replay/Tenant Isolation Tests
# =============================================================================


class TestGitHubCallbackEndpointSecurity:
    """End-to-end endpoint tests for GET /api/v1/oauth/github/callback."""

    @pytest.mark.asyncio
    async def test_callback_missing_code_or_state_returns_400(
        self, client: AsyncClient
    ) -> None:
        """Callback missing code or state parameter returns 400."""
        res1 = await client.get("/api/v1/oauth/github/callback?state=xyz")
        res2 = await client.get("/api/v1/oauth/github/callback?code=xyz")
        assert res1.status_code == 400
        assert res2.status_code == 400

    @pytest.mark.asyncio
    async def test_callback_consent_denial_returns_400(
        self, client: AsyncClient
    ) -> None:
        """Callback receiving provider error=access_denied returns 400."""
        res = await client.get(
            "/api/v1/oauth/github/callback?error=access_denied&error_description=The+user+has+denied+your+application+access."
        )
        assert res.status_code == 400
        assert "denied" in res.text.lower()

    @pytest.mark.asyncio
    async def test_callback_consent_denial_browser_mode_returns_303(
        self, client: AsyncClient
    ) -> None:
        """Callback receiving error in redirect/browser mode returns 303 to settings."""
        res = await client.get(
            "/api/v1/oauth/github/callback?error=access_denied&redirect=true",
            follow_redirects=False,
        )
        assert res.status_code == 303
        assert "/settings" in res.headers["location"]
        assert "error=access_denied" in res.headers["location"]

    @pytest.mark.asyncio
    async def test_callback_state_replay_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Consuming the same state twice fails on the second attempt (one-time replay prevention)."""
        user = await _create_test_user(db_session, "gh_replay@example.com")
        mock_redis = MockRedisStateStore()
        monkeypatch.setattr(oauth_state_service, "_redis", mock_redis)
        monkeypatch.setattr(settings, "github_client_id", "gh_test_id")
        monkeypatch.setattr(
            settings, "github_client_secret", SecretStr("gh_test_secret")
        )

        state_res = await oauth_state_service.create_state(
            user_id=user.id, provider="github"
        )

        # Mock token exchange
        mock_token_data = {
            "access_token": "gho_test_token_replay",
            "refresh_token": None,
            "token_type": "bearer",
            "scopes": ["repo"],
            "expires_at": None,
        }
        monkeypatch.setattr(
            github_oauth_service,
            "exchange_code_for_token",
            AsyncMock(return_value=mock_token_data),
        )

        # First attempt succeeds
        res1 = await client.get(
            f"/api/v1/oauth/github/callback?code=code_1&state={state_res.state}",
            headers=_auth_headers(user),
        )
        # Replay attempt fails
        res2 = await client.get(
            f"/api/v1/oauth/github/callback?code=code_2&state={state_res.state}",
            headers=_auth_headers(user),
        )

        assert res1.status_code == 200
        assert res2.status_code == 400
        assert "invalid, expired, or already consumed" in res2.text.lower()

    @pytest.mark.asyncio
    async def test_callback_cross_user_isolation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """User B cannot complete OAuth callback using a state created by User A."""
        user_a = await _create_test_user(db_session, "user_a_gh@example.com")
        user_b = await _create_test_user(db_session, "user_b_gh@example.com")

        mock_redis = MockRedisStateStore()
        monkeypatch.setattr(oauth_state_service, "_redis", mock_redis)
        monkeypatch.setattr(settings, "github_client_id", "gh_test_id")
        monkeypatch.setattr(
            settings, "github_client_secret", SecretStr("gh_test_secret")
        )

        # User A initiates authorization
        state_res = await oauth_state_service.create_state(
            user_id=user_a.id, provider="github"
        )

        # User B attempts to consume User A's state
        res = await client.get(
            f"/api/v1/oauth/github/callback?code=code_cross&state={state_res.state}",
            headers=_auth_headers(user_b),
        )

        assert res.status_code == 400
        assert "user binding mismatch" in res.text.lower()

    @pytest.mark.asyncio
    async def test_callback_redis_unavailable_fails_closed(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If Redis is down during callback, fails closed with 503 Service Unavailable."""
        user = await _create_test_user(db_session, "gh_redis_down@example.com")
        broken_redis = MagicMock()
        broken_redis.eval = AsyncMock(side_effect=OSError("Redis connection refused"))
        monkeypatch.setattr(oauth_state_service, "_redis", broken_redis)

        res = await client.get(
            "/api/v1/oauth/github/callback?code=code_1&state=valid_looking_state_token",
            headers=_auth_headers(user),
        )

        assert res.status_code == 503
        assert "storage unavailable" in res.text.lower()

    @pytest.mark.asyncio
    async def test_callback_full_success_stores_tokens_and_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Full callback flow successfully exchanges code and persists encrypted token."""
        user = await _create_test_user(db_session, "gh_full_success@example.com")
        mock_redis = MockRedisStateStore()
        monkeypatch.setattr(oauth_state_service, "_redis", mock_redis)
        monkeypatch.setattr(settings, "github_client_id", "gh_test_id")
        monkeypatch.setattr(
            settings, "github_client_secret", SecretStr("gh_test_secret")
        )

        state_res = await oauth_state_service.create_state(
            user_id=user.id,
            provider="github",
            frontend_redirect_url="/settings",
        )

        mock_token_data = {
            "access_token": "gho_super_secret_access_token_12345",
            "refresh_token": None,
            "token_type": "bearer",
            "scopes": ["repo"],
            "expires_at": None,
        }
        monkeypatch.setattr(
            github_oauth_service,
            "exchange_code_for_token",
            AsyncMock(return_value=mock_token_data),
        )

        res = await client.get(
            f"/api/v1/oauth/github/callback?code=valid_code_123&state={state_res.state}",
            headers=_auth_headers(user),
        )

        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["provider"] == "github"
        assert data["redirect_url"] == "/settings"

        # Verify vault record in database
        vault = OAuthVaultService()
        creds = await vault.get_decrypted_credentials(
            db=db_session, user_id=user.id, provider="github"
        )
        assert creds is not None
        assert creds["access_token"] == "gho_super_secret_access_token_12345"
        assert creds["scopes"] == ["repo"]
        assert creds["status"] == "connected"


# =============================================================================
# 4. Vault Encryption, Persistence & Disconnect Tests
# =============================================================================


class TestGitHubVaultAndLifecycle:
    """Verifies encrypted storage, cross-user isolation, duplicate updates, and disconnect."""

    @pytest.mark.asyncio
    async def test_tokens_are_encrypted_in_database(
        self, db_session: AsyncSession
    ) -> None:
        """Raw plaintext token NEVER exists in database; only AES-256-GCM ciphertext bytes."""
        user = await _create_test_user(db_session, "gh_enc_test@example.com")
        vault = OAuthVaultService()

        raw_token = "gho_raw_plaintext_oauth_token_12345"
        await vault.store_tokens(
            db=db_session,
            user_id=user.id,
            provider="github",
            access_token=raw_token,
            scopes=["repo"],
        )
        await db_session.commit()

        # Direct SQL query bypassing vault decrypt
        stmt = select(UserConnectedApp).where(
            UserConnectedApp.user_id == user.id,
            UserConnectedApp.provider == "github",
        )
        res = await db_session.execute(stmt)
        record = res.scalar_one()

        assert record.encrypted_access_token != raw_token.encode()
        assert raw_token.encode() not in record.encrypted_access_token
        # Verify repr excludes secret material
        assert raw_token not in repr(record)
        assert "encrypted_access_token" not in repr(record)

    @pytest.mark.asyncio
    async def test_duplicate_connection_updates_existing_record(
        self, db_session: AsyncSession
    ) -> None:
        """Connecting GitHub twice cleanly updates existing tokens without duplicate error."""
        user = await _create_test_user(db_session, "gh_dupe_test@example.com")
        vault = OAuthVaultService()

        # First connection
        await vault.store_tokens(
            db=db_session,
            user_id=user.id,
            provider="github",
            access_token="gho_token_v1",
            scopes=["repo"],
        )
        await db_session.commit()

        # Second connection with updated token
        await vault.store_tokens(
            db=db_session,
            user_id=user.id,
            provider="github",
            access_token="gho_token_v2",
            scopes=["repo", "read:user"],
        )
        await db_session.commit()

        # Confirm exactly 1 record in database
        stmt = select(UserConnectedApp).where(
            UserConnectedApp.user_id == user.id,
            UserConnectedApp.provider == "github",
        )
        res = await db_session.execute(stmt)
        records = res.scalars().all()
        assert len(records) == 1

        creds = await vault.get_decrypted_credentials(
            db=db_session, user_id=user.id, provider="github"
        )
        assert creds["access_token"] == "gho_token_v2"
        assert creds["scopes"] == ["repo", "read:user"]

    @pytest.mark.asyncio
    async def test_list_connections_and_disconnect_flow(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Full lifecycle: list connections -> disconnect -> connection marked revoked."""
        user = await _create_test_user(db_session, "gh_lifecycle@example.com")
        vault = OAuthVaultService()

        # 1. Store connection
        await vault.store_tokens(
            db=db_session,
            user_id=user.id,
            provider="github",
            access_token="gho_token_lifecycle",
            scopes=["repo"],
        )
        await db_session.commit()

        # 2. List connections via API
        res_list = await client.get(
            "/api/v1/oauth/connections",
            headers=_auth_headers(user),
        )
        assert res_list.status_code == 200
        conns = res_list.json()["connections"]
        assert len(conns) == 1
        assert conns[0]["provider"] == "github"
        assert conns[0]["connection_status"] == "connected"
        assert conns[0]["scopes"] == ["repo"]

        # 3. Disconnect via API
        res_disc = await client.post(
            "/api/v1/oauth/github/disconnect",
            headers=_auth_headers(user),
        )
        assert res_disc.status_code == 200
        assert res_disc.json()["success"] is True

        # 4. Verify local vault status is revoked
        with pytest.raises(InactiveConnectionError):
            await vault.get_decrypted_credentials(
                db=db_session, user_id=user.id, provider="github"
            )

        # 5. List connections reflects revoked status
        res_list_after = await client.get(
            "/api/v1/oauth/connections",
            headers=_auth_headers(user),
        )
        conns_after = res_list_after.json()["connections"]
        assert conns_after[0]["connection_status"] == "revoked"


# =============================================================================
# 5. GitHubSearchTool Integration with Vault Credentials
# =============================================================================


class TestGitHubSearchToolIntegration:
    """Verifies that GitHubSearchTool seamlessly retrieves credentials from vault."""

    @pytest.mark.asyncio
    async def test_tool_executes_with_vault_credentials(
        self, db_session: AsyncSession
    ) -> None:
        """GitHubSearchTool fetches token from OAuthVaultService and queries GitHub API."""
        user = await _create_test_user(db_session, "gh_tool_user@example.com")
        vault = OAuthVaultService()

        await vault.store_tokens(
            db=db_session,
            user_id=user.id,
            provider="github",
            access_token="gho_test_tool_token",
            scopes=["repo"],
        )
        await db_session.commit()

        tool = GitHubSearchTool()

        # Mock outbound GitHub REST search response
        mock_issues_response = httpx.Response(
            status_code=200,
            json={
                "items": [
                    {
                        "id": 101,
                        "number": 42,
                        "title": "OAuth security issue",
                        "html_url": "https://github.com/org/repo/issues/42",
                        "state": "open",
                        "body": "Fixed CSRF state handling in auth flow.",
                        "user": {"login": "dev1"},
                    }
                ]
            },
            request=httpx.Request("GET", "https://api.github.com/search/issues"),
        )

        mock_repos_response = httpx.Response(
            status_code=200,
            json={"items": []},
            request=httpx.Request("GET", "https://api.github.com/search/repositories"),
        )

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = [mock_issues_response, mock_repos_response]
            result = await tool._run(
                params={"query": "OAuth bug", "search_type": "issues"},
                user_id=user.id,
                db=db_session,
            )

        assert result.success is True
        assert result.output is not None
        assert len(result.output) == 1
        item = result.output[0]
        assert item["provider"] == "github"
        assert "OAuth security issue" in item["title"]
        assert item["source_url"] == "https://github.com/org/repo/issues/42"

    @pytest.mark.asyncio
    async def test_tool_returns_graceful_failure_when_unconnected(
        self, db_session: AsyncSession
    ) -> None:
        """GitHubSearchTool returns ToolResult(success=False) when account is not connected."""
        user = await _create_test_user(db_session, "gh_not_connected@example.com")
        tool = GitHubSearchTool()

        result = await tool._run(
            params={"query": "my repo"},
            user_id=user.id,
            db=db_session,
        )

        assert result.success is False
        assert "Connect your account first" in result.error


# =============================================================================
# 6. Phase 5.6.2.2 — Account-Linking Remediation & Security Guard Tests
# =============================================================================


class TestGitHubOAuthAccountLinkingRemediation:
    """
    Comprehensive tests demonstrating that:
    1. Unauthenticated callback cannot link credentials.
    2. Cross-user state hijacking is strictly rejected.
    3. Safe browser handoff redirects unauthenticated users without consuming state.
    4. Authenticated POST callback completes securely.
    5. Concurrency allows at most one state consumption.
    6. Provider error and code exchange failures consume state to prevent replay.
    7. Disconnect zeroes access token ciphertext.
    8. Upstream 401 marks connection as expired.
    9. Configurable scopes are respected.
    """

    @pytest.mark.asyncio
    async def test_unauthenticated_api_callback_rejected_with_401(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Direct unauthenticated API calls to GET or POST callback return 401 and never link."""
        res_get = await client.get(
            "/api/v1/oauth/github/callback?code=some_code&state=some_state_token",
            headers={"Accept": "application/json"},
        )
        assert res_get.status_code == 401
        assert "Authentication required" in res_get.text

        res_post = await client.post(
            "/api/v1/oauth/github/callback",
            json={"code": "some_code", "state": "some_state_token"},
            headers={"Accept": "application/json"},
        )
        assert res_post.status_code == 401

        # Assert no records exist
        stmt = select(UserConnectedApp)
        res = await db_session.execute(stmt)
        assert res.scalars().all() == []

    @pytest.mark.asyncio
    async def test_unauthenticated_browser_callback_redirects_without_linking(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Unauthenticated browser callback redirects to frontend handoff URL with code and state,
        WITHOUT consuming the state in Redis and WITHOUT exchanging code or storing tokens.
        """
        user = await _create_test_user(db_session, "gh_browser_handoff@example.com")
        mock_redis = MockRedisStateStore()
        monkeypatch.setattr(oauth_state_service, "_redis", mock_redis)
        monkeypatch.setattr(settings, "github_client_id", "gh_test_id")
        monkeypatch.setattr(
            settings, "github_client_secret", SecretStr("gh_test_secret")
        )

        state_res = await oauth_state_service.create_state(
            user_id=user.id,
            provider="github",
            frontend_redirect_url="/settings",
        )

        # Mock exchange to assert it is NEVER called
        mock_exchange = AsyncMock()
        monkeypatch.setattr(github_oauth_service, "exchange_code_for_token", mock_exchange)

        res = await client.get(
            f"/api/v1/oauth/github/callback?code=gh_code_123&state={state_res.state}&redirect=true",
            follow_redirects=False,
        )

        assert res.status_code == 303
        loc = res.headers["location"]
        assert loc.startswith("/settings")
        assert "code=gh_code_123" in loc
        assert f"state={state_res.state}" in loc
        assert "action=link" in loc

        # Verify state is STILL IN REDIS (not consumed)
        stored_state = await mock_redis.get(f"oauth:state:{state_res.state}")
        assert stored_state is not None

        # Verify exchange was never invoked
        mock_exchange.assert_not_called()

        # Verify zero database records
        stmt = select(UserConnectedApp)
        db_res = await db_session.execute(stmt)
        assert db_res.scalars().all() == []

    @pytest.mark.asyncio
    async def test_user_a_state_cannot_be_completed_by_user_b_via_get_or_post(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """User B cannot link an account using a state token initiated by User A."""
        user_a = await _create_test_user(db_session, "victim_a@example.com")
        user_b = await _create_test_user(db_session, "attacker_b@example.com")

        mock_redis = MockRedisStateStore()
        monkeypatch.setattr(oauth_state_service, "_redis", mock_redis)
        monkeypatch.setattr(settings, "github_client_id", "gh_test_id")
        monkeypatch.setattr(
            settings, "github_client_secret", SecretStr("gh_test_secret")
        )

        # User A creates state
        state_res = await oauth_state_service.create_state(
            user_id=user_a.id, provider="github"
        )

        # User B attempts to complete callback via GET
        res_get = await client.get(
            f"/api/v1/oauth/github/callback?code=stolen_code&state={state_res.state}",
            headers=_auth_headers(user_b),
        )
        assert res_get.status_code == 400
        assert "user binding mismatch" in res_get.text.lower()

        # User A creates a second state
        state_res_2 = await oauth_state_service.create_state(
            user_id=user_a.id, provider="github"
        )

        # User B attempts to complete callback via POST
        res_post = await client.post(
            "/api/v1/oauth/github/callback",
            json={"code": "stolen_code", "state": state_res_2.state},
            headers=_auth_headers(user_b),
        )
        assert res_post.status_code == 400
        assert "user binding mismatch" in res_post.text.lower()

        # Assert no tokens were linked to either user
        stmt = select(UserConnectedApp)
        db_res = await db_session.execute(stmt)
        assert db_res.scalars().all() == []

    @pytest.mark.asyncio
    async def test_authenticated_post_callback_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Authenticated POST callback exchanges code, verifies scopes, and stores tokens."""
        user = await _create_test_user(db_session, "gh_post_user@example.com")
        mock_redis = MockRedisStateStore()
        monkeypatch.setattr(oauth_state_service, "_redis", mock_redis)
        monkeypatch.setattr(settings, "github_client_id", "gh_test_id")
        monkeypatch.setattr(
            settings, "github_client_secret", SecretStr("gh_test_secret")
        )

        state_res = await oauth_state_service.create_state(
            user_id=user.id,
            provider="github",
            frontend_redirect_url="/settings",
        )

        mock_token_data = {
            "access_token": "gho_token_from_post_exchange",
            "refresh_token": None,
            "token_type": "bearer",
            "scopes": ["repo"],
            "expires_at": None,
        }
        monkeypatch.setattr(
            github_oauth_service,
            "exchange_code_for_token",
            AsyncMock(return_value=mock_token_data),
        )

        res = await client.post(
            "/api/v1/oauth/github/callback",
            json={"code": "gh_post_code_123", "state": state_res.state},
            headers=_auth_headers(user),
        )

        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["provider"] == "github"

        # Verify credentials stored in vault
        vault = OAuthVaultService()
        creds = await vault.get_decrypted_credentials(
            db=db_session, user_id=user.id, provider="github"
        )
        assert creds is not None
        assert creds["access_token"] == "gho_token_from_post_exchange"

    @pytest.mark.asyncio
    async def test_concurrent_callback_allows_at_most_one_consumption(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Atomic Redis Lua GETDEL guarantees that out of concurrent callbacks, exactly one succeeds."""
        import asyncio

        user = await _create_test_user(db_session, "gh_concurrent@example.com")
        mock_redis = MockRedisStateStore()
        monkeypatch.setattr(oauth_state_service, "_redis", mock_redis)
        monkeypatch.setattr(settings, "github_client_id", "gh_test_id")
        monkeypatch.setattr(
            settings, "github_client_secret", SecretStr("gh_test_secret")
        )

        state_res = await oauth_state_service.create_state(
            user_id=user.id, provider="github"
        )

        mock_token_data = {
            "access_token": "gho_token_concurrent",
            "refresh_token": None,
            "token_type": "bearer",
            "scopes": ["repo"],
            "expires_at": None,
        }
        monkeypatch.setattr(
            github_oauth_service,
            "exchange_code_for_token",
            AsyncMock(return_value=mock_token_data),
        )

        async def send_callback() -> int:
            res = await client.post(
                "/api/v1/oauth/github/callback",
                json={"code": "code_race", "state": state_res.state},
                headers=_auth_headers(user),
            )
            return res.status_code

        res1, res2 = await asyncio.gather(send_callback(), send_callback())
        codes = sorted([res1, res2])
        assert codes == [200, 400]

    @pytest.mark.asyncio
    async def test_provider_error_consumes_state_preventing_reuse(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Provider error consumes state to prevent subsequent code replay."""
        user = await _create_test_user(db_session, "gh_error_consume@example.com")
        mock_redis = MockRedisStateStore()
        monkeypatch.setattr(oauth_state_service, "_redis", mock_redis)

        state_res = await oauth_state_service.create_state(
            user_id=user.id, provider="github"
        )

        # Provider sends error callback with state
        res_err = await client.get(
            f"/api/v1/oauth/github/callback?error=access_denied&state={state_res.state}"
        )
        assert res_err.status_code == 400

        # State must now be gone from Redis
        assert await mock_redis.get(f"oauth:state:{state_res.state}") is None

        # Subsequent callback attempt using that state fails
        res_reuse = await client.post(
            "/api/v1/oauth/github/callback",
            json={"code": "valid_code", "state": state_res.state},
            headers=_auth_headers(user),
        )
        assert res_reuse.status_code == 400
        assert "invalid, expired, or already consumed" in res_reuse.text.lower()

    @pytest.mark.asyncio
    async def test_code_exchange_failure_consumes_state_preventing_reuse(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If code exchange fails with GitHub, the state was already consumed and cannot be reused."""
        user = await _create_test_user(db_session, "gh_exchange_fail@example.com")
        mock_redis = MockRedisStateStore()
        monkeypatch.setattr(oauth_state_service, "_redis", mock_redis)
        monkeypatch.setattr(settings, "github_client_id", "gh_test_id")
        monkeypatch.setattr(
            settings, "github_client_secret", SecretStr("gh_test_secret")
        )

        state_res = await oauth_state_service.create_state(
            user_id=user.id, provider="github"
        )

        # Exchange fails with 502 Bad Gateway
        monkeypatch.setattr(
            github_oauth_service,
            "exchange_code_for_token",
            AsyncMock(side_effect=GitHubOAuthNetworkError("Connection timed out")),
        )

        res1 = await client.post(
            "/api/v1/oauth/github/callback",
            json={"code": "code_timeout", "state": state_res.state},
            headers=_auth_headers(user),
        )
        assert res1.status_code == 502

        # Subsequent attempt with the same state is rejected with 400 (already consumed)
        res2 = await client.post(
            "/api/v1/oauth/github/callback",
            json={"code": "code_timeout", "state": state_res.state},
            headers=_auth_headers(user),
        )
        assert res2.status_code == 400
        assert "invalid, expired, or already consumed" in res2.text.lower()

    @pytest.mark.asyncio
    async def test_disconnect_clears_access_token_ciphertext(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Disconnect sets encrypted_access_token to b'' on disk without schema modification."""
        user = await _create_test_user(db_session, "gh_zero_ciphertext@example.com")
        vault = OAuthVaultService()

        await vault.store_tokens(
            db=db_session,
            user_id=user.id,
            provider="github",
            access_token="gho_temporary_token",
            refresh_token="ghr_temporary_refresh",
            scopes=["repo"],
        )
        await db_session.commit()

        # Disconnect via API
        res = await client.post(
            "/api/v1/oauth/github/disconnect",
            headers=_auth_headers(user),
        )
        assert res.status_code == 200

        # Query database row directly
        stmt = select(UserConnectedApp).where(
            UserConnectedApp.user_id == user.id,
            UserConnectedApp.provider == "github",
        )
        db_res = await db_session.execute(stmt)
        record = db_res.scalar_one()

        assert record.connection_status == "revoked"
        assert record.encrypted_access_token == b""
        assert record.encrypted_refresh_token is None

    @pytest.mark.asyncio
    async def test_tool_upstream_401_marks_connection_expired_in_vault(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Upstream 401 response from GitHub API marks connection as expired in the vault."""
        user = await _create_test_user(db_session, "gh_upstream_401@example.com")
        vault = OAuthVaultService()

        await vault.store_tokens(
            db=db_session,
            user_id=user.id,
            provider="github",
            access_token="gho_revoked_on_github",
            scopes=["repo"],
        )
        await db_session.commit()

        tool = GitHubSearchTool()

        # Mock GitHub search raising 401 Unauthorized
        mock_request = httpx.Request("GET", "https://api.github.com/search/issues")
        mock_response = httpx.Response(
            status_code=401,
            json={"message": "Bad credentials"},
            request=mock_request,
        )
        err = httpx.HTTPStatusError("401 Unauthorized", request=mock_request, response=mock_response)

        with patch("httpx.AsyncClient.get", side_effect=err):
            result = await tool._run(
                params={"query": "test query"},
                user_id=user.id,
                db=db_session,
            )

        assert result.success is False
        assert "Authorization failed (HTTP 401)" in result.error

        # Verify vault status in database transitioned to expired
        stmt = select(UserConnectedApp).where(
            UserConnectedApp.user_id == user.id,
            UserConnectedApp.provider == "github",
        )
        db_res = await db_session.execute(stmt)
        record = db_res.scalar_one()
        assert record.connection_status == "expired"

    def test_configurable_github_scopes_setting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """github_oauth_scopes in settings parses comma/space separated scopes correctly."""
        monkeypatch.setattr(settings, "github_oauth_scopes", "public_repo, read:user")
        assert settings.github_scopes_list == ["public_repo", "read:user"]

        monkeypatch.setattr(settings, "github_client_id", "test_id")
        monkeypatch.setattr(
            settings, "github_client_secret", SecretStr("test_secret")
        )
        svc = GitHubOAuthService()
        auth_url = svc.get_authorization_url(
            state="test_state_12345",
            redirect_uri="http://localhost:8000/callback",
        )
        assert "scope=public_repo+read%3Auser" in auth_url
