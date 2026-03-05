"""Tests for the Policy Engine (src/services/policy_engine.py).

All tests mock DB calls — NO real API calls.

Structure:
- Pure function tests (no mocks needed)
- get_effective_policy tests (mock user_policy table)
- run_pre_policy tests (mock get_effective_policy)
- run_full_policy tests (mock DB + policy)
"""

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services.exceptions import ConfigurationError
from src.services.policy_engine import (
    ALWAYS_FORBIDDEN,
    CONSTRAINTS,
    PRESETS,
    EffectivePolicy,
    PolicyResult,
    PolicyViolation,
    TradeProposal,
    _build_effective_policy,
    _calculate_portfolio_drawdown,
    _calculate_portfolio_value,
    _calculate_remaining_cash_pct,
    _count_monthly_trades,
    _is_within_constraints,
    get_effective_policy,
    run_full_policy,
    run_pre_policy,
)

FAKE_USER_ID = "test-user-id-123"
FAKE_ANALYSIS_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def _mock_admin_table():
    """Create a mock Supabase admin client with chainable table calls.

    Chains needed:
    - user_policy: .select("*").eq().execute()
    - policy_change_log: .select().eq().order().limit().execute()
    - portfolio_holdings: .select("*").eq().eq().execute()
    - analysis_runs: .select().eq().execute()
    - trade_log: .select().eq().gte().neq().execute()
    """
    admin = MagicMock()
    tables = {}

    def table_factory(name):
        if name in tables:
            return tables[name]

        mock_table = MagicMock()

        # Default: .select().eq().execute() → empty
        chain_eq = mock_table.select.return_value.eq.return_value
        chain_eq.execute.return_value = SimpleNamespace(data=[])

        # Double .eq(): .select().eq().eq().execute() (portfolio_holdings)
        chain_eq_eq = chain_eq.eq.return_value
        chain_eq_eq.execute.return_value = SimpleNamespace(data=[])

        # .select().eq().order().limit().execute() (policy_change_log)
        chain_order = chain_eq.order.return_value
        chain_limit = chain_order.limit.return_value
        chain_limit.execute.return_value = SimpleNamespace(data=[])

        # .select().eq().gte().neq().execute() (trade_log)
        chain_gte = chain_eq.gte.return_value
        chain_neq = chain_gte.neq.return_value
        chain_neq.execute.return_value = SimpleNamespace(data=[])

        # .select("highwater_mark_value").limit(1).execute() (system_state)
        mock_table.select.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[{"highwater_mark_value": None}]
        )

        tables[name] = mock_table
        return mock_table

    admin.table = MagicMock(side_effect=table_factory)
    admin._tables = tables
    return admin


# --- Pure Function Tests (no mocks needed) ---


class TestCalculatePortfolioValue:
    def test_normal_holdings(self):
        holdings = [
            {"shares": 10, "current_price": 150.0},
            {"shares": 5, "current_price": 200.0},
        ]
        assert _calculate_portfolio_value(holdings) == pytest.approx(2500.0)

    def test_none_current_price_skipped(self):
        holdings = [
            {"shares": 10, "current_price": 150.0},
            {"shares": 5, "current_price": None},
        ]
        assert _calculate_portfolio_value(holdings) == pytest.approx(1500.0)

    def test_empty_list(self):
        assert _calculate_portfolio_value([]) == 0.0


class TestCalculateRemainingCashPct:
    def test_normal_calculation(self):
        holdings = [{"shares": 10, "current_price": 100.0}]
        portfolio_value = 2000.0  # 1000 invested + 1000 cash
        trade_value = 500.0
        result = _calculate_remaining_cash_pct(trade_value, holdings, portfolio_value)
        # cash = 2000 - 1000 = 1000, remaining = 1000 - 500 = 500
        # pct = 500 / 2000 * 100 = 25%
        assert result == pytest.approx(25.0)

    def test_zero_portfolio_value(self):
        result = _calculate_remaining_cash_pct(100.0, [], 0.0)
        assert result == 0.0


class TestCalculatePortfolioDrawdown:
    def test_returns_zero_no_highwater(self):
        holdings = [{"shares": 10, "current_price": 100.0}]
        assert _calculate_portfolio_drawdown(holdings, 0.0) == 0.0

    def test_empty_holdings(self):
        assert _calculate_portfolio_drawdown([], 10000.0) == 0.0

    def test_calculates_drawdown_correctly(self):
        # Highwater = 10000, current = 8000 → 20% drawdown
        holdings = [{"shares": 80, "current_price": 100.0}]
        assert _calculate_portfolio_drawdown(holdings, 10000.0) == pytest.approx(20.0)

    def test_no_drawdown_when_above_highwater(self):
        # Current value (11000) > highwater (10000) → 0% drawdown
        holdings = [{"shares": 110, "current_price": 100.0}]
        assert _calculate_portfolio_drawdown(holdings, 10000.0) == 0.0

    def test_negative_highwater_returns_zero(self):
        holdings = [{"shares": 10, "current_price": 100.0}]
        assert _calculate_portfolio_drawdown(holdings, -1.0) == 0.0


class TestIsWithinConstraints:
    def test_valid_value(self):
        assert _is_within_constraints("max_drawdown_pct", 20) is True

    def test_below_min(self):
        assert _is_within_constraints("max_drawdown_pct", 5) is False

    def test_above_max(self):
        assert _is_within_constraints("max_drawdown_pct", 50) is False

    def test_at_min_boundary(self):
        assert _is_within_constraints("max_drawdown_pct", 10) is True

    def test_at_max_boundary(self):
        assert _is_within_constraints("max_drawdown_pct", 30) is True

    def test_unknown_key(self):
        assert _is_within_constraints("nonexistent_key", 10) is False

    def test_non_numeric_value(self):
        assert _is_within_constraints("max_drawdown_pct", "abc") is False

    def test_none_value(self):
        assert _is_within_constraints("max_drawdown_pct", None) is False


class TestBuildEffectivePolicy:
    def test_builds_with_hard_constraints(self):
        policy = _build_effective_policy(PRESETS["balanced"])
        assert policy.maturity_stage == 1
        assert policy.human_confirm_required is True
        assert policy.em_instruments == ["etf"]
        assert set(policy.forbidden_types) == ALWAYS_FORBIDDEN

    def test_beginner_preset_values(self):
        policy = _build_effective_policy(PRESETS["beginner"])
        assert policy.core_pct == 80
        assert policy.satellite_pct == 20
        assert policy.max_drawdown_pct == 15
        assert policy.max_trades_per_month == 4


class TestCountMonthlyTrades:
    def test_counts_trades(self):
        admin = _mock_admin_table()
        trade_table = admin.table("trade_log")
        chain = trade_table.select.return_value.eq.return_value.gte.return_value.neq.return_value
        chain.execute.return_value = SimpleNamespace(
            data=[{"id": "t1"}, {"id": "t2"}, {"id": "t3"}]
        )
        assert _count_monthly_trades(admin, FAKE_USER_ID) == 3

    def test_excludes_rejected_trades(self):
        """Rejected trades should not count towards monthly limit."""
        admin = _mock_admin_table()
        trade_table = admin.table("trade_log")
        chain = trade_table.select.return_value.eq.return_value.gte.return_value.neq.return_value
        chain.execute.return_value = SimpleNamespace(
            data=[{"id": "t1"}, {"id": "t2"}]  # 2 non-rejected trades
        )
        result = _count_monthly_trades(admin, FAKE_USER_ID)
        assert result == 2
        # Verify .neq was called with correct args
        trade_table.select.return_value.eq.return_value.gte.return_value.neq.assert_called_once_with(
            "status", "rejected"
        )

    def test_no_trades(self):
        admin = _mock_admin_table()
        assert _count_monthly_trades(admin, FAKE_USER_ID) == 0


# --- get_effective_policy Tests ---


class TestGetEffectivePolicy:
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_no_user_policy_row_returns_beginner(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        policy = get_effective_policy(FAKE_USER_ID)

        assert policy.core_pct == 80
        assert policy.satellite_pct == 20
        assert policy.max_drawdown_pct == 15
        assert policy.max_trades_per_month == 4

    @patch("src.services.policy_engine.get_supabase_admin")
    def test_beginner_mode(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        up_table = admin.table("user_policy")
        up_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{"policy_mode": "BEGINNER", "preset_id": "beginner", "cooldown_until": None, "policy_overrides": {}}]
        )

        policy = get_effective_policy(FAKE_USER_ID)

        assert policy.core_pct == 80
        assert policy.satellite_pct == 20

    @patch("src.services.policy_engine.get_supabase_admin")
    def test_preset_balanced(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        up_table = admin.table("user_policy")
        up_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{"policy_mode": "PRESET", "preset_id": "balanced", "cooldown_until": None, "policy_overrides": {}}]
        )

        policy = get_effective_policy(FAKE_USER_ID)

        assert policy.core_pct == 70
        assert policy.satellite_pct == 30
        assert policy.max_drawdown_pct == 20

    @patch("src.services.policy_engine.get_supabase_admin")
    def test_preset_active(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        up_table = admin.table("user_policy")
        up_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{"policy_mode": "PRESET", "preset_id": "active", "cooldown_until": None, "policy_overrides": {}}]
        )

        policy = get_effective_policy(FAKE_USER_ID)

        assert policy.core_pct == 60
        assert policy.satellite_pct == 40
        assert policy.max_drawdown_pct == 25
        assert policy.max_trades_per_month == 10

    @patch("src.services.policy_engine.get_supabase_admin")
    def test_advanced_valid_overrides_applied(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        up_table = admin.table("user_policy")
        up_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{
                "policy_mode": "ADVANCED",
                "preset_id": "balanced",
                "cooldown_until": None,
                "policy_overrides": {"max_drawdown_pct": 25, "max_trades_per_month": 10},
            }]
        )

        policy = get_effective_policy(FAKE_USER_ID)

        assert policy.max_drawdown_pct == 25
        assert policy.max_trades_per_month == 10
        # Non-overridden values stay at balanced preset
        assert policy.max_single_position_pct == 5

    @patch("src.services.policy_engine.get_supabase_admin")
    def test_advanced_out_of_bounds_override_ignored(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        up_table = admin.table("user_policy")
        up_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{
                "policy_mode": "ADVANCED",
                "preset_id": "balanced",
                "cooldown_until": None,
                "policy_overrides": {"max_drawdown_pct": 50},  # Max is 30
            }]
        )

        policy = get_effective_policy(FAKE_USER_ID)

        # Out-of-bounds → stays at preset default
        assert policy.max_drawdown_pct == 20  # balanced default

    @patch("src.services.policy_engine.get_supabase_admin")
    def test_advanced_unknown_key_ignored(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        up_table = admin.table("user_policy")
        up_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{
                "policy_mode": "ADVANCED",
                "preset_id": "balanced",
                "cooldown_until": None,
                "policy_overrides": {"unknown_setting": 42},
            }]
        )

        policy = get_effective_policy(FAKE_USER_ID)

        # Unknown key ignored — all values stay at balanced preset
        assert policy.max_drawdown_pct == 20

    @patch("src.services.policy_engine.get_supabase_admin")
    def test_invalid_preset_id_falls_back_to_beginner(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        up_table = admin.table("user_policy")
        up_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{
                "policy_mode": "PRESET",
                "preset_id": "nonexistent",
                "cooldown_until": None,
                "policy_overrides": {},
            }]
        )

        policy = get_effective_policy(FAKE_USER_ID)

        assert policy.core_pct == 80  # beginner default

    @patch("src.services.policy_engine.get_supabase_admin")
    def test_hard_constraints_always_present(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        up_table = admin.table("user_policy")
        up_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{"policy_mode": "PRESET", "preset_id": "active", "cooldown_until": None, "policy_overrides": {}}]
        )

        policy = get_effective_policy(FAKE_USER_ID)

        assert set(policy.forbidden_types) == ALWAYS_FORBIDDEN
        assert policy.em_instruments == ["etf"]
        assert policy.maturity_stage == 1
        assert policy.human_confirm_required is True

    @patch("src.services.policy_engine.get_supabase_admin")
    def test_cooldown_active_uses_old_preset(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        future_ts = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()

        up_table = admin.table("user_policy")
        up_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{
                "policy_mode": "PRESET",
                "preset_id": "active",
                "cooldown_until": future_ts,
                "policy_overrides": {},
            }]
        )

        # policy_change_log shows old_preset was balanced
        log_table = admin.table("policy_change_log")
        chain = log_table.select.return_value.eq.return_value.order.return_value.limit.return_value
        chain.execute.return_value = SimpleNamespace(
            data=[{"old_preset": "balanced"}]
        )

        policy = get_effective_policy(FAKE_USER_ID)

        # Should use old preset (balanced), not new (active)
        assert policy.core_pct == 70  # balanced
        assert policy.satellite_pct == 30  # balanced

    @patch("src.services.policy_engine.get_supabase_admin")
    def test_cooldown_expired_uses_current_preset(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        past_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        up_table = admin.table("user_policy")
        up_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{
                "policy_mode": "PRESET",
                "preset_id": "active",
                "cooldown_until": past_ts,
                "policy_overrides": {},
            }]
        )

        policy = get_effective_policy(FAKE_USER_ID)

        # Cooldown expired → use current preset (active)
        assert policy.core_pct == 60
        assert policy.satellite_pct == 40

    @patch("src.services.policy_engine.get_supabase_admin")
    def test_cooldown_active_no_change_log_uses_current(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        future_ts = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()

        up_table = admin.table("user_policy")
        up_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{
                "policy_mode": "PRESET",
                "preset_id": "active",
                "cooldown_until": future_ts,
                "policy_overrides": {},
            }]
        )

        # No change_log entries (default empty from _mock_admin_table)

        policy = get_effective_policy(FAKE_USER_ID)

        # Graceful fallback: use current preset
        assert policy.core_pct == 60

    @patch("src.services.policy_engine.get_supabase_admin")
    def test_cooldown_as_datetime_object(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        future_dt = datetime.now(timezone.utc) + timedelta(hours=12)

        up_table = admin.table("user_policy")
        up_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{
                "policy_mode": "PRESET",
                "preset_id": "active",
                "cooldown_until": future_dt,  # datetime object, not string
                "policy_overrides": {},
            }]
        )

        log_table = admin.table("policy_change_log")
        chain = log_table.select.return_value.eq.return_value.order.return_value.limit.return_value
        chain.execute.return_value = SimpleNamespace(
            data=[{"old_preset": "beginner"}]
        )

        policy = get_effective_policy(FAKE_USER_ID)

        assert policy.core_pct == 80  # beginner (old preset)

    @patch("src.services.policy_engine.get_supabase_admin")
    def test_db_error_raises_configuration_error(self, mock_admin_fn):
        mock_admin_fn.side_effect = Exception("connection refused")

        with pytest.raises(ConfigurationError, match="Policy database unavailable"):
            get_effective_policy(FAKE_USER_ID)


# --- run_pre_policy Tests ---


class TestRunPrePolicy:
    @patch("src.services.policy_engine.is_kill_switch_active", return_value=False)
    @patch("src.services.policy_engine.get_effective_policy")
    def test_valid_ticker_passes(self, mock_get_policy, _mock_ks):
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        result = run_pre_policy("AAPL", FAKE_USER_ID)

        assert result.passed is True
        assert result.violations == []

    @patch("src.services.policy_engine.is_kill_switch_active", return_value=False)
    @patch("src.services.policy_engine.get_effective_policy")
    def test_invalid_ticker_blocked(self, mock_get_policy, _mock_ks):
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        result = run_pre_policy("BTC", FAKE_USER_ID)

        assert result.passed is False
        assert len(result.violations) == 1
        assert result.violations[0].rule == "asset_universe"
        assert result.violations[0].severity == "blocking"

    @patch("src.services.policy_engine.is_kill_switch_active", return_value=False)
    @patch("src.services.policy_engine.get_effective_policy")
    def test_policy_snapshot_always_set(self, mock_get_policy, _mock_ks):
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        result = run_pre_policy("AAPL", FAKE_USER_ID)

        assert result.policy_snapshot is not None
        assert "max_drawdown_pct" in result.policy_snapshot

    @patch("src.services.policy_engine.is_kill_switch_active", return_value=False)
    @patch("src.services.policy_engine.get_effective_policy")
    def test_case_insensitive_ticker(self, mock_get_policy, _mock_ks):
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        result = run_pre_policy("aapl", FAKE_USER_ID)

        assert result.passed is True

    @patch("src.services.policy_engine.is_kill_switch_active", return_value=False)
    @patch("src.services.policy_engine.get_effective_policy")
    def test_multiple_invalid_tickers(self, mock_get_policy, _mock_ks):
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        for ticker in ["BTC", "TQQQ", "DOGE", "SPAC_XYZ"]:
            result = run_pre_policy(ticker, FAKE_USER_ID)
            assert result.passed is False
            assert result.violations[0].rule == "asset_universe"

    @patch("src.services.policy_engine.is_kill_switch_active")
    @patch("src.services.policy_engine.get_effective_policy")
    def test_kill_switch_active_blocks_pre_policy(self, mock_get_policy, mock_ks):
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])
        mock_ks.return_value = True

        result = run_pre_policy("AAPL", FAKE_USER_ID)

        assert result.passed is False
        rules = [v.rule for v in result.violations]
        assert "kill_switch" in rules

    @patch("src.services.policy_engine.is_kill_switch_active")
    @patch("src.services.policy_engine.get_effective_policy")
    def test_kill_switch_inactive_allows_pre_policy(self, mock_get_policy, mock_ks):
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])
        mock_ks.return_value = False

        result = run_pre_policy("AAPL", FAKE_USER_ID)

        assert result.passed is True
        rules = [v.rule for v in result.violations]
        assert "kill_switch" not in rules


# --- run_full_policy Tests ---


def _make_trade_proposal(**overrides) -> TradeProposal:
    """Create a default TradeProposal with overrides."""
    defaults = {
        "ticker": "AAPL",
        "action": "BUY",
        "shares": 10,
        "price": 150.0,
        "analysis_id": FAKE_ANALYSIS_ID,
        "sector": None,
        "is_live_order": False,
    }
    defaults.update(overrides)
    return TradeProposal(**defaults)


def _setup_full_policy_mocks(admin, analysis_verification=None, holdings=None, trades_count=0):
    """Set up mocks for run_full_policy.

    Args:
        admin: Mock admin from _mock_admin_table()
        analysis_verification: verification dict for analysis_runs (None = no verification)
        holdings: list of holding dicts (None = empty)
        trades_count: number of trades this month
    """
    # analysis_runs
    runs_table = admin.table("analysis_runs")
    runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[{
            "id": FAKE_ANALYSIS_ID,
            "user_id": FAKE_USER_ID,
            "verification": analysis_verification,
        }]
    )

    # portfolio_holdings (double .eq())
    holdings_table = admin.table("portfolio_holdings")
    chain_eq_eq = holdings_table.select.return_value.eq.return_value.eq.return_value
    chain_eq_eq.execute.return_value = SimpleNamespace(data=holdings or [])

    # trade_log (monthly count — .select().eq().gte().neq().execute())
    trades_table = admin.table("trade_log")
    chain_gte = trades_table.select.return_value.eq.return_value.gte.return_value
    chain_neq = chain_gte.neq.return_value
    chain_neq.execute.return_value = SimpleNamespace(
        data=[{"id": f"t{i}"} for i in range(trades_count)]
    )


class TestRunFullPolicy:
    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_trade_within_all_limits_passes(self, mock_admin_fn, mock_get_policy):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        _setup_full_policy_mocks(
            admin,
            analysis_verification={"has_blocking_disputed": False},
            holdings=[{"shares": 100, "current_price": 150.0}],
            trades_count=2,
        )

        proposal = _make_trade_proposal(shares=1, price=150.0)
        result = run_full_policy(proposal, FAKE_USER_ID)

        assert result.passed is True
        assert result.violations == []

    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_blocking_disputed_blocks_trade(self, mock_admin_fn, mock_get_policy):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        _setup_full_policy_mocks(
            admin,
            analysis_verification={"has_blocking_disputed": True},
        )

        proposal = _make_trade_proposal()
        result = run_full_policy(proposal, FAKE_USER_ID)

        assert result.passed is False
        rules = [v.rule for v in result.violations]
        assert "blocking_disputed_claims" in rules

    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_no_blocking_disputed_no_block(self, mock_admin_fn, mock_get_policy):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        _setup_full_policy_mocks(
            admin,
            analysis_verification={"has_blocking_disputed": False},
            holdings=[{"shares": 100, "current_price": 150.0}],
        )

        proposal = _make_trade_proposal(shares=1, price=150.0)
        result = run_full_policy(proposal, FAKE_USER_ID)

        rules = [v.rule for v in result.violations]
        assert "blocking_disputed_claims" not in rules

    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_verification_none_no_block(self, mock_admin_fn, mock_get_policy):
        """analysis_runs.verification is None (not yet verified) → no block."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        _setup_full_policy_mocks(admin, analysis_verification=None)

        proposal = _make_trade_proposal()
        result = run_full_policy(proposal, FAKE_USER_ID)

        rules = [v.rule for v in result.violations]
        assert "blocking_disputed_claims" not in rules

    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_analysis_not_found_blocks(self, mock_admin_fn, mock_get_policy):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        # analysis_runs returns empty (default from _mock_admin_table)

        proposal = _make_trade_proposal()
        result = run_full_policy(proposal, FAKE_USER_ID)

        assert result.passed is False
        rules = [v.rule for v in result.violations]
        assert "analysis_not_found" in rules

    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_wrong_user_same_error_as_not_found(self, mock_admin_fn, mock_get_policy):
        """Ownership check — same message for not-found and wrong-user (no info leak)."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{
                "id": FAKE_ANALYSIS_ID,
                "user_id": "different-user-id",
                "verification": None,
            }]
        )

        proposal = _make_trade_proposal()
        result = run_full_policy(proposal, FAKE_USER_ID)

        assert result.passed is False
        violations = [v for v in result.violations if v.rule == "analysis_not_found"]
        assert len(violations) == 1
        assert violations[0].message == "Analysis run not found"

    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_max_single_position_exceeded(self, mock_admin_fn, mock_get_policy):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        _setup_full_policy_mocks(
            admin,
            analysis_verification={"has_blocking_disputed": False},
            holdings=[{"shares": 100, "current_price": 100.0}],  # portfolio = $10,000
        )

        # Trade = 10 * 150 = $1,500 = 15% of $10,000 (exceeds 5% limit)
        proposal = _make_trade_proposal(shares=10, price=150.0)
        result = run_full_policy(proposal, FAKE_USER_ID)

        assert result.passed is False
        rules = [v.rule for v in result.violations]
        assert "max_single_position" in rules

    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_max_trades_per_month_exceeded(self, mock_admin_fn, mock_get_policy):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        _setup_full_policy_mocks(
            admin,
            analysis_verification={"has_blocking_disputed": False},
            trades_count=8,  # balanced limit is 8
        )

        proposal = _make_trade_proposal()
        result = run_full_policy(proposal, FAKE_USER_ID)

        assert result.passed is False
        rules = [v.rule for v in result.violations]
        assert "max_trades_per_month" in rules

    @patch("src.services.policy_engine._calculate_portfolio_drawdown")
    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_drawdown_kill_switch_blocks(self, mock_admin_fn, mock_get_policy, mock_drawdown):
        """Mock _calculate_portfolio_drawdown to return high value to verify check logic."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        _setup_full_policy_mocks(
            admin,
            analysis_verification={"has_blocking_disputed": False},
        )

        # Mock drawdown to return 25% (exceeds balanced limit of 20%)
        mock_drawdown.return_value = 25.0

        proposal = _make_trade_proposal()
        result = run_full_policy(proposal, FAKE_USER_ID)

        assert result.passed is False
        rules = [v.rule for v in result.violations]
        assert "drawdown_kill_switch" in rules

    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_maturity_stage_blocks_live_order(self, mock_admin_fn, mock_get_policy):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        _setup_full_policy_mocks(
            admin,
            analysis_verification={"has_blocking_disputed": False},
        )

        proposal = _make_trade_proposal(is_live_order=True)
        result = run_full_policy(proposal, FAKE_USER_ID)

        assert result.passed is False
        rules = [v.rule for v in result.violations]
        assert "maturity_stage" in rules

    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_empty_portfolio_trade_allowed(self, mock_admin_fn, mock_get_policy):
        """Empty portfolio (portfolio_value=0) → trade allowed, no division by zero."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        _setup_full_policy_mocks(
            admin,
            analysis_verification={"has_blocking_disputed": False},
            holdings=[],  # empty portfolio
        )

        proposal = _make_trade_proposal()
        result = run_full_policy(proposal, FAKE_USER_ID)

        # No position violations when portfolio is empty
        rules = [v.rule for v in result.violations]
        assert "max_single_position" not in rules

    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_sell_trade_skips_position_and_cash_checks(self, mock_admin_fn, mock_get_policy):
        """SELL trades skip position-size and cash-reserve checks."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        _setup_full_policy_mocks(
            admin,
            analysis_verification={"has_blocking_disputed": False},
            holdings=[{"shares": 100, "current_price": 100.0}],
        )

        # SELL trade — even a large sell should not trigger position/cash checks
        proposal = _make_trade_proposal(action="SELL", shares=50, price=100.0)
        result = run_full_policy(proposal, FAKE_USER_ID)

        rules = [v.rule for v in result.violations]
        assert "max_single_position" not in rules

    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_multiple_violations_all_collected(self, mock_admin_fn, mock_get_policy):
        """Multiple violations should all be collected, not just the first one."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        _setup_full_policy_mocks(
            admin,
            analysis_verification={"has_blocking_disputed": True},
            holdings=[{"shares": 100, "current_price": 100.0}],
            trades_count=8,  # at limit
        )

        # Large BUY → triggers position + cash + disputed + trades
        proposal = _make_trade_proposal(shares=100, price=100.0, is_live_order=True)
        result = run_full_policy(proposal, FAKE_USER_ID)

        assert result.passed is False
        rules = [v.rule for v in result.violations]
        assert len(rules) >= 3
        assert "blocking_disputed_claims" in rules
        assert "max_trades_per_month" in rules
        assert "maturity_stage" in rules

    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_policy_snapshot_always_set(self, mock_admin_fn, mock_get_policy):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        _setup_full_policy_mocks(
            admin,
            analysis_verification={"has_blocking_disputed": False},
        )

        proposal = _make_trade_proposal()
        result = run_full_policy(proposal, FAKE_USER_ID)

        assert result.policy_snapshot is not None
        assert "max_drawdown_pct" in result.policy_snapshot
        assert "forbidden_types" in result.policy_snapshot

    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_blocking_manual_check_blocks_trade(self, mock_admin_fn, mock_get_policy):
        """has_blocking_manual_check=True → trade blocked with blocking_manual_check violation."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        _setup_full_policy_mocks(
            admin,
            analysis_verification={"has_blocking_disputed": False, "has_blocking_manual_check": True},
        )

        proposal = _make_trade_proposal()
        result = run_full_policy(proposal, FAKE_USER_ID)

        assert result.passed is False
        rules = [v.rule for v in result.violations]
        assert "blocking_manual_check" in rules

    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_no_blocking_manual_check_allows(self, mock_admin_fn, mock_get_policy):
        """has_blocking_manual_check=False → no blocking_manual_check violation."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        _setup_full_policy_mocks(
            admin,
            analysis_verification={"has_blocking_disputed": False, "has_blocking_manual_check": False},
            holdings=[{"shares": 100, "current_price": 150.0}],
        )

        proposal = _make_trade_proposal(shares=1, price=150.0)
        result = run_full_policy(proposal, FAKE_USER_ID)

        rules = [v.rule for v in result.violations]
        assert "blocking_manual_check" not in rules

    @patch("src.services.policy_engine.get_effective_policy")
    @patch("src.services.policy_engine.get_supabase_admin")
    def test_both_disputed_and_manual_check_violations(self, mock_admin_fn, mock_get_policy):
        """has_blocking_disputed=True AND has_blocking_manual_check=True → both violations present."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_get_policy.return_value = _build_effective_policy(PRESETS["balanced"])

        _setup_full_policy_mocks(
            admin,
            analysis_verification={"has_blocking_disputed": True, "has_blocking_manual_check": True},
        )

        proposal = _make_trade_proposal()
        result = run_full_policy(proposal, FAKE_USER_ID)

        assert result.passed is False
        rules = [v.rule for v in result.violations]
        assert "blocking_disputed_claims" in rules
        assert "blocking_manual_check" in rules
