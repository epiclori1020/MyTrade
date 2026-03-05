"""Tests for the Verification Layer (src/services/verification.py).

All tests mock DB calls and AV client — NO real API calls.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services.exceptions import ConfigurationError, DataProviderError, PreconditionError
from src.services.verification import (
    CLAIM_MATCHERS,
    TIER_A_AVAILABLE,
    VerificationResult,
    _build_summary,
    _calculate_deviation,
    _match_claim_to_av,
    _process_single_claim,
    run_verification,
)

FAKE_USER_ID = "test-user-id-123"
FAKE_ANALYSIS_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

SAMPLE_RUN_ROW = {
    "id": FAKE_ANALYSIS_ID,
    "user_id": FAKE_USER_ID,
    "ticker": "AAPL",
    "status": "completed",
    "fundamental_out": {"score": 72},
    "verification": None,
}

SAMPLE_CLAIM_REVENUE = {
    "id": "claim-uuid-001",
    "analysis_id": FAKE_ANALYSIS_ID,
    "claim_id": f"{FAKE_ANALYSIS_ID}_001",
    "claim_text": "AAPL Revenue TTM: $394.3B",
    "claim_type": "number",
    "value": 394_328_000_000,
    "unit": "USD",
    "ticker": "AAPL",
    "period": "TTM",
    "trade_critical": True,
    "tier": "B",
    "required_tier": "A",
}

SAMPLE_CLAIM_PE = {
    "id": "claim-uuid-002",
    "analysis_id": FAKE_ANALYSIS_ID,
    "claim_id": f"{FAKE_ANALYSIS_ID}_002",
    "claim_text": "P/E Ratio: 28.5",
    "claim_type": "ratio",
    "value": 28.5,
    "unit": "ratio",
    "ticker": "AAPL",
    "period": "TTM",
    "trade_critical": True,
    "tier": "B",
    "required_tier": "A",
}

SAMPLE_CLAIM_OPINION = {
    "id": "claim-uuid-003",
    "analysis_id": FAKE_ANALYSIS_ID,
    "claim_id": f"{FAKE_ANALYSIS_ID}_003",
    "claim_text": "Wide moat due to ecosystem lock-in",
    "claim_type": "opinion",
    "value": None,
    "unit": "text",
    "ticker": "AAPL",
    "period": "current",
    "trade_critical": False,
    "tier": "C",
    "required_tier": "C",
}

SAMPLE_AV_DATA = {
    "ticker": "AAPL",
    "period": "2026-TTM",
    "fetched_at": "2026-03-01T12:00:00+00:00",
    "revenue": 395_100_000_000,   # ~0.2% deviation from claim
    "eps": 6.50,
    "pe_ratio": 29.0,             # ~1.75% deviation from claim
    "pb_ratio": 48.5,
    "ev_ebitda": 22.1,
    "roe": 0.175,
    "net_income": None,
    "free_cash_flow": None,
}


def _mock_admin_table():
    """Create a mock Supabase admin client with chainable table calls.

    Extended from test_claim_extraction.py to support .in_() chain
    needed for the idempotency check.
    """
    admin = MagicMock()
    tables = {}

    def table_factory(name):
        if name in tables:
            return tables[name]

        mock_table = MagicMock()
        # .select().eq().execute()
        chain = mock_table.select.return_value.eq.return_value
        chain.execute.return_value = SimpleNamespace(data=[])

        # .select().in_().execute() — for idempotency check
        chain_in = mock_table.select.return_value.in_.return_value
        chain_in.execute.return_value = SimpleNamespace(data=[])

        # .insert().execute()
        mock_table.insert.return_value.execute.return_value = SimpleNamespace(data=[])

        # .update().eq().execute()
        mock_table.update.return_value.eq.return_value.execute.return_value = SimpleNamespace(data=[])

        tables[name] = mock_table
        return mock_table

    admin.table = MagicMock(side_effect=table_factory)
    admin._tables = tables
    return admin


# --- Pure Function Tests (no mocks needed) ---


class TestCalculateDeviation:
    def test_small_deviation(self):
        assert _calculate_deviation(100, 101) == pytest.approx(1.0)

    def test_large_deviation(self):
        assert _calculate_deviation(100, 106) == pytest.approx(6.0)

    def test_zero_deviation(self):
        assert _calculate_deviation(100, 100) == pytest.approx(0.0)

    def test_negative_deviation_is_absolute(self):
        assert _calculate_deviation(100, 94) == pytest.approx(6.0)

    def test_real_world_revenue(self):
        # 394.3B vs 395.1B → ~0.2%
        result = _calculate_deviation(394_328_000_000, 395_100_000_000)
        assert result == pytest.approx(0.1959, rel=0.01)

    def test_real_world_pe(self):
        # 28.5 vs 29.0 → ~1.75%
        result = _calculate_deviation(28.5, 29.0)
        assert result == pytest.approx(1.7544, rel=0.01)


class TestMatchClaimToAv:
    def test_revenue_keyword_matches(self):
        result = _match_claim_to_av(SAMPLE_CLAIM_REVENUE, SAMPLE_AV_DATA)
        assert result is not None
        av_field, av_value = result
        assert av_field == "revenue"
        assert av_value == 395_100_000_000

    def test_pe_ratio_with_slash_matches(self):
        result = _match_claim_to_av(SAMPLE_CLAIM_PE, SAMPLE_AV_DATA)
        assert result is not None
        av_field, av_value = result
        assert av_field == "pe_ratio"
        assert av_value == 29.0

    def test_pe_ratio_without_slash_matches(self):
        """LLM may write 'PE Ratio' without slash."""
        claim = {**SAMPLE_CLAIM_PE, "claim_text": "PE Ratio: 28.5"}
        result = _match_claim_to_av(claim, SAMPLE_AV_DATA)
        assert result is not None
        assert result[0] == "pe_ratio"

    def test_opinion_claim_no_match(self):
        result = _match_claim_to_av(SAMPLE_CLAIM_OPINION, SAMPLE_AV_DATA)
        assert result is None

    def test_av_data_none_returns_none(self):
        result = _match_claim_to_av(SAMPLE_CLAIM_REVENUE, None)
        assert result is None

    def test_claim_type_mismatch_no_match(self):
        """Revenue claim_type is 'number' — won't match ratio matchers."""
        claim = {**SAMPLE_CLAIM_REVENUE, "claim_type": "ratio"}
        result = _match_claim_to_av(claim, SAMPLE_AV_DATA)
        assert result is None

    def test_eps_keyword_matches(self):
        claim = {
            "claim_text": "AAPL EPS TTM: $6.42",
            "claim_type": "number",
        }
        result = _match_claim_to_av(claim, SAMPLE_AV_DATA)
        assert result is not None
        assert result[0] == "eps"

    def test_ev_ebitda_keyword_matches(self):
        claim = {
            "claim_text": "EV/EBITDA: 22.1",
            "claim_type": "ratio",
        }
        result = _match_claim_to_av(claim, SAMPLE_AV_DATA)
        assert result is not None
        assert result[0] == "ev_ebitda"


class TestProcessSingleClaim:
    def test_no_av_match_returns_none(self):
        result = _process_single_claim(SAMPLE_CLAIM_OPINION, SAMPLE_AV_DATA)
        assert result is None

    def test_av_field_none_returns_none(self):
        av_data = {**SAMPLE_AV_DATA, "revenue": None}
        result = _process_single_claim(SAMPLE_CLAIM_REVENUE, av_data)
        assert result is None

    def test_claim_value_none_returns_none(self):
        """Defensive guard: value=None shouldn't cause TypeError."""
        claim = {**SAMPLE_CLAIM_REVENUE, "value": None}
        result = _process_single_claim(claim, SAMPLE_AV_DATA)
        assert result is None

    def test_primary_value_zero_returns_none(self):
        """Division by zero guard."""
        claim = {**SAMPLE_CLAIM_REVENUE, "value": 0}
        result = _process_single_claim(claim, SAMPLE_AV_DATA)
        assert result is None

    def test_primary_value_near_zero_returns_none(self):
        """Near-zero guard — math.isclose tolerance catches tiny floats."""
        claim = {**SAMPLE_CLAIM_REVENUE, "value": 1e-12}
        result = _process_single_claim(claim, SAMPLE_AV_DATA)
        assert result is None

    def test_disputed_trade_critical_high_deviation(self):
        """Deviation >5% + trade_critical → disputed with -15."""
        av_data = {**SAMPLE_AV_DATA, "revenue": 420_000_000_000}  # ~6.5% deviation
        status, conf_adj, sv_json = _process_single_claim(SAMPLE_CLAIM_REVENUE, av_data)
        assert status == "disputed"
        assert conf_adj == -15
        assert sv_json["provider"] == "alpha_vantage"
        assert sv_json["deviation_pct"] > 5.0

    def test_disputed_non_critical_high_deviation(self):
        """Deviation >5% + NOT trade_critical → disputed with -10."""
        claim = {**SAMPLE_CLAIM_REVENUE, "trade_critical": False}
        av_data = {**SAMPLE_AV_DATA, "revenue": 420_000_000_000}
        status, conf_adj, _sv_json = _process_single_claim(claim, av_data)
        assert status == "disputed"
        assert conf_adj == -10

    def test_manual_check_trade_critical_low_deviation(self):
        """trade_critical + deviation ≤5% + no Tier A → manual_check."""
        assert not TIER_A_AVAILABLE  # MVP assumption
        status, conf_adj, sv_json = _process_single_claim(SAMPLE_CLAIM_REVENUE, SAMPLE_AV_DATA)
        assert status == "manual_check"
        assert conf_adj == -15
        assert sv_json["deviation_pct"] < 5.0

    def test_consistent_non_critical_low_deviation(self):
        """NOT trade_critical + deviation ≤5% → consistent."""
        claim = {**SAMPLE_CLAIM_REVENUE, "trade_critical": False}
        status, conf_adj, sv_json = _process_single_claim(claim, SAMPLE_AV_DATA)
        assert status == "consistent"
        assert conf_adj == 0
        assert sv_json["deviation_pct"] < 5.0

    def test_source_verification_json_structure(self):
        """sv_json has all required fields."""
        _status, _conf, sv_json = _process_single_claim(SAMPLE_CLAIM_REVENUE, SAMPLE_AV_DATA)
        assert sv_json["provider"] == "alpha_vantage"
        assert isinstance(sv_json["value"], (int, float))
        assert isinstance(sv_json["deviation_pct"], float)
        assert sv_json["retrieved_at"] == SAMPLE_AV_DATA["fetched_at"]

    def test_av_data_none_returns_none(self):
        result = _process_single_claim(SAMPLE_CLAIM_REVENUE, None)
        assert result is None


class TestBuildSummary:
    def test_all_consistent(self):
        results = [
            ({"trade_critical": False}, ("consistent", 0, {})),
            ({"trade_critical": False}, ("consistent", 0, {})),
        ]
        summary = _build_summary(total_claims=5, cross_checked_results=results)
        assert summary["consistent"] == 2
        assert summary["unverified"] == 3  # 5 - 2
        assert summary["verified"] == 0  # always 0 in MVP
        assert summary["disputed"] == 0
        assert summary["manual_check"] == 0
        assert summary["has_blocking_disputed"] is False
        assert summary["has_blocking_manual_check"] is False

    def test_disputed_trade_critical_sets_blocking(self):
        results = [
            ({"trade_critical": True}, ("disputed", -15, {})),
        ]
        summary = _build_summary(total_claims=3, cross_checked_results=results)
        assert summary["disputed"] == 1
        assert summary["has_blocking_disputed"] is True

    def test_disputed_non_critical_no_blocking(self):
        results = [
            ({"trade_critical": False}, ("disputed", -10, {})),
        ]
        summary = _build_summary(total_claims=3, cross_checked_results=results)
        assert summary["disputed"] == 1
        assert summary["has_blocking_disputed"] is False

    def test_verified_always_zero_in_mvp(self):
        results = [
            ({"trade_critical": False}, ("consistent", 0, {})),
        ]
        summary = _build_summary(total_claims=1, cross_checked_results=results)
        assert summary["verified"] == 0

    def test_unverified_equals_total_minus_cross_checked(self):
        results = [
            ({"trade_critical": False}, ("consistent", 0, {})),
        ]
        summary = _build_summary(total_claims=10, cross_checked_results=results)
        assert summary["unverified"] == 9

    def test_empty_cross_checked_all_unverified(self):
        summary = _build_summary(total_claims=5, cross_checked_results=[])
        assert summary["unverified"] == 5
        assert summary["consistent"] == 0
        assert summary["has_blocking_disputed"] is False
        assert summary["has_blocking_manual_check"] is False

    def test_mixed_scenario(self):
        results = [
            ({"trade_critical": True}, ("manual_check", -15, {})),
            ({"trade_critical": True}, ("disputed", -15, {})),
            ({"trade_critical": False}, ("consistent", 0, {})),
        ]
        summary = _build_summary(total_claims=6, cross_checked_results=results)
        assert summary["manual_check"] == 1
        assert summary["disputed"] == 1
        assert summary["consistent"] == 1
        assert summary["unverified"] == 3
        assert summary["has_blocking_disputed"] is True
        assert summary["has_blocking_manual_check"] is True

    def test_manual_check_trade_critical_sets_blocking(self):
        """manual_check + trade_critical=True → has_blocking_manual_check is True."""
        results = [
            ({"trade_critical": True}, ("manual_check", -15, {})),
        ]
        summary = _build_summary(total_claims=3, cross_checked_results=results)
        assert summary["manual_check"] == 1
        assert summary["has_blocking_manual_check"] is True

    def test_manual_check_non_critical_no_blocking(self):
        """manual_check + trade_critical=False → has_blocking_manual_check is False."""
        results = [
            ({"trade_critical": False}, ("manual_check", -15, {})),
        ]
        summary = _build_summary(total_claims=3, cross_checked_results=results)
        assert summary["manual_check"] == 1
        assert summary["has_blocking_manual_check"] is False

    def test_both_blocking_flags_can_be_true(self):
        """disputed+trade_critical and manual_check+trade_critical → both flags True."""
        results = [
            ({"trade_critical": True}, ("disputed", -15, {})),
            ({"trade_critical": True}, ("manual_check", -15, {})),
        ]
        summary = _build_summary(total_claims=4, cross_checked_results=results)
        assert summary["has_blocking_disputed"] is True
        assert summary["has_blocking_manual_check"] is True


# --- Phase A Pre-Condition Tests ---


class TestPhaseAPreConditions:
    @patch("src.services.verification.get_supabase_admin")
    def test_analysis_not_found(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        with pytest.raises(PreconditionError, match="Analysis run not found"):
            run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

    @patch("src.services.verification.get_supabase_admin")
    def test_wrong_user_same_error_message(self, mock_admin_fn):
        """Wrong user gets same error as not-found (no info leak)."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{**SAMPLE_RUN_ROW, "user_id": "different-user"}]
        )

        with pytest.raises(PreconditionError, match="Analysis run not found"):
            run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

    @patch("src.services.verification.get_supabase_admin")
    def test_no_claims_found(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_RUN_ROW]
        )
        # claims table returns empty (default from _mock_admin_table)

        with pytest.raises(PreconditionError, match="No claims found"):
            run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

    @patch("src.services.verification.get_supabase_admin")
    def test_already_verified(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_RUN_ROW]
        )

        claims_table = admin.table("claims")
        claims_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_CLAIM_REVENUE]
        )

        # verification_results already exist
        vr_table = admin.table("verification_results")
        vr_table.select.return_value.in_.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "existing-vr-uuid"}]
        )

        with pytest.raises(PreconditionError, match="Verification already exists"):
            run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

    @patch("src.services.verification.get_settings")
    @patch("src.services.verification.get_supabase_admin")
    def test_no_av_api_key(self, mock_admin_fn, mock_settings):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_RUN_ROW]
        )

        claims_table = admin.table("claims")
        claims_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_CLAIM_REVENUE]
        )

        mock_settings.return_value.alpha_vantage_api_key = ""

        with pytest.raises(ConfigurationError, match="Alpha Vantage API key"):
            run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)


# --- Phase B Orchestration Tests ---


def _setup_phase_b(admin, claims=None):
    """Configure mock admin for Phase B (all pre-conditions pass)."""
    runs_table = admin.table("analysis_runs")
    runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[SAMPLE_RUN_ROW]
    )

    claims_table = admin.table("claims")
    claims_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=claims or [SAMPLE_CLAIM_REVENUE, SAMPLE_CLAIM_PE, SAMPLE_CLAIM_OPINION]
    )


class TestPhaseBOrchestration:
    @patch("src.services.verification.log_error")
    @patch("src.services.verification.AlphaVantageClient")
    @patch("src.services.verification.get_settings")
    @patch("src.services.verification.get_supabase_admin")
    def test_success_revenue_and_pe_cross_checked(
        self, mock_admin_fn, mock_settings, mock_av_cls, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.alpha_vantage_api_key = "test-key"
        _setup_phase_b(admin)

        mock_client = MagicMock()
        mock_client.get_fundamentals.return_value = SAMPLE_AV_DATA
        mock_av_cls.return_value = mock_client

        result = run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        assert result.status == "completed"
        assert result.analysis_id == FAKE_ANALYSIS_ID
        assert result.results_count == 2  # revenue + PE (opinion not cross-checked)
        assert result.summary["unverified"] == 1  # opinion
        assert result.error_message is None

    @patch("src.services.verification.log_error")
    @patch("src.services.verification.AlphaVantageClient")
    @patch("src.services.verification.get_settings")
    @patch("src.services.verification.get_supabase_admin")
    def test_av_failure_graceful_degradation(
        self, mock_admin_fn, mock_settings, mock_av_cls, mock_log_error
    ):
        """AV API failure → all claims unverified, status still 'completed'."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.alpha_vantage_api_key = "test-key"
        _setup_phase_b(admin)

        mock_client = MagicMock()
        mock_client.get_fundamentals.side_effect = DataProviderError("alpha_vantage", "timeout")
        mock_av_cls.return_value = mock_client

        result = run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        assert result.status == "completed"
        assert result.results_count == 0
        assert result.summary["unverified"] == 3
        assert result.summary["consistent"] == 0

    @patch("src.services.verification.log_error")
    @patch("src.services.verification.AlphaVantageClient")
    @patch("src.services.verification.get_settings")
    @patch("src.services.verification.get_supabase_admin")
    def test_av_client_closed_on_success(
        self, mock_admin_fn, mock_settings, mock_av_cls, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.alpha_vantage_api_key = "test-key"
        _setup_phase_b(admin)

        mock_client = MagicMock()
        mock_client.get_fundamentals.return_value = SAMPLE_AV_DATA
        mock_av_cls.return_value = mock_client

        run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        mock_client.close.assert_called_once()

    @patch("src.services.verification.log_error")
    @patch("src.services.verification.AlphaVantageClient")
    @patch("src.services.verification.get_settings")
    @patch("src.services.verification.get_supabase_admin")
    def test_av_client_closed_on_failure(
        self, mock_admin_fn, mock_settings, mock_av_cls, mock_log_error
    ):
        """AV client.close() called even when get_fundamentals raises."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.alpha_vantage_api_key = "test-key"
        _setup_phase_b(admin)

        mock_client = MagicMock()
        mock_client.get_fundamentals.side_effect = DataProviderError("alpha_vantage", "timeout")
        mock_av_cls.return_value = mock_client

        run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        mock_client.close.assert_called_once()

    @patch("src.services.verification.log_error")
    @patch("src.services.verification.AlphaVantageClient")
    @patch("src.services.verification.get_settings")
    @patch("src.services.verification.get_supabase_admin")
    def test_av_revenue_none_claim_unverified(
        self, mock_admin_fn, mock_settings, mock_av_cls, mock_log_error
    ):
        """AV returns revenue=None → revenue claim is unverified, PE still works."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.alpha_vantage_api_key = "test-key"
        _setup_phase_b(admin)

        av_data = {**SAMPLE_AV_DATA, "revenue": None}
        mock_client = MagicMock()
        mock_client.get_fundamentals.return_value = av_data
        mock_av_cls.return_value = mock_client

        result = run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        assert result.results_count == 1  # only PE
        assert result.summary["unverified"] == 2  # revenue + opinion

    @patch("src.services.verification.log_error")
    @patch("src.services.verification.AlphaVantageClient")
    @patch("src.services.verification.get_settings")
    @patch("src.services.verification.get_supabase_admin")
    def test_verification_results_inserted_correctly(
        self, mock_admin_fn, mock_settings, mock_av_cls, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.alpha_vantage_api_key = "test-key"
        _setup_phase_b(admin)

        mock_client = MagicMock()
        mock_client.get_fundamentals.return_value = SAMPLE_AV_DATA
        mock_av_cls.return_value = mock_client

        run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        vr_table = admin.table("verification_results")
        insert_call = vr_table.insert.call_args[0][0]
        assert isinstance(insert_call, list)
        assert len(insert_call) == 2  # revenue + PE

        # Check structure of first row
        row = insert_call[0]
        assert row["claim_id"] == "claim-uuid-001"
        assert row["status"] in ("manual_check", "consistent", "disputed")
        assert "provider" in row["source_verification"]
        assert "deviation_pct" in row["source_verification"]

    @patch("src.services.verification.log_error")
    @patch("src.services.verification.AlphaVantageClient")
    @patch("src.services.verification.get_settings")
    @patch("src.services.verification.get_supabase_admin")
    def test_analysis_runs_verification_summary_updated(
        self, mock_admin_fn, mock_settings, mock_av_cls, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.alpha_vantage_api_key = "test-key"
        _setup_phase_b(admin)

        mock_client = MagicMock()
        mock_client.get_fundamentals.return_value = SAMPLE_AV_DATA
        mock_av_cls.return_value = mock_client

        run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        runs_table = admin.table("analysis_runs")
        update_call = runs_table.update.call_args[0][0]
        assert "verification" in update_call
        summary = update_call["verification"]
        assert "verified" in summary
        assert "consistent" in summary
        assert "unverified" in summary

    @patch("src.services.verification.log_error")
    @patch("src.services.verification.AlphaVantageClient")
    @patch("src.services.verification.get_settings")
    @patch("src.services.verification.get_supabase_admin")
    def test_db_insert_failure_returns_failed(
        self, mock_admin_fn, mock_settings, mock_av_cls, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.alpha_vantage_api_key = "test-key"
        _setup_phase_b(admin)

        mock_client = MagicMock()
        mock_client.get_fundamentals.return_value = SAMPLE_AV_DATA
        mock_av_cls.return_value = mock_client

        # Make verification_results insert fail
        vr_table = admin.table("verification_results")
        vr_table.insert.return_value.execute.side_effect = Exception("DB unavailable")

        result = run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        assert result.status == "failed"
        assert "database" in result.error_message.lower()
        # Ensure raw exception details are NOT in the error message
        assert "DB unavailable" not in result.error_message

    @patch("src.services.verification.log_error")
    @patch("src.services.verification.AlphaVantageClient")
    @patch("src.services.verification.get_settings")
    @patch("src.services.verification.get_supabase_admin")
    def test_summary_update_failure_still_completed(
        self, mock_admin_fn, mock_settings, mock_av_cls, mock_log_error
    ):
        """analysis_runs UPDATE failure is best-effort — doesn't break verification."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.alpha_vantage_api_key = "test-key"
        _setup_phase_b(admin)

        mock_client = MagicMock()
        mock_client.get_fundamentals.return_value = SAMPLE_AV_DATA
        mock_av_cls.return_value = mock_client

        runs_table = admin.table("analysis_runs")
        runs_table.update.return_value.eq.return_value.execute.side_effect = Exception("DB error")

        result = run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        assert result.status == "completed"

    @patch("src.services.verification.log_error")
    @patch("src.services.verification.AlphaVantageClient")
    @patch("src.services.verification.get_settings")
    @patch("src.services.verification.get_supabase_admin")
    def test_mixed_disputed_and_manual_check(
        self, mock_admin_fn, mock_settings, mock_av_cls, mock_log_error
    ):
        """Revenue disputed (>5%) + PE manual_check → has_blocking_disputed=True."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.alpha_vantage_api_key = "test-key"
        _setup_phase_b(admin)

        # Revenue will have >5% deviation → disputed
        av_data = {**SAMPLE_AV_DATA, "revenue": 420_000_000_000}
        mock_client = MagicMock()
        mock_client.get_fundamentals.return_value = av_data
        mock_av_cls.return_value = mock_client

        result = run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        assert result.summary["disputed"] == 1
        assert result.summary["has_blocking_disputed"] is True  # revenue is trade_critical

    @patch("src.services.verification.log_error")
    @patch("src.services.verification.AlphaVantageClient")
    @patch("src.services.verification.get_settings")
    @patch("src.services.verification.get_supabase_admin")
    def test_no_cross_checkable_claims_no_insert(
        self, mock_admin_fn, mock_settings, mock_av_cls, mock_log_error
    ):
        """All opinion claims → nothing to insert, all unverified."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.alpha_vantage_api_key = "test-key"
        _setup_phase_b(admin, claims=[SAMPLE_CLAIM_OPINION])

        mock_client = MagicMock()
        mock_client.get_fundamentals.return_value = SAMPLE_AV_DATA
        mock_av_cls.return_value = mock_client

        result = run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        assert result.status == "completed"
        assert result.results_count == 0
        assert result.summary["unverified"] == 1

        # No insert call should be made
        vr_table = admin.table("verification_results")
        vr_table.insert.assert_not_called()

    @patch("src.services.verification.log_error")
    @patch("src.services.verification.AlphaVantageClient")
    @patch("src.services.verification.get_settings")
    @patch("src.services.verification.get_supabase_admin")
    def test_av_error_logged(
        self, mock_admin_fn, mock_settings, mock_av_cls, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.alpha_vantage_api_key = "test-key"
        _setup_phase_b(admin)

        mock_client = MagicMock()
        mock_client.get_fundamentals.side_effect = DataProviderError("alpha_vantage", "timeout")
        mock_av_cls.return_value = mock_client

        run_verification(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        # Should have error logs for AV failures
        assert mock_log_error.call_count >= 1
