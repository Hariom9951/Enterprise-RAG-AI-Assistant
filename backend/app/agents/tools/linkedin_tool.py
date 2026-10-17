"""
Enterprise RAG AI Assistant — LinkedIn Basic Profile & Manual Import Tool
=========================================================================
Implements restricted, authorized basic profile access via the LinkedIn
REST API (v2 /userinfo OpenID Connect) and a manual import fallback for
user-provided LinkedIn content (e.g. pasted posts, articles, or resumes).

Permissions & Limitations:
- Public/developer LinkedIn apps are strictly restricted by LinkedIn to
  'openid', 'profile', and 'email' scopes (Sign In with LinkedIn).
- LinkedIn strictly forbids scraping and restricts feed/messages/connections
  to approved Enterprise Partners.
- Therefore, this tool strictly scopes live API calls to /v2/userinfo.
- For post history, saved articles, or connections, the user must use the
  explicit manual-import capability provided here, which clearly marks the
  data as user-provided evidence rather than verified live LinkedIn data.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Final

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_tool import ParameterSpec, PermissionLevel, ToolResult
from app.agents.tools.personal_app_base import (
    MAX_RESULTS_PER_CALL,
    PersonalAppBaseTool,
    ProviderItem,
)
from app.core.logging import logger

_LINKEDIN_HOST: Final[str] = "api.linkedin.com"
_USERINFO_ENDPOINT: Final[str] = "/v2/userinfo"
_EXCERPT_MAX_CHARS: Final[int] = 1000


class LinkedInProfileTool(PersonalAppBaseTool):
    """
    Retrieve basic authorized profile details or manually imported LinkedIn content.

    Provides verified user identity data from LinkedIn OIDC userinfo endpoint,
    or retrieves user-supplied LinkedIn text snippets.
    """

    id = "linkedin_profile"
    name = "LinkedIn Profile & Content Access"
    description = (
        "Retrieve the authenticated user's authorized basic LinkedIn profile (name, headline, email) "
        "or access clearly labeled user-imported LinkedIn posts/content. "
        "Note: Live search of external LinkedIn posts, connections, or messages is restricted by LinkedIn "
        "and is not supported via live API."
    )
    permission_level = PermissionLevel.USER
    provider_name = "linkedin"
    api_host = _LINKEDIN_HOST

    parameters = [
        ParameterSpec(
            name="action",
            type="string",
            description="Action to perform: 'get_profile' (live OIDC userinfo) or 'import_content' (manual text import).",
            required=False,
            default="get_profile",
            enum=["get_profile", "import_content"],
        ),
        ParameterSpec(
            name="manual_content",
            type="string",
            description="User-provided LinkedIn text (required only when action='import_content').",
            required=False,
            default=None,
        ),
        ParameterSpec(
            name="content_label",
            type="string",
            description="Descriptive title for manual content (e.g. 'My Recent LinkedIn Post on AI').",
            required=False,
            default="User-provided LinkedIn Content",
        ),
    ]

    async def _fetch(
        self,
        params: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> list[ProviderItem]:
        action: str = params.get("action") or "get_profile"

        if action == "import_content":
            raw_text = (params.get("manual_content") or "").strip()
            label = (params.get("content_label") or "User-provided LinkedIn Content").strip()
            if not raw_text:
                raise ValueError("manual_content is required when action='import_content'.")

            retrieved_at = datetime.now(UTC).isoformat()
            return [
                ProviderItem(
                    provider="linkedin",
                    source_id=f"linkedin:manual:{uuid.uuid4().hex[:12]}",
                    title=f"[Manual Import] {label[:150]}",
                    excerpt=f"[User-Provided LinkedIn Content: Not verified by live API] {raw_text[:_EXCERPT_MAX_CHARS]}",
                    source_url=None,
                    retrieved_at=retrieved_at,
                    extra_metadata={
                        "is_manual_import": True,
                        "verified_by_api": False,
                        "label": label,
                    },
                )
            ]

        # Standard action: fetch live /v2/userinfo
        resp = await client.get(_USERINFO_ENDPOINT)
        resp.raise_for_status()
        data = resp.json()

        item = _parse_linkedin_userinfo(data)
        return [item] if item else []


def _parse_linkedin_userinfo(data: dict[str, Any]) -> ProviderItem | None:
    """Normalize LinkedIn OIDC userinfo response into a ProviderItem."""
    try:
        sub = data.get("sub", "")
        name = data.get("name") or "(name not provided)"
        given_name = data.get("given_name", "")
        family_name = data.get("family_name", "")
        email = data.get("email") or "not provided"
        email_verified = data.get("email_verified", False)
        locale_obj = data.get("locale") or {}
        locale_str = f"{locale_obj.get('language', '')}_{locale_obj.get('country', '')}" if isinstance(locale_obj, dict) else str(locale_obj)

        excerpt = (
            f"Authorized LinkedIn Profile: {name} (Email: {email}, "
            f"Locale: {locale_str}). "
            "[Notice: LinkedIn feed search and member connection access require enterprise partnership "
            "and are not available via standard developer authorization.]"
        )[:_EXCERPT_MAX_CHARS]

        retrieved_at = datetime.now(UTC).isoformat()

        # Only use a verified canonical profile URL provided directly by the API response.
        # Do not guess or generate a generic directory stub like 'https://www.linkedin.com/in/'.
        canonical_url = data.get("profile") or data.get("canonical_url") or data.get("url")
        source_url: str | None = None
        if canonical_url and isinstance(canonical_url, str):
            clean_url = canonical_url.strip()
            if (
                clean_url.startswith("https://")
                and "linkedin.com/in/" in clean_url
                and clean_url.rstrip("/") != "https://www.linkedin.com/in"
            ):
                source_url = clean_url

        return ProviderItem(
            provider="linkedin",
            source_id=f"linkedin:user:{sub}",
            title=f"LinkedIn Profile: {name}",
            excerpt=excerpt,
            source_url=source_url,
            retrieved_at=retrieved_at,
            extra_metadata={
                "is_manual_import": False,
                "verified_by_api": True,
                "email": email,
                "email_verified": email_verified,
                "given_name": given_name,
                "family_name": family_name,
            },
        )
    except Exception as exc:
        logger.warning("[linkedin] Failed to parse userinfo: {}", type(exc).__name__)
        return None
