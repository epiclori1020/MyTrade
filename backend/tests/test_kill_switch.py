"""Tests for the Kill-Switch (src/services/kill_switch.py).

All tests mock DB calls and external dependencies — NO real API calls.

Test priorities (from task specification):
1. is_kill_switch_active: fail-closed behaviour (True on DB error)
2. activate_kill_switch: idempotency, payload correctness
3. deactivate_kill_switch: clears all fields
4. get_kill_switch_status: pure read, unreadable-state fallback
5. update_highwater_mark: only updates when higher, best-effort on error
6. _check_drawdown_trigger: threshold logic, edge cases
7. _check_broker_cb_trigger: open vs. closed circuit breaker
8. _check_verification_rate_trigger: rate calculation, thresholds
9. evaluate_kill_switch_triggers: orchestration + auto-activation

Mock pattern matches test_policy_engine.py:
- @patch("src.services.kill_switch.get_supabase_admin") for DB mocks
- MagicMock() admin with table-factory pattern
- SimpleNamespace(data=[...]) for DB responses
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services.kill_switch import (
    RECENT_ANALYSES_COUNT,
    SYSTEM_STATE_ID,
    VERIFICATION_RATE_THRESHOLD,
    _check_broker_cb_trigger,
    _check_drawdown_trigger,
    _check_verification_rate_trigger,
    activate_kill_switch,
    deactivate_kill_switch,
    evaluate_kill_switch_triggers,
    get_kill_switch_status,
    is_kill_switch_active,
    update_highwater_mark,
)

FAKE_USER_ID = "test-user-id-123"


# ---------------------------------------------------------------------------
# Mock admin factory — matches pattern from test_policy_engine.py
# ---------------------------------------------------------------------------


def _mock_admin_table():
    """Create a mock Supabase admin client with chainable table calls.

    Chains needed by kill_switch.py:
    - system_state:         .select("*").limit(1).execute()
                            .update({}).eq("id", ...).execute()
    - portfolio_holdings:   .select(...).eq().eq().execute()
    - analysis_runs:        .select("id").eq().order().limit().execute()
    - claims:               .select("id").in_().execute()
    - verification_results: .select("status").in_().execute()
    """
    admin = MagicMock()
    tables = {}

    def table_factory(name):
        if name in tables:
            return tables[name]

        mock_table = MagicMock()

        # system_state: .select("*").limit(1).execute() -> empty by default
        mock_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[])
        )

        # system_state update: .update({}).eq("id", ...).execute()
        mock_table.update.return_value.eq.return_value.execute.return_value = (
            SimpleNamespace(data=[])
        )

        # .select().eq().execute() (generic single eq)
        chain_eq = mock_table.select.return_value.eq.return_value
        chain_eq.execute.return_value = SimpleNamespace(data=[])

        # .select().eq().eq().execute() (portfolio_holdings: user_id + status)
        chain_eq.eq.return_value.execute.return_value = SimpleNamespace(data=[])

        # .select().eq().order().limit().execute() (analysis_runs)
        chain_eq.order.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[])
        )

        # .select().in_().execute() (claims, verification_results)
        mock_table.select.return_value.in_.return_value.execute.return_value = (
            SimpleNamespace(data=[])
        )

        tables[name] = mock_table
        return mock_table

    admin.table = MagicMock(side_effect=table_factory)
    admin._tables = tables
    return admin


def _mock_system_state_row(**kwargs) -> dict:
    """Build a minimal system_state row with sensible defaults."""
    defaults = {
        "id": SYSTEM_STATE_ID,
        "kill_switch_active": False,
        "kill_switch_reason": None,
        "kill_switch_activated_at": None,
        "highwater_mark_value": 0.0,
        "highwater_mark_at": None,
        "updated_at": "2026-03-03T10:00:00+00:00",
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# 1. is_kill_switch_active
# ---------------------------------------------------------------------------


class TestIsKillSwitchActive:
    @patch("src.services.kill_switch.get_supabase_admin")
    def test_inactive_returns_false(self, mock_admin_fn):
        """system_state row with kill_switch_active=False returns False."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        ss_table = admin.table("system_state")
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[_mock_system_state_row(kill_switch_active=False)])
        )

        assert is_kill_switch_active() is False

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_active_returns_true(self, mock_admin_fn):
        """system_state row with kill_switch_active=True returns True."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        ss_table = admin.table("system_state")
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(
                data=[
                    _mock_system_state_row(
                        kill_switch_active=True,
                        kill_switch_reason="auto_drawdown",
                    )
                ]
            )
        )

        assert is_kill_switch_active() is True

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_db_error_returns_true_fail_closed(self, mock_admin_fn):
        """get_supabase_admin raises Exception -> True (fail-closed)."""
        mock_admin_fn.side_effect = Exception("connection refused")

        assert is_kill_switch_active() is True

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_no_system_state_row_returns_true(self, mock_admin_fn):
        """Empty data (no row in system_state) -> True (fail-closed)."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        # Default mock already returns data=[] for system_state — no override needed
        assert is_kill_switch_active() is True


# ---------------------------------------------------------------------------
# 2. activate_kill_switch
# ---------------------------------------------------------------------------


class TestActivateKillSwitch:
    @patch("src.services.kill_switch.log_error")
    @patch("src.services.kill_switch.get_supabase_admin")
    def test_activates_correctly(self, mock_admin_fn, mock_log_error):
        """activate_kill_switch writes active=True and returns the expected dict."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        ss_table = admin.table("system_state")
        # Initial state: not yet active
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[_mock_system_state_row(kill_switch_active=False)])
        )

        result = activate_kill_switch("auto_drawdown")

        assert result["active"] is True
        assert result["reason"] == "auto_drawdown"
        assert "activated_at" in result
        assert result["activated_at"] is not None

    @patch("src.services.kill_switch.log_error")
    @patch("src.services.kill_switch.get_supabase_admin")
    def test_idempotent_when_already_active(self, mock_admin_fn, mock_log_error):
        """If already active, returns existing state without calling update."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        ss_table = admin.table("system_state")
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(
                data=[
                    _mock_system_state_row(
                        kill_switch_active=True,
                        kill_switch_reason="existing_reason",
                        kill_switch_activated_at="2026-03-03T09:00:00+00:00",
                    )
                ]
            )
        )

        result = activate_kill_switch("new_reason")

        # Returns existing state, not the new reason
        assert result["active"] is True
        assert result["reason"] == "existing_reason"
        assert result["activated_at"] == "2026-03-03T09:00:00+00:00"

        # update must NOT have been called
        ss_table.update.assert_not_called()

    @patch("src.services.kill_switch.log_error")
    @patch("src.services.kill_switch.get_supabase_admin")
    def test_update_call_includes_updated_at(self, mock_admin_fn, mock_log_error):
        """The update payload must include the updated_at timestamp field."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        ss_table = admin.table("system_state")
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[_mock_system_state_row(kill_switch_active=False)])
        )

        activate_kill_switch("test_reason")

        # Verify update was called once
        ss_table.update.assert_called_once()
        payload = ss_table.update.call_args[0][0]

        assert payload["kill_switch_active"] is True
        assert payload["kill_switch_reason"] == "test_reason"
        assert "kill_switch_activated_at" in payload
        assert "updated_at" in payload

    @patch("src.services.kill_switch.log_error")
    @patch("src.services.kill_switch.get_supabase_admin")
    def test_update_targets_correct_system_state_id(self, mock_admin_fn, mock_log_error):
        """The update must target SYSTEM_STATE_ID via .eq('id', ...)."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        ss_table = admin.table("system_state")
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[_mock_system_state_row(kill_switch_active=False)])
        )

        activate_kill_switch("test")

        eq_call = ss_table.update.return_value.eq
        eq_call.assert_called_once_with("id", SYSTEM_STATE_ID)


# ---------------------------------------------------------------------------
# 3. deactivate_kill_switch
# ---------------------------------------------------------------------------


class TestDeactivateKillSwitch:
    @patch("src.services.kill_switch.log_error")
    @patch("src.services.kill_switch.get_supabase_admin")
    def test_deactivates_correctly(self, mock_admin_fn, mock_log_error):
        """deactivate_kill_switch returns {active: False, reason: None, activated_at: None}."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        result = deactivate_kill_switch()

        assert result == {"active": False, "reason": None, "activated_at": None}

    @patch("src.services.kill_switch.log_error")
    @patch("src.services.kill_switch.get_supabase_admin")
    def test_update_clears_fields(self, mock_admin_fn, mock_log_error):
        """The update payload must set active=False and clear reason and activated_at."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        ss_table = admin.table("system_state")

        deactivate_kill_switch()

        ss_table.update.assert_called_once()
        payload = ss_table.update.call_args[0][0]

        assert payload["kill_switch_active"] is False
        assert payload["kill_switch_reason"] is None
        assert payload["kill_switch_activated_at"] is None
        assert "updated_at" in payload

    @patch("src.services.kill_switch.log_error")
    @patch("src.services.kill_switch.get_supabase_admin")
    def test_update_targets_correct_system_state_id(self, mock_admin_fn, mock_log_error):
        """The deactivate update must target SYSTEM_STATE_ID."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        ss_table = admin.table("system_state")

        deactivate_kill_switch()

        eq_call = ss_table.update.return_value.eq
        eq_call.assert_called_once_with("id", SYSTEM_STATE_ID)


# ---------------------------------------------------------------------------
# 4. get_kill_switch_status
# ---------------------------------------------------------------------------


class TestGetKillSwitchStatus:
    @patch("src.services.kill_switch.get_supabase_admin")
    def test_returns_active_state(self, mock_admin_fn):
        """Returns active=True with reason when switch is on."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        ss_table = admin.table("system_state")
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(
                data=[
                    _mock_system_state_row(
                        kill_switch_active=True,
                        kill_switch_reason="auto_drawdown",
                        kill_switch_activated_at="2026-03-03T09:00:00+00:00",
                    )
                ]
            )
        )

        status = get_kill_switch_status()

        assert status["active"] is True
        assert status["reason"] == "auto_drawdown"
        assert status["activated_at"] == "2026-03-03T09:00:00+00:00"

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_returns_inactive_state(self, mock_admin_fn):
        """Returns active=False when switch is off."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        ss_table = admin.table("system_state")
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[_mock_system_state_row(kill_switch_active=False)])
        )

        status = get_kill_switch_status()

        assert status["active"] is False
        assert status["reason"] is None

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_unreadable_state_returns_active_with_message(self, mock_admin_fn):
        """When system_state row is None (unreadable), returns active=True with reason."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        # Default mock returns data=[] -> state is None
        status = get_kill_switch_status()

        assert status["active"] is True
        assert status["reason"] == "system_state unreadable"
        assert status["activated_at"] is None


# ---------------------------------------------------------------------------
# 5. update_highwater_mark
# ---------------------------------------------------------------------------


class TestUpdateHighwaterMark:
    @patch("src.services.kill_switch.get_supabase_admin")
    def test_updates_when_higher(self, mock_admin_fn):
        """When new value > current highwater, update is called."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        ss_table = admin.table("system_state")
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[_mock_system_state_row(highwater_mark_value=8000.0)])
        )

        update_highwater_mark(10000.0)

        ss_table.update.assert_called_once()
        payload = ss_table.update.call_args[0][0]
        assert payload["highwater_mark_value"] == 10000.0

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_no_update_when_lower(self, mock_admin_fn):
        """When new value < current highwater, update is NOT called."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        ss_table = admin.table("system_state")
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[_mock_system_state_row(highwater_mark_value=12000.0)])
        )

        update_highwater_mark(9000.0)

        ss_table.update.assert_not_called()

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_updates_from_zero(self, mock_admin_fn):
        """When current highwater is 0 (never set), any positive value triggers update."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        ss_table = admin.table("system_state")
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[_mock_system_state_row(highwater_mark_value=0.0)])
        )

        update_highwater_mark(5000.0)

        ss_table.update.assert_called_once()
        payload = ss_table.update.call_args[0][0]
        assert payload["highwater_mark_value"] == 5000.0

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_db_error_does_not_raise(self, mock_admin_fn):
        """Best-effort: if DB raises, the function swallows the error and returns None."""
        mock_admin_fn.side_effect = Exception("DB connection lost")

        # Must not raise — best-effort design
        result = update_highwater_mark(10000.0)

        assert result is None

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_no_system_state_row_does_not_raise(self, mock_admin_fn):
        """When system_state row is missing, function returns without updating."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        # Default mock returns data=[] -> state is None
        update_highwater_mark(10000.0)

        ss_table = admin._tables.get("system_state")
        if ss_table:
            ss_table.update.assert_not_called()


# ---------------------------------------------------------------------------
# 6. _check_drawdown_trigger
# ---------------------------------------------------------------------------


class TestCheckDrawdownTrigger:
    @patch("src.services.policy_engine.get_supabase_admin")
    @patch("src.services.kill_switch.get_supabase_admin")
    def test_triggered_when_drawdown_exceeds_threshold(
        self, mock_admin_fn, mock_policy_admin_fn
    ):
        """Drawdown of 25% with threshold of 20% -> triggered=True."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        # highwater = 10000, current = 7500 -> 25% drawdown
        ss_table = admin.table("system_state")
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(
                data=[_mock_system_state_row(highwater_mark_value=10000.0)]
            )
        )

        holdings_table = admin.table("portfolio_holdings")
        holdings_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{"shares": 75, "current_price": 100.0}]  # 75 * 100 = 7500
        )

        # Mock get_effective_policy at its source module (lazy import inside _check_drawdown_trigger)
        policy_mock = MagicMock()
        policy_mock.max_drawdown_pct = 20.0
        policy_admin = _mock_admin_table()
        mock_policy_admin_fn.return_value = policy_admin
        # user_policy table returns no row -> falls back to beginner (20% drawdown threshold
        # for balanced, but beginner is 15% which still triggers at 25%)

        with patch("src.services.policy_engine.get_effective_policy", return_value=policy_mock):
            result = _check_drawdown_trigger(FAKE_USER_ID)

        assert result["triggered"] is True
        assert result["drawdown_pct"] == pytest.approx(25.0)
        assert result["threshold_pct"] == 20.0
        assert result["current_value"] == pytest.approx(7500.0)
        assert result["highwater_value"] == 10000.0

    @patch("src.services.policy_engine.get_supabase_admin")
    @patch("src.services.kill_switch.get_supabase_admin")
    def test_not_triggered_when_within_threshold(
        self, mock_admin_fn, mock_policy_admin_fn
    ):
        """Drawdown of 10% with threshold of 20% -> triggered=False."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        # highwater = 10000, current = 9000 -> 10% drawdown
        ss_table = admin.table("system_state")
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(
                data=[_mock_system_state_row(highwater_mark_value=10000.0)]
            )
        )

        holdings_table = admin.table("portfolio_holdings")
        holdings_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{"shares": 90, "current_price": 100.0}]  # 90 * 100 = 9000
        )

        policy_mock = MagicMock()
        policy_mock.max_drawdown_pct = 20.0
        mock_policy_admin_fn.return_value = _mock_admin_table()

        with patch("src.services.policy_engine.get_effective_policy", return_value=policy_mock):
            result = _check_drawdown_trigger(FAKE_USER_ID)

        assert result["triggered"] is False
        assert result["drawdown_pct"] == pytest.approx(10.0)

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_no_highwater_returns_not_triggered(self, mock_admin_fn):
        """highwater_mark_value of 0 -> not triggered (no baseline to compare)."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        ss_table = admin.table("system_state")
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=[_mock_system_state_row(highwater_mark_value=0.0)])
        )

        result = _check_drawdown_trigger(FAKE_USER_ID)

        assert result["triggered"] is False
        assert "No highwater mark set" in result["detail"]

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_no_holdings_returns_not_triggered(self, mock_admin_fn):
        """Empty holdings list -> not triggered."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        ss_table = admin.table("system_state")
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(
                data=[_mock_system_state_row(highwater_mark_value=10000.0)]
            )
        )

        # portfolio_holdings returns empty list (default)
        result = _check_drawdown_trigger(FAKE_USER_ID)

        assert result["triggered"] is False
        assert "No active holdings" in result["detail"]

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_policy_failure_uses_yaml_fallback_threshold(self, mock_admin_fn):
        """When get_effective_policy raises, falls back to YAML default of 20%."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        # 25% drawdown: highwater=10000, current=7500
        ss_table = admin.table("system_state")
        ss_table.select.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(
                data=[_mock_system_state_row(highwater_mark_value=10000.0)]
            )
        )

        holdings_table = admin.table("portfolio_holdings")
        holdings_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{"shares": 75, "current_price": 100.0}]
        )

        # get_effective_policy is a lazy import — patch at its source to raise
        with patch(
            "src.services.policy_engine.get_effective_policy",
            side_effect=Exception("DB unavailable"),
        ):
            result = _check_drawdown_trigger(FAKE_USER_ID)

        # 25% > 20% fallback threshold -> triggered
        assert result["triggered"] is True
        assert result["threshold_pct"] == 20.0

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_system_state_unreadable_returns_not_triggered(self, mock_admin_fn):
        """When system_state is None (unreadable) -> fail-open, not triggered."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        # Default mock returns data=[] -> state is None
        result = _check_drawdown_trigger(FAKE_USER_ID)

        assert result["triggered"] is False
        assert "Cannot read system_state" in result["detail"]


# ---------------------------------------------------------------------------
# 7. _check_broker_cb_trigger
# ---------------------------------------------------------------------------


class TestCheckBrokerCbTrigger:
    @patch("src.services.circuit_breaker.alpaca_breaker")
    def test_triggered_when_open(self, mock_alpaca_breaker):
        """alpaca_breaker state='open' -> triggered=True.

        alpaca_breaker is a lazy import inside _check_broker_cb_trigger, so it must
        be patched at its definition site (src.services.circuit_breaker), not at
        the kill_switch module level.
        """
        mock_alpaca_breaker.get_state.return_value = {
            "state": "open",
            "failure_count": 5,
        }

        result = _check_broker_cb_trigger()

        assert result["triggered"] is True
        assert result["cb_state"] == "open"
        assert result["failure_count"] == 5

    @patch("src.services.circuit_breaker.alpaca_breaker")
    def test_not_triggered_when_closed(self, mock_alpaca_breaker):
        """alpaca_breaker state='closed' -> triggered=False."""
        mock_alpaca_breaker.get_state.return_value = {
            "state": "closed",
            "failure_count": 0,
        }

        result = _check_broker_cb_trigger()

        assert result["triggered"] is False
        assert result["cb_state"] == "closed"

    @patch("src.services.circuit_breaker.alpaca_breaker")
    def test_not_triggered_when_half_open(self, mock_alpaca_breaker):
        """alpaca_breaker state='half_open' -> triggered=False (not fully open)."""
        mock_alpaca_breaker.get_state.return_value = {
            "state": "half_open",
            "failure_count": 5,
        }

        result = _check_broker_cb_trigger()

        assert result["triggered"] is False
        assert result["cb_state"] == "half_open"

    @patch("src.services.circuit_breaker.alpaca_breaker")
    def test_get_state_exception_returns_not_triggered(self, mock_alpaca_breaker):
        """If alpaca_breaker.get_state() raises, fail-open: triggered=False."""
        mock_alpaca_breaker.get_state.side_effect = Exception("breaker unavailable")

        result = _check_broker_cb_trigger()

        assert result["triggered"] is False
        assert "detail" in result


# ---------------------------------------------------------------------------
# 8. _check_verification_rate_trigger
# ---------------------------------------------------------------------------


class TestCheckVerificationRateTrigger:
    @patch("src.services.kill_switch.get_supabase_admin")
    def test_triggered_when_below_threshold(self, mock_admin_fn):
        """50% verification rate (< 70% threshold) -> triggered=True."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        # 2 recent analyses
        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "run-001"}, {"id": "run-002"}]
        )

        # 4 total claims
        claims_table = admin.table("claims")
        claims_table.select.return_value.in_.return_value.execute.return_value = (
            SimpleNamespace(
                data=[
                    {"id": "claim-1"},
                    {"id": "claim-2"},
                    {"id": "claim-3"},
                    {"id": "claim-4"},
                ]
            )
        )

        # Only 2 verified out of 4 = 50%
        vr_table = admin.table("verification_results")
        vr_table.select.return_value.in_.return_value.execute.return_value = (
            SimpleNamespace(
                data=[
                    {"status": "verified"},
                    {"status": "consistent"},
                ]
            )
        )

        result = _check_verification_rate_trigger(FAKE_USER_ID)

        assert result["triggered"] is True
        assert result["rate_pct"] == pytest.approx(50.0)
        assert result["threshold_pct"] == VERIFICATION_RATE_THRESHOLD
        assert result["verified_count"] == 2
        assert result["total_claims"] == 4

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_not_triggered_when_above_threshold(self, mock_admin_fn):
        """80% verification rate (> 70% threshold) -> triggered=False."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        # 1 recent analysis
        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "run-001"}]
        )

        # 5 total claims
        claims_table = admin.table("claims")
        claims_table.select.return_value.in_.return_value.execute.return_value = (
            SimpleNamespace(
                data=[
                    {"id": "claim-1"},
                    {"id": "claim-2"},
                    {"id": "claim-3"},
                    {"id": "claim-4"},
                    {"id": "claim-5"},
                ]
            )
        )

        # 4 verified out of 5 = 80%
        vr_table = admin.table("verification_results")
        vr_table.select.return_value.in_.return_value.execute.return_value = (
            SimpleNamespace(
                data=[
                    {"status": "verified"},
                    {"status": "consistent"},
                    {"status": "verified"},
                    {"status": "consistent"},
                ]
            )
        )

        result = _check_verification_rate_trigger(FAKE_USER_ID)

        assert result["triggered"] is False
        assert result["rate_pct"] == pytest.approx(80.0)

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_no_analyses_returns_not_triggered(self, mock_admin_fn):
        """No recent analyses found -> not triggered (no data to evaluate)."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        # Default: analysis_runs returns data=[] via chain eq().order().limit().execute()
        result = _check_verification_rate_trigger(FAKE_USER_ID)

        assert result["triggered"] is False
        assert "No analyses found" in result["detail"]

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_no_claims_returns_not_triggered(self, mock_admin_fn):
        """Analyses exist but no claims -> not triggered."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        # analyses exist
        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "run-001"}]
        )

        # claims returns empty (default)
        result = _check_verification_rate_trigger(FAKE_USER_ID)

        assert result["triggered"] is False
        assert "No claims found" in result["detail"]

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_disputed_and_unverified_claims_not_counted_as_verified(
        self, mock_admin_fn
    ):
        """disputed and unverified statuses do NOT count towards verified_count."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "run-001"}]
        )

        claims_table = admin.table("claims")
        claims_table.select.return_value.in_.return_value.execute.return_value = (
            SimpleNamespace(
                data=[
                    {"id": "claim-1"},
                    {"id": "claim-2"},
                    {"id": "claim-3"},
                    {"id": "claim-4"},
                ]
            )
        )

        # disputed and unverified should not be counted
        vr_table = admin.table("verification_results")
        vr_table.select.return_value.in_.return_value.execute.return_value = (
            SimpleNamespace(
                data=[
                    {"status": "disputed"},
                    {"status": "unverified"},
                    {"status": "manual_check"},
                    {"status": "verified"},
                ]
            )
        )

        result = _check_verification_rate_trigger(FAKE_USER_ID)

        # Only 1 verified out of 4 total claims = 25%
        assert result["verified_count"] == 1
        assert result["rate_pct"] == pytest.approx(25.0)
        assert result["triggered"] is True

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_exactly_at_threshold_not_triggered(self, mock_admin_fn):
        """Rate exactly at 70% threshold is not triggered (trigger requires strictly < 70%)."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "run-001"}]
        )

        # 10 total claims, 7 verified = 70.0%
        claims_table = admin.table("claims")
        claims_table.select.return_value.in_.return_value.execute.return_value = (
            SimpleNamespace(data=[{"id": f"claim-{i}"} for i in range(10)])
        )

        vr_table = admin.table("verification_results")
        vr_table.select.return_value.in_.return_value.execute.return_value = (
            SimpleNamespace(data=[{"status": "verified"} for _ in range(7)])
        )

        result = _check_verification_rate_trigger(FAKE_USER_ID)

        assert result["rate_pct"] == pytest.approx(70.0)
        # At exactly 70%, rate < 70.0 is False -> not triggered
        assert result["triggered"] is False

    @patch("src.services.kill_switch.get_supabase_admin")
    def test_db_error_returns_not_triggered_fail_open(self, mock_admin_fn):
        """DB error during check -> fail-open: triggered=False with detail."""
        mock_admin_fn.side_effect = Exception("DB error")

        result = _check_verification_rate_trigger(FAKE_USER_ID)

        assert result["triggered"] is False
        assert "detail" in result


# ---------------------------------------------------------------------------
# 9. evaluate_kill_switch_triggers
# ---------------------------------------------------------------------------


class TestEvaluateKillSwitchTriggers:
    @patch("src.services.kill_switch._check_verification_rate_trigger")
    @patch("src.services.kill_switch._check_broker_cb_trigger")
    @patch("src.services.kill_switch._check_drawdown_trigger")
    def test_no_triggers_fire(
        self,
        mock_drawdown,
        mock_broker_cb,
        mock_verification,
    ):
        """When all 3 checks return triggered=False, result is {triggered: False}."""
        mock_drawdown.return_value = {"triggered": False, "detail": "No highwater mark set"}
        mock_broker_cb.return_value = {"triggered": False, "cb_state": "closed", "failure_count": 0}
        mock_verification.return_value = {"triggered": False, "detail": "No analyses found"}

        result = evaluate_kill_switch_triggers(FAKE_USER_ID)

        assert result["triggered"] is False
        assert result["triggers"]["drawdown"]["triggered"] is False
        assert result["triggers"]["broker_cb"]["triggered"] is False
        assert result["triggers"]["verification_rate"]["triggered"] is False

    @patch("src.services.kill_switch.activate_kill_switch")
    @patch("src.services.kill_switch._check_verification_rate_trigger")
    @patch("src.services.kill_switch._check_broker_cb_trigger")
    @patch("src.services.kill_switch._check_drawdown_trigger")
    def test_drawdown_trigger_fires_and_activates_kill_switch(
        self,
        mock_drawdown,
        mock_broker_cb,
        mock_verification,
        mock_activate,
    ):
        """When drawdown trigger fires, activate_kill_switch is called and result is triggered."""
        mock_drawdown.return_value = {
            "triggered": True,
            "drawdown_pct": 25.0,
            "threshold_pct": 20.0,
            "current_value": 7500.0,
            "highwater_value": 10000.0,
        }
        mock_broker_cb.return_value = {"triggered": False, "cb_state": "closed", "failure_count": 0}
        mock_verification.return_value = {"triggered": False, "detail": "No analyses found"}
        mock_activate.return_value = {
            "active": True,
            "reason": "auto_drawdown",
            "activated_at": "2026-03-03T10:00:00+00:00",
        }

        result = evaluate_kill_switch_triggers(FAKE_USER_ID)

        assert result["triggered"] is True
        mock_activate.assert_called_once()
        reason_arg = mock_activate.call_args[0][0]
        assert "drawdown" in reason_arg

    @patch("src.services.kill_switch.activate_kill_switch")
    @patch("src.services.kill_switch._check_verification_rate_trigger")
    @patch("src.services.kill_switch._check_broker_cb_trigger")
    @patch("src.services.kill_switch._check_drawdown_trigger")
    def test_broker_cb_trigger_fires_and_activates_kill_switch(
        self,
        mock_drawdown,
        mock_broker_cb,
        mock_verification,
        mock_activate,
    ):
        """When broker CB trigger fires, activate_kill_switch is called."""
        mock_drawdown.return_value = {"triggered": False, "detail": "No highwater mark set"}
        mock_broker_cb.return_value = {
            "triggered": True,
            "cb_state": "open",
            "failure_count": 5,
        }
        mock_verification.return_value = {"triggered": False, "detail": "No analyses found"}
        mock_activate.return_value = {
            "active": True,
            "reason": "auto_broker_cb",
            "activated_at": "2026-03-03T10:00:00+00:00",
        }

        result = evaluate_kill_switch_triggers(FAKE_USER_ID)

        assert result["triggered"] is True
        mock_activate.assert_called_once()
        reason_arg = mock_activate.call_args[0][0]
        assert "broker_cb" in reason_arg

    @patch("src.services.kill_switch.activate_kill_switch")
    @patch("src.services.kill_switch._check_verification_rate_trigger")
    @patch("src.services.kill_switch._check_broker_cb_trigger")
    @patch("src.services.kill_switch._check_drawdown_trigger")
    def test_verification_rate_trigger_fires_and_activates_kill_switch(
        self,
        mock_drawdown,
        mock_broker_cb,
        mock_verification,
        mock_activate,
    ):
        """When verification rate trigger fires, activate_kill_switch is called."""
        mock_drawdown.return_value = {"triggered": False, "detail": "No highwater mark set"}
        mock_broker_cb.return_value = {"triggered": False, "cb_state": "closed", "failure_count": 0}
        mock_verification.return_value = {
            "triggered": True,
            "rate_pct": 50.0,
            "threshold_pct": 70.0,
            "verified_count": 5,
            "total_claims": 10,
        }
        mock_activate.return_value = {
            "active": True,
            "reason": "auto_verification_rate",
            "activated_at": "2026-03-03T10:00:00+00:00",
        }

        result = evaluate_kill_switch_triggers(FAKE_USER_ID)

        assert result["triggered"] is True
        mock_activate.assert_called_once()
        reason_arg = mock_activate.call_args[0][0]
        assert "verification_rate" in reason_arg

    @patch("src.services.kill_switch.activate_kill_switch")
    @patch("src.services.kill_switch._check_verification_rate_trigger")
    @patch("src.services.kill_switch._check_broker_cb_trigger")
    @patch("src.services.kill_switch._check_drawdown_trigger")
    def test_multiple_triggers_fire_combined_reason(
        self,
        mock_drawdown,
        mock_broker_cb,
        mock_verification,
        mock_activate,
    ):
        """When multiple triggers fire, activate_kill_switch reason includes all names."""
        mock_drawdown.return_value = {
            "triggered": True,
            "drawdown_pct": 25.0,
            "threshold_pct": 20.0,
            "current_value": 7500.0,
            "highwater_value": 10000.0,
        }
        mock_broker_cb.return_value = {
            "triggered": True,
            "cb_state": "open",
            "failure_count": 5,
        }
        mock_verification.return_value = {"triggered": False, "detail": "No analyses found"}
        mock_activate.return_value = {
            "active": True,
            "reason": "auto_drawdown+broker_cb",
            "activated_at": "2026-03-03T10:00:00+00:00",
        }

        result = evaluate_kill_switch_triggers(FAKE_USER_ID)

        assert result["triggered"] is True
        mock_activate.assert_called_once()
        reason_arg = mock_activate.call_args[0][0]
        # Both trigger names must appear in the combined reason
        assert "drawdown" in reason_arg
        assert "broker_cb" in reason_arg

    @patch("src.services.kill_switch.activate_kill_switch")
    @patch("src.services.kill_switch._check_verification_rate_trigger")
    @patch("src.services.kill_switch._check_broker_cb_trigger")
    @patch("src.services.kill_switch._check_drawdown_trigger")
    def test_activate_not_called_when_no_trigger_fires(
        self,
        mock_drawdown,
        mock_broker_cb,
        mock_verification,
        mock_activate,
    ):
        """When no triggers fire, activate_kill_switch must NOT be called."""
        mock_drawdown.return_value = {"triggered": False, "detail": "No highwater mark set"}
        mock_broker_cb.return_value = {"triggered": False, "cb_state": "closed", "failure_count": 0}
        mock_verification.return_value = {"triggered": False, "detail": "No analyses found"}

        evaluate_kill_switch_triggers(FAKE_USER_ID)

        mock_activate.assert_not_called()

    @patch("src.services.kill_switch.activate_kill_switch")
    @patch("src.services.kill_switch._check_verification_rate_trigger")
    @patch("src.services.kill_switch._check_broker_cb_trigger")
    @patch("src.services.kill_switch._check_drawdown_trigger")
    def test_all_trigger_results_present_in_response(
        self,
        mock_drawdown,
        mock_broker_cb,
        mock_verification,
        mock_activate,
    ):
        """The response dict always contains all 3 trigger results under 'triggers' key."""
        drawdown_result = {"triggered": False, "detail": "No highwater mark set"}
        broker_result = {"triggered": False, "cb_state": "closed", "failure_count": 0}
        verification_result = {"triggered": False, "detail": "No analyses found"}

        mock_drawdown.return_value = drawdown_result
        mock_broker_cb.return_value = broker_result
        mock_verification.return_value = verification_result

        result = evaluate_kill_switch_triggers(FAKE_USER_ID)

        assert "triggers" in result
        assert "drawdown" in result["triggers"]
        assert "broker_cb" in result["triggers"]
        assert "verification_rate" in result["triggers"]
        assert result["triggers"]["drawdown"] == drawdown_result
        assert result["triggers"]["broker_cb"] == broker_result
        assert result["triggers"]["verification_rate"] == verification_result


# ---------------------------------------------------------------------------
# 10. Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_system_state_id_is_fixed_uuid(self):
        """SYSTEM_STATE_ID must be the expected fixed UUID string."""
        assert SYSTEM_STATE_ID == "00000000-0000-0000-0000-000000000001"

    def test_verification_rate_threshold_is_70(self):
        """VERIFICATION_RATE_THRESHOLD must be 70.0 per the kill-switch spec."""
        assert VERIFICATION_RATE_THRESHOLD == 70.0

    def test_recent_analyses_count_is_5(self):
        """RECENT_ANALYSES_COUNT must be 5."""
        assert RECENT_ANALYSES_COUNT == 5
