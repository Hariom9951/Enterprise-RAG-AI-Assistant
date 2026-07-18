"""
Enterprise RAG AI Assistant — Shared Pydantic Response Schemas
==============================================================
All response models used across API endpoints are defined here.
Using shared schemas keeps the API contract consistent and makes
it trivial to generate accurate OpenAPI documentation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

# Generic type variable for paginated / wrapped responses.
T = TypeVar("T")


# =============================================================================
# Base Response
# =============================================================================


class BaseResponse(BaseModel):
    """
    Base class for all API response models.

    Provides a consistent ``model_config`` so every response schema
    uses ``from_attributes=True`` (ORM mode) by default.
    """

    model_config = {"from_attributes": True}


# =============================================================================
# Root & Informational
# =============================================================================


class MessageResponse(BaseResponse):
    """Simple message envelope returned by the root endpoint."""

    message: str = Field(
        ...,
        description="Human-readable message string.",
        examples=["Enterprise RAG AI Assistant API"],
    )


# =============================================================================
# Health Check
# =============================================================================


class HealthStatus(BaseResponse):
    """Detailed health-check response with component statuses."""

    status: str = Field(
        ...,
        description="Overall service health: 'healthy' | 'degraded' | 'unhealthy'.",
        examples=["healthy"],
    )
    version: str = Field(
        ..., description="Current application version.", examples=["0.1.0"]
    )
    environment: str = Field(
        ..., description="Deployment environment.", examples=["development"]
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of the health-check response.",
    )
    components: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Status of individual components keyed by name. "
            "Values follow the same convention: healthy | degraded | unhealthy."
        ),
        examples=[{"api": "healthy", "database": "healthy"}],
    )


# =============================================================================
# Error
# =============================================================================


class ErrorDetail(BaseResponse):
    """Inner payload of an error response."""

    code: str = Field(
        ...,
        description="Machine-readable error code (SCREAMING_SNAKE_CASE).",
        examples=["RESOURCE_NOT_FOUND"],
    )
    message: str = Field(
        ...,
        description="Human-readable error message.",
        examples=["The requested document was not found."],
    )
    detail: Any = Field(None, description="Optional extra context for debugging.")


class ErrorResponse(BaseResponse):
    """Wrapper for all error responses returned by the API."""

    error: ErrorDetail


# =============================================================================
# Generic Paginated Response
# =============================================================================


class PaginatedResponse(BaseResponse, Generic[T]):
    """
    Generic paginated list response.

    Usage::

        @router.get("/documents", response_model=PaginatedResponse[DocumentSchema])
        async def list_documents(...):
            ...
    """

    items: list[T] = Field(..., description="List of items for the current page.")
    total: int = Field(..., ge=0, description="Total number of items across all pages.")
    page: int = Field(..., ge=1, description="Current page number (1-indexed).")
    page_size: int = Field(..., ge=1, description="Number of items per page.")
    pages: int = Field(..., ge=0, description="Total number of pages.")

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[T]:
        """Factory method to build a paginated response without manual math."""
        import math

        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if page_size > 0 else 0,
        )
