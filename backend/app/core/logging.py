"""
Enterprise RAG AI Assistant — Logging Configuration
=====================================================
Configures Loguru as the sole logging backend.

Features:
  - Intercepts standard-library `logging` calls (e.g. from uvicorn, httpx)
    and routes them through Loguru so every log goes to one place.
  - Text format for development: colourised, human-readable.
  - JSON format for production: structured, machine-parseable.
  - Optional file sink with automatic rotation and retention.
"""

import logging
import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    pass


# =============================================================================
# Standard-Library Logging Bridge
# =============================================================================

class _InterceptHandler(logging.Handler):
    """
    Route all standard-library `logging` records into Loguru.

    This ensures uvicorn, httpx, and any other library that uses the stdlib
    logging module will appear in the same Loguru sink.
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Map stdlib level to Loguru level name.
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Walk the call-stack to find the correct originating frame.
        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


# =============================================================================
# Log Format Strings
# =============================================================================

_TEXT_FORMAT: str = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)

_JSON_FORMAT: str = (
    '{{"time":"{time:YYYY-MM-DDThh:mm:ss.SSS}Z","level":"{level}",'
    '"name":"{name}","function":"{function}","line":{line},'
    '"message":"{message}"}}'
)


# =============================================================================
# Public API
# =============================================================================

def setup_logging(
    level: str = "INFO",
    fmt: str = "text",
    file_path: str = "",
) -> None:
    """
    Initialise and configure the Loguru logger.

    Call this function **once** at application startup (inside `main.py`
    or the lifespan context manager).

    Args:
        level:     Minimum log level (DEBUG | INFO | WARNING | ERROR | CRITICAL).
        fmt:       Output format — ``"text"`` (colourised) or ``"json"``.
        file_path: If non-empty, write logs to this file path with rotation.
    """
    # Remove Loguru's default handler.
    logger.remove()

    # -------------------------------------------------------------------------
    # Choose log format.
    # -------------------------------------------------------------------------
    log_format = _JSON_FORMAT if fmt == "json" else _TEXT_FORMAT

    # -------------------------------------------------------------------------
    # Console sink.
    # -------------------------------------------------------------------------
    logger.add(
        sys.stdout,
        level=level,
        format=log_format,
        colorize=(fmt == "text"),
        backtrace=True,
        diagnose=True,   # Show variable values in tracebacks (disable in prod)
    )

    # -------------------------------------------------------------------------
    # File sink (optional).
    # -------------------------------------------------------------------------
    if file_path:
        logger.add(
            file_path,
            level=level,
            format=_JSON_FORMAT,   # Files are always JSON for log aggregators
            rotation="10 MB",      # Rotate when file exceeds 10 MB
            retention="30 days",   # Keep logs for 30 days
            compression="gz",      # Compress rotated files
            backtrace=True,
            diagnose=False,        # Never write variable values to file in prod
            enqueue=True,          # Thread-safe async write
        )

    # -------------------------------------------------------------------------
    # Intercept standard-library logging.
    # -------------------------------------------------------------------------
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    # Set levels for noisy third-party loggers.
    for noisy_logger in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        logging.getLogger(noisy_logger).handlers = [_InterceptHandler()]
        logging.getLogger(noisy_logger).propagate = False

    logger.info(
        "Logging initialised",
        extra={"level": level, "format": fmt, "file": file_path or "disabled"},
    )
