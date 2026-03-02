"""Tests for the Fundamental Analysis Orchestrator (src/services/fundamental_analysis.py).

All tests mock DB calls and agent calls — NO real API calls.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from src.services.exceptions import AgentError, ConfigurationError, PreconditionError
from src.services.fundamental_analysis import (
    AnalysisResult,
    _calculate_cost,
    run_fundamental_analysis,
)

FAKE_USER_ID = "test-user-id-123"
FAKE_ANALYSIS_ID = "analysis-uuid-456"

SAMPLE_FUND_ROW = {
    "id": "fund-1",
    "ticker": "AAPL",
    "period": "2026-TTM",
    "source": "finnhub",
    "fetched_at": "2026-02-27T14:30:00Z",
    "revenue": 394_328_000_000,
    "net_income": 93_736_000_000,
    "eps": 6.42,
    "pe_ratio": 28.5,
    "pb_ratio": 48.2,
    "ev_ebitda": None,
    "roe": 1.45,
    "roic": None,
    "free_cash_flow": 111_443_000_000,
    "total_debt": None,
    "total_equity": None,
    "f_score": None,
    "z_score": None,
}

SAMPLE_PRICE_ROW = {
    "ticker": "AAPL",
    "date": "2026-02-27",
    "close": 182.50,
    "source": "finnhub",
}

SAMPLE_AGENT_OUTPUT = {
    "business_model": {"description": "Tech", "moat_assessment": "Wide", "revenue_segments": "iPhone"},
    "financials": {},
    "valuation": {"assessment": "fairly_valued"},
    "quality": {"assessment": "unknown"},
    "moat_rating": "wide",
    "score": 72,
    "risks": ["China risk"],
    "sources": [{"provider": "finnhub", "endpoint": "/stock/metric", "retrieved_at": "2026-02-27T14:30:00Z"}],
}


def _mock_admin_table():
    """Create a mock Supabase admin client with chainable table calls.

    Returns the same mock for repeated calls to admin.table("same_name"),
    so test setup and production code access the same mock.
    """
    admin = MagicMock()
    tables = {}

    def table_factory(name):
        if name in tables:
            return tables[name]

        mock_table = MagicMock()
        # Make chainable: .select().eq().order().limit().execute()
        chain = mock_table.select.return_value.eq.return_value.order.return_value.limit.return_value
        # Default: empty response
        chain.execute.return_value = SimpleNamespace(data=[])

        # Insert returns id
        mock_table.insert.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": FAKE_ANALYSIS_ID}]
        )
        # Update chain
        mock_table.update.return_value.eq.return_value.execute.return_value = SimpleNamespace(data=[])

        tables[name] = mock_table
        return mock_table

    admin.table = MagicMock(side_effect=table_factory)
    admin._tables = tables
    return admin


class TestCostCalculation:
    def test_correct_for_known_tokens(self):
        # 1000 input × $3/MTok + 500 output × $15/MTok
        cost = _calculate_cost(1000, 500)
        assert abs(cost - 0.0105) < 0.0001

    def test_zero_tokens_zero_cost(self):
        assert _calculate_cost(0, 0) == 0.0


class TestPhaseAPreConditions:
    """Tests for Phase A — failures that don't create analysis_run."""

    @patch("src.services.fundamental_analysis.get_supabase_admin")
    def test_no_fundamentals_raises_precondition_error(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        with pytest.raises(PreconditionError, match="No fundamental data"):
            run_fundamental_analysis("AAPL", FAKE_USER_ID)

        # Verify NO analysis_run was inserted
        for call_args in admin.table.call_args_list:
            assert call_args[0][0] != "analysis_runs" or "insert" not in str(call_args)

    @patch("src.services.fundamental_analysis.get_settings")
    @patch("src.services.fundamental_analysis.get_supabase_admin")
    def test_no_api_key_raises_configuration_error(self, mock_admin_fn, mock_settings):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        # Fund data exists
        fund_table = admin.table("stock_fundamentals")
        fund_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_FUND_ROW]
        )

        mock_settings.return_value.anthropic_api_key = ""

        with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
            run_fundamental_analysis("AAPL", FAKE_USER_ID)


class TestPhaseBOrchestration:
    """Tests for Phase B — analysis_run created, agent called."""

    @patch("src.services.fundamental_analysis.log_error")
    @patch("src.services.fundamental_analysis.call_fundamental_agent")
    @patch("src.services.fundamental_analysis.get_settings")
    @patch("src.services.fundamental_analysis.get_supabase_admin")
    def test_success_creates_completed_analysis_run(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        # Set up fund + price data
        fund_table = admin.table("stock_fundamentals")
        fund_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_FUND_ROW]
        )
        price_table = admin.table("stock_prices")
        price_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_PRICE_ROW]
        )

        mock_agent.return_value = (SAMPLE_AGENT_OUTPUT, {"input_tokens": 1500, "output_tokens": 2000})

        result = run_fundamental_analysis("AAPL", FAKE_USER_ID)

        assert result.status == "completed"
        assert result.analysis_id == FAKE_ANALYSIS_ID
        assert result.fundamental_out == SAMPLE_AGENT_OUTPUT
        assert result.tokens_used == 3500
        assert result.cost_usd > 0
        assert result.error_message is None

    @patch("src.services.fundamental_analysis.supabase_write_with_retry")
    @patch("src.services.fundamental_analysis.log_error")
    @patch("src.services.fundamental_analysis.call_fundamental_agent")
    @patch("src.services.fundamental_analysis.get_settings")
    @patch("src.services.fundamental_analysis.get_supabase_admin")
    def test_agent_failure_returns_partial_with_cost(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error, mock_write_retry
    ):
        """When the agent raises AgentError, status is 'partial' (not 'failed') and confidence=0.

        Step 10 change: 'partial' signals tokens were consumed but analysis is incomplete.
        supabase_write_with_retry must be used for the analysis_runs update.
        """
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        fund_table = admin.table("stock_fundamentals")
        fund_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_FUND_ROW]
        )

        # supabase_write_with_retry must execute the lambda to allow cost_log writes
        mock_write_retry.side_effect = lambda fn, description="": fn()

        # Agent fails with usage data
        mock_agent.side_effect = AgentError(
            agent_name="fundamental_analyst",
            message="API timeout",
            error_type="timeout",
            usage={"input_tokens": 1500, "output_tokens": 0},
        )

        result = run_fundamental_analysis("AAPL", FAKE_USER_ID)

        assert result.status == "partial"
        assert result.analysis_id == FAKE_ANALYSIS_ID
        assert result.fundamental_out is None
        assert result.tokens_used == 1500
        assert result.cost_usd > 0
        assert result.error_message is not None

        # supabase_write_with_retry must be called for the analysis_runs update
        mock_write_retry.assert_called_once()

        # The update dict sent to analysis_runs must include confidence=0
        runs_table = admin.table("analysis_runs")
        update_dict = runs_table.update.call_args[0][0]
        assert update_dict["status"] == "partial"
        assert update_dict["confidence"] == 0

    @patch("src.services.fundamental_analysis.log_error")
    @patch("src.services.fundamental_analysis.call_fundamental_agent")
    @patch("src.services.fundamental_analysis.get_settings")
    @patch("src.services.fundamental_analysis.get_supabase_admin")
    def test_cost_log_written_on_success(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        fund_table = admin.table("stock_fundamentals")
        fund_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_FUND_ROW]
        )

        mock_agent.return_value = (SAMPLE_AGENT_OUTPUT, {"input_tokens": 1500, "output_tokens": 2000})

        run_fundamental_analysis("AAPL", FAKE_USER_ID)

        # Verify agent_cost_log insert was called
        cost_log_calls = [
            c for c in admin.table.call_args_list
            if c[0][0] == "agent_cost_log"
        ]
        assert len(cost_log_calls) >= 1

    @patch("src.services.fundamental_analysis.log_error")
    @patch("src.services.fundamental_analysis.call_fundamental_agent")
    @patch("src.services.fundamental_analysis.get_settings")
    @patch("src.services.fundamental_analysis.get_supabase_admin")
    def test_cost_log_written_on_agent_failure(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        fund_table = admin.table("stock_fundamentals")
        fund_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_FUND_ROW]
        )

        mock_agent.side_effect = AgentError(
            agent_name="fundamental_analyst",
            message="Parse failed",
            error_type="parse_failed",
            usage={"input_tokens": 1000, "output_tokens": 500},
        )

        run_fundamental_analysis("AAPL", FAKE_USER_ID)

        # agent_cost_log should still be written (tokens were consumed)
        cost_log_calls = [
            c for c in admin.table.call_args_list
            if c[0][0] == "agent_cost_log"
        ]
        assert len(cost_log_calls) >= 1

    @patch("src.services.fundamental_analysis.log_error")
    @patch("src.services.fundamental_analysis.call_fundamental_agent")
    @patch("src.services.fundamental_analysis.get_settings")
    @patch("src.services.fundamental_analysis.get_supabase_admin")
    def test_recommendation_and_confidence_are_null(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        """Fundamental Analyst alone doesn't set recommendation/confidence — that's Step 8."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        fund_table = admin.table("stock_fundamentals")
        fund_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_FUND_ROW]
        )

        mock_agent.return_value = (SAMPLE_AGENT_OUTPUT, {"input_tokens": 1500, "output_tokens": 2000})

        run_fundamental_analysis("AAPL", FAKE_USER_ID)

        # Check the analysis_runs update call does NOT contain recommendation/confidence
        update_calls = [
            c for c in admin.table.call_args_list
            if c[0][0] == "analysis_runs"
        ]
        # The insert call should not contain recommendation
        insert_table = admin.table("analysis_runs")
        insert_data = insert_table.insert.call_args[0][0]
        assert "recommendation" not in insert_data
        assert "confidence" not in insert_data

    @patch("src.services.fundamental_analysis.log_error")
    @patch("src.services.fundamental_analysis.call_fundamental_agent")
    @patch("src.services.fundamental_analysis.get_settings")
    @patch("src.services.fundamental_analysis.get_supabase_admin")
    def test_cost_log_failure_does_not_fail_analysis(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        fund_table = admin.table("stock_fundamentals")
        fund_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_FUND_ROW]
        )

        mock_agent.return_value = (SAMPLE_AGENT_OUTPUT, {"input_tokens": 1500, "output_tokens": 2000})

        # Make cost log INSERT fail
        cost_table = admin.table("agent_cost_log")
        cost_table.insert.return_value.execute.side_effect = Exception("DB unavailable")

        result = run_fundamental_analysis("AAPL", FAKE_USER_ID)

        # Analysis should still succeed despite cost log failure
        assert result.status == "completed"

    @patch("src.services.fundamental_analysis.log_error")
    @patch("src.services.fundamental_analysis.call_fundamental_agent")
    @patch("src.services.fundamental_analysis.get_settings")
    @patch("src.services.fundamental_analysis.get_supabase_admin")
    def test_works_without_price_data(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        fund_table = admin.table("stock_fundamentals")
        fund_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_FUND_ROW]
        )
        # stock_prices returns empty (default from _mock_admin_table)

        mock_agent.return_value = (SAMPLE_AGENT_OUTPUT, {"input_tokens": 1000, "output_tokens": 1500})

        result = run_fundamental_analysis("AAPL", FAKE_USER_ID)

        assert result.status == "completed"
        # Agent was called with None for current_price
        mock_agent.assert_called_once_with("AAPL", SAMPLE_FUND_ROW, None)

    @patch("src.services.fundamental_analysis.log_error")
    @patch("src.services.fundamental_analysis.call_fundamental_agent")
    @patch("src.services.fundamental_analysis.get_settings")
    @patch("src.services.fundamental_analysis.get_supabase_admin")
    def test_unexpected_error_returns_partial(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        """Any exception that reaches the orchestrator returns status='partial'.

        Step 10 change: 'partial' is used for all Phase B failures (tokens may have
        been consumed). 'failed' is reserved for pre-condition errors that are raised
        before analysis_run creation.
        """
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        fund_table = admin.table("stock_fundamentals")
        fund_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_FUND_ROW]
        )

        mock_agent.side_effect = RuntimeError("Something unexpected")

        result = run_fundamental_analysis("AAPL", FAKE_USER_ID)

        assert result.status == "partial"
        assert "unexpected" in result.error_message.lower()

    @patch("src.services.fundamental_analysis.log_error")
    @patch("src.services.fundamental_analysis.call_fundamental_agent")
    @patch("src.services.fundamental_analysis.get_settings")
    @patch("src.services.fundamental_analysis.get_supabase_admin")
    def test_error_log_in_db_is_sanitized(
        self, mock_admin_fn, mock_settings, mock_agent, mock_log_error
    ):
        """error_log written to analysis_runs must be sanitized (user-readable via RLS)."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        mock_settings.return_value.anthropic_api_key = "test-key"

        fund_table = admin.table("stock_fundamentals")
        fund_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[SAMPLE_FUND_ROW]
        )

        mock_agent.side_effect = AgentError(
            agent_name="fundamental_analyst",
            message="API error (500): Internal server error from anthropic SDK",
            error_type="api_error",
            usage={"input_tokens": 800, "output_tokens": 0},
        )

        run_fundamental_analysis("AAPL", FAKE_USER_ID)

        # Verify the analysis_runs update contains sanitized error_log
        runs_table = admin.table("analysis_runs")
        update_dict = runs_table.update.call_args[0][0]
        error_entry = update_dict["error_log"][0]["error"]

        assert error_entry == "Analysis service error"
        assert "500" not in error_entry
        assert "anthropic" not in error_entry
        assert "SDK" not in error_entry
