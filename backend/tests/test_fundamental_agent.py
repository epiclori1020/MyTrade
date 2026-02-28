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
from src.services.exceptions import AgentError


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


class TestCallFundamentalAgent:
    @patch("src.agents.fundamental._get_client")
    def test_success_returns_dict_and_usage(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.return_value = _make_mock_response(
            parsed_output=SAMPLE_ANALYSIS_OUTPUT
        )

        result, usage = call_fundamental_agent("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)

        assert isinstance(result, dict)
        assert result["score"] == 72
        assert result["moat_rating"] == "wide"
        assert usage["input_tokens"] == 1500
        assert usage["output_tokens"] == 2000

    @patch("src.agents.fundamental._get_client")
    def test_output_validates_against_schema(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.return_value = _make_mock_response(
            parsed_output=SAMPLE_ANALYSIS_OUTPUT
        )

        result, _ = call_fundamental_agent("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)

        # Validate round-trips through Pydantic
        validated = FundamentalAnalysis.model_validate(result)
        assert validated.score == 72
        assert len(validated.sources) == 1

    @patch("src.agents.fundamental._get_client")
    def test_raises_agent_error_on_none_parsed_output(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.return_value = _make_mock_response(
            parsed_output=None, stop_reason="max_tokens"
        )

        with pytest.raises(AgentError) as exc_info:
            call_fundamental_agent("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)

        assert exc_info.value.error_type == "parse_failed"
        assert exc_info.value.usage["input_tokens"] == 1500

    @patch("src.agents.fundamental._get_client")
    def test_raises_agent_error_on_api_timeout(self, mock_get_client):
        import anthropic

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.side_effect = anthropic.APITimeoutError(request=MagicMock())

        with pytest.raises(AgentError) as exc_info:
            call_fundamental_agent("AAPL", SAMPLE_FUNDAMENTALS, SAMPLE_PRICE)

        assert exc_info.value.error_type == "timeout"

    @patch("src.agents.fundamental._get_client")
    def test_raises_agent_error_on_api_error(self, mock_get_client):
        import anthropic

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
