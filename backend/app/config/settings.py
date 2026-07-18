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
from typing import Literal

from pydantic import Field, field_validator
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
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,        # Allow both APP_NAME and app_name
        extra="ignore",              # Ignore unknown env vars silently
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
    host: str = Field(default="0.0.0.0", description="Bind address for Uvicorn.")
    port: int = Field(default=8000, ge=1, le=65535, description="Bind port.")
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
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="List of allowed CORS origins.",
    )
    allowed_methods: list[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        description="Allowed HTTP methods for CORS.",
    )
    allowed_headers: list[str] = Field(
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
        default="text",
        description="Log output format. Use 'json' in production.",
    )
    log_file_path: str = Field(
        default="logs/app.log",
        description="File path for persistent log output. Empty string disables.",
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
    # Validators
    # -------------------------------------------------------------------------
    @field_validator("allowed_origins", "allowed_methods", "allowed_headers", mode="before")
    @classmethod
    def parse_comma_separated(cls, value: str | list) -> list[str]:
        """Allow comma-separated strings from env vars, e.g. ALLOWED_ORIGINS=a,b,c."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        """Warn loudly if the default secret key is used outside development."""
        if value == "change-me-in-production":
            import warnings
            warnings.warn(
                "SECRET_KEY is set to the default placeholder value. "
                "This is insecure and MUST be changed before any production deployment.",
                stacklevel=2,
            )
        return value

    # -------------------------------------------------------------------------
    # Computed Properties
    # -------------------------------------------------------------------------
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
