"""Centralized error-to-HTTPException mapping for route handlers.

Eliminates repetitive try-except blocks across route files.
Each exception type maps to a fixed HTTP status code with a safe error message.
Supports both sync and async endpoints via auto-detection.

Usage:
    @router.post("/analyze/{ticker}")
    @limiter.limit("100/minute")
    @handle_service_errors(service_name="Analysis service")
    def analyze_ticker(ticker: str, request: Request) -> dict:
        ...
"""

import asyncio
import functools
import logging

from fastapi import HTTPException

from src.services.exceptions import (
    BrokerError,
    BudgetExhaustedError,
    CircuitBreakerOpenError,
    ConfigurationError,
    PreconditionError,
)

logger = logging.getLogger(__name__)


def handle_service_errors(
    service_name: str = "Service",
    precondition_status: int = 400,
):
    """Decorator that maps service exceptions to HTTPException responses.

    Args:
        service_name: Human-readable name for error messages.
        precondition_status: HTTP status for PreconditionError (400 default, 404 for trades).

    Decorator stacking order (outermost -> innermost):
        @router.post(...)       <- outermost (FastAPI)
        @limiter.limit(...)     <- rate limiter
        @handle_service_errors  <- innermost (closest to function)
    """

    def _handle_exception(exc: Exception):
        """Map exception to HTTPException. Always raises."""
        if isinstance(exc, HTTPException):
            raise exc
        if isinstance(exc, PreconditionError):
            raise HTTPException(
                status_code=precondition_status, detail=str(exc)
            )
        if isinstance(exc, BudgetExhaustedError):
            raise HTTPException(
                status_code=503,
                detail="Monthly API budget exhausted. Try again next month.",
            )
        # CircuitBreakerOpenError BEFORE BrokerError (siblings, not parent-child)
        if isinstance(exc, CircuitBreakerOpenError):
            logger.warning(
                "Circuit breaker open in %s: %s", service_name, exc
            )
            raise HTTPException(
                status_code=503,
                detail="Broker temporarily unavailable — circuit breaker active",
            )
        if isinstance(exc, BrokerError):
            logger.error("Broker error in %s: %s", service_name, exc)
            raise HTTPException(
                status_code=502,
                detail="Broker temporarily unavailable",
            )
        if isinstance(exc, ConfigurationError):
            logger.error(
                "Configuration error in %s: %s", service_name, exc
            )
            raise HTTPException(
                status_code=503,
                detail=f"{service_name} not configured",
            )
        # Catch-all for unexpected exceptions
        logger.error(
            "Unexpected error in %s: %s",
            service_name,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail=f"{service_name} temporarily unavailable",
        )

    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    _handle_exception(exc)

            return async_wrapper

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                _handle_exception(exc)

        return wrapper

    return decorator
