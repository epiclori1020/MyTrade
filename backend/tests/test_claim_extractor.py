"""Tests for the Claim Extractor Agent (src/agents/claim_extractor.py).

All tests mock the Anthropic client — NO real API calls.
Tests cover: system prompt, Haiku->retry->Sonnet fallback chain, cost tracking.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agents.claim_extractor import (
    HAIKU_INPUT_PRICE,
    HAIKU_OUTPUT_PRICE,
    MODEL_HAIKU,
    MODEL_SONNET,
    SONNET_INPUT_PRICE,
    SONNET_OUTPUT_PRICE,
    SYSTEM_PROMPT,
    RawClaim,
    RawClaimsOutput,
    _get_client,
    call_claim_extractor,
)
from src.services.exceptions import AgentError


# --- Test data ---

SAMPLE_FUNDAMENTAL_OUT = {
    "financials": {
        "revenue": {
            "value": 394_328_000_000,
            "unit": "USD",
            "source": "finnhub",
            "period": "TTM",
            "retrieved_at": "2026-02-27T14:30:00Z",
        },
        "eps": {
            "value": 6.42,
            "unit": "USD",
            "source": "finnhub",
            "period": "TTM",
            "retrieved_at": "2026-02-27T14:30:00Z",
        },
    },
    "score": 72,
    "moat_rating": "wide",
}

SAMPLE_CLAIMS_OUTPUT = RawClaimsOutput(
    claims=[
        RawClaim(
            claim_text="AAPL Revenue TTM: $394.3B",
            claim_type="number",
            value=394_328_000_000,
            unit="USD",
            ticker="AAPL",
            period="TTM",
            source="finnhub",
            retrieved_at="2026-02-27T14:30:00Z",
        ),
        RawClaim(
            claim_text="AAPL EPS TTM: $6.42",
            claim_type="number",
            value=6.42,
            unit="USD",
            ticker="AAPL",
            period="TTM",
            source="finnhub",
            retrieved_at="2026-02-27T14:30:00Z",
        ),
    ]
)


def _make_mock_response(
    parsed_output=None, stop_reason="end_turn", input_tokens=800, output_tokens=500
):
    """Create a mock ParsedMessage response."""
    resp = MagicMock()
    resp.parsed_output = parsed_output
    resp.stop_reason = stop_reason
    resp.usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return resp


# --- System Prompt Tests ---


class TestSystemPrompt:
    def test_prompt_is_german(self):
        assert "Daten-Extraktions-Spezialist" in SYSTEM_PROMPT

    def test_prompt_forbids_inventing_numbers(self):
        assert "Erfinde KEINE Zahlen" in SYSTEM_PROMPT

    def test_prompt_mentions_all_claim_types(self):
        for claim_type in ("number", "ratio", "opinion", "forecast", "event"):
            assert f'"{claim_type}"' in SYSTEM_PROMPT

    def test_prompt_requires_all_fields(self):
        assert "claim_text, claim_type, value, unit, ticker, period, source, retrieved_at" in SYSTEM_PROMPT

    def test_prompt_skip_null_values(self):
        assert "value: null" in SYSTEM_PROMPT


# --- Fallback Chain Tests ---


class TestCallClaimExtractor:
    @patch("src.agents.claim_extractor._get_client")
    def test_success_on_first_haiku_attempt(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.return_value = _make_mock_response(
            parsed_output=SAMPLE_CLAIMS_OUTPUT
        )

        claims, usage = call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        assert len(claims) == 2
        assert claims[0]["claim_text"] == "AAPL Revenue TTM: $394.3B"
        assert usage["model_used"] == MODEL_HAIKU
        assert mock_client.messages.parse.call_count == 1

    @patch("src.agents.claim_extractor._get_client")
    def test_haiku_retry_on_first_parse_failure(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # First attempt: parse failure, second: success
        mock_client.messages.parse.side_effect = [
            _make_mock_response(parsed_output=None, stop_reason="max_tokens"),
            _make_mock_response(parsed_output=SAMPLE_CLAIMS_OUTPUT),
        ]

        claims, usage = call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        assert len(claims) == 2
        assert mock_client.messages.parse.call_count == 2
        assert usage["model_used"] == MODEL_HAIKU

    @patch("src.agents.claim_extractor._get_client")
    def test_retry_prompt_includes_error_description(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.messages.parse.side_effect = [
            _make_mock_response(parsed_output=None, stop_reason="max_tokens"),
            _make_mock_response(parsed_output=SAMPLE_CLAIMS_OUTPUT),
        ]

        call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        # Second call should have [RETRY] in the prompt
        second_call = mock_client.messages.parse.call_args_list[1]
        user_content = second_call[1]["messages"][0]["content"]
        assert "[RETRY]" in user_content
        assert "max_tokens" in user_content

    @patch("src.agents.claim_extractor._get_client")
    def test_sonnet_fallback_on_both_haiku_failures(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Two Haiku failures, then Sonnet success
        mock_client.messages.parse.side_effect = [
            _make_mock_response(parsed_output=None, stop_reason="max_tokens"),
            _make_mock_response(parsed_output=None, stop_reason="max_tokens"),
            _make_mock_response(parsed_output=SAMPLE_CLAIMS_OUTPUT),
        ]

        claims, usage = call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        assert len(claims) == 2
        assert mock_client.messages.parse.call_count == 3
        assert usage["model_used"] == MODEL_SONNET

        # Verify Sonnet was called with correct model
        third_call = mock_client.messages.parse.call_args_list[2]
        assert third_call[1]["model"] == MODEL_SONNET

    @patch("src.agents.claim_extractor._get_client")
    def test_sonnet_fallback_receives_original_prompt(self, mock_get_client):
        """Sonnet gets clean input without the [RETRY] suffix."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.messages.parse.side_effect = [
            _make_mock_response(parsed_output=None),
            _make_mock_response(parsed_output=None),
            _make_mock_response(parsed_output=SAMPLE_CLAIMS_OUTPUT),
        ]

        call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        # Third call (Sonnet) should NOT have [RETRY]
        third_call = mock_client.messages.parse.call_args_list[2]
        user_content = third_call[1]["messages"][0]["content"]
        assert "[RETRY]" not in user_content

    @patch("src.agents.claim_extractor._get_client")
    def test_cumulative_tokens_across_attempts(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.messages.parse.side_effect = [
            _make_mock_response(parsed_output=None, input_tokens=800, output_tokens=100),
            _make_mock_response(parsed_output=SAMPLE_CLAIMS_OUTPUT, input_tokens=900, output_tokens=500),
        ]

        _, usage = call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        assert usage["input_tokens"] == 1700  # 800 + 900
        assert usage["output_tokens"] == 600  # 100 + 500

    @patch("src.agents.claim_extractor._get_client")
    def test_cumulative_cost_mixed_models(self, mock_get_client):
        """Haiku attempts priced at Haiku rates, Sonnet at Sonnet rates."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.messages.parse.side_effect = [
            _make_mock_response(parsed_output=None, input_tokens=1000, output_tokens=100),
            _make_mock_response(parsed_output=None, input_tokens=1000, output_tokens=100),
            _make_mock_response(parsed_output=SAMPLE_CLAIMS_OUTPUT, input_tokens=1000, output_tokens=500),
        ]

        _, usage = call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        # Haiku: 2 * (1000 * 0.80/M + 100 * 4.00/M)
        haiku_cost = 2 * (1000 * HAIKU_INPUT_PRICE + 100 * HAIKU_OUTPUT_PRICE)
        # Sonnet: 1000 * 3.00/M + 500 * 15.00/M
        sonnet_cost = 1000 * SONNET_INPUT_PRICE + 500 * SONNET_OUTPUT_PRICE
        expected_cost = haiku_cost + sonnet_cost

        assert abs(usage["cost_usd"] - expected_cost) < 0.0001

    @patch("src.agents.claim_extractor._get_client")
    def test_all_attempts_fail_raises_agent_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.messages.parse.side_effect = [
            _make_mock_response(parsed_output=None),
            _make_mock_response(parsed_output=None),
            _make_mock_response(parsed_output=None),
        ]

        with pytest.raises(AgentError) as exc_info:
            call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        assert exc_info.value.error_type == "extraction_failed"
        # Usage should be cumulative from all 3 attempts
        assert exc_info.value.usage["input_tokens"] == 2400  # 3 * 800
        assert exc_info.value.usage["cost_usd"] > 0

    @patch("src.agents.claim_extractor._get_client")
    def test_api_timeout_raises_agent_error(self, mock_get_client):
        import anthropic

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.side_effect = anthropic.APITimeoutError(
            request=MagicMock()
        )

        with pytest.raises(AgentError) as exc_info:
            call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        assert exc_info.value.error_type == "timeout"

    @patch("src.agents.claim_extractor._get_client")
    def test_api_error_raises_agent_error(self, mock_get_client):
        import anthropic

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.side_effect = anthropic.APIStatusError(
            message="Server error",
            response=MagicMock(status_code=500),
            body={"error": {"message": "Server error"}},
        )

        with pytest.raises(AgentError) as exc_info:
            call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        assert exc_info.value.error_type == "api_error"

    @patch("src.agents.claim_extractor._get_client")
    def test_user_prompt_includes_ticker_and_json(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.return_value = _make_mock_response(
            parsed_output=SAMPLE_CLAIMS_OUTPUT
        )

        call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        call_kwargs = mock_client.messages.parse.call_args[1]
        user_content = call_kwargs["messages"][0]["content"]
        assert "AAPL" in user_content
        assert json.dumps(SAMPLE_FUNDAMENTAL_OUT, indent=2, ensure_ascii=False) in user_content


# --- Client Singleton Tests ---


class TestGetClient:
    def test_raises_value_error_when_no_api_key(self):
        _get_client.cache_clear()
        try:
            with patch("src.agents.claim_extractor.get_settings") as mock_settings:
                mock_settings.return_value.anthropic_api_key = ""
                with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not configured"):
                    _get_client()
        finally:
            _get_client.cache_clear()
