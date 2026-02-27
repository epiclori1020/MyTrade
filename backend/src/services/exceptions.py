"""Custom exceptions for data provider errors.

Shared by Finnhub and Alpha Vantage clients. The retry module
catches DataProviderError subtypes; parse errors propagate immediately.
"""


class DataProviderError(Exception):
    """Base exception for all data provider failures."""

    def __init__(self, provider: str, message: str, status_code: int | None = None):
        self.provider = provider
        self.message = message
        self.status_code = status_code
        super().__init__(f"[{provider}] {message}")


class RateLimitError(DataProviderError):
    """Provider returned 429 Too Many Requests."""

    def __init__(self, provider: str, message: str = "Rate limit exceeded"):
        super().__init__(provider, message, status_code=429)


class ProviderTimeoutError(DataProviderError):
    """Request to provider timed out."""

    def __init__(self, provider: str, message: str = "Request timed out"):
        super().__init__(provider, message, status_code=None)


class ProviderUnavailableError(DataProviderError):
    """Provider returned 500/502/503 or is otherwise unreachable."""

    def __init__(self, provider: str, message: str, status_code: int = 503):
        super().__init__(provider, message, status_code=status_code)
