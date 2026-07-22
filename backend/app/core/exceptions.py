"""
Enterprise RAG AI Assistant — Custom Exceptions & Global Handlers
=================================================================
Defines the application's exception hierarchy and registers
FastAPI exception handlers that return consistent JSON error responses.

Error response format:
    {
        "error": {
            "code":    "RESOURCE_NOT_FOUND",
            "message": "The requested document was not found.",
            "detail":  null
        }
    }
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger

# =============================================================================
# Base Exception
# =============================================================================


class AppException(Exception):
    """
    Base class for all application-level exceptions.

    All custom exceptions should inherit from this class so that the
    global exception handler can catch and format them uniformly.

    Args:
        message:     Human-readable explanation of the error.
        status_code: HTTP status code to return to the client.
        code:        Machine-readable error code string (SCREAMING_SNAKE_CASE).
        detail:      Optional extra context (e.g. field names, allowed values).
    """

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        code: str = "INTERNAL_SERVER_ERROR",
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.detail = detail


# =============================================================================
# Concrete Exception Classes
# =============================================================================


class NotFoundException(AppException):
    """Raised when a requested resource cannot be found (404)."""

    def __init__(
        self, message: str = "Resource not found.", detail: Any = None
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            detail=detail,
        )


class BadRequestException(AppException):
    """Raised when the client sends an invalid request (400)."""

    def __init__(self, message: str = "Bad request.", detail: Any = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            detail=detail,
        )


class UnauthorizedException(AppException):
    """Raised when the client is not authenticated (401)."""

    def __init__(
        self, message: str = "Authentication required.", detail: Any = None
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            detail=detail,
        )


class ForbiddenException(AppException):
    """Raised when the client lacks permission for the action (403)."""

    def __init__(self, message: str = "Access denied.", detail: Any = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            detail=detail,
        )


class ConflictException(AppException):
    """Raised when the request conflicts with existing server state (409)."""

    def __init__(self, message: str = "Resource conflict.", detail: Any = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            code="CONFLICT",
            detail=detail,
        )


class UnprocessableEntityException(AppException):
    """Raised when business-rule validation fails (422)."""

    def __init__(self, message: str = "Validation error.", detail: Any = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="UNPROCESSABLE_ENTITY",
            detail=detail,
        )


class ServiceUnavailableException(AppException):
    """Raised when a downstream service is temporarily unavailable (503)."""

    def __init__(
        self, message: str = "Service temporarily unavailable.", detail: Any = None
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="SERVICE_UNAVAILABLE",
            detail=detail,
        )


# =============================================================================
# Response Helper
# =============================================================================


def _error_response(
    status_code: int,
    code: str,
    message: str,
    detail: Any = None,
) -> JSONResponse:
    """Build a standardised JSON error response payload."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "detail": detail,
            }
        },
    )


# =============================================================================
# Exception Handlers
# =============================================================================


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle all AppException subclasses uniformly."""
    logger.warning(
        "Application exception",
        extra={
            "code": exc.code,
            "message": exc.message,
            "path": str(request.url),
            "method": request.method,
        },
    )
    return _error_response(exc.status_code, exc.code, exc.message, exc.detail)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected exceptions to prevent stack traces leaking to clients."""
    logger.exception(
        "Unhandled exception",
        extra={"path": str(request.url), "method": request.method},
    )
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "INTERNAL_SERVER_ERROR",
        "An unexpected error occurred. Please try again later.",
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Format input validation errors in a uniform JSON structure."""
    logger.warning(
        "Request validation failed",
        extra={
            "errors": exc.errors(),
            "path": str(request.url),
            "method": request.method,
        },
    )
    # Extract clean details
    details = []
    for err in exc.errors():
        loc = " -> ".join(str(item) for item in err.get("loc", []))
        msg = err.get("msg", "Unknown error")
        details.append({"location": loc, "message": msg})

    return _error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="VALIDATION_ERROR",
        message="Request validation failed.",
        detail=details,
    )


async def http_exception_handler(request: Request, exc: Any) -> JSONResponse:
    """Format HTTP exceptions in a uniform JSON structure."""
    logger.warning(
        "HTTP exception",
        extra={
            "status_code": exc.status_code,
            "message": exc.detail,
            "path": str(request.url),
            "method": request.method,
        },
    )
    return _error_response(
        status_code=exc.status_code,
        code="HTTP_EXCEPTION",
        message=str(exc.detail),
    )


# =============================================================================
# Registration Helper
# =============================================================================


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register all custom exception handlers on the FastAPI application instance.

    Call this from ``main.py`` after creating the ``app`` object.
    """
    from starlette.exceptions import HTTPException as StarletteHTTPException

    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)  # type: ignore[arg-type]
    logger.debug("Exception handlers registered.")
