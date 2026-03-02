"""Tests for the Claim Extraction Orchestrator (src/services/claim_extraction.py).

All tests mock DB calls and agent calls — NO real API calls.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agents.claim_extractor import MODEL_HAIKU, MODEL_SONNET
from src.services.claim_extraction import (
    ClaimExtractionResult,
    _build_claim_id,
    _build_source_primary,
    _determine_required_tier,
    _determine_tier,
    _determine_trade_critical,
    _post_process_claims,
    run_claim_extraction,
)
from src.services.exceptions import AgentError, ConfigurationError, PreconditionError

FAKE_USER_ID = "test-user-id-123"
FAKE_ANALYSIS_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

SAMPLE_ANALYSIS_ROW = {
    "id": FAKE_ANALYSIS_ID,
    "user_id": FAKE_USER_ID,
    "ticker": "AAPL",
    "status": "completed",
    "fundamental_out": {
        "financials": {
            "revenue": {
                "value": 394_328_000_000,
                "unit": "USD",
                "source": "finnhub",
                "period": "TTM",
                "retrieved_at": "2026-02-27T14:30:00Z",
            }
        },
        "score": 72,
    },
    "total_tokens": 3500,
    "total_cost_usd": 0.0345,
}

SAMPLE_RAW_CLAIMS = [
    {
        "claim_text": "AAPL Revenue TTM: $394.3B",
        "claim_type": "number",
        "value": 394_328_000_000,
        "unit": "USD",
        "ticker": "AAPL",
        "period": "TTM",
        "source": "finnhub",
        "retrieved_at": "2026-02-27T14:30:00Z",
    },
    {
        "claim_text": "Wide moat due to ecosystem lock-in",
        "claim_type": "opinion",
        "value": None,
        "unit": "text",
        "ticker": "AAPL",
        "period": "current",
        "source": "finnhub",
        "retrieved_at": "2026-02-27T14:30:00Z",
    },
]

SAMPLE_USAGE = {
    "input_tokens": 800,
    "output_tokens": 500,
    "cost_usd": 0.0026,
    "model_used": MODEL_HAIKU,
}


def _mock_admin_table():
    """Create a mock Supabase admin client with chainable table calls."""
    admin = MagicMock()
    tables = {}

    def table_factory(name):
        if name in tables:
            return tables[name]

        mock_table = MagicMock()
        # Make chainable: .select().eq().execute()
        chain = mock_table.select.return_value.eq.return_value
        chain.execute.return_value = SimpleNamespace(data=[])

        # Also support .order().limit() chain
        chain.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[])

        # Insert returns data
        mock_table.insert.return_value.execute.return_value = SimpleNamespace(data=[])
        # Update chain
        mock_table.update.return_value.eq.return_value.execute.return_value = SimpleNamespace(data=[])

        tables[name] = mock_table
        return mock_table

    admin.table = MagicMock(side_effect=table_factory)
    admin._tables = tables
    return admin


# --- Deterministic Post-Processing Tests (no mocks needed) ---


class TestDetermineTradeCritical:
    def test_revenue_is_trade_critical(self):
        assert _determine_trade_critical("AAPL Revenue TTM: $394.3B") is True

    def test_eps_is_trade_critical(self):
        assert _determine_trade_critical("AAPL EPS TTM: $6.42") is True

    def test_pe_ratio_is_trade_critical(self):
        assert _determine_trade_critical("P/E Ratio: 28.5") is True

    def test_net_income_is_trade_critical(self):
        assert _determine_trade_critical("Net Income: $93.7B") is True

    def test_free_cash_flow_is_trade_critical(self):
        assert _determine_trade_critical("Free Cash Flow: $111.4B") is True

    def test_fcf_is_trade_critical(self):
        assert _determine_trade_critical("FCF Yield: 3.2%") is True

    def test_ev_ebitda_is_trade_critical(self):
        assert _determine_trade_critical("EV/EBITDA: 22.1") is True

    def test_moat_is_not_trade_critical(self):
        assert _determine_trade_critical("Wide moat due to ecosystem lock-in") is False

    def test_risk_is_not_trade_critical(self):
        assert _determine_trade_critical("China geopolitical risk") is False

    def test_case_insensitive(self):
        assert _determine_trade_critical("aapl REVENUE ttm") is True


class TestDetermineTier:
    def test_finnhub_is_tier_b(self):
        assert _determine_tier("finnhub") == "B"

    def test_alpha_vantage_is_tier_b(self):
        assert _determine_tier("alpha_vantage") == "B"

    def test_sec_edgar_is_tier_a(self):
        assert _determine_tier("sec_edgar") == "A"

    def test_fred_is_tier_a(self):
        assert _determine_tier("fred") == "A"

    def test_calculated_is_tier_c(self):
        assert _determine_tier("calculated") == "C"

    def test_unknown_source_is_tier_c(self):
        assert _determine_tier("yahoo_finance") == "C"


class TestDetermineRequiredTier:
    def test_trade_critical_needs_tier_a(self):
        assert _determine_required_tier(True, "number") == "A"

    def test_trade_critical_ratio_needs_tier_a(self):
        assert _determine_required_tier(True, "ratio") == "A"

    def test_non_critical_number_needs_tier_b(self):
        assert _determine_required_tier(False, "number") == "B"

    def test_non_critical_ratio_needs_tier_b(self):
        assert _determine_required_tier(False, "ratio") == "B"

    def test_opinion_needs_tier_c(self):
        assert _determine_required_tier(False, "opinion") == "C"

    def test_forecast_needs_tier_c(self):
        assert _determine_required_tier(False, "forecast") == "C"

    def test_event_needs_tier_c(self):
        assert _determine_required_tier(False, "event") == "C"


class TestBuildClaimId:
    def test_format_with_padding(self):
        assert _build_claim_id("abc-123", 0) == "abc-123_001"
        assert _build_claim_id("abc-123", 9) == "abc-123_010"
        assert _build_claim_id("abc-123", 99) == "abc-123_100"


class TestBuildSourcePrimary:
    def test_finnhub_source(self):
        result = _build_source_primary("finnhub", "2026-02-27T14:30:00Z")
        assert result == {
            "provider": "finnhub",
            "endpoint": "/stock/metric",
            "retrieved_at": "2026-02-27T14:30:00Z",
        }

    def test_unknown_source_endpoint(self):
        result = _build_source_primary("yahoo", "2026-02-27T14:30:00Z")
        assert result["endpoint"] == "unknown"


class TestPostProcessClaims:
    def test_adds_all_required_fields(self):
        processed = _post_process_claims(SAMPLE_RAW_CLAIMS, FAKE_ANALYSIS_ID, "AAPL")

        claim = processed[0]
        assert claim["analysis_id"] == FAKE_ANALYSIS_ID
        assert claim["claim_id"] == f"{FAKE_ANALYSIS_ID}_001"
        assert claim["tier"] == "B"
        assert claim["required_tier"] == "A"  # revenue is trade-critical
        assert claim["trade_critical"] is True
        assert claim["source_primary"]["provider"] == "finnhub"

    def test_forces_value_null_for_opinion(self):
        raw = [
            {
                "claim_text": "Wide moat",
                "claim_type": "opinion",
                "value": 42,  # LLM returned a value for opinion — should be forced to None
                "unit": "text",
                "ticker": "AAPL",
                "period": "current",
                "source": "finnhub",
                "retrieved_at": "2026-02-27T14:30:00Z",
            }
        ]
        processed = _post_process_claims(raw, FAKE_ANALYSIS_ID, "AAPL")
        assert processed[0]["value"] is None

    def test_preserves_value_for_number(self):
        processed = _post_process_claims(SAMPLE_RAW_CLAIMS, FAKE_ANALYSIS_ID, "AAPL")
        assert processed[0]["value"] == 394_328_000_000

    def test_ticker_uppercased(self):
        processed = _post_process_claims(SAMPLE_RAW_CLAIMS, FAKE_ANALYSIS_ID, "aapl")
        assert processed[0]["ticker"] == "AAPL"

    def test_sequential_claim_ids(self):
        processed = _post_process_claims(SAMPLE_RAW_CLAIMS, FAKE_ANALYSIS_ID, "AAPL")
        assert processed[0]["claim_id"] == f"{FAKE_ANALYSIS_ID}_001"
        assert processed[1]["claim_id"] == f"{FAKE_ANALYSIS_ID}_002"


# --- Phase A Pre-Condition Tests ---


class TestPhaseAPreConditions:
    @patch("src.services.claim_extraction.get_supabase_admin")
    def test_analysis_not_found_raises_precondition_error(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        with pytest.raises(PreconditionError, match="Analysis run not found"):
            run_claim_extraction(FAKE_ANALYSIS_ID, FAKE_USER_ID)

    @patch("src.services.claim_extraction.get_supabase_admin")
    def test_wrong_user_raises_precondition_error(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        # Analysis exists but belongs to different user
        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{**SAMPLE_ANALYSIS_ROW, "user_id": "different-user-id"}]
        )

        with pytest.raises(PreconditionError, match="Analysis run not found"):
            run_claim_extraction(FAKE_ANALYSIS_ID, FAKE_USER_ID)

    @patch("src.services.claim_extraction.get_supabase_admin")
    def test_no_fundamental_out_raises_precondition_error(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{**SAMPLE_ANALYSIS_ROW, "fundamental_out": None}]
        )

        with pytest.raises(PreconditionError, match="No fundamental analysis output"):
            run_claim_extraction(FAKE_ANALYSIS_ID, FAKE_USER_ID)

    @patch("src.services.claim_extraction.get_settings")
    @patch("src.services.claim_extraction.get_supabase_admin")
    def test_no_api_key_raises_configuration_error(self, mock_admin_fn, mock_settings):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_ANALYSIS_ROW]
        )

        mock_settings.return_value.anthropic_api_key = ""

        with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
            run_claim_extraction(FAKE_ANALYSIS_ID, FAKE_USER_ID)


# --- Phase B Orchestration Tests ---


class TestPhaseBOrchestration:
    @patch("src.services.claim_extraction.log_error")
    @patch("src.services.claim_extraction.call_claim_extractor")
    @patch("src.services.claim_extraction.get_settings")
    @patch("src.services.claim_extraction.get_supabase_admin")
    def test_success_returns_completed_with_claims(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_ANALYSIS_ROW]
        )

        mock_agent.return_value = (SAMPLE_RAW_CLAIMS, SAMPLE_USAGE)

        result = run_claim_extraction(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        assert result.status == "completed"
        assert result.analysis_id == FAKE_ANALYSIS_ID
        assert result.claims_count == 2
        assert result.claims is not None
        assert len(result.claims) == 2
        assert result.tokens_used == 1300  # 800 + 500
        assert result.cost_usd > 0
        assert result.error_message is None

    @patch("src.services.claim_extraction.log_error")
    @patch("src.services.claim_extraction.call_claim_extractor")
    @patch("src.services.claim_extraction.get_settings")
    @patch("src.services.claim_extraction.get_supabase_admin")
    def test_claims_written_to_db_via_batch_insert(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_ANALYSIS_ROW]
        )

        mock_agent.return_value = (SAMPLE_RAW_CLAIMS, SAMPLE_USAGE)

        run_claim_extraction(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        # Verify claims table insert was called with a list
        claims_table = admin.table("claims")
        insert_call = claims_table.insert.call_args[0][0]
        assert isinstance(insert_call, list)
        assert len(insert_call) == 2
        assert insert_call[0]["claim_id"] == f"{FAKE_ANALYSIS_ID}_001"

    @patch("src.services.claim_extraction.log_error")
    @patch("src.services.claim_extraction.call_claim_extractor")
    @patch("src.services.claim_extraction.get_settings")
    @patch("src.services.claim_extraction.get_supabase_admin")
    def test_agent_cost_log_written_with_all_fields(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_ANALYSIS_ROW]
        )

        mock_agent.return_value = (SAMPLE_RAW_CLAIMS, SAMPLE_USAGE)

        run_claim_extraction(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        cost_table = admin.table("agent_cost_log")
        cost_data = cost_table.insert.call_args[0][0]
        assert cost_data["agent_name"] == "claim_extractor"
        assert cost_data["model"] == MODEL_HAIKU
        assert cost_data["tier"] == "light"
        assert cost_data["effort"] == "low"
        assert cost_data["input_tokens"] == 800
        assert cost_data["output_tokens"] == 500
        assert cost_data["cache_read_tokens"] == 0
        assert cost_data["fallback_from"] is None
        assert cost_data["degraded"] is False

    @patch("src.services.claim_extraction.log_error")
    @patch("src.services.claim_extraction.call_claim_extractor")
    @patch("src.services.claim_extraction.get_settings")
    @patch("src.services.claim_extraction.get_supabase_admin")
    def test_sonnet_fallback_cost_log(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_ANALYSIS_ROW]
        )

        sonnet_usage = {**SAMPLE_USAGE, "model_used": MODEL_SONNET}
        mock_agent.return_value = (SAMPLE_RAW_CLAIMS, sonnet_usage)

        run_claim_extraction(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        cost_table = admin.table("agent_cost_log")
        cost_data = cost_table.insert.call_args[0][0]
        assert cost_data["model"] == MODEL_SONNET
        assert cost_data["tier"] == "standard"
        assert cost_data["fallback_from"] == MODEL_HAIKU

    @patch("src.services.claim_extraction.log_error")
    @patch("src.services.claim_extraction.call_claim_extractor")
    @patch("src.services.claim_extraction.get_settings")
    @patch("src.services.claim_extraction.get_supabase_admin")
    def test_agent_failure_returns_failed_with_cost(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_ANALYSIS_ROW]
        )

        mock_agent.side_effect = AgentError(
            agent_name="claim_extractor",
            message="All extraction attempts failed",
            error_type="extraction_failed",
            usage={"input_tokens": 2400, "output_tokens": 300, "cost_usd": 0.003, "model_used": MODEL_HAIKU},
        )

        result = run_claim_extraction(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        assert result.status == "failed"
        assert result.claims is None
        assert result.tokens_used == 2700
        assert result.cost_usd > 0
        assert result.error_message is not None

    @patch("src.services.claim_extraction.log_error")
    @patch("src.services.claim_extraction.call_claim_extractor")
    @patch("src.services.claim_extraction.get_settings")
    @patch("src.services.claim_extraction.get_supabase_admin")
    def test_agent_failure_logs_to_error_log(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_ANALYSIS_ROW]
        )

        mock_agent.side_effect = AgentError(
            agent_name="claim_extractor",
            message="Timeout",
            error_type="timeout",
            usage={"input_tokens": 800, "output_tokens": 0, "cost_usd": 0.001, "model_used": MODEL_HAIKU},
        )

        run_claim_extraction(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        mock_log_error.assert_called_once_with(
            component="claim_extractor",
            error_type="timeout",
            message="[claim_extractor] Timeout",
            analysis_id=FAKE_ANALYSIS_ID,
        )

    @patch("src.services.claim_extraction.log_error")
    @patch("src.services.claim_extraction.call_claim_extractor")
    @patch("src.services.claim_extraction.get_settings")
    @patch("src.services.claim_extraction.get_supabase_admin")
    def test_analysis_runs_cost_updated_cumulatively(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_ANALYSIS_ROW]
        )

        mock_agent.return_value = (SAMPLE_RAW_CLAIMS, SAMPLE_USAGE)

        run_claim_extraction(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        # Verify update was called on analysis_runs with cumulative cost
        update_call = runs_table.update.call_args[0][0]
        assert update_call["total_tokens"] == 3500 + 1300  # existing + new
        assert update_call["total_cost_usd"] == pytest.approx(0.0345 + 0.0026)

    @patch("src.services.claim_extraction.log_error")
    @patch("src.services.claim_extraction.call_claim_extractor")
    @patch("src.services.claim_extraction.get_settings")
    @patch("src.services.claim_extraction.get_supabase_admin")
    def test_cost_log_failure_does_not_break_extraction(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_ANALYSIS_ROW]
        )

        mock_agent.return_value = (SAMPLE_RAW_CLAIMS, SAMPLE_USAGE)

        # Make cost log fail
        cost_table = admin.table("agent_cost_log")
        cost_table.insert.return_value.execute.side_effect = Exception("DB unavailable")

        result = run_claim_extraction(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        assert result.status == "completed"

    @patch("src.services.claim_extraction.log_error")
    @patch("src.services.claim_extraction.call_claim_extractor")
    @patch("src.services.claim_extraction.get_settings")
    @patch("src.services.claim_extraction.get_supabase_admin")
    def test_unexpected_error_returns_failed(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_ANALYSIS_ROW]
        )

        mock_agent.side_effect = RuntimeError("Something unexpected")

        result = run_claim_extraction(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        assert result.status == "failed"
        assert "unexpected" in result.error_message.lower()


class TestWriteRetryIntegration:
    """Tests for supabase_write_with_retry integration in claim_extraction."""

    @patch("src.services.claim_extraction.supabase_write_with_retry", return_value=True)
    @patch("src.services.claim_extraction.log_error")
    @patch("src.services.claim_extraction.call_claim_extractor")
    @patch("src.services.claim_extraction.get_settings")
    @patch("src.services.claim_extraction.get_supabase_admin")
    def test_claims_insert_uses_write_retry(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error, mock_write_retry
    ):
        """Claims INSERT must go through supabase_write_with_retry, not raw insert."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_ANALYSIS_ROW]
        )

        mock_agent.return_value = (SAMPLE_RAW_CLAIMS, SAMPLE_USAGE)

        result = run_claim_extraction(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        assert result.status == "completed"
        mock_write_retry.assert_called_once()
        # Verify description contains analysis_id for debugging
        _, kwargs = mock_write_retry.call_args
        assert FAKE_ANALYSIS_ID in kwargs.get("description", "")

    @patch("src.services.claim_extraction.supabase_write_with_retry", return_value=False)
    @patch("src.services.claim_extraction.log_error")
    @patch("src.services.claim_extraction.call_claim_extractor")
    @patch("src.services.claim_extraction.get_settings")
    @patch("src.services.claim_extraction.get_supabase_admin")
    def test_write_retry_failure_returns_failed(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error, mock_write_retry
    ):
        """When supabase_write_with_retry returns False, result is failed with 0 claims."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        runs_table = admin.table("analysis_runs")
        runs_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_ANALYSIS_ROW]
        )

        mock_agent.return_value = (SAMPLE_RAW_CLAIMS, SAMPLE_USAGE)

        result = run_claim_extraction(FAKE_ANALYSIS_ID, FAKE_USER_ID)

        assert result.status == "failed"
        assert result.claims_count == 0
        assert result.error_message == "Failed to write claims to DB"
        # Tokens were consumed even though write failed
        assert result.tokens_used == 1300
        assert result.cost_usd > 0
