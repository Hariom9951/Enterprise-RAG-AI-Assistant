"""
Enterprise RAG AI Assistant — Application Settings
====================================================
Single source of truth for all configuration values.

Uses pydantic-settings to:
  - Load from environment variables
  - Load from .env file (via python-dotenv)
  - Validate types at startup
  - Provide defaults with clear documentation
"""

from functools import lru_cache
from typing import Any, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Pydantic-settings automatically reads values from:
      1. Environment variables (highest priority)
      2. .env file in the backend directory
      3. Default values defined below (lowest priority)
    """

    model_config = SettingsConfigDict(
        # Load .env for local development. On Hugging Face Spaces, secrets are
        # injected as real OS environment variables (highest priority) so no
        # production env file is needed or loaded — the OS env always wins.
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # Allow both APP_NAME and app_name
        extra="ignore",  # Ignore unknown env vars silently
    )

    # -------------------------------------------------------------------------
    # Application Metadata
    # -------------------------------------------------------------------------
    app_name: str = Field(
        default="Enterprise RAG AI Assistant",
        description="Human-readable name of the application.",
    )
    app_version: str = Field(
        default="0.2.0",
        description="Semantic version string (major.minor.patch).",
    )
    app_description: str = Field(
        default="Production-ready Enterprise RAG AI Assistant API",
        description="Short description shown in API docs.",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode. NEVER set True in production.",
    )
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Deployment environment identifier.",
    )

    # -------------------------------------------------------------------------
    # Server
    # -------------------------------------------------------------------------
    host: str = Field(
        default="0.0.0.0",  # nosec B104
        description="Bind address for Uvicorn.",
    )
    port: int = Field(
        default=7860,
        ge=1,
        le=65535,
        description="Bind port. Defaults to 7860 for Hugging Face Spaces compatibility.",
    )
    workers: int = Field(
        default=1,
        ge=1,
        description="Number of Uvicorn worker processes.",
    )
    reload: bool = Field(
        default=False,
        description="Hot-reload on file changes (dev only).",
    )

    # -------------------------------------------------------------------------
    # API Routing
    # -------------------------------------------------------------------------
    api_v1_prefix: str = Field(
        default="/api/v1",
        description="URL prefix for all v1 endpoints.",
    )
    docs_url: str | None = Field(
        default="/docs",
        description="Swagger UI path. Set to None to disable.",
    )
    redoc_url: str | None = Field(
        default="/redoc",
        description="ReDoc path. Set to None to disable.",
    )

    # -------------------------------------------------------------------------
    # CORS
    # -------------------------------------------------------------------------
    allowed_origins: str | list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="List of allowed CORS origins.",
    )
    allowed_methods: str | list[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        description="Allowed HTTP methods for CORS.",
    )
    allowed_headers: str | list[str] = Field(
        default=["*"],
        description="Allowed HTTP headers for CORS.",
    )
    allow_credentials: bool = Field(
        default=True,
        description="Allow cookies/auth headers in cross-origin requests.",
    )

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Minimum log level to emit.",
    )
    log_format: Literal["text", "json"] = Field(
        default="json",
        description="Log output format. 'json' for production (HF Spaces default); 'text' for local dev.",
    )
    log_file_path: str = Field(
        default="",
        description=(
            "File path for persistent log output. Empty string (default) disables file logging "
            "so all output goes to stdout — required for Hugging Face Spaces and container environments."
        ),
    )

    # -------------------------------------------------------------------------
    # Database (Phase 2)
    # -------------------------------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://raguser:ragpassword@localhost:5432/ragdb",
        description="Async SQLAlchemy database connection string.",
    )

    # -------------------------------------------------------------------------
    # Security (Phase 2)
    # -------------------------------------------------------------------------
    secret_key: str = Field(
        default="change-me-in-production",
        description="Secret key for signing tokens. MUST be changed in production.",
    )
    algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm. HS256 for symmetric, RS256 for asymmetric.",
    )
    access_token_expire_minutes: int = Field(
        default=30,
        ge=1,
        description="JWT access token TTL in minutes.",
    )
    refresh_token_expire_days: int = Field(
        default=7,
        ge=1,
        description="JWT refresh token TTL in days.",
    )
    encryption_master_key: str | None = Field(
        default=None,
        description="Dedicated 32-byte master encryption key for OAuth Credential Vault (64 hex characters or 32 raw bytes).",
    )
    oauth_redirect_base_url: str = Field(
        default="http://localhost:8000",
        description="Base URL for OAuth redirect callbacks (e.g. https://api.example.com).",
    )
    oauth_state_ttl_seconds: int = Field(
        default=600,
        ge=60,
        le=3600,
        description="TTL for ephemeral OAuth state and PKCE verifier parameters in seconds.",
    )
    # Google OAuth
    google_client_id: str | None = Field(
        default=None,
        description="Google OAuth 2.0 Client ID for Gmail and Drive personal app integration.",
    )
    google_client_secret: SecretStr | None = Field(
        default=None,
        description="Google OAuth 2.0 Client Secret.",
    )
    # GitHub OAuth
    github_client_id: str | None = Field(
        default=None,
        description="GitHub OAuth App / GitHub App Client ID.",
    )
    github_client_secret: SecretStr | None = Field(
        default=None,
        description="GitHub OAuth Client Secret.",
    )
    github_oauth_scopes: str = Field(
        default="repo",
        description=(
            "Configured OAuth scopes to request from GitHub (space- or comma-separated). "
            "Defaults to 'repo' for full repository/issue read access required by GitHubSearchTool. "
            "Use 'public_repo' or fine-grained GitHub App permissions for reduced privilege."
        ),
    )
    # LinkedIn OAuth
    linkedin_client_id: str | None = Field(
        default=None,
        description="LinkedIn OAuth 2.0 Client ID for profile tools.",
    )
    linkedin_client_secret: SecretStr | None = Field(
        default=None,
        description="LinkedIn OAuth Client Secret.",
    )

    # -------------------------------------------------------------------------
    # Phase 3: Document Management
    # -------------------------------------------------------------------------
    max_upload_size_mb: int = Field(
        default=50,
        ge=1,
        description="Maximum file upload size limit in Megabytes.",
    )
    storage_dir: str = Field(
        default="storage",
        description="Path to local document storage folder.",
    )

    # -------------------------------------------------------------------------
    # Phase 4: Asynchronous Processing
    # -------------------------------------------------------------------------
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for Celery message broker.",
    )

    # -------------------------------------------------------------------------
    # Phase 6: Intelligent Chunking & Metadata Enrichment
    # -------------------------------------------------------------------------
    default_chunk_size: int = Field(
        default=500,
        ge=1,
        description="Default semantic text chunk size in tokens.",
    )
    default_chunk_overlap: int = Field(
        default=50,
        ge=0,
        description="Default token overlap between consecutive chunks.",
    )
    max_chunk_size: int = Field(
        default=1000,
        ge=1,
        description="Maximum allowed chunk size in tokens.",
    )
    tokenizer_name: str = Field(
        default="cl100k_base",
        description="Tiktoken tokenizer name (encoding) to count tokens.",
    )

    # -------------------------------------------------------------------------
    # Phase 7: Vector Embeddings
    # -------------------------------------------------------------------------
    embedding_model: str = Field(
        default="BAAI/bge-base-en-v1.5",
        description="The SentenceTransformers model name or path.",
    )
    embedding_batch_size: int = Field(
        default=32,
        ge=1,
        description="Batch size for embedding generation.",
    )
    embedding_device: str = Field(
        default="cpu",
        description="Hardware device for model execution (cpu, cuda, mps).",
    )
    vector_dimension: int = Field(
        default=768,
        ge=1,
        description="Dimensionality of vectors generated by the embedding model.",
    )

    # -------------------------------------------------------------------------
    # Phase 9: Enterprise RAG Pipeline
    # -------------------------------------------------------------------------
    llm_provider: str = Field(
        default="gemini",
        description="The primary LLM provider to use: 'gemini'.",
    )
    gemini_api_key: str | None = Field(
        default=None,
        description="API Key for Google Gemini services.",
    )
    gemini_model: str = Field(
        default="gemini-3.5-flash",
        description="The Google Gemini model name to use.",
    )
    rag_top_k: int = Field(
        default=5,
        ge=1,
        description="Default top-k chunks to retrieve for context assembly.",
    )
    rag_max_context_tokens: int = Field(
        default=4000,
        ge=500,
        description="Maximum token budget for context prompt payload.",
    )
    rag_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Temperature for answer generation.",
    )
    rag_max_output_tokens: int = Field(
        default=1000,
        ge=50,
        description="Maximum output tokens for answer generation.",
    )

    # -------------------------------------------------------------------------
    # Phase 10: Enterprise Conversational AI Interface
    # -------------------------------------------------------------------------
    chat_max_history: int = Field(
        default=10,
        ge=1,
        description="Maximum conversational query rounds to preserve in short-term history memory.",
    )
    chat_max_history_turns: int = Field(
        default=10,
        ge=1,
        description="Maximum complete conversational turns to preserve in short-term history memory.",
    )
    chat_max_tokens: int = Field(
        default=4000,
        ge=500,
        description="Maximum token budget for chat history context injection.",
    )
    stream_timeout: float = Field(
        default=30.0,
        ge=1.0,
        description="HTTP connection streaming response timeout threshold in seconds.",
    )
    stream_chunk_size: int = Field(
        default=512,
        ge=1,
        description="Chunk size configuration for SSE transmission blocks.",
    )

    # -------------------------------------------------------------------------
    # Phase 11: Enterprise AI Agents & Tool Calling
    # -------------------------------------------------------------------------
    agent_max_tool_calls: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of tool calls allowed per agent run.",
    )
    agent_tool_timeout_s: float = Field(
        default=15.0,
        ge=1.0,
        description="Per-tool execution timeout in seconds.",
    )
    agent_loop_budget_s: float = Field(
        default=60.0,
        ge=5.0,
        description="Total wall-clock budget for the entire agent run in seconds.",
    )
    agent_max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retry attempts per tool call on transient failures.",
    )
    enable_langgraph: bool = Field(
        default=False,
        description="Enable LangGraph-based agent runner. When False, legacy runner is used.",
    )
    agent_max_reformulations: int = Field(
        default=1,
        ge=0,
        le=3,
        description="Maximum query reformulations allowed in adaptive agentic research.",
    )
    agent_min_relevance_threshold: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
        description="Minimum normalized similarity score floor for evaluating sufficient evidence.",
    )

    # -------------------------------------------------------------------------
    # Phase 12: Production Hardening, Caching, & Monitoring
    # -------------------------------------------------------------------------
    enable_redis_caching: bool = Field(
        default=True,
        description="Enable query caching in Redis.",
    )
    redis_cache_ttl_seconds: int = Field(
        default=3600,
        ge=0,
        description="Time to live for Redis cache records.",
    )
    rate_limit_requests_per_minute: int = Field(
        default=60,
        ge=1,
        description="Maximum requests allowed per client IP per minute.",
    )
    rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        description="Rate limit evaluation sliding window in seconds.",
    )
    trusted_proxies: list[str] = Field(
        default=[],
        description=(
            "List of trusted reverse proxy IP addresses or CIDR blocks (e.g. ['127.0.0.1', '10.0.0.0/8']). "
            "If empty, forwarded headers (X-Forwarded-For) are ignored and direct socket IP is used."
        ),
    )
    max_request_body_size_bytes: int = Field(
        default=2097152,  # 2MB
        ge=1024,
        description="Maximum allowed HTTP request payload size in bytes.",
    )
    database_pool_size: int = Field(
        default=10,
        ge=1,
        description="SQLAlchemy DB pool size.",
    )
    database_max_overflow: int = Field(
        default=20,
        ge=0,
        description="SQLAlchemy DB max overflow.",
    )

    # -------------------------------------------------------------------------
    # Validators
    # -------------------------------------------------------------------------
    @field_validator(
        "allowed_origins",
        "allowed_methods",
        "allowed_headers",
        "trusted_proxies",
        mode="before",
    )
    @classmethod
    def parse_comma_separated(cls, value: str | list) -> list[str]:
        """Allow comma-separated strings from env vars, e.g. ALLOWED_ORIGINS=a,b,c."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        """
        Validate security constraints in production.

        Enforces:
        1. SECRET_KEY cannot be missing, empty, default/placeholder, or shorter than 32 chars in production.
        2. Wildcard ALLOWED_ORIGINS ('*') is strictly forbidden when allow_credentials=True in production.
        """
        lowered_key = (self.secret_key or "").lower().strip()
        is_placeholder = (
            not lowered_key
            or "change-me" in lowered_key
            or "changeme" in lowered_key
            or "placeholder" in lowered_key
            or lowered_key in {
                "secret",
                "default",
                "testsecret",
                "123456",
                "admin",
                "password",
                "secretkey",
                "insecure",
            }
        )

        if self.environment == "production":
            if not self.secret_key or not self.secret_key.strip():
                raise ValueError(
                    "SECRET_KEY must be set in production and cannot be empty."
                )
            if is_placeholder:
                raise ValueError(
                    "SECRET_KEY cannot be a default or placeholder value in production. "
                    "You MUST set a strong, cryptographically secure secret key."
                )
            if len(self.secret_key.strip()) < 32:
                raise ValueError(
                    "SECRET_KEY must be at least 32 characters long in production."
                )

            if self.allow_credentials:
                origins = self.allowed_origins
                has_wildcard = False
                if isinstance(origins, list):
                    has_wildcard = any(o.strip() == "*" for o in origins)
                elif isinstance(origins, str):
                    has_wildcard = origins.strip() == "*"

                if has_wildcard:
                    raise ValueError(
                        "Wildcard CORS origin ('*') is forbidden when allow_credentials=True in production. "
                        "You MUST specify explicit allowed origins (e.g. 'https://app.example.com')."
                    )

            # ENCRYPTION_MASTER_KEY validation in production
            if not self.encryption_master_key or not self.encryption_master_key.strip():
                raise ValueError(
                    "ENCRYPTION_MASTER_KEY must be set in production and cannot be empty."
                )
            cleaned_enc = self.encryption_master_key.strip()
            if len(cleaned_enc) != 64:
                raise ValueError(
                    "ENCRYPTION_MASTER_KEY must be exactly 64 hexadecimal characters representing 32 bytes in production."
                )
            try:
                bytes.fromhex(cleaned_enc)
            except ValueError:
                raise ValueError(
                    "ENCRYPTION_MASTER_KEY must be a valid hex-encoded string in production."
                )
            lowered_enc = cleaned_enc.lower()
            if (
                len(set(lowered_enc)) <= 1
                or "change" in lowered_enc
                or "placeholder" in lowered_enc
                or "secret" in lowered_enc
            ):
                raise ValueError(
                    "ENCRYPTION_MASTER_KEY cannot be a default or placeholder value in production."
                )
        else:
            if is_placeholder:
                import warnings

                warnings.warn(
                    "SECRET_KEY is set to an insecure placeholder value. "
                    "This is insecure and MUST be changed before any production deployment.",
                    UserWarning,
                    stacklevel=2,
                )

        return self

    # -------------------------------------------------------------------------
    # Computed Properties & Helpers
    # -------------------------------------------------------------------------
    def get_oauth_callback_url(self, provider: str) -> str:
        """Return the canonical OAuth callback URL for a given provider."""
        norm_provider = provider.lower().strip()
        base = self.oauth_redirect_base_url.rstrip("/")
        prefix = self.api_v1_prefix.rstrip("/")
        return f"{base}{prefix}/oauth/{norm_provider}/callback"

    @property
    def github_scopes_list(self) -> list[str]:
        """Parse configured GitHub scopes into a clean list of scope names."""
        raw = self.github_oauth_scopes.replace(",", " ")
        scopes = [s.strip() for s in raw.split() if s.strip()]
        return scopes if scopes else ["repo"]

    @property
    def is_production(self) -> bool:
        """True when running in the production environment."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """True when running in the development environment."""
        return self.environment == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the cached application settings singleton.

    Using @lru_cache ensures the .env file is read only once per process,
    which is the correct behaviour for production workloads.

    Usage:
        from app.config.settings import get_settings
        settings = get_settings()
    """
    return Settings()


# Convenience alias — import this instead of calling get_settings() directly.
settings: Settings = get_settings()
