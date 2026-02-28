"""Fundamental Analysis Orchestrator — coordinates DB reads, agent call, DB writes.

Follows data_collector.py pattern: dataclass result, isolated error handling,
best-effort logging. Two-phase architecture:

Phase A (Pre-Conditions): Checks before any tokens are consumed.
    Failures raise exceptions → no analysis_run created, no cost.

Phase B (LLM Execution): Creates analysis_run, calls agent, logs cost.
    Failures return AnalysisResult with status="failed" + cost tracking.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from src.agents.fundamental import call_fundamental_agent
from src.config import get_settings
from src.services.error_logger import log_error
from src.services.exceptions import AgentError, ConfigurationError, PreconditionError
from src.services.supabase import get_supabase_admin

logger = logging.getLogger(__name__)

# Claude Sonnet 4.6 pricing (as of 2026-02)
SONNET_INPUT_PRICE_PER_TOKEN = 3.0 / 1_000_000  # $3/MTok
SONNET_OUTPUT_PRICE_PER_TOKEN = 15.0 / 1_000_000  # $15/MTok


@dataclass
class AnalysisResult:
    """Result of a fundamental analysis run."""

    ticker: str
    analysis_id: str
    status: str  # "completed" | "failed"
    fundamental_out: dict | None = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    error_message: str | None = None


def _calculate_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * SONNET_INPUT_PRICE_PER_TOKEN
        + output_tokens * SONNET_OUTPUT_PRICE_PER_TOKEN
    )


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_utc_iso() -> str:
    return _now_utc().isoformat()


def run_fundamental_analysis(ticker: str, user_id: str) -> AnalysisResult:
    """Run fundamental analysis for a ticker.

    Phase A: Pre-condition checks (no tokens consumed).
    Phase B: LLM call with full cost tracking.

    Raises:
        PreconditionError: No fundamental data in DB.
        ConfigurationError: ANTHROPIC_API_KEY not set.
    """
    ticker = ticker.upper()
    admin = get_supabase_admin()

    # --- Phase A: Pre-Condition Checks ---

    # Step 1: Fetch fundamentals from DB
    fund_resp = (
        admin.table("stock_fundamentals")
        .select("*")
        .eq("ticker", ticker)
        .order("fetched_at", desc=True)
        .limit(1)
        .execute()
    )
    if not fund_resp.data:
        raise PreconditionError(
            f"No fundamental data for {ticker}. "
            f"Run POST /api/collect/{ticker} first."
        )
    fundamentals = fund_resp.data[0]

    # Step 2: Fetch current price (optional — analysis works without it)
    price_resp = (
        admin.table("stock_prices")
        .select("*")
        .eq("ticker", ticker)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    current_price = price_resp.data[0] if price_resp.data else None

    # Step 3: Check API key
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ConfigurationError("ANTHROPIC_API_KEY not configured")

    # --- Phase B: LLM Execution (tokens will be consumed) ---

    # Step 4: Create analysis_run
    run_row = {
        "user_id": user_id,
        "ticker": ticker,
        "status": "running",
        "started_at": _now_utc_iso(),
    }
    run_resp = admin.table("analysis_runs").insert(run_row).execute()
    analysis_id = run_resp.data[0]["id"]

    # Step 5: Call agent
    usage = {"input_tokens": 0, "output_tokens": 0}
    analysis_dict = None
    error_message = None

    try:
        analysis_dict, usage = call_fundamental_agent(
            ticker, fundamentals, current_price
        )
    except AgentError as exc:
        error_message = str(exc)
        if exc.usage:
            usage = exc.usage
        logger.error("Agent error for %s: %s", ticker, exc)
        log_error(
            component="fundamental_analyst",
            error_type=exc.error_type,
            message=str(exc),
            analysis_id=analysis_id,
        )
    except Exception as exc:
        error_message = f"Unexpected error: {exc}"
        logger.error("Unexpected error for %s: %s", ticker, exc, exc_info=True)
        log_error(
            component="fundamental_analyst",
            error_type="unexpected",
            message=str(exc),
            analysis_id=analysis_id,
        )

    # Step 6: Calculate cost
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    total_tokens = input_tokens + output_tokens
    cost = _calculate_cost(input_tokens, output_tokens)

    # Step 7: Log to agent_cost_log (best-effort)
    if total_tokens > 0:
        try:
            admin.table("agent_cost_log").insert({
                "analysis_id": analysis_id,
                "agent_name": "fundamental_analyst",
                "model": "claude-sonnet-4-6",
                "tier": "standard",
                "effort": "medium",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": 0,
                "cost_usd": cost,
                "fallback_from": None,
                "degraded": False,
            }).execute()
        except Exception as exc:
            logger.warning("Failed to log agent cost: %s", exc)

    # Step 8: Update analysis_run
    status = "completed" if analysis_dict else "failed"
    update = {
        "status": status,
        "completed_at": _now_utc_iso(),
        "total_tokens": total_tokens,
        "total_cost_usd": cost,
    }
    if analysis_dict:
        update["fundamental_out"] = analysis_dict
    if error_message:
        update["error_log"] = [{"error": error_message, "timestamp": _now_utc_iso()}]

    try:
        admin.table("analysis_runs").update(update).eq("id", analysis_id).execute()
    except Exception as exc:
        logger.error("Failed to update analysis_run %s: %s", analysis_id, exc)

    return AnalysisResult(
        ticker=ticker,
        analysis_id=analysis_id,
        status=status,
        fundamental_out=analysis_dict,
        tokens_used=total_tokens,
        cost_usd=cost,
        error_message=error_message,
    )
