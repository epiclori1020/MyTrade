"""Verification Layer — cross-checks claims against a second data source.

Purely deterministic (no LLM). Compares claim values against Alpha Vantage
data and assigns verification statuses based on deviation thresholds.

Phase A (Pre-Conditions): Validates analysis_run, claims exist, no prior
    verification. Failures raise exceptions.

Phase B (Execution): Fetches AV data, processes each claim, writes results.
    AV failures degrade gracefully (all claims become unverified).

MVP Limitation: No SEC EDGAR client → no Tier A → 'verified' status impossible.
Best result is 'consistent' (two Tier B sources agree) or 'manual_check'
(trade-critical claims need Tier A, have only B).
"""

import logging
import math
from dataclasses import dataclass

from src.config import get_settings
from src.services.alpha_vantage import AlphaVantageClient
from src.services.error_logger import log_error
from src.services.exceptions import (
    ConfigurationError,
    DataProviderError,
    PreconditionError,
)
from src.services.retry import retry_with_backoff
from src.services.supabase import get_supabase_admin

logger = logging.getLogger(__name__)

# No SEC EDGAR client in MVP — flip to True when added
TIER_A_AVAILABLE = False

# Maps claim keywords to Alpha Vantage fields for cross-checking.
# Multiple keyword variants because LLM may write "PE Ratio" (no slash)
# or "P/E Ratio" (with slash). See claim_extraction.py:43-54.
CLAIM_MATCHERS = {
    "revenue": {
        "claim_type": "number",
        "keywords": ["revenue"],
        "av_field": "revenue",
    },
    "pe_ratio": {
        "claim_type": "ratio",
        "keywords": ["p/e", "pe ratio", "p/e ratio"],
        "av_field": "pe_ratio",
    },
    "eps": {
        "claim_type": "number",
        "keywords": ["eps", "earnings per share"],
        "av_field": "eps",
    },
    "ev_ebitda": {
        "claim_type": "ratio",
        "keywords": ["ev/ebitda"],
        "av_field": "ev_ebitda",
    },
    "pb_ratio": {
        "claim_type": "ratio",
        "keywords": ["p/b", "pb ratio", "price-to-book", "price to book"],
        "av_field": "pb_ratio",
    },
    "roe": {
        "claim_type": "ratio",
        "keywords": ["roe", "return on equity"],
        "av_field": "roe",
    },
}


@dataclass
class VerificationResult:
    """Result of a verification run."""

    analysis_id: str
    status: str  # "completed" | "failed"
    summary: dict  # {verified, consistent, unverified, disputed, manual_check, has_blocking_disputed}
    results_count: int = 0  # Rows written to verification_results (cross-checked only)
    error_message: str | None = None


# --- Pure functions (testable without mocks) ---


def _calculate_deviation(primary_value: float, verification_value: float) -> float:
    """Calculate percentage deviation between two values.

    Precondition: caller ensures primary_value != 0 (division-by-zero guard
    is in _process_single_claim).
    """
    return abs(primary_value - verification_value) / abs(primary_value) * 100


def _match_claim_to_av(
    claim_row: dict, av_data: dict | None
) -> tuple[str, float | int | None] | None:
    """Match a claim to an Alpha Vantage field by keyword + claim_type.

    Returns (av_field_name, av_value) on match, None otherwise.
    av_value may be None if AV doesn't have data for that field.
    """
    if av_data is None:
        return None

    claim_type = claim_row.get("claim_type", "")
    claim_text_lower = claim_row.get("claim_text", "").lower()

    for _matcher_name, matcher in CLAIM_MATCHERS.items():
        if claim_type != matcher["claim_type"]:
            continue
        if any(kw in claim_text_lower for kw in matcher["keywords"]):
            return (matcher["av_field"], av_data.get(matcher["av_field"]))

    return None


def _process_single_claim(
    claim_row: dict, av_data: dict | None
) -> tuple[str, int, dict] | None:
    """Process a single claim against AV data.

    Returns (status, confidence_adjustment, source_verification_json)
    or None if claim cannot be cross-checked (unverified).

    Decision tree (order matters):
    1. No AV match or AV value None → None (unverified)
    2. Primary value None or 0 → None (unverified, defensive guard)
    3. deviation > 5% → "disputed" (-15 if trade_critical, -10 otherwise)
    4. trade_critical and no Tier A → "manual_check" (-15)
    5. Otherwise → "consistent" (0)
    """
    match = _match_claim_to_av(claim_row, av_data)
    if match is None:
        return None

    _av_field, av_value = match
    if av_value is None:
        return None

    # Defensive None-check before float() — float(None) raises TypeError.
    # Normally number/ratio claims always have a value, but a bug in the
    # Claim Extractor could produce value=None.
    raw_value = claim_row.get("value")
    if raw_value is None:
        return None

    primary_value = float(raw_value)
    if math.isclose(primary_value, 0.0, abs_tol=1e-9):
        return None  # Division by zero guard

    av_value_float = float(av_value)
    deviation = _calculate_deviation(primary_value, av_value_float)

    sv_json = {
        "provider": "alpha_vantage",
        "value": av_value,
        "deviation_pct": round(deviation, 2),
        "retrieved_at": av_data.get("fetched_at", ""),
    }

    trade_critical = claim_row.get("trade_critical", False)

    # Decision tree — order is critical
    if deviation > 5.0:
        conf_adj = -15 if trade_critical else -10
        return ("disputed", conf_adj, sv_json)

    if trade_critical and not TIER_A_AVAILABLE:
        return ("manual_check", -15, sv_json)

    return ("consistent", 0, sv_json)


def _build_summary(
    total_claims: int,
    cross_checked_results: list[tuple[dict, tuple[str, int, dict]]],
) -> dict:
    """Build verification summary from cross-check results.

    Args:
        total_claims: Total number of claims for this analysis.
        cross_checked_results: List of (claim_row, (status, conf_adj, sv_json))
            for claims that were successfully cross-checked.
    """
    counts = {"verified": 0, "consistent": 0, "disputed": 0, "manual_check": 0}

    has_blocking_disputed = False

    for claim_row, (status, _conf_adj, _sv_json) in cross_checked_results:
        if status in counts:
            counts[status] += 1
        if status == "disputed" and claim_row.get("trade_critical", False):
            has_blocking_disputed = True

    unverified_count = total_claims - len(cross_checked_results)

    return {
        "verified": counts["verified"],
        "consistent": counts["consistent"],
        "unverified": unverified_count,
        "disputed": counts["disputed"],
        "manual_check": counts["manual_check"],
        "has_blocking_disputed": has_blocking_disputed,
    }


# --- Orchestrator ---


def run_verification(analysis_id: str, user_id: str) -> VerificationResult:
    """Cross-check claims against Alpha Vantage data.

    Phase A: Pre-condition checks (no external calls).
    Phase B: AV fetch + claim processing + DB writes.

    Raises:
        PreconditionError: Analysis not found, wrong user, no claims, already verified.
        ConfigurationError: AV API key not configured.
    """
    admin = get_supabase_admin()

    # --- Phase A: Pre-Condition Checks ---

    # 1. Fetch analysis_run
    run_resp = (
        admin.table("analysis_runs").select("*").eq("id", analysis_id).execute()
    )
    if not run_resp.data:
        raise PreconditionError("Analysis run not found")

    run_row = run_resp.data[0]

    # 2. Verify ownership (same error message — no info leak)
    if run_row["user_id"] != user_id:
        raise PreconditionError("Analysis run not found")

    # 3. Fetch claims
    claims_resp = (
        admin.table("claims").select("*").eq("analysis_id", analysis_id).execute()
    )
    if not claims_resp.data:
        raise PreconditionError("No claims found for this analysis")

    claims_rows = claims_resp.data

    # 4. Idempotency check — prevent duplicate verification
    claim_ids = [c["id"] for c in claims_rows]
    existing_resp = (
        admin.table("verification_results")
        .select("id")
        .in_("claim_id", claim_ids)
        .execute()
    )
    if existing_resp.data:
        raise PreconditionError(
            "Verification already exists for this analysis. "
            "Delete existing results before re-verifying."
        )

    # 5. Check AV API key
    settings = get_settings()
    if not settings.alpha_vantage_api_key:
        raise ConfigurationError("Alpha Vantage API key not configured")

    # --- Phase B: Execution ---

    ticker = run_row["ticker"]

    # Fetch AV data with retry (graceful degradation on failure)
    av_data = None
    client = AlphaVantageClient()
    try:
        av_data = retry_with_backoff(
            lambda: client.get_fundamentals(ticker),
            max_retries=2,  # 1 initial + 1 retry (AV has 25/day limit)
            provider="alpha_vantage",
            on_error=lambda exc, attempt: log_error(
                component="verification",
                error_type="av_fetch_failed",
                message=f"AV attempt {attempt}: {exc}",
                analysis_id=analysis_id,
            ),
        )
    except DataProviderError as exc:
        log_error(
            component="verification",
            error_type="av_all_failed",
            message=str(exc),
            analysis_id=analysis_id,
        )
        # av_data stays None → all claims become unverified
    finally:
        client.close()

    # Process each claim
    cross_checked: list[tuple[dict, tuple[str, int, dict]]] = []
    for claim_row in claims_rows:
        result = _process_single_claim(claim_row, av_data)
        if result is not None:
            cross_checked.append((claim_row, result))

    # Build summary
    summary = _build_summary(
        total_claims=len(claims_rows),
        cross_checked_results=cross_checked,
    )

    # Batch INSERT verification_results (only cross-checked claims)
    rows_to_insert = [
        {
            "claim_id": claim["id"],
            "source_verification": sv_json,
            "status": status,
            "confidence_adjustment": conf_adj,
        }
        for claim, (status, conf_adj, sv_json) in cross_checked
    ]

    if rows_to_insert:
        try:
            admin.table("verification_results").insert(rows_to_insert).execute()
        except Exception as exc:
            logger.error("Failed to insert verification_results for %s: %s", analysis_id, exc)
            log_error(
                component="verification",
                error_type="db_write_failed",
                message=str(exc),
                analysis_id=analysis_id,
            )
            return VerificationResult(
                analysis_id=analysis_id,
                status="failed",
                summary=summary,
                error_message="Failed to save verification results to database.",
            )

    # Update analysis_runs.verification summary (best-effort)
    try:
        admin.table("analysis_runs").update(
            {"verification": summary}
        ).eq("id", analysis_id).execute()
    except Exception as exc:
        logger.warning("Failed to update analysis_runs verification summary: %s", exc)

    return VerificationResult(
        analysis_id=analysis_id,
        status="completed",
        summary=summary,
        results_count=len(rows_to_insert),
    )
