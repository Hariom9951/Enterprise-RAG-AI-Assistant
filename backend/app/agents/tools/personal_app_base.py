"""
Enterprise RAG AI Assistant — Personal-App Provider Tool Base
=============================================================
Shared infrastructure for Gmail, Notion, and Jira read-only retrieval tools.

Security Contract:
- Credentials are ONLY sourced from OAuthVaultService via the authenticated user_id.
- Caller-supplied tool arguments may NEVER override authorization headers or bearer tokens.
- All outbound HTTPS hosts are allowlisted here; no arbitrary URL construction.
- Retrieved content is treated as untrusted evidence and is never executed as instructions.
- Access tokens, refresh tokens, and raw auth headers are NEVER logged.
- InactiveConnectionError from the vault propagates as a graceful ToolResult failure.
- A 15-second maximum per external request is enforced via HTTPX timeouts.
- Results are capped at MAX_RESULTS_PER_CALL (5) items per call.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Final

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_tool import BaseTool, ToolResult
from app.core.logging import logger
from app.services.oauth_vault_service import InactiveConnectionError, OAuthVaultService

# =============================================================================
# Constants
# =============================================================================

MAX_RESULTS_PER_CALL: Final[int] = 5
REQUEST_TIMEOUT_SECONDS: Final[float] = 15.0

# Allowlisted HTTPS API hosts — provider tools may ONLY contact these.
ALLOWLISTED_HOSTS: Final[frozenset[str]] = frozenset(
    {
        "gmail.googleapis.com",
        "www.googleapis.com",
        "drive.googleapis.com",
        "api.github.com",
        "api.linkedin.com",
        "api.notion.com",
        "api.atlassian.com",
    }
)

_vault_service = OAuthVaultService()


# =============================================================================
# Normalized Result Item
# =============================================================================


@dataclass
class ProviderItem:
    """
    Normalized evidence item returned by every personal-app tool.

    Fields are intentionally safe for inclusion in LLM context — they carry
    provenance metadata sufficient for later citation generation.
    """

    provider: str
    """Provider identifier, e.g. 'gmail', 'google_drive', 'github', 'linkedin'."""

    source_id: str
    """Stable identifier assigned by the provider (message ID, file ID, repo/issue ID)."""

    title: str
    """Human-readable title or subject of the item."""

    excerpt: str
    """Safe, truncated excerpt of the content (maximum 1000 characters)."""

    source_url: str | None = None
    """Direct URL to the item at the provider, if available."""

    retrieved_at: str | None = None
    """ISO-8601 UTC timestamp when the item was fetched."""

    extra_metadata: dict[str, Any] | None = None
    """Additional safe metadata: sender, labels, status, dates, etc."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "source_id": self.source_id,
            "title": self.title,
            "excerpt": self.excerpt,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "extra_metadata": self.extra_metadata or {},
        }


# =============================================================================
# Secure HTTP Client Factory
# =============================================================================


def _build_http_client(bearer_token: str, host: str) -> httpx.AsyncClient:
    """
    Build an HTTPX AsyncClient pre-configured with:
    - Bearer authorization bound to a single allowlisted host.
    - 15-second timeout on all operations.
    - No redirects (to avoid accidental token leakage).

    The bearer_token is injected server-side from the vault; it must NEVER
    appear in tool-call arguments or response bodies.
    """
    if host not in ALLOWLISTED_HOSTS:
        raise ValueError(
            f"Host '{host}' is not in the allowlisted provider API hosts."
        )

    return httpx.AsyncClient(
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "User-Agent": "NexusAI-Enterprise-RAG/1.0",
        },
        timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
        follow_redirects=False,
        base_url=f"https://{host}",
    )


# =============================================================================
# Provider Tool Base
# =============================================================================


class PersonalAppBaseTool(BaseTool):
    """
    Abstract base for personal-app retrieval tools.

    Subclasses implement:
      - provider_name: str     — e.g. 'gmail', 'google_drive', 'github'
      - api_host: str          — must be in ALLOWLISTED_HOSTS
      - _fetch()               — performs the actual API call, returns list[ProviderItem]

    This base handles:
      - Credential resolution from OAuthVaultService for the authenticated user.
      - InactiveConnectionError → graceful ToolResult(success=False).
      - HTTPX timeout → ToolResult with descriptive error.
      - HTTP 401/403 → ToolResult with auth error (no token details logged).
      - Result capping at MAX_RESULTS_PER_CALL.
    """

    provider_name: str = ""
    api_host: str = ""

    async def _get_credentials(
        self,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """
        Retrieve decrypted credentials dict from the vault for the authenticated user.
        Raises InactiveConnectionError if revoked or expired.
        Raises ValueError if connection is not configured.
        """
        creds = await _vault_service.get_decrypted_credentials(
            db=db,
            user_id=user_id,
            provider=self.provider_name,
        )
        if creds is None:
            raise ValueError(
                f"No {self.provider_name} connection found for this user. "
                "Connect your account first."
            )
        return creds

    async def _get_bearer_token(
        self,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> str:
        """
        Retrieve the decrypted access token from the vault for the authenticated user.
        """
        creds = await self._get_credentials(user_id, db)
        return creds["access_token"]


    async def _fetch(
        self,
        params: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> list[ProviderItem]:
        """
        Perform the provider-specific API call.
        Must be overridden by subclasses.
        """
        raise NotImplementedError

    async def _run(
        self,
        params: dict[str, Any],
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> ToolResult:
        """
        Credential resolution → HTTP call → normalization → result capping.
        Errors are returned in ToolResult; never raised.
        """
        try:
            bearer_token = await self._get_bearer_token(user_id, db)
        except InactiveConnectionError as exc:
            return ToolResult(
                success=False,
                output=None,
                error=f"[{self.provider_name}] Connection is inactive: {exc}",
            )
        except ValueError as exc:
            return ToolResult(
                success=False,
                output=None,
                error=f"[{self.provider_name}] {exc}",
            )

        try:
            async with _build_http_client(bearer_token, self.api_host) as client:
                items = await self._fetch(params, client)
        except httpx.TimeoutException:
            logger.warning(
                "[{}] API request timed out after {}s",
                self.provider_name,
                REQUEST_TIMEOUT_SECONDS,
            )
            return ToolResult(
                success=False,
                output=None,
                error=(
                    f"[{self.provider_name}] Request timed out after "
                    f"{REQUEST_TIMEOUT_SECONDS:.0f} seconds."
                ),
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                logger.warning(
                    "[{}] Authorization error: HTTP {}",
                    self.provider_name,
                    status,
                )
                try:
                    await _vault_service.mark_connection_expired(
                        db=db,
                        user_id=user_id,
                        provider=self.provider_name,
                    )
                except Exception as sync_exc:
                    logger.warning(
                        "[{}] Failed to mark connection expired in vault: {}",
                        self.provider_name,
                        sync_exc,
                    )
                return ToolResult(
                    success=False,
                    output=None,
                    error=(
                        f"[{self.provider_name}] Authorization failed (HTTP {status}). "
                        "The stored access token may have been revoked by the provider. "
                        "Please reconnect your account."
                    ),
                )
            if status == 429:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"[{self.provider_name}] Rate limit exceeded (HTTP 429). Retry later.",
                )
            return ToolResult(
                success=False,
                output=None,
                error=f"[{self.provider_name}] API error: HTTP {status}.",
            )
        except (httpx.RequestError, ValueError, KeyError) as exc:
            logger.warning("[{}] Request or parsing error: {}", self.provider_name, type(exc).__name__)
            return ToolResult(
                success=False,
                output=None,
                error=f"[{self.provider_name}] Failed to retrieve data: {type(exc).__name__}.",
            )

        # Cap results to MAX_RESULTS_PER_CALL
        capped = items[:MAX_RESULTS_PER_CALL]
        output = [item.to_dict() for item in capped]

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "provider": self.provider_name,
                "total_returned": len(capped),
                "result_limit": MAX_RESULTS_PER_CALL,
            },
        )
