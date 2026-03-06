"""Circuit Breaker for external API providers.

States:
    CLOSED: Normal operation. All calls pass through.
    OPEN: Calls are rejected immediately (CircuitBreakerOpenError).
    HALF_OPEN: One probe call allowed to test if service recovered.

Transitions:
    CLOSED -> OPEN: After FAILURE_THRESHOLD consecutive failures.
    OPEN -> HALF_OPEN: After OPEN_TIMEOUT seconds.
    HALF_OPEN -> CLOSED: Probe call succeeds.
    HALF_OPEN -> OPEN: Probe call fails (with EXTENDED_TIMEOUT).
"""

import logging
import threading
import time

from src.services.error_logger import log_error
from src.services.exceptions import CircuitBreakerOpenError

logger = logging.getLogger(__name__)

# --- Constants (not ENV-configurable in MVP) ---

FAILURE_THRESHOLD = 5  # consecutive failures before opening
OPEN_TIMEOUT = 60  # seconds before half-open probe
EXTENDED_TIMEOUT = 120  # seconds after failed probe


class CircuitBreaker:
    """Per-provider circuit breaker with thread-safe state management.

    Uses time.monotonic() (consistent with provider_rate_limiter.py)
    and threading.Lock for thread safety.
    """

    def __init__(self, provider: str) -> None:
        self.provider = provider
        self._state = "closed"
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._probe_in_flight = False
        self._lock = threading.Lock()

    def check(self) -> None:
        """Check if a call is allowed. Raise CircuitBreakerOpenError if open.

        If the open timeout has elapsed, transition to half_open and allow
        one probe call through.
        """
        with self._lock:
            if self._state == "closed":
                return

            if self._state == "open":
                elapsed = time.monotonic() - self._last_failure_time
                timeout = self._current_timeout()
                if elapsed >= timeout:
                    self._state = "half_open"
                    self._probe_in_flight = True
                    logger.info(
                        "Circuit breaker %s: open -> half_open (probe allowed)",
                        self.provider,
                    )
                    return
                raise CircuitBreakerOpenError(self.provider)

            # half_open: allow exactly one probe call
            if self._probe_in_flight:
                raise CircuitBreakerOpenError(self.provider)

    def record_success(self) -> None:
        """Record a successful call. Reset failure count, close circuit."""
        was_half_open = False
        with self._lock:
            if self._state == "half_open":
                was_half_open = True
                self._probe_in_flight = False
                logger.info(
                    "Circuit breaker %s: half_open -> closed (probe succeeded)",
                    self.provider,
                )
                log_error(
                    "circuit_breaker",
                    "circuit_recovered",
                    f"Circuit breaker closed for {self.provider} after successful probe",
                )
            self._failure_count = 0
            self._state = "closed"

        if was_half_open and self.provider == "alpaca":
            persist_alpaca_cb()

    def record_failure(self) -> None:
        """Record a failed call. Increment counter, open circuit if threshold reached."""
        transitioned_to_open = False
        with self._lock:
            self._failure_count += 1

            if self._state == "half_open":
                # Probe failed — reopen with extended timeout
                self._probe_in_flight = False
                self._state = "open"
                self._last_failure_time = time.monotonic()
                transitioned_to_open = True
                logger.warning(
                    "Circuit breaker %s: half_open -> open (probe failed, "
                    "extended timeout %ds)",
                    self.provider, EXTENDED_TIMEOUT,
                )
                log_error(
                    "circuit_breaker",
                    "probe_failed",
                    f"Probe call failed for {self.provider}, "
                    f"extended timeout {EXTENDED_TIMEOUT}s",
                )
                # Bridge: Alpaca CB open -> Kill-Switch
                if self.provider == "alpaca":
                    try:
                        from src.services.kill_switch import activate_kill_switch
                        activate_kill_switch("auto_broker_cb")
                    except Exception as exc:
                        logger.warning("Failed to activate kill-switch from CB: %s", exc)

            elif (
                self._state == "closed"
                and self._failure_count >= FAILURE_THRESHOLD
            ):
                self._state = "open"
                self._last_failure_time = time.monotonic()
                transitioned_to_open = True
                logger.warning(
                    "Circuit breaker %s: closed -> open "
                    "(%d consecutive failures)",
                    self.provider, self._failure_count,
                )
                log_error(
                    "circuit_breaker",
                    "circuit_open",
                    f"Circuit breaker opened for {self.provider} "
                    f"after {self._failure_count} consecutive failures",
                )
                # Bridge: Alpaca CB open -> Kill-Switch
                if self.provider == "alpaca":
                    try:
                        from src.services.kill_switch import activate_kill_switch
                        activate_kill_switch("auto_broker_cb")
                    except Exception as exc:
                        logger.warning("Failed to activate kill-switch from CB: %s", exc)

        if transitioned_to_open and self.provider == "alpaca":
            persist_alpaca_cb()

    def _current_timeout(self) -> float:
        """Return the current timeout based on failure count.

        After a failed probe (failure_count > FAILURE_THRESHOLD),
        use EXTENDED_TIMEOUT. Otherwise use OPEN_TIMEOUT.
        """
        if self._failure_count > FAILURE_THRESHOLD:
            return EXTENDED_TIMEOUT
        return OPEN_TIMEOUT

    def get_state(self) -> dict:
        """Return current state for monitoring/debugging."""
        with self._lock:
            return {
                "provider": self.provider,
                "state": self._state,
                "failure_count": self._failure_count,
                "last_failure_time": self._last_failure_time,
                "probe_in_flight": self._probe_in_flight,
            }

    def reset(self) -> None:
        """Reset to closed state. For test teardown."""
        with self._lock:
            self._state = "closed"
            self._failure_count = 0
            self._last_failure_time = 0.0
            self._probe_in_flight = False


# --- Module-level singletons (like rate limiter instances) ---

finnhub_breaker = CircuitBreaker("finnhub")
alpha_vantage_breaker = CircuitBreaker("alpha_vantage")
alpaca_breaker = CircuitBreaker("alpaca")

SYSTEM_STATE_ID = "00000000-0000-0000-0000-000000000001"


def persist_alpaca_cb() -> None:
    """Persist Alpaca circuit breaker state to system_state. Best-effort.

    Called on state transitions only (CLOSED->OPEN, HALF_OPEN->OPEN,
    HALF_OPEN->CLOSED), not on every failure count increment.
    """
    try:
        from src.services.supabase import get_supabase_admin

        state = alpaca_breaker.get_state()
        admin = get_supabase_admin()
        admin.table("system_state").update({
            "cb_state": state["state"],
            "cb_failure_count": state["failure_count"],
            "cb_last_failure_time": state["last_failure_time"],
        }).eq("id", SYSTEM_STATE_ID).execute()
    except Exception as exc:
        logger.warning("Failed to persist CB state: %s", exc)


def restore_alpaca_cb() -> None:
    """Restore Alpaca circuit breaker state from system_state on startup.

    Called from lifespan in main.py. If the persisted state is 'open',
    we restore it with the timeout starting fresh from restart (conservative).
    """
    try:
        from src.services.supabase import get_supabase_admin

        admin = get_supabase_admin()
        resp = (
            admin.table("system_state")
            .select("cb_state, cb_failure_count, cb_last_failure_time")
            .limit(1)
            .execute()
        )
        if not resp.data:
            return

        row = resp.data[0]
        persisted_state = row.get("cb_state")
        if not persisted_state or persisted_state == "closed":
            return

        if persisted_state not in ("open", "half_open"):
            logger.warning("Unexpected persisted CB state: %s, ignoring", persisted_state)
            return

        failure_count = row.get("cb_failure_count") or 0

        with alpaca_breaker._lock:
            alpaca_breaker._state = persisted_state
            alpaca_breaker._failure_count = failure_count
            # Timeout starts fresh from restart (conservative)
            alpaca_breaker._last_failure_time = time.monotonic()

        logger.info(
            "Restored Alpaca CB: state=%s, failures=%d",
            persisted_state, failure_count,
        )
    except Exception as exc:
        logger.warning("Failed to restore CB state: %s", exc)
