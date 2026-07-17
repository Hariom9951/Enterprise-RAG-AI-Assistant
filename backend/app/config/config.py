"""
Enterprise RAG AI Assistant — Application Constants & Feature Flags
====================================================================
This module holds application-wide constants that are NOT driven by
environment variables (those live in settings.py).

Typical contents:
  - Magic string/number constants
  - Feature flag definitions (to be wired to a flag service in Phase 2)
  - Route tag definitions for OpenAPI grouping
"""

from typing import Final

# =============================================================================
# API Metadata
# =============================================================================

#: Top-level API title displayed in Swagger UI and ReDoc.
API_TITLE: Final[str] = "Enterprise RAG AI Assistant API"

#: Contact information surfaced in the OpenAPI spec.
API_CONTACT: Final[dict] = {
    "name": "Engineering Team",
    "email": "engineering@example.com",
}

#: License shown in the OpenAPI spec.
API_LICENSE: Final[dict] = {
    "name": "MIT",
    "url": "https://opensource.org/licenses/MIT",
}

# =============================================================================
# OpenAPI Tags
# =============================================================================
# Tags are used to group endpoints logically in Swagger UI.

TAGS_METADATA: Final[list[dict]] = [
    {
        "name": "health",
        "description": "Health-check and liveness probe endpoints.",
    },
    {
        "name": "root",
        "description": "Root informational endpoints.",
    },
    # Phase 2 stubs — uncomment as features are implemented:
    # {"name": "auth",      "description": "Authentication & authorisation."},
    # {"name": "documents", "description": "Document ingestion and management."},
    # {"name": "chat",      "description": "Conversational RAG interface."},
    # {"name": "search",    "description": "Semantic search over the knowledge base."},
]

# =============================================================================
# Pagination
# =============================================================================

#: Default number of items returned per page.
DEFAULT_PAGE_SIZE: Final[int] = 20

#: Maximum number of items that can be requested in a single page.
MAX_PAGE_SIZE: Final[int] = 100

# =============================================================================
# Rate Limiting (Placeholders — implement in Phase 2)
# =============================================================================

#: Maximum requests per minute per client IP (for future rate-limiter).
RATE_LIMIT_PER_MINUTE: Final[int] = 60

# =============================================================================
# Feature Flags (Placeholders — wire to LaunchDarkly / Unleash in Phase 2)
# =============================================================================

class FeatureFlags:
    """
    Static feature flags for Phase 1.

    In a later phase, replace these constants with dynamic flag evaluation
    from a remote flag service (e.g. LaunchDarkly, Unleash, or GrowthBook).
    """

    #: Enable the conversational RAG chat endpoint.
    ENABLE_RAG_CHAT: bool = False

    #: Enable document upload and ingestion pipeline.
    ENABLE_DOCUMENT_INGESTION: bool = False

    #: Enable semantic search endpoint.
    ENABLE_SEMANTIC_SEARCH: bool = False

    #: Enable user authentication middleware.
    ENABLE_AUTH: bool = False
