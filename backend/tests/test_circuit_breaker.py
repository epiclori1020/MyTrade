"""Tests for CircuitBreaker (src/services/circuit_breaker.py).

All state-machine tests use fresh CircuitBreaker("test") instances to avoid
any inter-test state leakage. Module-level singletons (finnhub_breaker,
alpha_vantage_breaker, alpaca_breaker) are only tested for existence and
independence — never mutated.

Mock patterns:
- @patch("src.services.circuit_breaker.time.monotonic") for timeout tests
- @patch("src.services.circuit_breaker.log_error") for logging verification
"""

import threading
from unittest.mock import MagicMock, call, patch

import pytest

from src.services.circuit_breaker import (
    EXTENDED_TIMEOUT,
    FAILURE_THRESHOLD,
    OPEN_TIMEOUT,
    CircuitBreaker,
    alpha_vantage_breaker,
    alpaca_breaker,
    finnhub_breaker,
)
from src.services.exceptions import CircuitBreakerOpenError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open_breaker(breaker: CircuitBreaker) -> None:
    """Drive a breaker from closed -> open by recording FAILURE_THRESHOLD failures."""
    for _ in range(FAILURE_THRESHOLD):
        breaker.record_failure()


# ---------------------------------------------------------------------------
# 1. Initial State
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_starts_closed(self):
        """A newly created breaker must be in the closed state."""
        breaker = CircuitBreaker("test")
        state = breaker.get_state()
        assert state["state"] == "closed"

    def test_initial_failure_count_is_zero(self):
        """Failure counter must be zero at creation."""
        breaker = CircuitBreaker("test")
        assert breaker.get_state()["failure_count"] == 0

    def test_initial_last_failure_time_is_zero(self):
        """last_failure_time must be 0.0 at creation."""
        breaker = CircuitBreaker("test")
        assert breaker.get_state()["last_failure_time"] == 0.0

    def test_provider_name_stored(self):
        """Provider name must be stored and returned in get_state()."""
        breaker = CircuitBreaker("finnhub")
        assert breaker.get_state()["provider"] == "finnhub"


# ---------------------------------------------------------------------------
# 2. Closed State: check() passes, record_success() works
# ---------------------------------------------------------------------------


class TestClosedState:
    def test_check_does_not_raise_when_closed(self):
        """check() must not raise when the breaker is closed."""
        breaker = CircuitBreaker("test")
        breaker.check()  # Should not raise

    def test_record_success_in_closed_state(self):
        """record_success() in closed state keeps the breaker closed."""
        breaker = CircuitBreaker("test")
        breaker.record_success()
        assert breaker.get_state()["state"] == "closed"

    def test_record_success_keeps_failure_count_zero(self):
        """record_success() in closed state keeps failure_count at zero."""
        breaker = CircuitBreaker("test")
        breaker.record_success()
        assert breaker.get_state()["failure_count"] == 0


# ---------------------------------------------------------------------------
# 3. Failure Counting: failures below threshold do not open
# ---------------------------------------------------------------------------


class TestFailureCounting:
    def test_single_failure_stays_closed(self):
        """One failure below threshold must not open the breaker."""
        breaker = CircuitBreaker("test")
        breaker.record_failure()
        assert breaker.get_state()["state"] == "closed"

    def test_failures_below_threshold_stay_closed(self):
        """Failures below FAILURE_THRESHOLD must keep the breaker closed."""
        breaker = CircuitBreaker("test")
        for _ in range(FAILURE_THRESHOLD - 1):
            breaker.record_failure()
        assert breaker.get_state()["state"] == "closed"

    def test_failure_count_increments_correctly(self):
        """failure_count must increment for each recorded failure."""
        breaker = CircuitBreaker("test")
        for i in range(3):
            breaker.record_failure()
        assert breaker.get_state()["failure_count"] == 3


# ---------------------------------------------------------------------------
# 4. Closed -> Open Transition
# ---------------------------------------------------------------------------


class TestClosedToOpenTransition:
    @patch("src.services.circuit_breaker.log_error")
    def test_threshold_failures_opens_breaker(self, mock_log_error):
        """Exactly FAILURE_THRESHOLD consecutive failures must open the breaker."""
        breaker = CircuitBreaker("test")
        _open_breaker(breaker)
        assert breaker.get_state()["state"] == "open"

    @patch("src.services.circuit_breaker.log_error")
    def test_log_error_called_on_open(self, mock_log_error):
        """log_error must be called with 'circuit_open' when breaker opens."""
        from unittest.mock import ANY

        breaker = CircuitBreaker("test")
        _open_breaker(breaker)
        mock_log_error.assert_called_once_with(
            "circuit_breaker",
            "circuit_open",
            ANY,  # message — checked below
        )
        message = mock_log_error.call_args[0][2]
        assert "test" in message

    @patch("src.services.circuit_breaker.log_error")
    @patch("src.services.circuit_breaker.time.monotonic", return_value=1000.0)
    def test_last_failure_time_set_on_open(self, mock_monotonic, mock_log_error):
        """last_failure_time must be recorded when the breaker opens."""
        breaker = CircuitBreaker("test")
        _open_breaker(breaker)
        assert breaker.get_state()["last_failure_time"] == 1000.0


# ---------------------------------------------------------------------------
# 5. Open State: check() raises CircuitBreakerOpenError
# ---------------------------------------------------------------------------


class TestOpenState:
    @patch("src.services.circuit_breaker.log_error")
    @patch("src.services.circuit_breaker.time.monotonic", return_value=1000.0)
    def test_check_raises_when_open_and_timeout_not_elapsed(
        self, mock_monotonic, mock_log_error
    ):
        """check() must raise CircuitBreakerOpenError while the breaker is open
        and the open timeout has not yet elapsed."""
        breaker = CircuitBreaker("test")
        _open_breaker(breaker)  # records last_failure_time = 1000.0
        # Advance time by less than OPEN_TIMEOUT
        mock_monotonic.return_value = 1000.0 + OPEN_TIMEOUT - 1
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            breaker.check()
        assert exc_info.value.provider == "test"

    @patch("src.services.circuit_breaker.log_error")
    @patch("src.services.circuit_breaker.time.monotonic", return_value=1000.0)
    def test_check_raises_correct_exception_type(self, mock_monotonic, mock_log_error):
        """CircuitBreakerOpenError must be a DataProviderError subclass."""
        from src.services.exceptions import DataProviderError

        breaker = CircuitBreaker("test")
        _open_breaker(breaker)
        mock_monotonic.return_value = 1001.0  # still within OPEN_TIMEOUT
        with pytest.raises(DataProviderError):
            breaker.check()


# ---------------------------------------------------------------------------
# 6. Open -> Half-Open Transition: after OPEN_TIMEOUT
# ---------------------------------------------------------------------------


class TestOpenToHalfOpenTransition:
    @patch("src.services.circuit_breaker.log_error")
    def test_transitions_to_half_open_after_open_timeout(self, mock_log_error):
        """After OPEN_TIMEOUT seconds, check() must silently transition to
        half_open and allow the call through (no exception raised)."""
        breaker = CircuitBreaker("test")

        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=1000.0
        ):
            _open_breaker(breaker)  # last_failure_time = 1000.0

        # Advance time past OPEN_TIMEOUT
        with patch(
            "src.services.circuit_breaker.time.monotonic",
            return_value=1000.0 + OPEN_TIMEOUT,
        ):
            breaker.check()  # Must NOT raise

        assert breaker.get_state()["state"] == "half_open"

    @patch("src.services.circuit_breaker.log_error")
    def test_check_exactly_at_timeout_boundary_allows_probe(self, mock_log_error):
        """At exactly elapsed == OPEN_TIMEOUT the probe must be allowed (>= check)."""
        breaker = CircuitBreaker("test")

        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=500.0
        ):
            _open_breaker(breaker)

        with patch(
            "src.services.circuit_breaker.time.monotonic",
            return_value=500.0 + OPEN_TIMEOUT,
        ):
            breaker.check()  # Should not raise (elapsed >= timeout)

        assert breaker.get_state()["state"] == "half_open"


# ---------------------------------------------------------------------------
# 7. Half-Open -> Closed: probe succeeds
# ---------------------------------------------------------------------------


class TestHalfOpenToClosedTransition:
    @patch("src.services.circuit_breaker.log_error")
    def test_record_success_in_half_open_closes_breaker(self, mock_log_error):
        """record_success() in half_open must close the circuit."""
        breaker = CircuitBreaker("test")

        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=1000.0
        ):
            _open_breaker(breaker)

        with patch(
            "src.services.circuit_breaker.time.monotonic",
            return_value=1000.0 + OPEN_TIMEOUT,
        ):
            breaker.check()  # transitions to half_open

        breaker.record_success()
        assert breaker.get_state()["state"] == "closed"

    @patch("src.services.circuit_breaker.log_error")
    def test_record_success_in_half_open_resets_failure_count(self, mock_log_error):
        """record_success() after a probe must reset failure_count to zero."""
        breaker = CircuitBreaker("test")

        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=1000.0
        ):
            _open_breaker(breaker)

        with patch(
            "src.services.circuit_breaker.time.monotonic",
            return_value=1000.0 + OPEN_TIMEOUT,
        ):
            breaker.check()

        breaker.record_success()
        assert breaker.get_state()["failure_count"] == 0

    @patch("src.services.circuit_breaker.log_error")
    def test_log_error_called_with_circuit_recovered_on_half_open_success(
        self, mock_log_error
    ):
        """log_error must be called with 'circuit_recovered' when probe succeeds."""
        breaker = CircuitBreaker("test")

        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=1000.0
        ):
            _open_breaker(breaker)

        with patch(
            "src.services.circuit_breaker.time.monotonic",
            return_value=1000.0 + OPEN_TIMEOUT,
        ):
            breaker.check()

        mock_log_error.reset_mock()
        breaker.record_success()

        mock_log_error.assert_called_once()
        _, error_type, message = mock_log_error.call_args[0]
        assert error_type == "circuit_recovered"
        assert "test" in message


# ---------------------------------------------------------------------------
# 8. Half-Open -> Open (probe failed): record_failure() in half_open reopens
# ---------------------------------------------------------------------------


class TestHalfOpenToOpenOnProbeFailed:
    @patch("src.services.circuit_breaker.log_error")
    def test_record_failure_in_half_open_reopens_breaker(self, mock_log_error):
        """record_failure() in half_open must reopen the circuit."""
        breaker = CircuitBreaker("test")

        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=1000.0
        ):
            _open_breaker(breaker)

        with patch(
            "src.services.circuit_breaker.time.monotonic",
            return_value=1000.0 + OPEN_TIMEOUT,
        ):
            breaker.check()  # half_open

        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=2000.0
        ):
            breaker.record_failure()

        assert breaker.get_state()["state"] == "open"

    @patch("src.services.circuit_breaker.log_error")
    def test_log_error_called_with_probe_failed_on_half_open_failure(
        self, mock_log_error
    ):
        """log_error must be called with 'probe_failed' when the probe fails."""
        breaker = CircuitBreaker("test")

        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=1000.0
        ):
            _open_breaker(breaker)

        with patch(
            "src.services.circuit_breaker.time.monotonic",
            return_value=1000.0 + OPEN_TIMEOUT,
        ):
            breaker.check()

        mock_log_error.reset_mock()

        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=2000.0
        ):
            breaker.record_failure()

        mock_log_error.assert_called_once()
        _, error_type, message = mock_log_error.call_args[0]
        assert error_type == "probe_failed"
        assert "test" in message


# ---------------------------------------------------------------------------
# 9. Extended Timeout: failed probe uses EXTENDED_TIMEOUT (120s)
# ---------------------------------------------------------------------------


class TestExtendedTimeout:
    @patch("src.services.circuit_breaker.log_error")
    def test_check_still_raises_within_extended_timeout(self, mock_log_error):
        """After a failed probe, check() must still raise within EXTENDED_TIMEOUT."""
        breaker = CircuitBreaker("test")

        # Open the breaker at t=1000
        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=1000.0
        ):
            _open_breaker(breaker)

        # Trigger half-open at t=1060 (OPEN_TIMEOUT elapsed)
        with patch(
            "src.services.circuit_breaker.time.monotonic",
            return_value=1000.0 + OPEN_TIMEOUT,
        ):
            breaker.check()

        # Probe fails at t=2000 — last_failure_time = 2000.0
        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=2000.0
        ):
            breaker.record_failure()

        # At t=2060 (only OPEN_TIMEOUT elapsed since probe fail), still open
        with patch(
            "src.services.circuit_breaker.time.monotonic",
            return_value=2000.0 + OPEN_TIMEOUT,
        ):
            with pytest.raises(CircuitBreakerOpenError):
                breaker.check()

    @patch("src.services.circuit_breaker.log_error")
    def test_check_allows_probe_after_extended_timeout(self, mock_log_error):
        """After EXTENDED_TIMEOUT, check() must allow a new probe (half_open)."""
        breaker = CircuitBreaker("test")

        # Open at t=1000
        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=1000.0
        ):
            _open_breaker(breaker)

        # Trigger half-open at t=1060
        with patch(
            "src.services.circuit_breaker.time.monotonic",
            return_value=1000.0 + OPEN_TIMEOUT,
        ):
            breaker.check()

        # Probe fails at t=2000
        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=2000.0
        ):
            breaker.record_failure()

        # At t=2120 (EXTENDED_TIMEOUT elapsed), allow new probe
        with patch(
            "src.services.circuit_breaker.time.monotonic",
            return_value=2000.0 + EXTENDED_TIMEOUT,
        ):
            breaker.check()  # Must not raise

        assert breaker.get_state()["state"] == "half_open"

    def test_extended_timeout_constant_is_longer_than_open_timeout(self):
        """EXTENDED_TIMEOUT must be strictly greater than OPEN_TIMEOUT."""
        assert EXTENDED_TIMEOUT > OPEN_TIMEOUT


# ---------------------------------------------------------------------------
# 10. Success Resets Counter
# ---------------------------------------------------------------------------


class TestSuccessResetsCounter:
    def test_record_success_in_closed_state_resets_failure_count(self):
        """record_success() must reset failure_count even in closed state."""
        breaker = CircuitBreaker("test")
        # Accumulate some failures (below threshold)
        for _ in range(FAILURE_THRESHOLD - 1):
            breaker.record_failure()
        assert breaker.get_state()["failure_count"] == FAILURE_THRESHOLD - 1

        breaker.record_success()
        assert breaker.get_state()["failure_count"] == 0

    def test_success_after_partial_failures_prevents_future_open(self):
        """After record_success() resets the counter, FAILURE_THRESHOLD new
        failures are required to open the breaker again."""
        breaker = CircuitBreaker("test")
        for _ in range(FAILURE_THRESHOLD - 1):
            breaker.record_failure()
        breaker.record_success()

        # Only one more failure — must still be closed
        breaker.record_failure()
        assert breaker.get_state()["state"] == "closed"


# ---------------------------------------------------------------------------
# 11. get_state() returns correct dict with all fields
# ---------------------------------------------------------------------------


class TestGetState:
    def test_get_state_returns_all_required_keys(self):
        """get_state() must return a dict with provider, state, failure_count,
        and last_failure_time."""
        breaker = CircuitBreaker("my_provider")
        state = breaker.get_state()
        assert "provider" in state
        assert "state" in state
        assert "failure_count" in state
        assert "last_failure_time" in state

    def test_get_state_initial_values(self):
        """get_state() must reflect the initial closed state correctly."""
        breaker = CircuitBreaker("my_provider")
        state = breaker.get_state()
        assert state == {
            "provider": "my_provider",
            "state": "closed",
            "failure_count": 0,
            "last_failure_time": 0.0,
            "probe_in_flight": False,
        }

    @patch("src.services.circuit_breaker.log_error")
    @patch("src.services.circuit_breaker.time.monotonic", return_value=555.0)
    def test_get_state_reflects_open_state(self, mock_monotonic, mock_log_error):
        """get_state() must show 'open' with correct last_failure_time after opening."""
        breaker = CircuitBreaker("my_provider")
        _open_breaker(breaker)
        state = breaker.get_state()
        assert state["state"] == "open"
        assert state["failure_count"] == FAILURE_THRESHOLD
        assert state["last_failure_time"] == 555.0


# ---------------------------------------------------------------------------
# 12. reset() resets to initial closed state
# ---------------------------------------------------------------------------


class TestReset:
    @patch("src.services.circuit_breaker.log_error")
    def test_reset_from_open_returns_to_closed(self, mock_log_error):
        """reset() on an open breaker must return it to closed state."""
        breaker = CircuitBreaker("test")
        _open_breaker(breaker)
        assert breaker.get_state()["state"] == "open"

        breaker.reset()
        assert breaker.get_state()["state"] == "closed"

    @patch("src.services.circuit_breaker.log_error")
    def test_reset_clears_failure_count(self, mock_log_error):
        """reset() must set failure_count back to zero."""
        breaker = CircuitBreaker("test")
        _open_breaker(breaker)
        breaker.reset()
        assert breaker.get_state()["failure_count"] == 0

    @patch("src.services.circuit_breaker.log_error")
    def test_reset_clears_last_failure_time(self, mock_log_error):
        """reset() must clear last_failure_time back to 0.0."""
        breaker = CircuitBreaker("test")
        _open_breaker(breaker)
        breaker.reset()
        assert breaker.get_state()["last_failure_time"] == 0.0

    @patch("src.services.circuit_breaker.log_error")
    def test_reset_allows_check_without_raising(self, mock_log_error):
        """After reset(), check() must succeed without raising."""
        breaker = CircuitBreaker("test")
        _open_breaker(breaker)
        breaker.reset()
        breaker.check()  # Must not raise


# ---------------------------------------------------------------------------
# 13. Thread Safety: concurrent check() calls do not crash
# ---------------------------------------------------------------------------


class TestThreadSafety:
    @patch("src.services.circuit_breaker.log_error")
    def test_concurrent_checks_do_not_raise_unexpected_exceptions(
        self, mock_log_error
    ):
        """Multiple threads calling check() concurrently must not raise
        any exception other than CircuitBreakerOpenError."""
        breaker = CircuitBreaker("test")
        errors = []

        def call_check():
            try:
                breaker.check()
            except CircuitBreakerOpenError:
                pass  # Expected when open
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=call_check) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Unexpected exceptions during concurrent check(): {errors}"

    @patch("src.services.circuit_breaker.log_error")
    def test_concurrent_record_failure_does_not_corrupt_state(
        self, mock_log_error
    ):
        """Multiple threads recording failures concurrently must not leave
        the breaker in an inconsistent state."""
        breaker = CircuitBreaker("test")
        errors = []

        def record_fail():
            try:
                breaker.record_failure()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=record_fail) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], (
            f"Unexpected exceptions during concurrent record_failure(): {errors}"
        )
        state = breaker.get_state()
        assert state["state"] in ("closed", "open")
        assert state["failure_count"] >= FAILURE_THRESHOLD or state["state"] == "open"


# ---------------------------------------------------------------------------
# 14. Module Singletons: exist and are separate instances
# ---------------------------------------------------------------------------


class TestModuleSingletons:
    def test_finnhub_breaker_exists(self):
        """finnhub_breaker must be a CircuitBreaker instance."""
        assert isinstance(finnhub_breaker, CircuitBreaker)

    def test_alpha_vantage_breaker_exists(self):
        """alpha_vantage_breaker must be a CircuitBreaker instance."""
        assert isinstance(alpha_vantage_breaker, CircuitBreaker)

    def test_alpaca_breaker_exists(self):
        """alpaca_breaker must be a CircuitBreaker instance."""
        assert isinstance(alpaca_breaker, CircuitBreaker)

    def test_singletons_are_separate_instances(self):
        """All three singletons must be distinct objects."""
        assert finnhub_breaker is not alpha_vantage_breaker
        assert finnhub_breaker is not alpaca_breaker
        assert alpha_vantage_breaker is not alpaca_breaker

    def test_finnhub_breaker_provider_name(self):
        """finnhub_breaker must have provider='finnhub'."""
        assert finnhub_breaker.provider == "finnhub"

    def test_alpha_vantage_breaker_provider_name(self):
        """alpha_vantage_breaker must have provider='alpha_vantage'."""
        assert alpha_vantage_breaker.provider == "alpha_vantage"

    def test_alpaca_breaker_provider_name(self):
        """alpaca_breaker must have provider='alpaca'."""
        assert alpaca_breaker.provider == "alpaca"


# ---------------------------------------------------------------------------
# 15. log_error Integration: state transitions call log_error() correctly
# ---------------------------------------------------------------------------


class TestLogErrorIntegration:
    @patch("src.services.circuit_breaker.log_error")
    def test_no_log_error_on_partial_failures(self, mock_log_error):
        """log_error must NOT be called while failure count is below threshold."""
        breaker = CircuitBreaker("test")
        for _ in range(FAILURE_THRESHOLD - 1):
            breaker.record_failure()
        mock_log_error.assert_not_called()

    @patch("src.services.circuit_breaker.log_error")
    def test_log_error_called_exactly_once_on_open(self, mock_log_error):
        """log_error must be called exactly once with 'circuit_open' when
        the threshold is hit."""
        breaker = CircuitBreaker("test")
        _open_breaker(breaker)
        assert mock_log_error.call_count == 1
        component, error_type, message = mock_log_error.call_args[0]
        assert component == "circuit_breaker"
        assert error_type == "circuit_open"

    @patch("src.services.circuit_breaker.log_error")
    def test_log_error_not_called_on_check(self, mock_log_error):
        """check() must never call log_error regardless of state."""
        breaker = CircuitBreaker("test")
        # Closed state
        breaker.check()
        mock_log_error.assert_not_called()

    @patch("src.services.circuit_breaker.log_error")
    def test_log_error_sequence_open_then_recovered(self, mock_log_error):
        """The full happy-path sequence (closed->open->half_open->closed) must
        produce exactly two log_error calls: 'circuit_open' then
        'circuit_recovered'."""
        breaker = CircuitBreaker("test")

        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=1000.0
        ):
            _open_breaker(breaker)

        with patch(
            "src.services.circuit_breaker.time.monotonic",
            return_value=1000.0 + OPEN_TIMEOUT,
        ):
            breaker.check()

        breaker.record_success()

        assert mock_log_error.call_count == 2
        first_call_args = mock_log_error.call_args_list[0][0]
        second_call_args = mock_log_error.call_args_list[1][0]
        assert first_call_args[1] == "circuit_open"
        assert second_call_args[1] == "circuit_recovered"

    @patch("src.services.circuit_breaker.log_error")
    def test_log_error_sequence_open_then_probe_failed(self, mock_log_error):
        """The sequence closed->open->half_open->open must produce exactly two
        log_error calls: 'circuit_open' then 'probe_failed'."""
        breaker = CircuitBreaker("test")

        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=1000.0
        ):
            _open_breaker(breaker)

        with patch(
            "src.services.circuit_breaker.time.monotonic",
            return_value=1000.0 + OPEN_TIMEOUT,
        ):
            breaker.check()

        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=2000.0
        ):
            breaker.record_failure()

        assert mock_log_error.call_count == 2
        first_call_args = mock_log_error.call_args_list[0][0]
        second_call_args = mock_log_error.call_args_list[1][0]
        assert first_call_args[1] == "circuit_open"
        assert second_call_args[1] == "probe_failed"


# ---------------------------------------------------------------------------
# 16. Half-Open Probe Concurrency: only one probe allowed
# ---------------------------------------------------------------------------


class TestHalfOpenProbeConcurrency:
    @patch("src.services.circuit_breaker.log_error")
    def test_only_one_probe_allowed_in_half_open(self, mock_log_error):
        """After the first check() transitions to half_open (probe in flight),
        a second check() must raise CircuitBreakerOpenError."""
        breaker = CircuitBreaker("test")

        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=1000.0
        ):
            _open_breaker(breaker)

        # First check: transitions open -> half_open, probe_in_flight = True
        with patch(
            "src.services.circuit_breaker.time.monotonic",
            return_value=1000.0 + OPEN_TIMEOUT,
        ):
            breaker.check()  # Must not raise — this is the probe

        assert breaker.get_state()["state"] == "half_open"
        assert breaker.get_state()["probe_in_flight"] is True

        # Second check: probe already in flight — must raise
        with pytest.raises(CircuitBreakerOpenError):
            breaker.check()

    @patch("src.services.circuit_breaker.log_error")
    def test_probe_resets_after_record_success(self, mock_log_error):
        """After record_success() clears probe_in_flight, a new probe is allowed
        (after the breaker re-opens and times out again)."""
        breaker = CircuitBreaker("test")

        with patch(
            "src.services.circuit_breaker.time.monotonic", return_value=1000.0
        ):
            _open_breaker(breaker)

        with patch(
            "src.services.circuit_breaker.time.monotonic",
            return_value=1000.0 + OPEN_TIMEOUT,
        ):
            breaker.check()  # half_open, probe in flight

        # Probe succeeds — resets probe_in_flight and closes circuit
        breaker.record_success()
        assert breaker.get_state()["state"] == "closed"
        assert breaker.get_state()["probe_in_flight"] is False

        # Circuit works normally again
        breaker.check()  # closed — must not raise
