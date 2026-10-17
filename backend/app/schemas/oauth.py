"""
Enterprise RAG AI Assistant — Safe OAuth Pydantic Schemas
=========================================================
Request and response models for OAuth credentials metadata and connection statuses.

Security Guarantees:
- Strictly excludes raw tokens, encrypted bytes, client secrets, and keys.
- Exposes only benign operational metadata: provider, scopes, expiry, and status.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class OAuthProvider(str, Enum):
    """Supported third-party OAuth providers."""

    GMAIL = "gmail"
    GOOGLE_DRIVE = "google_drive"
    GITHUB = "github"
    LINKEDIN = "linkedin"


class OAuthConnectionStatus(str, Enum):
    """Lifecycle status for a connected third-party app."""

    CONNECTED = "connected"
    EXPIRED = "expired"
    REVOKED = "revoked"


class OAuthConnectionMetadata(BaseModel):
    """
    Public connection metadata for an authorized application.
    Contains zero secret material or token bytes.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique connection identifier.")
    provider: str = Field(
        description="Third-party provider identifier (gmail, notion, jira)."
    )
    scopes: list[str] = Field(
        default_factory=list, description="Authorized OAuth scopes."
    )
    expires_at: datetime | None = Field(
        default=None, description="Access token expiration timestamp (UTC)."
    )
    connection_status: str = Field(
        description="Current status (connected, expired, revoked)."
    )
    created_at: datetime = Field(description="Timestamp when the app was first linked.")
    updated_at: datetime | None = Field(
        default=None, description="Timestamp of the last token update."
    )


class OAuthConnectionStatusResponse(BaseModel):
    """Response model listing all connected apps for the authenticated user."""

    connections: list[OAuthConnectionMetadata] = Field(
        default_factory=list, description="List of connected apps."
    )
    total: int = Field(default=0, description="Total number of registered connections.")


class OAuthDisconnectResponse(BaseModel):
    """Response returned upon disconnecting or revoking an application."""

    success: bool = Field(description="Whether the disconnection succeeded.")
    provider: str = Field(description="The provider that was disconnected.")
    message: str = Field(description="Human-readable result summary.")


class OAuthAuthorizeResponse(BaseModel):
    """Response returned when initiating an OAuth flow."""

    authorization_url: str = Field(
        description="Third-party OAuth authorization URL."
    )
    provider: str = Field(description="Target OAuth provider.")
    state: str = Field(description="Opaque CSRF state token.")


class OAuthCallbackResponse(BaseModel):
    """Response returned upon successful OAuth callback completion."""

    success: bool = Field(
        description="Whether the OAuth connection was completed successfully."
    )
    provider: str = Field(description="Target OAuth provider.")
    message: str = Field(description="Human-readable result summary.")
    redirect_url: str = Field(
        description="Safe frontend redirect destination."
    )


class OAuthCallbackRequest(BaseModel):
    """Payload for completing an OAuth flow via authenticated POST."""

    code: str = Field(min_length=1, description="OAuth authorization code.")
    state: str = Field(min_length=16, description="OAuth state parameter.")

