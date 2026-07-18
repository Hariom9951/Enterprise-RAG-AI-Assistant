"""
Enterprise RAG AI Assistant — Authentication Pydantic Schemas
=============================================================
Request and response models for the authentication API endpoints.

All passwords are write-only (excluded from serialisation) to ensure
they can never leak in API responses or log output.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import UserRole

# =============================================================================
# Shared Config
# =============================================================================


class _BaseSchema(BaseModel):
    """Base schema with consistent model configuration."""

    model_config = {"from_attributes": True}  # Enable ORM mode


# =============================================================================
# Password Validation
# =============================================================================

_PASSWORD_PATTERN = re.compile(
    r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[@$!%*?&_\-#^])[A-Za-z\d@$!%*?&_\-#^]{8,}$"
)

_PASSWORD_REQUIREMENTS = (
    "Password must be at least 8 characters and contain at least one "
    "uppercase letter, one lowercase letter, one digit, and one special "
    "character (@$!%*?&_-#^)."
)


def _validate_password_strength(value: str) -> str:
    """Raise ValueError if the password does not meet strength requirements."""
    if not _PASSWORD_PATTERN.match(value):
        raise ValueError(_PASSWORD_REQUIREMENTS)
    return value


# =============================================================================
# Registration
# =============================================================================


class RegisterRequest(_BaseSchema):
    """
    Request body for ``POST /api/v1/auth/register``.

    Fields are validated strictly:
      - ``email``: RFC-compliant format (requires email-validator package).
      - ``password``: Strong password policy enforced by regex.
      - ``full_name``: Non-empty, trimmed, max 255 characters.
    """

    full_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="User's full display name.",
        examples=["Jane Doe"],
    )
    email: EmailStr = Field(
        ...,
        description="Valid email address. Used as the login identifier.",
        examples=["jane.doe@example.com"],
    )
    password: str = Field(
        ...,
        min_length=8,
        description=_PASSWORD_REQUIREMENTS,
        examples=["Secure@123"],
    )

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        """Trim leading/trailing whitespace from full_name."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("full_name must not be blank.")
        return stripped

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        """Enforce password strength policy."""
        return _validate_password_strength(value)


# =============================================================================
# Login
# =============================================================================


class LoginRequest(_BaseSchema):
    """Request body for ``POST /api/v1/auth/login``."""

    email: EmailStr = Field(
        ..., description="Registered email address.", examples=["jane.doe@example.com"]
    )
    password: str = Field(..., description="Account password.", examples=["Secure@123"])


# =============================================================================
# Token Refresh
# =============================================================================


class RefreshRequest(_BaseSchema):
    """Request body for ``POST /api/v1/auth/refresh``."""

    refresh_token: str = Field(
        ..., description="Valid refresh token obtained at login."
    )


# =============================================================================
# Token Response
# =============================================================================


class TokenResponse(_BaseSchema):
    """
    Response body for login and refresh endpoints.

    ``access_token``  — short-lived JWT for API authentication.
    ``refresh_token`` — long-lived JWT to obtain a new access token.
    ``expires_in``    — access token TTL in seconds (for client-side timers).
    """

    access_token: str = Field(..., description="Short-lived JWT access token.")
    refresh_token: str = Field(..., description="Long-lived JWT refresh token.")
    token_type: str = Field(
        default="bearer", description="Token scheme (always 'bearer')."
    )
    expires_in: int = Field(..., description="Access token TTL in seconds.")


# =============================================================================
# User Responses
# =============================================================================


class UserResponse(_BaseSchema):
    """
    Public user representation returned by the API.

    ``hashed_password`` is intentionally omitted — it must NEVER appear
    in API responses.
    """

    id: uuid.UUID = Field(..., description="Unique user identifier.")
    full_name: str = Field(..., description="User's display name.")
    email: str = Field(..., description="User's email address.")
    role: UserRole = Field(..., description="RBAC role: 'user' or 'admin'.")
    is_active: bool = Field(..., description="Whether the account is currently active.")
    is_verified: bool = Field(..., description="Whether the email has been verified.")
    created_at: datetime = Field(..., description="Account creation timestamp (UTC).")
    updated_at: datetime = Field(
        ..., description="Last profile update timestamp (UTC)."
    )
