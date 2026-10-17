"""
Enterprise RAG AI Assistant — User Memory Schemas
=================================================
Pydantic v2 validation models for persistent user memories.

Guarantees:
- Restricts memory types to supported vocabulary (preference, fact, goal, context).
- Prevents clients from injecting or claiming server-controlled fields
  (user_id, provenance, confidence_score, is_active).
- Validates content length (1 to 2000 characters).
- Enforces conservative credential screening to reject secret leakage.
- Enforces privacy controls to prevent storing raw dialog transcripts or sensitive national IDs/cards.
- Preserves readable user content while providing strict duplicate detection contracts.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# =============================================================================
# Enumerations
# =============================================================================


class MemoryType(str, Enum):
    """Permitted memory categories."""

    PREFERENCE = "preference"
    FACT = "fact"
    GOAL = "goal"
    CONTEXT = "context"


class MemoryProvenance(str, Enum):
    """Source provenance tracking for stored memories."""

    USER_EXPLICIT = "user_explicit"
    AGENT_EXTRACTED = "agent_extracted"
    SYSTEM = "system"


class MemoryCreationStatus(str, Enum):
    """Outcome status for explicit memory creation workflows."""

    CREATED = "created"
    DUPLICATE = "duplicate"
    INVALID_CONTENT = "invalid_content"
    REJECTED_SECRET = "rejected_secret"
    REJECTED_PRIVACY = "rejected_privacy"
    REJECTED_TRANSCRIPT = "rejected_transcript"


# =============================================================================
# Privacy and Conservative Security Detection Patterns
# =============================================================================

# High-precision patterns to prevent storing keys, certificates, or tokens
# without triggering false positives on ordinary text.
CREDENTIAL_PATTERNS: list[re.Pattern[str]] = [
    # PEM private key headers
    re.compile(r"-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----"),
    # OpenAI API keys
    re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b"),
    # GitHub PATs / tokens
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{20,}\b"),
    # GitLab Personal Access Tokens
    re.compile(r"\bglpat-[a-zA-Z0-9\-_]{20,}\b"),
    # Slack tokens
    re.compile(r"\bxox[baprs]-[a-zA-Z0-9]{10,}\b"),
    # AWS Access Key ID
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    # JSON Web Tokens (standard 3-part base64 encoded)
    re.compile(r"\beyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b"),
    # Explicit secret assignments with high-entropy token strings
    re.compile(
        r"(?i)\b(?:api[_-]?key|secret[_-]?key|client[_-]?secret|auth[_-]?token|access[_-]?token)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-\.]{20,}['\"]?"
    ),
]

# Raw conversation transcript multi-turn dialog pattern
TRANSCRIPT_PATTERN: re.Pattern[str] = re.compile(
    r"(?im)^(?:user|human|assistant|ai|system)\s*:\s*.+\n+(?:user|human|assistant|ai|system)\s*:\s*.+"
)

# Sensitive national identifiers / payment card patterns
SSN_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?!000|666|9\d{2})\d{3}[- ](?!00)\d{2}[- ](?!0000)\d{4}\b"
)
CARD_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:\d{4}[- ]){3}\d{4}\b"
)


def validate_safe_memory_content(content: str) -> str:
    """
    Validate memory text for length, privacy safeguards, and credential presence.

    Raises:
        ValueError: If content is empty, exceeds 2000 characters, matches a raw
                    dialog transcript, contains sensitive financial/national IDs,
                    or matches credential signatures.
    """
    cleaned = content.strip()
    if not cleaned:
        raise ValueError("Memory content cannot be empty or whitespace only.")
    if len(cleaned) > 2000:
        raise ValueError("Memory content exceeds the maximum limit of 2,000 characters.")

    # 1. Reject raw multi-turn conversation transcripts
    if TRANSCRIPT_PATTERN.search(cleaned):
        raise ValueError(
            "Memory content appears to be a raw conversation transcript. "
            "Persistent memories must be discrete user preferences, facts, goals, or context."
        )

    # 2. Reject sensitive financial or national identification numbers (PII)
    if CARD_PATTERN.search(cleaned) or SSN_PATTERN.search(cleaned):
        raise ValueError(
            "Memory content appears to contain sensitive personal identifiers (card or national ID numbers)."
        )

    # 3. Reject credentials and secret keys
    for pattern in CREDENTIAL_PATTERNS:
        if pattern.search(cleaned):
            raise ValueError(
                "Memory content appears to contain sensitive credential or secret material."
            )

    return cleaned


# =============================================================================
# Request Schemas
# =============================================================================


class UserMemoryCreate(BaseModel):
    """
    Payload for creating a new user memory.

    Client-provided user_id, provenance, and confidence_score are strictly forbidden.
    """

    model_config = ConfigDict(extra="forbid")

    content: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Text content of the memory (1 to 2000 characters).",
        examples=["I prefer concise technical summaries with code snippets."],
    )
    memory_type: MemoryType = Field(
        ...,
        description="Categorization of the memory: 'preference', 'fact', 'goal', or 'context'.",
        examples=[MemoryType.PREFERENCE],
    )

    @field_validator("content")
    @classmethod
    def check_content(cls, v: str) -> str:
        return validate_safe_memory_content(v)


class UserMemoryUpdate(BaseModel):
    """
    Payload for updating an existing user memory.

    Only content and memory_type can be modified. Ownership and provenance
    remain immutable and server-controlled.
    """

    model_config = ConfigDict(extra="forbid")

    content: str | None = Field(
        default=None,
        min_length=1,
        max_length=2000,
        description="Updated text content of the memory.",
        examples=["I prefer concise summaries in markdown format."],
    )
    memory_type: MemoryType | None = Field(
        default=None,
        description="Updated memory category.",
        examples=[MemoryType.PREFERENCE],
    )

    @field_validator("content")
    @classmethod
    def check_content(cls, v: str | None) -> str | None:
        if v is not None:
            return validate_safe_memory_content(v)
        return v

    @model_validator(mode="after")
    def verify_at_least_one_field(self) -> UserMemoryUpdate:
        if self.content is None and self.memory_type is None:
            raise ValueError("At least one of 'content' or 'memory_type' must be provided.")
        return self


# =============================================================================
# Response & Workflow Schemas
# =============================================================================


class UserMemoryResponse(BaseModel):
    """Public representation of a user memory."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID = Field(description="Unique memory identifier.")
    user_id: uuid.UUID = Field(description="ID of the user who owns this memory.")
    content: str = Field(description="Original memory text.")
    memory_type: str = Field(description="Category of the memory.")
    provenance: str = Field(description="Provenance source of the memory.")
    confidence_score: float | None = Field(
        default=None, description="Confidence score in the range [0.0, 1.0]."
    )
    is_active: bool = Field(description="Active lifecycle status.")
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="metadata_",
        serialization_alias="metadata",
        description="Safe operational metadata.",
    )
    created_at: datetime = Field(description="Timestamp when created (UTC).")
    updated_at: datetime = Field(description="Timestamp when last updated (UTC).")


class UserMemorySearchResponse(BaseModel):
    """Response envelope for memory keyword search queries."""

    items: list[UserMemoryResponse] = Field(
        default_factory=list, description="Matched active memories (at most 5)."
    )
    query: str = Field(description="The executed search query.")
    total: int = Field(description="Number of returned results.")
    disclaimer: str = Field(
        default="Keyword match only; semantic search is not enabled.",
        description="Retrieval methodology clarification.",
    )


class ExplicitMemoryResult(BaseModel):
    """Structured result returned by the explicit memory creation operation."""

    model_config = ConfigDict(from_attributes=True)

    status: MemoryCreationStatus = Field(description="Outcome status of the creation request.")
    memory: UserMemoryResponse | None = Field(
        default=None, description="The created memory if successful."
    )
    conflicting_memory_id: uuid.UUID | None = Field(
        default=None, description="ID of existing memory in case of duplicate conflict."
    )
    error_message: str | None = Field(
        default=None, description="Sanitized, privacy-safe explanation if not created."
    )
