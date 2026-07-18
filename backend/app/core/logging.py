"""
Enterprise RAG AI Assistant — Logging Configuration
=====================================================
Configures Loguru as the sole logging backend.

Features:
  - Intercepts standard-library `logging` calls (e.g. from uvicorn, httpx)
    and routes them through Loguru so every log goes to one place.
  - Text format for development: colourised, human-readable.
  - JSON format for production: structured, machine-parseable.
  - Splits file output into rotating logs (app.log, api.log, worker.log, error.log, audit.log).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from loguru import logger

# =============================================================================
# Standard-Library Logging Bridge
# =============================================================================


class _InterceptHandler(logging.Handler):
    """
    Route all standard-library `logging` records into Loguru.
    Automatically tags Celery logs with log_type="worker".
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

        # Check if this log comes from Celery, tag as worker logs
        kwargs: dict[str, Any] = {}
        if record.name.startswith("celery") or "celery" in record.filename:
            kwargs["log_type"] = "worker"
        elif record.name.startswith("uvicorn.access"):
            kwargs["log_type"] = "api"

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, "{}", record.getMessage(), **kwargs
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
    '"message":"{message}","extra":{extra}}}'
)


# =============================================================================
# Log Filtering Functions
# =============================================================================


def api_log_filter(record: Any) -> bool:
    return bool(record["extra"].get("log_type") == "api")


def worker_log_filter(record: Any) -> bool:
    return bool(record["extra"].get("log_type") == "worker")


def audit_log_filter(record: Any) -> bool:
    return bool(record["extra"].get("log_type") == "audit")


def error_log_filter(record: Any) -> bool:
    # Log level Warning (30) or higher
    return bool(record["level"].no >= 30)


def app_log_filter(record: Any) -> bool:
    # App logs catch everything else
    log_type = record["extra"].get("log_type")
    return bool(log_type not in ("api", "worker", "audit"))


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
        file_path: Base file path for logs. In production, splits into separate logs.
    """
    # Remove Loguru's default handler.
    logger.remove()

    # Console sink.
    log_format = _JSON_FORMAT if fmt == "json" else _TEXT_FORMAT
    logger.add(
        sys.stdout,
        level=level,
        format=log_format,
        colorize=(fmt == "text"),
        backtrace=True,
        diagnose=(
            fmt == "text"
        ),  # Disable variable values dump in production json logs
    )

    # File sinks (optional).
    if file_path:
        log_dir = os.path.dirname(file_path) or "logs"
        os.makedirs(log_dir, exist_ok=True)

        common_kwargs = {
            "level": level,
            "format": _JSON_FORMAT,
            "rotation": "10 MB",
            "retention": "30 days",
            "compression": "gz",
            "backtrace": True,
            "diagnose": False,  # Never dump variable trace details in logs
            "enqueue": True,  # Thread-safe writing
        }

        # 1. Application log
        logger.add(  # type: ignore[call-overload]
            os.path.join(log_dir, "app.log"), filter=app_log_filter, **common_kwargs
        )

        # 2. API logs
        logger.add(  # type: ignore[call-overload]
            os.path.join(log_dir, "api.log"), filter=api_log_filter, **common_kwargs
        )

        # 3. Celery Worker logs
        logger.add(  # type: ignore[call-overload]
            os.path.join(log_dir, "worker.log"),
            filter=worker_log_filter,
            **common_kwargs,
        )

        # 4. Error logs
        logger.add(  # type: ignore[call-overload]
            os.path.join(log_dir, "error.log"), filter=error_log_filter, **common_kwargs
        )

        # 5. Audit logs
        logger.add(  # type: ignore[call-overload]
            os.path.join(log_dir, "audit.log"), filter=audit_log_filter, **common_kwargs
        )

    # Intercept standard-library logging.
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    # Set levels for noisy third-party loggers.
    for noisy_logger in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        logging.getLogger(noisy_logger).handlers = [_InterceptHandler()]
        logging.getLogger(noisy_logger).propagate = False

    logger.info(
        "Logging initialised",
        extra={"level": level, "format": fmt, "file": file_path or "disabled"},
    )
