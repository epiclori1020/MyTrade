"""Tests for the Fundamental Analyst Agent (src/agents/fundamental.py).

All tests mock the Anthropic client — NO real API calls.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agents.fundamental import (
    SYSTEM_PROMPT,
    FundamentalAnalysis,
    _build_user_prompt,
    _get_client,
    call_fundamental_agent,
)
from src.services.budget_manager import ModelRouting
from src.services.exceptions import AgentError, BudgetExhaustedError


# --- Test data fixtures ---

SAMPLE_FUNDAMENTALS = {
    "ticker": "AAPL",
    "period": "2026-TTM",
    "source": "finnhub",
    "fetched_at": "2026-02-27T14:30:00Z",
    "revenue": 394_328_000_000,
    "net_income": 93_736_000_000,
    "free_cash_flow": 111_443_000_000,
    "eps": 6.42,
    "pe_ratio": 28.5,
    "pb_ratio": 48.2,
    "ev_ebitda": None,
    "roe": 1.45,
    "roic": None,
    "f_score": None,
    "z_score": None,
}

SAMPLE_PRICE = {
    "ticker": "AAPL",
    "date": "2026-02-27",
    "close": 182.50,
    "source": "finnhub",
}

SAMPLE_ANALYSIS_OUTPUT = FundamentalAnalysis(
    business_model={
        "description": "Consumer electronics and services",
        "moat_assessment": "Wide moat due to ecosystem lock-in",
        "revenue_segments": "iPhone, Mac, iPad, Services, Wearables",
    },
    financials={
        "revenue": {"value": 394328000000, "unit": "USD", "source": "finnhub", "period": "TTM", "retrieved_at": "2026-02-27T14:30:00Z"},
        "net_income": {"value": 93736000000, "unit": "USD", "source": "finnhub", "period": "TTM", "retrieved_at": "2026-02-27T14:30:00Z"},
        "free_cash_flow": {"value": 111443000000, "unit": "USD", "source": "finnhub", "period": "TTM", "retrieved_at": "2026-02-27T14:30:00Z"},
        "eps": {"value": 6.42, "unit": "USD", "source": "finnhub", "period": "TTM", "retrieved_at": "2026-02-27T14:30:00Z"},
        "roe": {"value": 1.45, "unit": "ratio", "source": "finnhub", "period": "TTM", "retrieved_at": "2026-02-27T14:30:00Z"},
        "roic": None,
    },
    valuation={
        "pe_ratio": {"value": 28.5, "unit": "ratio", "source": "finnhub", "period": "TTM", "retrieved_at": "2026-02-27T14:30:00Z"},
        "pb_ratio": {"value": 48.2, "unit": "ratio", "source": "finnhub", "period": "TTM", "retrieved_at": "2026-02-27T14:30:00Z"},
        "ev_ebitda": None,
        "fcf_yield": None,
        "assessment": "fairly_valued — P/E of 28.5 reasonable for quality large cap",
    },
    quality={
        "f_score": None,
        "z_score": None,
        "assessment": "Quality metrics unavailable — cannot assess",
    },
    moat_rating="wide",
    score=72,
    risks=["Smartphone market saturation", "China geopolitical risk"],
    sources=[
        {"provider": "finnhub", "endpoint": "/stock/metric", "retrieved_at": "2026-02-27T14:30:00Z"},
    ],
)


def _make_mock_response(parsed_output=None, stop_reason="end_turn", input_tokens=1500, output_tokens=2000):
    """Create a mock ParsedMessage response."""
    resp = MagicMock()
    resp.parsed_output = parsed_output
    resp.stop_reason = stop_reason
    resp.usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return resp


# --- System Prompt Tests ---


class TestSystemPrompt:
    def test_prompt_is_german(self):
        assert "Equity-Research-Analyst" in SYSTEM_PROMPT

    def test_prompt_requires_source_attribution(self):
        assert "{value, unit, source, period, retrieved_at}" in SYSTEM_PROMPT

    def test_prompt_forbids_inventing_numbers(self):
        assert "Erfinde KEINE Zahlen" in SYSTEM_PROMPT

    def test_prompt_mentions_ttm(self):
        assert "TTM" in SYSTEM_PROMPT


# --- User Prompt Tests ---


class TestBuildUserPrompt:
    def test_formats_fundamentals_correctly(self):
        prompt = _build_user_prompt("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)
        assert "Ticker: AAPL" in prompt
        assert "Periode: 2026-TTM" in prompt
        assert "Quelle: finnhub" in prompt
        assert "Endpoint: /stock/metric" in prompt
        assert "EPS: 6.42" in prompt
        assert "ROE: 1.45 (145%)" in prompt

    def test_marks_null_fields_as_unavailable(self):
        prompt = _build_user_prompt("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)
        assert "EV/EBITDA: NICHT VERFÜGBAR" in prompt
        assert "ROIC: NICHT VERFÜGBAR" in prompt
        assert "F-Score: NICHT VERFÜGBAR" in prompt

    def test_handles_missing_price(self):
        prompt = _build_user_prompt("AAPL", SAMPLE_FUNDAMENTALS, None)
        assert "NICHT VERFÜGBAR — Bewertungskennzahlen" in prompt

    def test_includes_price_when_available(self):
        prompt = _build_user_prompt("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)
        assert "Kurs: 182.5 USD" in prompt
        assert "Datum: 2026-02-27" in prompt

    def test_alpha_vantage_endpoint(self):
        av_fundamentals = {**SAMPLE_FUNDAMENTALS, "source": "alpha_vantage"}
        prompt = _build_user_prompt("MSFT", av_fundamentals, None)
        assert "Endpoint: OVERVIEW" in prompt


# --- LLM Call Tests ---


def _make_repaired_model():
    """Return a mock FundamentalAnalysis instance with a working model_dump()."""
    mock_model = MagicMock(spec=FundamentalAnalysis)
    mock_model.model_dump.return_value = SAMPLE_ANALYSIS_OUTPUT.model_dump()
    return mock_model


class TestCallFundamentalAgent:
    @patch("src.agents.fundamental.get_model_for_tier")
    @patch("src.agents.fundamental._get_client")
    def test_success_returns_dict_usage_and_routing(self, mock_get_client, mock_route):
        mock_route.return_value = ModelRouting(
            model_id="claude-sonnet-4-6", tier="standard", degraded=False, original_tier="standard"
        )
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.return_value = _make_mock_response(
            parsed_output=SAMPLE_ANALYSIS_OUTPUT
        )

        result, usage, routing = call_fundamental_agent("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)

        assert isinstance(result, dict)
        assert result["score"] == 72
        assert result["moat_rating"] == "wide"
        assert usage["input_tokens"] == 1500
        assert usage["output_tokens"] == 2000
        assert routing.tier == "standard"
        assert routing.degraded is False

    @patch("src.agents.fundamental.get_model_for_tier")
    @patch("src.agents.fundamental._get_client")
    def test_output_validates_against_schema(self, mock_get_client, mock_route):
        mock_route.return_value = ModelRouting(
            model_id="claude-sonnet-4-6", tier="standard", degraded=False, original_tier="standard"
        )
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.return_value = _make_mock_response(
            parsed_output=SAMPLE_ANALYSIS_OUTPUT
        )

        result, _, _ = call_fundamental_agent("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)

        # Validate round-trips through Pydantic
        validated = FundamentalAnalysis.model_validate(result)
        assert validated.score == 72
        assert len(validated.sources) == 1

    @patch("src.agents.fundamental.get_model_for_tier")
    @patch("src.agents.fundamental.try_repair_json")
    @patch("src.agents.fundamental.extract_raw_text")
    @patch("src.agents.fundamental._get_client")
    def test_raises_agent_error_on_none_parsed_output(
        self, mock_get_client, mock_extract, mock_repair, mock_route
    ):
        """When both LLM attempts and both JSON repairs fail, AgentError is raised.

        Tokens from both attempts (1500 each) must be accumulated in usage.
        """
        mock_route.return_value = ModelRouting(
            model_id="claude-sonnet-4-6", tier="standard", degraded=False, original_tier="standard"
        )
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        # Both attempts return parsed_output=None
        mock_client.messages.parse.return_value = _make_mock_response(
            parsed_output=None, stop_reason="max_tokens", input_tokens=1500, output_tokens=200
        )
        # Repair also fails for both attempts
        mock_extract.return_value = "malformed"
        mock_repair.return_value = None

        with pytest.raises(AgentError) as exc_info:
            call_fundamental_agent("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)

        assert exc_info.value.error_type == "parse_failed"
        # Two LLM calls (attempt 1 + retry): 1500 + 1500 = 3000 input tokens
        assert exc_info.value.usage["input_tokens"] == 3000

    @patch("src.agents.fundamental.get_model_for_tier")
    @patch("src.agents.fundamental._get_client")
    def test_raises_agent_error_on_api_timeout(self, mock_get_client, mock_route):
        import anthropic

        mock_route.return_value = ModelRouting(
            model_id="claude-sonnet-4-6", tier="standard", degraded=False, original_tier="standard"
        )
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.side_effect = anthropic.APITimeoutError(request=MagicMock())

        with pytest.raises(AgentError) as exc_info:
            call_fundamental_agent("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)

        assert exc_info.value.error_type == "timeout"

    @patch("src.agents.fundamental.get_model_for_tier")
    @patch("src.agents.fundamental._get_client")
    def test_raises_agent_error_on_api_error(self, mock_get_client, mock_route):
        import anthropic

        mock_route.return_value = ModelRouting(
            model_id="claude-sonnet-4-6", tier="standard", degraded=False, original_tier="standard"
        )
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.side_effect = anthropic.APIStatusError(
            message="Server error",
            response=MagicMock(status_code=500),
            body={"error": {"message": "Server error"}},
        )

        with pytest.raises(AgentError) as exc_info:
            call_fundamental_agent("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)

        assert exc_info.value.error_type == "api_error"

    def test_budget_exhausted_propagates(self):
        """BudgetExhaustedError from get_model_for_tier must propagate."""
        with patch("src.agents.fundamental.get_model_for_tier") as mock_route:
            mock_route.side_effect = BudgetExhaustedError("Budget exhausted")
            with pytest.raises(BudgetExhaustedError):
                call_fundamental_agent("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)


class TestCallFundamentalAgentJsonRepair:
    """Tests for the JSON repair + retry flows inside call_fundamental_agent."""

    @patch("src.agents.fundamental.get_model_for_tier")
    @patch("src.agents.fundamental.try_repair_json")
    @patch("src.agents.fundamental.extract_raw_text")
    @patch("src.agents.fundamental._get_client")
    def test_json_repair_succeeds_attempt1(
        self, mock_get_client, mock_extract, mock_repair, mock_route
    ):
        mock_route.return_value = ModelRouting(
            model_id="claude-sonnet-4-6", tier="standard", degraded=False, original_tier="standard"
        )
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.return_value = _make_mock_response(
            parsed_output=None, stop_reason="max_tokens", input_tokens=1500, output_tokens=200
        )

        mock_extract.return_value = '{"business_model": {}}'
        mock_repair.return_value = _make_repaired_model()

        result, usage, routing = call_fundamental_agent("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)

        mock_client.messages.parse.assert_called_once()
        assert result["score"] == 72
        assert usage["input_tokens"] == 1500
        assert usage["output_tokens"] == 200

    @patch("src.agents.fundamental.get_model_for_tier")
    @patch("src.agents.fundamental.try_repair_json")
    @patch("src.agents.fundamental.extract_raw_text")
    @patch("src.agents.fundamental._get_client")
    def test_retry_succeeds_after_repair_fails(
        self, mock_get_client, mock_extract, mock_repair, mock_route
    ):
        mock_route.return_value = ModelRouting(
            model_id="claude-sonnet-4-6", tier="standard", degraded=False, original_tier="standard"
        )
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.messages.parse.side_effect = [
            _make_mock_response(parsed_output=None, input_tokens=1500, output_tokens=200),
            _make_mock_response(parsed_output=SAMPLE_ANALYSIS_OUTPUT, input_tokens=1600, output_tokens=2100),
        ]

        mock_extract.return_value = "malformed json"
        mock_repair.return_value = None

        result, usage, _ = call_fundamental_agent("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)

        assert mock_client.messages.parse.call_count == 2
        assert result["score"] == 72
        assert usage["input_tokens"] == 1500 + 1600
        assert usage["output_tokens"] == 200 + 2100

    @patch("src.agents.fundamental.get_model_for_tier")
    @patch("src.agents.fundamental.try_repair_json")
    @patch("src.agents.fundamental.extract_raw_text")
    @patch("src.agents.fundamental._get_client")
    def test_json_repair_succeeds_attempt2(
        self, mock_get_client, mock_extract, mock_repair, mock_route
    ):
        mock_route.return_value = ModelRouting(
            model_id="claude-sonnet-4-6", tier="standard", degraded=False, original_tier="standard"
        )
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.messages.parse.side_effect = [
            _make_mock_response(parsed_output=None, input_tokens=1500, output_tokens=200),
            _make_mock_response(parsed_output=None, input_tokens=1600, output_tokens=300),
        ]

        mock_extract.return_value = '{"business_model": {}}'
        mock_repair.side_effect = [None, _make_repaired_model()]

        result, usage, _ = call_fundamental_agent("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)

        assert mock_client.messages.parse.call_count == 2
        assert result["score"] == 72
        assert usage["input_tokens"] == 1500 + 1600
        assert usage["output_tokens"] == 200 + 300

    @patch("src.agents.fundamental.get_model_for_tier")
    @patch("src.agents.fundamental.try_repair_json")
    @patch("src.agents.fundamental.extract_raw_text")
    @patch("src.agents.fundamental._get_client")
    def test_all_attempts_and_repairs_fail(
        self, mock_get_client, mock_extract, mock_repair, mock_route
    ):
        mock_route.return_value = ModelRouting(
            model_id="claude-sonnet-4-6", tier="standard", degraded=False, original_tier="standard"
        )
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.messages.parse.side_effect = [
            _make_mock_response(parsed_output=None, input_tokens=1500, output_tokens=200),
            _make_mock_response(parsed_output=None, input_tokens=1600, output_tokens=300),
        ]

        mock_extract.return_value = "malformed"
        mock_repair.return_value = None

        with pytest.raises(AgentError) as exc_info:
            call_fundamental_agent("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)

        assert exc_info.value.error_type == "parse_failed"
        assert exc_info.value.usage["input_tokens"] == 1500 + 1600
        assert exc_info.value.usage["output_tokens"] == 200 + 300


# --- Client Singleton Tests ---


class TestGetClient:
    def test_raises_value_error_when_no_api_key(self):
        _get_client.cache_clear()
        try:
            with patch("src.agents.fundamental.get_settings") as mock_settings:
                mock_settings.return_value.anthropic_api_key = ""
                with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not configured"):
                    _get_client()
        finally:
            _get_client.cache_clear()
