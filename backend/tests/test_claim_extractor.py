"""Tests for the Claim Extractor Agent (src/agents/claim_extractor.py).

All tests mock the Anthropic client — NO real API calls.
Tests cover: system prompt, Haiku->retry->Sonnet fallback chain, cost tracking,
budget-aware model routing (Step 11).
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agents.claim_extractor import (
    SYSTEM_PROMPT,
    RawClaim,
    RawClaimsOutput,
    _get_client,
    call_claim_extractor,
)
from src.services.budget_manager import ModelRouting, get_pricing
from src.services.exceptions import AgentError, BudgetExhaustedError

# Model ID constants (centralized in budget_manager, tests use literals for clarity)
MODEL_HAIKU = "claude-haiku-4-5"
MODEL_SONNET = "claude-sonnet-4-6"

LIGHT_ROUTING = ModelRouting(
    model_id=MODEL_HAIKU, tier="light", degraded=False, original_tier="light"
)
STANDARD_ROUTING = ModelRouting(
    model_id=MODEL_SONNET, tier="standard", degraded=False, original_tier="standard"
)


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
    @patch("src.agents.claim_extractor.get_model_for_tier")
    @patch("src.agents.claim_extractor._get_client")
    def test_success_on_first_haiku_attempt(self, mock_get_client, mock_route):
        mock_route.return_value = LIGHT_ROUTING
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.return_value = _make_mock_response(
            parsed_output=SAMPLE_CLAIMS_OUTPUT
        )

        claims, usage, routing = call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        assert len(claims) == 2
        assert claims[0]["claim_text"] == "AAPL Revenue TTM: $394.3B"
        assert usage["model_used"] == MODEL_HAIKU
        assert routing == LIGHT_ROUTING
        assert mock_client.messages.parse.call_count == 1

    @patch("src.agents.claim_extractor.get_model_for_tier")
    @patch("src.agents.claim_extractor._get_client")
    def test_haiku_retry_on_first_parse_failure(self, mock_get_client, mock_route):
        mock_route.return_value = LIGHT_ROUTING
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # First attempt: parse failure, second: success
        mock_client.messages.parse.side_effect = [
            _make_mock_response(parsed_output=None, stop_reason="max_tokens"),
            _make_mock_response(parsed_output=SAMPLE_CLAIMS_OUTPUT),
        ]

        claims, usage, routing = call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        assert len(claims) == 2
        assert mock_client.messages.parse.call_count == 2
        assert usage["model_used"] == MODEL_HAIKU

    @patch("src.agents.claim_extractor.get_model_for_tier")
    @patch("src.agents.claim_extractor._get_client")
    def test_retry_prompt_includes_error_description(self, mock_get_client, mock_route):
        mock_route.return_value = LIGHT_ROUTING
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

    @patch("src.agents.claim_extractor.get_model_for_tier")
    @patch("src.agents.claim_extractor._get_client")
    def test_sonnet_fallback_on_both_haiku_failures(self, mock_get_client, mock_route):
        mock_route.side_effect = [LIGHT_ROUTING, STANDARD_ROUTING]
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Two Haiku failures, then Sonnet success
        mock_client.messages.parse.side_effect = [
            _make_mock_response(parsed_output=None, stop_reason="max_tokens"),
            _make_mock_response(parsed_output=None, stop_reason="max_tokens"),
            _make_mock_response(parsed_output=SAMPLE_CLAIMS_OUTPUT),
        ]

        claims, usage, routing = call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        assert len(claims) == 2
        assert mock_client.messages.parse.call_count == 3
        assert usage["model_used"] == MODEL_SONNET
        assert routing == STANDARD_ROUTING

        # Verify Sonnet was called with correct model
        third_call = mock_client.messages.parse.call_args_list[2]
        assert third_call[1]["model"] == MODEL_SONNET

    @patch("src.agents.claim_extractor.get_model_for_tier")
    @patch("src.agents.claim_extractor._get_client")
    def test_sonnet_fallback_receives_original_prompt(self, mock_get_client, mock_route):
        """Sonnet gets clean input without the [RETRY] suffix."""
        mock_route.side_effect = [LIGHT_ROUTING, STANDARD_ROUTING]
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

    @patch("src.agents.claim_extractor.get_model_for_tier")
    @patch("src.agents.claim_extractor._get_client")
    def test_cumulative_tokens_across_attempts(self, mock_get_client, mock_route):
        mock_route.return_value = LIGHT_ROUTING
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.messages.parse.side_effect = [
            _make_mock_response(parsed_output=None, input_tokens=800, output_tokens=100),
            _make_mock_response(parsed_output=SAMPLE_CLAIMS_OUTPUT, input_tokens=900, output_tokens=500),
        ]

        _, usage, _ = call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        assert usage["input_tokens"] == 1700  # 800 + 900
        assert usage["output_tokens"] == 600  # 100 + 500

    @patch("src.agents.claim_extractor.get_model_for_tier")
    @patch("src.agents.claim_extractor._get_client")
    def test_cumulative_cost_mixed_models(self, mock_get_client, mock_route):
        """Haiku attempts priced at Haiku rates, Sonnet at Sonnet rates."""
        mock_route.side_effect = [LIGHT_ROUTING, STANDARD_ROUTING]
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.messages.parse.side_effect = [
            _make_mock_response(parsed_output=None, input_tokens=1000, output_tokens=100),
            _make_mock_response(parsed_output=None, input_tokens=1000, output_tokens=100),
            _make_mock_response(parsed_output=SAMPLE_CLAIMS_OUTPUT, input_tokens=1000, output_tokens=500),
        ]

        _, usage, _ = call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        haiku_pricing = get_pricing(MODEL_HAIKU)
        sonnet_pricing = get_pricing(MODEL_SONNET)
        # Haiku: 2 * (1000 * input + 100 * output)
        haiku_cost = 2 * (1000 * haiku_pricing["input"] + 100 * haiku_pricing["output"])
        # Sonnet: 1000 * input + 500 * output
        sonnet_cost = 1000 * sonnet_pricing["input"] + 500 * sonnet_pricing["output"]
        expected_cost = haiku_cost + sonnet_cost

        assert abs(usage["cost_usd"] - expected_cost) < 0.0001

    @patch("src.agents.claim_extractor.get_model_for_tier")
    @patch("src.agents.claim_extractor._get_client")
    def test_all_attempts_fail_raises_agent_error(self, mock_get_client, mock_route):
        mock_route.side_effect = [LIGHT_ROUTING, STANDARD_ROUTING]
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
        # Last model attempted was Sonnet (attempt 3)
        assert exc_info.value.usage["model_used"] == MODEL_SONNET

    @patch("src.agents.claim_extractor.get_model_for_tier")
    @patch("src.agents.claim_extractor._get_client")
    def test_api_timeout_raises_agent_error(self, mock_get_client, mock_route):
        import anthropic

        mock_route.return_value = LIGHT_ROUTING
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.side_effect = anthropic.APITimeoutError(
            request=MagicMock()
        )

        with pytest.raises(AgentError) as exc_info:
            call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        assert exc_info.value.error_type == "timeout"
        # Timeout on first attempt — last_model is still Haiku
        assert exc_info.value.usage["model_used"] == MODEL_HAIKU

    @patch("src.agents.claim_extractor.get_model_for_tier")
    @patch("src.agents.claim_extractor._get_client")
    def test_api_error_raises_agent_error(self, mock_get_client, mock_route):
        import anthropic

        mock_route.return_value = LIGHT_ROUTING
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

    @patch("src.agents.claim_extractor.get_model_for_tier")
    @patch("src.agents.claim_extractor._get_client")
    def test_user_prompt_includes_ticker_and_json(self, mock_get_client, mock_route):
        mock_route.return_value = LIGHT_ROUTING
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

    @patch("src.agents.claim_extractor.get_model_for_tier")
    @patch("src.agents.claim_extractor._get_client")
    def test_budget_exhausted_propagates(self, mock_get_client, mock_route):
        """BudgetExhaustedError from get_model_for_tier must propagate."""
        mock_route.side_effect = BudgetExhaustedError("Monthly budget exhausted")

        with pytest.raises(BudgetExhaustedError):
            call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)


class TestAttemptExtractionJsonRepair:
    """Tests for the JSON repair path inside _attempt_extraction."""

    @patch("src.agents.claim_extractor.get_model_for_tier")
    @patch("src.agents.claim_extractor.try_repair_json")
    @patch("src.agents.claim_extractor.extract_raw_text")
    @patch("src.agents.claim_extractor._get_client")
    def test_json_repair_succeeds_in_attempt_extraction(
        self, mock_get_client, mock_extract, mock_repair, mock_route
    ):
        """Within _attempt_extraction, parsed_output=None but JSON repair succeeds.

        Expect: claims returned from first Haiku attempt without going to retry.
        """
        mock_route.return_value = LIGHT_ROUTING
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.parse.return_value = _make_mock_response(
            parsed_output=None, stop_reason="max_tokens", input_tokens=800, output_tokens=100
        )

        mock_extract.return_value = '{"claims": []}'

        # Build a repaired RawClaimsOutput mock with .claims list
        repaired_claim = MagicMock()
        repaired_claim.model_dump.return_value = SAMPLE_CLAIMS_OUTPUT.claims[0].model_dump()
        repaired_model = MagicMock(spec=RawClaimsOutput)
        repaired_model.claims = [repaired_claim]
        mock_repair.return_value = repaired_model

        claims, usage, routing = call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        # Only one LLM call — repair avoided the retry
        mock_client.messages.parse.assert_called_once()
        assert len(claims) == 1
        assert usage["model_used"] == MODEL_HAIKU
        assert routing == LIGHT_ROUTING

    @patch("src.agents.claim_extractor.get_model_for_tier")
    @patch("src.agents.claim_extractor.try_repair_json")
    @patch("src.agents.claim_extractor.extract_raw_text")
    @patch("src.agents.claim_extractor._get_client")
    def test_json_repair_fails_in_attempt_extraction(
        self, mock_get_client, mock_extract, mock_repair, mock_route
    ):
        """Within _attempt_extraction, parsed_output=None and repair returns None.

        Expect: the attempt returns (None, usage, error_desc), triggering the retry chain.
        The overall call_claim_extractor escalates to the Haiku retry attempt.
        """
        mock_route.side_effect = [LIGHT_ROUTING, STANDARD_ROUTING]
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Attempt 1: parse fails, repair fails
        # Attempt 2: parse fails, repair fails
        # Attempt 3 (Sonnet): succeeds
        mock_client.messages.parse.side_effect = [
            _make_mock_response(parsed_output=None, stop_reason="max_tokens"),
            _make_mock_response(parsed_output=None, stop_reason="max_tokens"),
            _make_mock_response(parsed_output=SAMPLE_CLAIMS_OUTPUT),
        ]

        mock_extract.return_value = "malformed json"
        mock_repair.return_value = None

        claims, usage, routing = call_claim_extractor("AAPL", SAMPLE_FUNDAMENTAL_OUT)

        # Repair failed on both Haiku attempts → escalated to Sonnet
        assert mock_client.messages.parse.call_count == 3
        assert len(claims) == 2
        assert usage["model_used"] == MODEL_SONNET
        assert routing == STANDARD_ROUTING


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
