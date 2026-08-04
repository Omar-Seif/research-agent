# src/api/exception_handlers.py

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from src.utils.exceptions import (
    ResearchAgentError,
    InputValidationError,
    ConfigurationError,
    ExternalAPITimeoutError,
    ExternalAPIRateLimitError,
    ContextWindowExceededError,
    MalformedResponseError,
    UnexpectedError,
)
from src.config.logger import get_logger

logger = get_logger(__name__)


def _map_exception_to_status(e: Exception) -> int:
    """Map domain exceptions to HTTP status codes."""
    if isinstance(e, InputValidationError):
        return status.HTTP_400_BAD_REQUEST
    elif isinstance(e, ConfigurationError):
        return status.HTTP_500_INTERNAL_SERVER_ERROR
    elif isinstance(e, ExternalAPITimeoutError):
        return status.HTTP_504_GATEWAY_TIMEOUT
    elif isinstance(e, ExternalAPIRateLimitError):
        return status.HTTP_429_TOO_MANY_REQUESTS
    elif isinstance(e, ContextWindowExceededError):
        return status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    elif isinstance(e, MalformedResponseError):
        return status.HTTP_502_BAD_GATEWAY
    elif isinstance(e, UnexpectedError):
        return status.HTTP_500_INTERNAL_SERVER_ERROR
    elif isinstance(e, ResearchAgentError):
        # Safety net for unmapped domain exceptions
        return status.HTTP_500_INTERNAL_SERVER_ERROR
    else:
        # Unknown/unexpected
        return status.HTTP_500_INTERNAL_SERVER_ERROR


def _format_error_response(e: Exception, status_code: int) -> JSONResponse:
    """Format a consistent error response."""
    error_detail = str(e)

    # Truncate long error messages for safety
    if len(error_detail) > 500:
        error_detail = error_detail[:500] + "..."

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "type": e.__class__.__name__,
                "message": error_detail,
                "status_code": status_code,
            }
        },
    )


def add_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers for the FastAPI application."""

    @app.exception_handler(ResearchAgentError)
    async def handle_research_agent_error(request: Request, exc: ResearchAgentError):
        """Handle all ResearchAgentError subclasses."""
        status_code = _map_exception_to_status(exc)
        logger.warning(
            f"ResearchAgentError: {exc}",
            extra={"status_code": status_code, "path": request.url.path},
        )
        return _format_error_response(exc, status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        """Handle any unexpected exceptions."""
        logger.error(
            f"Unexpected error: {exc}",
            exc_info=True,
            extra={"path": request.url.path},
        )
        return _format_error_response(
            exc,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
