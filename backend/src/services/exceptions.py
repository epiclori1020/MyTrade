"""Custom exceptions for MyTrade backend.

Data provider errors (shared by Finnhub/Alpha Vantage), agent errors
(LLM call failures), and pre-condition errors (missing data/config).
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


# --- Pre-condition errors (no tokens consumed, no analysis_run created) ---


class PreconditionError(Exception):
    """Pre-condition not met (e.g. no data in DB).

    Raised BEFORE analysis_run creation — no tokens consumed.
    """


class ConfigurationError(Exception):
    """Server misconfiguration (e.g. missing API key).

    Raised BEFORE analysis_run creation — no tokens consumed.
    """


# --- Agent errors (tokens may have been consumed) ---


class AgentError(Exception):
    """Error during LLM agent execution. Tokens may have been consumed."""

    def __init__(
        self,
        agent_name: str,
        message: str,
        error_type: str = "agent_error",
        usage: dict | None = None,
    ):
        self.agent_name = agent_name
        self.error_type = error_type
        self.usage = usage  # {"input_tokens": N, "output_tokens": N}
        super().__init__(f"[{agent_name}] {message}")


# --- Broker errors (connection failures, order rejections) ---


class BrokerError(DataProviderError):
    """Broker API failure (Alpaca, IBKR).

    Inherits DataProviderError so retry_with_backoff() catches it
    for read-only calls (get_positions, get_account).
    """

    def __init__(self, broker: str, message: str, status_code: int | None = None):
        super().__init__(provider=broker, message=message, status_code=status_code)


class BudgetExhaustedError(Exception):
    """Monthly API budget exhausted. Not a DataProviderError — no retry."""

    pass


class CircuitBreakerOpenError(DataProviderError):
    """Circuit breaker is open — provider temporarily blocked.

    Inherits DataProviderError so retry_with_backoff() catches it.
    retry_with_backoff() has an early-exit for this error type:
    on_error is called once for logging, then immediately re-raised
    (no further retries against a known-down provider).
    """

    def __init__(self, provider: str):
        super().__init__(
            provider=provider,
            message=f"Circuit breaker open for {provider}",
            status_code=None,
        )
