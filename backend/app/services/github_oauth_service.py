"""
Enterprise RAG AI Assistant — GitHub OAuth 2.0 Web Application Flow Service
===========================================================================
Implements GitHub OAuth 2.0 authorization-code flow, token exchange, and permission
validation strictly for personal application integration (GitHubSearchTool).

Protocol & Security Specifications:
- Flow: Authorization Code Grant for Web Applications (RFC 6749 Section 4.1).
- GitHub Endpoints:
    Authorization: https://github.com/login/oauth/authorize
    Token Exchange: https://github.com/login/oauth/access_token
- Authentication & PKCE:
    Standard GitHub OAuth Apps operate as confidential clients and authenticate
    to GitHub's token endpoint using client_id and client_secret.
    GitHub OAuth Apps do not natively enforce PKCE; however, NexusAI's OAuthStateService
    generates and server-side binds a PKCE S256 verifier/challenge to each state to
    guarantee tamper-proof CSRF protection and future compatibility.
- Scopes:
    Default minimum required scope: 'repo' (read-only search of accessible repos,
    issues, and pull requests via GitHub REST API v3 / 2022-11-28).
- Security Guarantees:
    - Client secrets and authorization codes are NEVER logged or exposed.
    - Granted scopes are explicitly validated before storing credentials.
    - Expiration timestamps accurately reflect provider responses without inventing artificial TTLs.
    - Network calls enforce a strict 15-second timeout and handle upstream errors gracefully.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final
from urllib.parse import urlencode

import httpx
from loguru import logger

from app.config.settings import settings

# =============================================================================
# Constants
# =============================================================================

GITHUB_AUTHORIZE_URL: Final[str] = "https://github.com/login/oauth/authorize"
GITHUB_ACCESS_TOKEN_URL: Final[str] = "https://github.com/login/oauth/access_token"
DEFAULT_GITHUB_SCOPES: Final[list[str]] = ["repo"]
GITHUB_TOKEN_EXCHANGE_TIMEOUT_SECONDS: Final[float] = 15.0


def get_default_github_scopes() -> list[str]:
    """
    Retrieve configured GitHub OAuth scopes from settings.
    Defaults to ['repo'] to preserve full read access to private repositories
    and issues required by GitHubSearchTool.
    Operators may configure 'public_repo' for reduced attack surface when
    private repository access is unnecessary.
    """
    try:
        return settings.github_scopes_list
    except Exception:
        return ["repo"]


# =============================================================================
# Exceptions
# =============================================================================


class GitHubOAuthError(Exception):
    """Base exception for GitHub OAuth operations."""


class GitHubOAuthConfigurationError(GitHubOAuthError):
    """Raised when GitHub client ID or client secret is unconfigured."""


class GitHubOAuthNetworkError(GitHubOAuthError):
    """Raised when communication with GitHub OAuth endpoints fails or times out."""


class GitHubOAuthResponseError(GitHubOAuthError):
    """Raised when GitHub returns a malformed response, non-2xx status, or missing token."""


class GitHubOAuthExchangeError(GitHubOAuthError):
    """Raised when GitHub explicitly rejects code exchange (e.g. bad_verification_code)."""

    def __init__(
        self,
        message: str,
        error_code: str = "unknown_error",
        error_description: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.error_description = error_description or error_code


class GitHubOAuthInsufficientScopeError(GitHubOAuthError):
    """Raised when the user did not grant the required OAuth scopes."""

    def __init__(
        self,
        message: str,
        required_scopes: list[str],
        granted_scopes: list[str],
    ) -> None:
        super().__init__(message)
        self.required_scopes = required_scopes
        self.granted_scopes = granted_scopes


# =============================================================================
# GitHub OAuth Service Implementation
# =============================================================================


class GitHubOAuthService:
    """
    Manages GitHub OAuth 2.0 Web Application Flow authorization URLs,
    token exchange, and scope validation.
    """

    def validate_configuration(self) -> None:
        """
        Verify that GitHub client credentials are set in configuration.
        Raises GitHubOAuthConfigurationError if missing or empty.
        """
        if not settings.github_client_id or not settings.github_client_id.strip():
            raise GitHubOAuthConfigurationError(
                "GitHub client ID (GITHUB_CLIENT_ID) is not configured on this server."
            )
        if (
            not settings.github_client_secret
            or not settings.github_client_secret.get_secret_value().strip()
        ):
            raise GitHubOAuthConfigurationError(
                "GitHub client secret (GITHUB_CLIENT_SECRET) is not configured on this server."
            )

    def get_authorization_url(
        self,
        state: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
    ) -> str:
        """
        Construct the GitHub authorization URL for user consent.

        Args:
            state: Cryptographically secure CSRF state token.
            redirect_uri: Canonical callback URL registered with GitHub.
            scopes: Requested permission scopes (defaults to ['repo']).

        Returns:
            Fully formed URL string ready for user browser redirection.
        """
        self.validate_configuration()

        if not state or not state.strip():
            raise ValueError("OAuth state parameter cannot be empty.")
        if not redirect_uri or not redirect_uri.strip():
            raise ValueError("OAuth redirect_uri parameter cannot be empty.")

        target_scopes = (
            scopes if scopes is not None else get_default_github_scopes()
        )
        scope_str = " ".join(target_scopes)

        params = {
            "client_id": settings.github_client_id.strip(),
            "redirect_uri": redirect_uri.strip(),
            "scope": scope_str,
            "state": state.strip(),
        }

        query = urlencode(params)
        return f"{GITHUB_AUTHORIZE_URL}?{query}"

    async def exchange_code_for_token(
        self,
        code: str,
        redirect_uri: str,
        required_scopes: list[str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        """
        Exchange a temporary GitHub authorization code for an OAuth access token.

        Enforces:
        - Confidential client authentication via client_id and client_secret.
        - Strict timeout of 15 seconds.
        - Rejection of malformed JSON, error responses, or missing tokens.
        - Verification that required scopes (e.g. 'repo') were actually granted.
        - Safe extraction of optional expiry and refresh token if supported.

        Returns:
            dict containing 'access_token', 'refresh_token', 'token_type',
            'scopes', and 'expires_at'.
        """
        self.validate_configuration()

        if not code or not code.strip():
            raise ValueError("Authorization code cannot be empty.")

        target_required = (
            required_scopes
            if required_scopes is not None
            else get_default_github_scopes()
        )

        payload = {
            "client_id": settings.github_client_id.strip(),
            "client_secret": settings.github_client_secret.get_secret_value().strip(),
            "code": code.strip(),
            "redirect_uri": redirect_uri.strip(),
        }

        headers = {
            "Accept": "application/json",
            "User-Agent": "NexusAI-Enterprise-Assistant",
        }

        # Perform the outbound HTTP POST to GitHub
        try:
            if client is not None:
                resp = await client.post(
                    GITHUB_ACCESS_TOKEN_URL,
                    json=payload,
                    headers=headers,
                )
            else:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(GITHUB_TOKEN_EXCHANGE_TIMEOUT_SECONDS)
                ) as default_client:
                    resp = await default_client.post(
                        GITHUB_ACCESS_TOKEN_URL,
                        json=payload,
                        headers=headers,
                    )
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            logger.warning(
                "[github_oauth] Network error contacting GitHub token endpoint: {}",
                type(exc).__name__,
            )
            raise GitHubOAuthNetworkError(
                f"Failed to communicate with GitHub OAuth server: {type(exc).__name__}"
            ) from exc

        if resp.status_code >= 400:
            logger.warning(
                "[github_oauth] Token exchange HTTP error: {}",
                resp.status_code,
            )
            raise GitHubOAuthResponseError(
                f"GitHub OAuth server returned HTTP {resp.status_code}."
            )

        try:
            data = resp.json()
        except Exception as exc:
            logger.warning("[github_oauth] Failed to decode JSON from GitHub: {}", exc)
            raise GitHubOAuthResponseError(
                "Invalid JSON received from GitHub OAuth token endpoint."
            ) from exc

        # Check for GitHub-level error in response body (GitHub returns 200 with error field)
        if "error" in data:
            err_code = str(data.get("error", "unknown_error"))
            err_desc = str(data.get("error_description", err_code))
            logger.warning(
                "[github_oauth] Token exchange rejected by GitHub: {}",
                err_code,
            )
            raise GitHubOAuthExchangeError(
                message=f"GitHub token exchange rejected: {err_desc}",
                error_code=err_code,
                error_description=err_desc,
            )

        access_token = data.get("access_token")
        if (
            not access_token
            or not isinstance(access_token, str)
            or not access_token.strip()
        ):
            raise GitHubOAuthResponseError(
                "GitHub OAuth response did not contain an access_token."
            )

        # Parse and validate granted scopes
        raw_scope = data.get("scope", "")
        granted_scopes = [s.strip() for s in raw_scope.split(",") if s.strip()]

        for req in target_required:
            if req not in granted_scopes:
                logger.warning(
                    "[github_oauth] User granted insufficient scopes: required '{}', granted '{}'",
                    req,
                    granted_scopes,
                )
                raise GitHubOAuthInsufficientScopeError(
                    f"Insufficient permissions granted by GitHub: required scope '{req}' was missing.",
                    required_scopes=target_required,
                    granted_scopes=granted_scopes,
                )

        # Parse expiry if provided (standard GitHub OAuth tokens do not expire by default;
        # GitHub Apps with expiring user tokens return expires_in integer seconds)
        expires_in = data.get("expires_in")
        expires_at: datetime | None = None
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))

        # Parse refresh token if provided
        raw_refresh = data.get("refresh_token")
        refresh_token = (
            raw_refresh.strip()
            if (raw_refresh and isinstance(raw_refresh, str) and raw_refresh.strip())
            else None
        )

        return {
            "access_token": access_token.strip(),
            "refresh_token": refresh_token,
            "token_type": data.get("token_type", "bearer"),
            "scopes": granted_scopes,
            "expires_at": expires_at,
        }


# Default singleton instance
github_oauth_service = GitHubOAuthService()
