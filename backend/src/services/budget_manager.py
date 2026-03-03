"""Budget Manager — 3-Tier model routing with cost tracking.

Manages monthly API budget per tier (heavy/standard/light) and routes
LLM calls to the appropriate model. When a tier's budget is exhausted,
degrades to the next lower tier (heavy->standard->light).

Fail-open design: DB errors return zero spend (allow calls when budget
state is unknown). This is the OPPOSITE of kill_switch's fail-closed.
Rationale: a single DB hiccup shouldn't block all LLM calls; the budget
will be rechecked on next call. A false-positive LLM call (few cents)
is less disruptive than a blocked system in Paper Trading MVP.

Budget caps from docs/03_architecture/monitoring.md.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from src.services.exceptions import BudgetExhaustedError
from src.services.supabase import get_supabase_admin

logger = logging.getLogger(__name__)

# --- Budget caps (USD per month, from monitoring.md) ---
BUDGET_CAPS: dict[str, float] = {
    "heavy": 30.0,
    "standard": 20.0,
    "light": 5.0,
}
TOTAL_BUDGET_CAP = 55.0

# --- Model IDs per tier ---
TIER_MODELS: dict[str, str] = {
    "heavy": "claude-opus-4-6",
    "standard": "claude-sonnet-4-6",
    "light": "claude-haiku-4-5",
}

# --- Degradation chain (higher tier -> lower tier) ---
DEGRADATION_CHAIN: dict[str, str] = {
    "heavy": "standard",
    "standard": "light",
}

# --- Centralized pricing (per token) ---
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-6": {
        "input": 15.0 / 1_000_000,   # $15/MTok
        "output": 75.0 / 1_000_000,  # $75/MTok
    },
    "claude-sonnet-4-6": {
        "input": 3.0 / 1_000_000,    # $3/MTok
        "output": 15.0 / 1_000_000,  # $15/MTok
    },
    "claude-haiku-4-5": {
        "input": 0.80 / 1_000_000,   # $0.80/MTok
        "output": 4.0 / 1_000_000,   # $4/MTok
    },
}

# Soft cap warning threshold (percentage of budget)
SOFT_CAP_THRESHOLD = 0.80  # 80%


@dataclass
class ModelRouting:
    """Result of budget-aware model routing."""

    model_id: str
    tier: str
    degraded: bool
    original_tier: str


def get_monthly_spend() -> dict[str, float]:
    """Read current month's spend from agent_cost_log, aggregated by tier.

    Fail-open: returns zeros on DB error (allow calls when state is unknown).
    """
    try:
        admin = get_supabase_admin()
        first_of_month = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        resp = (
            admin.table("agent_cost_log")
            .select("tier, cost_usd")
            .gte("timestamp", first_of_month)
            .execute()
        )

        spend = {"heavy": 0.0, "standard": 0.0, "light": 0.0}
        for row in (resp.data or []):
            tier = row.get("tier", "")
            cost = float(row.get("cost_usd", 0))
            if tier in spend:
                spend[tier] += cost

        return spend
    except Exception as exc:
        logger.warning("Failed to read monthly spend — fail-open: %s", exc)
        return {"heavy": 0.0, "standard": 0.0, "light": 0.0}


def get_budget_status() -> dict:
    """Return budget status per tier with remaining amounts and warnings.

    Returns: {tiers: {heavy: {...}, standard: {...}, light: {...}},
              total_spend, total_cap, warnings: [...]}
    """
    spend = get_monthly_spend()
    total_spend = sum(spend.values())

    tiers = {}
    warnings = []

    for tier, cap in BUDGET_CAPS.items():
        tier_spend = spend.get(tier, 0.0)
        remaining = max(0.0, cap - tier_spend)
        pct_used = (tier_spend / cap * 100) if cap > 0 else 0.0

        tiers[tier] = {
            "spend": round(tier_spend, 4),
            "cap": cap,
            "remaining": round(remaining, 4),
            "pct_used": round(pct_used, 1),
            "model": TIER_MODELS[tier],
        }

        if tier_spend >= cap * SOFT_CAP_THRESHOLD:
            warnings.append(f"{tier} tier at {pct_used:.0f}% of budget (${tier_spend:.2f}/${cap:.2f})")

    if total_spend >= TOTAL_BUDGET_CAP * SOFT_CAP_THRESHOLD:
        warnings.append(
            f"Total spend at {total_spend / TOTAL_BUDGET_CAP * 100:.0f}% "
            f"(${total_spend:.2f}/${TOTAL_BUDGET_CAP:.2f})"
        )

    return {
        "tiers": tiers,
        "total_spend": round(total_spend, 4),
        "total_cap": TOTAL_BUDGET_CAP,
        "warnings": warnings,
    }


def get_model_for_tier(requested_tier: str) -> ModelRouting:
    """Route to the correct model based on budget availability.

    Degrades down chain when a tier's budget is exhausted:
    heavy -> standard -> light.

    Raises:
        BudgetExhaustedError: When light tier is exhausted or total cap is hit.
    """
    spend = get_monthly_spend()
    total_spend = sum(spend.values())

    # Total cap check first
    if total_spend >= TOTAL_BUDGET_CAP:
        raise BudgetExhaustedError(
            f"Total monthly budget exhausted (${total_spend:.2f}/${TOTAL_BUDGET_CAP:.2f})"
        )

    current_tier = requested_tier

    while current_tier:
        tier_spend = spend.get(current_tier, 0.0)
        tier_cap = BUDGET_CAPS.get(current_tier, 0.0)

        if tier_spend < tier_cap:
            degraded = current_tier != requested_tier
            if degraded:
                logger.warning(
                    "Budget degradation: %s -> %s (spend: $%.2f/$%.2f)",
                    requested_tier, current_tier, tier_spend, tier_cap,
                )
            return ModelRouting(
                model_id=TIER_MODELS[current_tier],
                tier=current_tier,
                degraded=degraded,
                original_tier=requested_tier,
            )

        # Degrade to next lower tier
        current_tier = DEGRADATION_CHAIN.get(current_tier)

    # No tier has budget remaining
    raise BudgetExhaustedError(
        f"All tier budgets exhausted (total: ${total_spend:.2f}/${TOTAL_BUDGET_CAP:.2f})"
    )


def get_pricing(model_id: str) -> dict[str, float]:
    """Return per-token pricing for a model.

    Returns: {input: price_per_token, output: price_per_token}
    Falls back to Haiku pricing for unknown models.
    """
    if model_id in MODEL_PRICING:
        return MODEL_PRICING[model_id]
    logger.warning("Unknown model '%s' for pricing — falling back to Haiku pricing", model_id)
    return MODEL_PRICING["claude-haiku-4-5"]
