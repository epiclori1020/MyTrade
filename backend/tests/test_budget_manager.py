"""Tests for Budget Manager (src/services/budget_manager.py).

All DB calls are mocked — NO real Supabase calls.
LLM spend queries are mocked via patch("src.services.budget_manager.get_supabase_admin").
get_monthly_spend() is mocked directly for get_model_for_tier() and get_budget_status() tests.

Structure:
- TestGetMonthlySpend  — DB aggregation + fail-open behaviour
- TestGetBudgetStatus  — remaining amounts, soft-cap warnings
- TestGetModelForTier  — routing, degradation chain, BudgetExhaustedError
- TestGetPricing       — per-model pricing lookup + unknown-model fallback
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services.budget_manager import (
    BUDGET_CAPS,
    DEGRADATION_CHAIN,
    MODEL_PRICING,
    SOFT_CAP_THRESHOLD,
    TIER_MODELS,
    TOTAL_BUDGET_CAP,
    ModelRouting,
    get_budget_status,
    get_model_for_tier,
    get_monthly_spend,
    get_pricing,
)
from src.services.exceptions import BudgetExhaustedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_admin_with_rows(rows: list[dict]) -> MagicMock:
    """Build a minimal Supabase admin mock for agent_cost_log queries.

    Chains covered:
        admin.table("agent_cost_log").select("tier, cost_usd").gte(...).execute()
    """
    admin = MagicMock()
    chain = (
        admin.table.return_value
        .select.return_value
        .gte.return_value
    )
    chain.execute.return_value = SimpleNamespace(data=rows)
    return admin


# ---------------------------------------------------------------------------
# 1. get_monthly_spend
# ---------------------------------------------------------------------------


class TestGetMonthlySpend:
    @patch("src.services.budget_manager.get_supabase_admin")
    def test_empty_db_returns_zeros(self, mock_admin_fn):
        """No cost rows in DB → all tiers return 0.0 (fail-open baseline)."""
        mock_admin_fn.return_value = _mock_admin_with_rows([])

        result = get_monthly_spend()

        assert result == {"heavy": 0.0, "standard": 0.0, "light": 0.0}

    @patch("src.services.budget_manager.get_supabase_admin")
    def test_aggregates_spend_by_tier(self, mock_admin_fn):
        """Rows from multiple tiers are summed independently per tier."""
        rows = [
            {"tier": "heavy",    "cost_usd": 10.0},
            {"tier": "heavy",    "cost_usd": 5.5},
            {"tier": "standard", "cost_usd": 3.25},
            {"tier": "light",    "cost_usd": 0.50},
            {"tier": "light",    "cost_usd": 0.25},
        ]
        mock_admin_fn.return_value = _mock_admin_with_rows(rows)

        result = get_monthly_spend()

        assert result["heavy"]    == pytest.approx(15.5)
        assert result["standard"] == pytest.approx(3.25)
        assert result["light"]    == pytest.approx(0.75)

    @patch("src.services.budget_manager.get_supabase_admin")
    def test_unknown_tier_rows_are_ignored(self, mock_admin_fn):
        """Rows with an unrecognised tier key must not pollute the result dict."""
        rows = [
            {"tier": "heavy",   "cost_usd": 5.0},
            {"tier": "unknown", "cost_usd": 99.0},  # should be silently dropped
        ]
        mock_admin_fn.return_value = _mock_admin_with_rows(rows)

        result = get_monthly_spend()

        assert result["heavy"]    == pytest.approx(5.0)
        assert result["standard"] == pytest.approx(0.0)
        assert result["light"]    == pytest.approx(0.0)
        assert "unknown" not in result

    @patch("src.services.budget_manager.get_supabase_admin")
    def test_db_error_returns_zeros_fail_open(self, mock_admin_fn):
        """Any DB exception must be swallowed and zeros returned (fail-open design)."""
        mock_admin_fn.side_effect = Exception("connection refused")

        result = get_monthly_spend()

        assert result == {"heavy": 0.0, "standard": 0.0, "light": 0.0}

    @patch("src.services.budget_manager.get_supabase_admin")
    def test_single_tier_only_updates_that_tier(self, mock_admin_fn):
        """Only one tier with spend — the other two must stay at 0.0."""
        rows = [{"tier": "standard", "cost_usd": 7.0}]
        mock_admin_fn.return_value = _mock_admin_with_rows(rows)

        result = get_monthly_spend()

        assert result["standard"] == pytest.approx(7.0)
        assert result["heavy"]    == pytest.approx(0.0)
        assert result["light"]    == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 2. get_budget_status
# ---------------------------------------------------------------------------


class TestGetBudgetStatus:
    @patch("src.services.budget_manager.get_monthly_spend")
    def test_correct_remaining_per_tier(self, mock_spend):
        """remaining = cap - spend for each tier, floored at 0."""
        mock_spend.return_value = {"heavy": 10.0, "standard": 5.0, "light": 1.0}

        status = get_budget_status()

        assert status["tiers"]["heavy"]["remaining"]    == pytest.approx(BUDGET_CAPS["heavy"]    - 10.0)
        assert status["tiers"]["standard"]["remaining"] == pytest.approx(BUDGET_CAPS["standard"] - 5.0)
        assert status["tiers"]["light"]["remaining"]    == pytest.approx(BUDGET_CAPS["light"]    - 1.0)

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_total_spend_is_sum_of_all_tiers(self, mock_spend):
        """total_spend must equal the sum of all tier spends."""
        mock_spend.return_value = {"heavy": 10.0, "standard": 5.0, "light": 2.0}

        status = get_budget_status()

        assert status["total_spend"] == pytest.approx(17.0)
        assert status["total_cap"]   == TOTAL_BUDGET_CAP

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_no_warnings_when_well_under_threshold(self, mock_spend):
        """No warnings emitted when every tier is below 80% of its cap."""
        mock_spend.return_value = {"heavy": 1.0, "standard": 1.0, "light": 0.10}

        status = get_budget_status()

        assert status["warnings"] == []

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_tier_warning_at_exactly_soft_cap_threshold(self, mock_spend):
        """A tier at exactly 80% of its cap must emit a warning string."""
        # heavy cap = 30.0, 80% = 24.0
        heavy_spend = BUDGET_CAPS["heavy"] * SOFT_CAP_THRESHOLD
        mock_spend.return_value = {
            "heavy": heavy_spend,
            "standard": 0.0,
            "light": 0.0,
        }

        status = get_budget_status()

        heavy_warnings = [w for w in status["warnings"] if "heavy" in w]
        assert len(heavy_warnings) == 1

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_tier_warning_above_soft_cap_threshold(self, mock_spend):
        """A tier exceeding 80% must emit a warning; tiers below must not."""
        # standard cap = 20.0 — set to 90%
        mock_spend.return_value = {
            "heavy":    0.0,
            "standard": BUDGET_CAPS["standard"] * 0.90,
            "light":    0.0,
        }

        status = get_budget_status()

        standard_warnings = [w for w in status["warnings"] if "standard" in w]
        heavy_warnings    = [w for w in status["warnings"] if "heavy" in w]
        assert len(standard_warnings) == 1
        assert len(heavy_warnings)    == 0

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_total_cap_warning_when_total_exceeds_threshold(self, mock_spend):
        """Total budget ≥ 80% of TOTAL_BUDGET_CAP must add a total-spend warning."""
        # TOTAL_BUDGET_CAP = 55.0, 80% = 44.0 — distribute across tiers
        mock_spend.return_value = {
            "heavy":    20.0,
            "standard": 15.0,
            "light":    9.0,   # total = 44.0 = exactly 80%
        }

        status = get_budget_status()

        total_warnings = [w for w in status["warnings"] if "Total" in w or "total" in w.lower()]
        assert len(total_warnings) >= 1

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_zero_spend_no_warnings_and_full_remaining(self, mock_spend):
        """Zero spend → no warnings and remaining equals cap for every tier."""
        mock_spend.return_value = {"heavy": 0.0, "standard": 0.0, "light": 0.0}

        status = get_budget_status()

        assert status["warnings"] == []
        for tier, cap in BUDGET_CAPS.items():
            assert status["tiers"][tier]["remaining"] == pytest.approx(cap)
            assert status["tiers"][tier]["spend"]     == pytest.approx(0.0)

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_model_id_present_in_tier_info(self, mock_spend):
        """Each tier dict must expose the canonical model_id for that tier."""
        mock_spend.return_value = {"heavy": 0.0, "standard": 0.0, "light": 0.0}

        status = get_budget_status()

        for tier, expected_model in TIER_MODELS.items():
            assert status["tiers"][tier]["model"] == expected_model


# ---------------------------------------------------------------------------
# 3. get_model_for_tier
# ---------------------------------------------------------------------------


class TestGetModelForTier:
    @patch("src.services.budget_manager.get_monthly_spend")
    def test_budget_available_returns_requested_model(self, mock_spend):
        """When requested tier has budget, return that tier's model without degradation."""
        mock_spend.return_value = {"heavy": 0.0, "standard": 0.0, "light": 0.0}

        routing = get_model_for_tier("standard")

        assert routing.model_id    == TIER_MODELS["standard"]
        assert routing.tier        == "standard"
        assert routing.degraded    is False
        assert routing.original_tier == "standard"

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_heavy_available_returns_heavy_model(self, mock_spend):
        """Heavy tier with budget → opus model, no degradation."""
        mock_spend.return_value = {"heavy": 0.0, "standard": 0.0, "light": 0.0}

        routing = get_model_for_tier("heavy")

        assert routing.model_id == TIER_MODELS["heavy"]
        assert routing.tier     == "heavy"
        assert routing.degraded is False

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_standard_exhausted_degrades_to_light(self, mock_spend):
        """Standard budget fully used → degrade to light tier (haiku)."""
        mock_spend.return_value = {
            "heavy":    0.0,
            "standard": BUDGET_CAPS["standard"],   # exactly at cap
            "light":    0.0,
        }

        routing = get_model_for_tier("standard")

        assert routing.model_id      == TIER_MODELS["light"]
        assert routing.tier          == "light"
        assert routing.degraded      is True
        assert routing.original_tier == "standard"

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_heavy_exhausted_degrades_to_standard(self, mock_spend):
        """Heavy budget fully used → degrade to standard tier (sonnet)."""
        mock_spend.return_value = {
            "heavy":    BUDGET_CAPS["heavy"],   # exactly at cap
            "standard": 0.0,
            "light":    0.0,
        }

        routing = get_model_for_tier("heavy")

        assert routing.model_id      == TIER_MODELS["standard"]
        assert routing.tier          == "standard"
        assert routing.degraded      is True
        assert routing.original_tier == "heavy"

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_heavy_and_standard_exhausted_degrades_to_light(self, mock_spend):
        """Both heavy and standard exhausted → degrade all the way to light."""
        mock_spend.return_value = {
            "heavy":    BUDGET_CAPS["heavy"],
            "standard": BUDGET_CAPS["standard"],
            "light":    0.0,
        }

        routing = get_model_for_tier("heavy")

        assert routing.model_id      == TIER_MODELS["light"]
        assert routing.tier          == "light"
        assert routing.degraded      is True
        assert routing.original_tier == "heavy"

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_light_exhausted_raises_budget_exhausted_error(self, mock_spend):
        """All tiers exhausted → BudgetExhaustedError is raised (no further fallback)."""
        mock_spend.return_value = {
            "heavy":    BUDGET_CAPS["heavy"],
            "standard": BUDGET_CAPS["standard"],
            "light":    BUDGET_CAPS["light"],
        }

        with pytest.raises(BudgetExhaustedError):
            get_model_for_tier("light")

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_requesting_light_when_light_exhausted_raises_error(self, mock_spend):
        """Requesting light tier directly when light is exhausted raises BudgetExhaustedError."""
        mock_spend.return_value = {
            "heavy":    0.0,
            "standard": 0.0,
            "light":    BUDGET_CAPS["light"],   # light exhausted
        }

        with pytest.raises(BudgetExhaustedError):
            get_model_for_tier("light")

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_total_cap_exceeded_raises_error_before_tier_check(self, mock_spend):
        """Total spend at or above TOTAL_BUDGET_CAP raises BudgetExhaustedError immediately."""
        # Distribute spend across tiers such that total == TOTAL_BUDGET_CAP
        mock_spend.return_value = {
            "heavy":    30.0,   # = BUDGET_CAPS["heavy"]
            "standard": 20.0,   # = BUDGET_CAPS["standard"]
            "light":    5.0,    # = BUDGET_CAPS["light"] → total = 55.0
        }

        with pytest.raises(BudgetExhaustedError):
            get_model_for_tier("light")  # Even light would be rejected first by total cap

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_total_cap_exceeded_blocks_heavy_too(self, mock_spend):
        """Total cap check fires regardless of which tier is requested."""
        mock_spend.return_value = {
            "heavy":    TOTAL_BUDGET_CAP,  # absurdly overspent on heavy alone
            "standard": 0.0,
            "light":    0.0,
        }

        with pytest.raises(BudgetExhaustedError):
            get_model_for_tier("standard")

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_degraded_flag_true_and_original_tier_set(self, mock_spend):
        """Degraded routing must carry degraded=True and correct original_tier."""
        mock_spend.return_value = {
            "heavy":    0.0,
            "standard": BUDGET_CAPS["standard"],  # exhausted
            "light":    0.0,
        }

        routing = get_model_for_tier("standard")

        assert routing.degraded      is True
        assert routing.original_tier == "standard"
        assert routing.tier          != "standard"   # must have moved to a lower tier

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_model_routing_is_dataclass(self, mock_spend):
        """Return type must be ModelRouting with all four attributes populated."""
        mock_spend.return_value = {"heavy": 0.0, "standard": 0.0, "light": 0.0}

        routing = get_model_for_tier("heavy")

        assert isinstance(routing, ModelRouting)
        # All four required fields must be present
        assert hasattr(routing, "model_id")
        assert hasattr(routing, "tier")
        assert hasattr(routing, "degraded")
        assert hasattr(routing, "original_tier")

    @patch("src.services.budget_manager.get_monthly_spend")
    def test_spend_just_below_cap_does_not_degrade(self, mock_spend):
        """Spend one cent below the cap must not trigger degradation."""
        mock_spend.return_value = {
            "heavy":    0.0,
            "standard": BUDGET_CAPS["standard"] - 0.01,   # one cent under cap
            "light":    0.0,
        }

        routing = get_model_for_tier("standard")

        assert routing.tier     == "standard"
        assert routing.degraded is False


# ---------------------------------------------------------------------------
# 4. get_pricing
# ---------------------------------------------------------------------------


class TestGetPricing:
    def test_sonnet_pricing_correct(self):
        """claude-sonnet-4-6 must return the published $3/$15 per-MTok pricing."""
        pricing = get_pricing("claude-sonnet-4-6")

        assert pricing["input"]  == pytest.approx(3.0  / 1_000_000)
        assert pricing["output"] == pytest.approx(15.0 / 1_000_000)

    def test_opus_pricing_correct(self):
        """claude-opus-4-6 must return the published $15/$75 per-MTok pricing."""
        pricing = get_pricing("claude-opus-4-6")

        assert pricing["input"]  == pytest.approx(15.0 / 1_000_000)
        assert pricing["output"] == pytest.approx(75.0 / 1_000_000)

    def test_haiku_pricing_correct(self):
        """claude-haiku-4-5 must return the published $0.80/$4 per-MTok pricing."""
        pricing = get_pricing("claude-haiku-4-5")

        assert pricing["input"]  == pytest.approx(0.80 / 1_000_000)
        assert pricing["output"] == pytest.approx(4.0  / 1_000_000)

    def test_unknown_model_falls_back_to_haiku_pricing(self):
        """An unrecognised model ID must silently fall back to Haiku pricing."""
        pricing = get_pricing("some-future-model-xyz")

        haiku_pricing = MODEL_PRICING["claude-haiku-4-5"]
        assert pricing["input"]  == pytest.approx(haiku_pricing["input"])
        assert pricing["output"] == pytest.approx(haiku_pricing["output"])

    def test_empty_string_model_falls_back_to_haiku(self):
        """Empty string model ID is also unknown → Haiku fallback."""
        pricing = get_pricing("")

        haiku_pricing = MODEL_PRICING["claude-haiku-4-5"]
        assert pricing["input"]  == pytest.approx(haiku_pricing["input"])
        assert pricing["output"] == pytest.approx(haiku_pricing["output"])

    def test_pricing_dict_has_both_keys(self):
        """Returned dict must contain exactly 'input' and 'output' keys."""
        for model_id in TIER_MODELS.values():
            pricing = get_pricing(model_id)
            assert "input"  in pricing
            assert "output" in pricing

    def test_output_price_always_greater_than_input(self):
        """Output tokens cost more than input tokens for every known model."""
        for model_id in TIER_MODELS.values():
            pricing = get_pricing(model_id)
            assert pricing["output"] > pricing["input"], (
                f"Expected output > input for {model_id}"
            )
