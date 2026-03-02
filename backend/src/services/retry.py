"""Retry with exponential backoff for data provider calls.

Only catches DataProviderError subtypes — parse errors and other
exceptions propagate immediately. The on_error callback is called
on EVERY failed attempt (enables DB error logging per attempt).
"""

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from src.services.exceptions import CircuitBreakerOpenError, DataProviderError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    max_retries: int = 3,
    base_delay: float = 2.0,
    provider: str = "unknown",
    on_error: Callable[[Exception, int], None] | None = None,
) -> T:
    """Call fn() with exponential backoff on DataProviderError.

    Args:
        fn: Zero-argument callable to retry.
        max_retries: Maximum number of attempts (including first).
        base_delay: Base delay in seconds (doubles each retry: 2s, 4s, 8s).
        provider: Provider name for logging.
        on_error: Called on every failed attempt with (exception, attempt_number).

    Returns:
        The return value of fn() on success.

    Raises:
        DataProviderError: If all retries are exhausted.
        Any non-DataProviderError: Immediately, without retry.
    """
    last_error: DataProviderError | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except DataProviderError as exc:
            last_error = exc
            if on_error:
                on_error(exc, attempt)
            # Early-exit for circuit breaker — no point retrying a known-down provider
            if isinstance(exc, CircuitBreakerOpenError):
                break
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "%s: attempt %d/%d failed (%s), retrying in %.1fs",
                    provider, attempt, max_retries, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "%s: all %d attempts failed, last error: %s",
                    provider, max_retries, exc,
                )

    raise last_error  # type: ignore[misc]
