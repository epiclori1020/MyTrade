"""Centralized error-to-HTTPException mapping for route handlers.

Eliminates repetitive try-except blocks across route files.
Each exception type maps to a fixed HTTP status code with a safe error message.

Usage:
    @router.post("/analyze/{ticker}")
    @limiter.limit("100/minute")
    @handle_service_errors(service_name="Analysis service")
    def analyze_ticker(ticker: str, request: Request) -> dict:
        ...
"""

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

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except HTTPException:
                raise
            except PreconditionError as exc:
                raise HTTPException(
                    status_code=precondition_status, detail=str(exc)
                )
            except BudgetExhaustedError:
                raise HTTPException(
                    status_code=503,
                    detail="Monthly API budget exhausted. Try again next month.",
                )
            except CircuitBreakerOpenError as exc:
                logger.warning(
                    "Circuit breaker open in %s: %s", service_name, exc
                )
                raise HTTPException(
                    status_code=503,
                    detail="Broker temporarily unavailable — circuit breaker active",
                )
            except BrokerError as exc:
                logger.error("Broker error in %s: %s", service_name, exc)
                raise HTTPException(
                    status_code=502,
                    detail="Broker temporarily unavailable",
                )
            except ConfigurationError as exc:
                logger.error(
                    "Configuration error in %s: %s", service_name, exc
                )
                raise HTTPException(
                    status_code=503,
                    detail=f"{service_name} not configured",
                )
            except Exception as exc:
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

        return wrapper

    return decorator
