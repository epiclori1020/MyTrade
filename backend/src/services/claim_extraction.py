"""Claim Extraction Orchestrator — coordinates DB reads, agent call, DB writes.

Follows fundamental_analysis.py pattern: dataclass result, 2-phase architecture,
best-effort logging.

Phase A (Pre-Conditions): Validates analysis_run exists and has fundamental_out.
    Failures raise exceptions — no tokens consumed.

Phase B (LLM Execution): Calls claim extractor agent, post-processes claims,
    writes to claims table, logs cost.
    Failures return ClaimExtractionResult with status="failed" + cost tracking.
"""

import logging
from dataclasses import dataclass

from src.agents.claim_extractor import call_claim_extractor
from src.config import get_settings
from src.services.error_logger import log_error
from src.services.exceptions import (
    AgentError,
    BudgetExhaustedError,
    ConfigurationError,
    PreconditionError,
)
from src.services.supabase import get_supabase_admin
from src.services.supabase_retry import supabase_write_with_retry

logger = logging.getLogger(__name__)


# --- Deterministic constants for post-processing ---

TIER_BY_SOURCE = {
    "finnhub": "B",
    "alpha_vantage": "B",
    "sec_edgar": "A",
    "fred": "A",
    "calculated": "C",
}

SOURCE_ENDPOINTS = {
    "finnhub": "/stock/metric",
    "alpha_vantage": "OVERVIEW",
    "calculated": "derived",
}

# Keywords that indicate a claim is trade-critical (case-insensitive matching)
TRADE_CRITICAL_KEYWORDS = frozenset({
    "revenue",
    "eps",
    "earnings per share",
    "p/e",
    "pe ratio",
    "p/e ratio",
    "net income",
    "free cash flow",
    "fcf",
    "ev/ebitda",
})


@dataclass
class ClaimExtractionResult:
    """Result of a claim extraction run."""

    analysis_id: str
    status: str  # "completed" | "failed"
    claims_count: int = 0
    claims: list[dict] | None = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    error_message: str | None = None


# --- Deterministic post-processing functions (no LLM, no mocks needed for testing) ---


def _determine_trade_critical(claim_text: str) -> bool:
    """Check if a claim is trade-critical based on keyword matching."""
    text_lower = claim_text.lower()
    return any(keyword in text_lower for keyword in TRADE_CRITICAL_KEYWORDS)


def _determine_tier(source: str) -> str:
    """Map data source to evidence tier."""
    return TIER_BY_SOURCE.get(source, "C")


def _determine_required_tier(trade_critical: bool, claim_type: str) -> str:
    """Determine the minimum evidence tier required for this claim.

    - trade_critical claims need Tier A (primary/auditable source)
    - number/ratio claims need Tier B (two aggregators)
    - everything else (opinion/event/forecast) needs Tier C

    Note: The DB schema also allows "A+B" (dual-source required) — reserved
    for future use when Tier A sources are available (Step 7+).
    """
    if trade_critical:
        return "A"
    if claim_type in ("number", "ratio"):
        return "B"
    return "C"


def _build_source_primary(source: str, retrieved_at: str) -> dict:
    """Build claim-schema.json compatible source_primary object."""
    return {
        "provider": source,
        "endpoint": SOURCE_ENDPOINTS.get(source, "unknown"),
        "retrieved_at": retrieved_at,
    }


def _build_claim_id(analysis_id: str, index: int) -> str:
    """Build claim ID in format {analysis_id}_{001}."""
    return f"{analysis_id}_{index + 1:03d}"


def _post_process_claims(
    raw_claims: list[dict], analysis_id: str, ticker: str
) -> list[dict]:
    """Apply deterministic post-processing to raw LLM-extracted claims.

    Adds: claim_id, tier, required_tier, trade_critical, source_primary, status.
    Forces: value=None for opinion/event/forecast claims.
    Source provenance is deterministic — always 'finnhub' in MVP (the only
    data provider). LLM-supplied source field is ignored to prevent spoofing.
    """
    processed = []
    for i, raw in enumerate(raw_claims):
        claim_type = raw["claim_type"]
        claim_text = raw["claim_text"]

        # Force value to None for non-numeric claim types
        value = raw["value"] if claim_type in ("number", "ratio") else None

        trade_critical = _determine_trade_critical(claim_text)
        # MVP: Data always comes from Finnhub — ignore LLM-supplied source
        source = "finnhub"
        tier = _determine_tier(source)
        required_tier = _determine_required_tier(trade_critical, claim_type)

        processed.append({
            "analysis_id": analysis_id,
            "claim_id": _build_claim_id(analysis_id, i),
            "claim_text": claim_text,
            "claim_type": claim_type,
            "value": value,
            "unit": raw["unit"],
            "ticker": ticker.upper(),
            "period": raw["period"],
            "source_primary": _build_source_primary(source, raw.get("retrieved_at", "")),
            "tier": tier,
            "required_tier": required_tier,
            "trade_critical": trade_critical,
        })

    return processed


def run_claim_extraction(analysis_id: str, user_id: str) -> ClaimExtractionResult:
    """Extract claims from a completed fundamental analysis.

    Phase A: Pre-condition checks (no tokens consumed).
    Phase B: LLM call with full cost tracking.

    Raises:
        PreconditionError: Analysis not found, wrong user, or no fundamental output.
        ConfigurationError: ANTHROPIC_API_KEY not set.
    """
    admin = get_supabase_admin()

    # --- Phase A: Pre-Condition Checks ---

    # Step 1: Fetch analysis_run
    run_resp = (
        admin.table("analysis_runs")
        .select("user_id, ticker, fundamental_out, total_tokens, total_cost_usd")
        .eq("id", analysis_id)
        .execute()
    )
    if not run_resp.data:
        raise PreconditionError("Analysis run not found")

    run_row = run_resp.data[0]

    # Step 2: Verify ownership (same error message — no info leak)
    if run_row["user_id"] != user_id:
        raise PreconditionError("Analysis run not found")

    # Step 3: Check fundamental_out exists
    fundamental_out = run_row.get("fundamental_out")
    if not fundamental_out:
        raise PreconditionError(
            f"No fundamental analysis output. "
            f"Run POST /api/analyze/{run_row['ticker']} first."
        )

    # Step 4: Check API key
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ConfigurationError("ANTHROPIC_API_KEY not configured")

    ticker = run_row["ticker"]

    # --- Phase B: LLM Execution (tokens will be consumed) ---

    default_model = "claude-haiku-4-5"
    raw_claims, usage, error_message, routing = _call_extractor_safe(
        ticker, fundamental_out, analysis_id, default_model,
    )

    # Step 6: Post-process and write claims
    processed_claims = None
    claims_count = 0

    if raw_claims is not None:
        processed_claims = _post_process_claims(raw_claims, analysis_id, ticker)
        claims_count = len(processed_claims)

        if processed_claims:
            success = _persist_claims(admin, processed_claims, analysis_id)
            if not success:
                return ClaimExtractionResult(
                    analysis_id=analysis_id,
                    status="failed",
                    claims_count=0,
                    tokens_used=usage["input_tokens"] + usage["output_tokens"],
                    cost_usd=usage["cost_usd"],
                    error_message="Failed to write claims to DB",
                )

    # Step 7: Calculate token totals and log cost
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    total_tokens = input_tokens + output_tokens
    cost_usd = usage.get("cost_usd", 0.0)

    _log_extraction_cost(admin, analysis_id, usage, routing, default_model, run_row)

    status = "completed" if raw_claims is not None else "failed"

    return ClaimExtractionResult(
        analysis_id=analysis_id,
        status=status,
        claims_count=claims_count,
        claims=processed_claims,
        tokens_used=total_tokens,
        cost_usd=cost_usd,
        error_message=error_message,
    )


def _call_extractor_safe(
    ticker: str, fundamental_out: dict, analysis_id: str, default_model: str,
) -> tuple[list[dict] | None, dict, str | None, object]:
    """Call the LLM claim extractor with error handling.

    Returns (raw_claims, usage, error_message, routing).
    BudgetExhaustedError is re-raised (must propagate for 503 response).
    """
    usage = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "model_used": default_model}
    try:
        raw_claims, usage, routing = call_claim_extractor(ticker, fundamental_out)
        return raw_claims, usage, None, routing
    except BudgetExhaustedError:
        raise
    except AgentError as exc:
        if exc.usage:
            usage = {
                "input_tokens": exc.usage.get("input_tokens", 0),
                "output_tokens": exc.usage.get("output_tokens", 0),
                "cost_usd": exc.usage.get("cost_usd", 0.0),
                "model_used": exc.usage.get("model_used", default_model),
            }
        logger.error("Claim extraction error for %s: %s", analysis_id, exc)
        log_error(
            component="claim_extractor",
            error_type=exc.error_type,
            message=str(exc),
            analysis_id=analysis_id,
        )
        return None, usage, str(exc), None
    except Exception as exc:
        logger.error(
            "Unexpected claim extraction error for %s: %s",
            analysis_id, exc, exc_info=True,
        )
        log_error(
            component="claim_extractor",
            error_type="unexpected",
            message=str(exc),
            analysis_id=analysis_id,
        )
        return None, usage, f"Unexpected error: {exc}", None


def _persist_claims(admin, processed_claims: list[dict], analysis_id: str) -> bool:
    """Batch INSERT claims into DB with retry + queue fallback.

    Returns True on success, False on failure.
    """
    success = supabase_write_with_retry(
        lambda: admin.table("claims").insert(processed_claims).execute(),
        description=f"claims insert for {analysis_id}",
    )
    if not success:
        logger.error("Failed to insert claims for %s (queued)", analysis_id)
    return success


def _log_extraction_cost(
    admin, analysis_id: str, usage: dict, routing, default_model: str, run_row: dict
) -> None:
    """Log extraction cost to agent_cost_log and update analysis_runs. Best-effort."""
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    total_tokens = input_tokens + output_tokens
    cost_usd = usage.get("cost_usd", 0.0)
    model_used = usage.get("model_used", default_model)

    if total_tokens <= 0:
        return

    tier = routing.tier if routing else ("standard" if "sonnet" in model_used else "light")
    is_quality_fallback = routing is not None and model_used != routing.model_id
    try:
        admin.table("agent_cost_log").insert({
            "analysis_id": analysis_id,
            "agent_name": "claim_extractor",
            "model": model_used,
            "tier": tier,
            "effort": "low",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": 0,
            "cost_usd": cost_usd,
            "fallback_from": default_model if is_quality_fallback else (
                routing.original_tier if routing and routing.degraded else None
            ),
            "degraded": routing.degraded if routing else False,
        }).execute()
    except Exception as exc:
        logger.warning("Failed to log agent cost: %s", exc)

    # Update analysis_runs cumulative cost (best-effort)
    # Note: read-then-update without transaction — acceptable for MVP single user.
    try:
        existing_tokens = run_row.get("total_tokens") or 0
        existing_cost = float(run_row.get("total_cost_usd") or 0)
        admin.table("analysis_runs").update({
            "total_tokens": existing_tokens + total_tokens,
            "total_cost_usd": existing_cost + cost_usd,
        }).eq("id", analysis_id).execute()
    except Exception as exc:
        logger.warning("Failed to update analysis_runs cost: %s", exc)
