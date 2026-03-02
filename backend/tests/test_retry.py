"""Tests for retry_with_backoff."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.exceptions import (
    CircuitBreakerOpenError,
    DataProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
)
from src.services.retry import retry_with_backoff


class TestRetryWithBackoff:
    @patch("src.services.retry.time.sleep")
    def test_success_no_retry(self, mock_sleep):
        """Should return immediately on first success."""
        fn = MagicMock(return_value="ok")
        result = retry_with_backoff(fn, provider="test")
        assert result == "ok"
        fn.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("src.services.retry.time.sleep")
    def test_one_failure_then_success(self, mock_sleep):
        """Should retry once and return on second success."""
        fn = MagicMock(side_effect=[
            ProviderTimeoutError("test"),
            "ok",
        ])
        on_error = MagicMock()
        result = retry_with_backoff(fn, provider="test", on_error=on_error)
        assert result == "ok"
        assert fn.call_count == 2
        on_error.assert_called_once()
        mock_sleep.assert_called_once_with(2.0)  # base_delay * 2^0

    @patch("src.services.retry.time.sleep")
    def test_all_retries_exhausted(self, mock_sleep):
        """Should raise after max_retries failures."""
        error = ProviderUnavailableError("test", "down", 503)
        fn = MagicMock(side_effect=error)
        on_error = MagicMock()
        with pytest.raises(ProviderUnavailableError):
            retry_with_backoff(fn, max_retries=3, provider="test", on_error=on_error)
        assert fn.call_count == 3
        assert on_error.call_count == 3

    @patch("src.services.retry.time.sleep")
    def test_exponential_delays(self, mock_sleep):
        """Should use exponential backoff: 2s, 4s, 8s."""
        fn = MagicMock(side_effect=[
            RateLimitError("test"),
            RateLimitError("test"),
            RateLimitError("test"),
        ])
        with pytest.raises(RateLimitError):
            retry_with_backoff(fn, max_retries=3, base_delay=2.0, provider="test")
        # Only 2 sleeps (between attempts 1→2 and 2→3, not after final failure)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(2.0)   # 2.0 * 2^0
        mock_sleep.assert_any_call(4.0)   # 2.0 * 2^1

    @patch("src.services.retry.time.sleep")
    def test_non_provider_error_propagates_immediately(self, mock_sleep):
        """Non-DataProviderError should propagate without retry."""
        fn = MagicMock(side_effect=ValueError("parse error"))
        with pytest.raises(ValueError, match="parse error"):
            retry_with_backoff(fn, provider="test")
        fn.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("src.services.retry.time.sleep")
    def test_circuit_breaker_early_exit(self, mock_sleep):
        """CircuitBreakerOpenError: on_error called once, no sleep, error re-raised immediately."""
        error = CircuitBreakerOpenError("test-provider")
        fn = MagicMock(side_effect=error)
        on_error = MagicMock()

        with pytest.raises(CircuitBreakerOpenError):
            retry_with_backoff(fn, max_retries=3, provider="test-provider", on_error=on_error)

        # Function called exactly once — no retries against a known-down provider
        fn.assert_called_once()
        # on_error called once for logging purposes
        on_error.assert_called_once_with(error, 1)
        # No sleep — circuit breaker exits immediately without waiting
        mock_sleep.assert_not_called()
