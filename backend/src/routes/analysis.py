"""Analysis API endpoints."""

from uuid import UUID

from fastapi import HTTPException, Request

from src.constants import MVP_UNIVERSE, is_valid_ticker
from src.dependencies.auth import authenticated_router
from src.dependencies.error_handler import handle_service_errors
from src.dependencies.rate_limit import limiter
from src.routes.helpers import sanitize_error_message
from src.services.fundamental_analysis import run_fundamental_analysis
from src.services.supabase import get_supabase_admin

router = authenticated_router(prefix="/api", tags=["analysis"])


@router.post("/analyze/{ticker}")
@limiter.limit("100/minute")
@handle_service_errors(service_name="Analysis service")
def analyze_ticker(ticker: str, request: Request) -> dict:
    """Run fundamental analysis for a ticker.

    Fetches data from DB (populated by POST /api/collect/{ticker}),
    calls the Fundamental Analyst LLM agent, and stores results.
    """
    if not is_valid_ticker(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Ticker '{ticker.upper()}' is not in the MVP universe. "
            f"Allowed: {', '.join(MVP_UNIVERSE)}",
        )

    user_id = request.state.user["id"]
    result = run_fundamental_analysis(ticker, user_id)

    return {
        "status": result.status,
        "analysis_id": result.analysis_id,
        "ticker": result.ticker,
        "fundamental_out": result.fundamental_out,
        "tokens_used": result.tokens_used,
        "cost_usd": result.cost_usd,
        "error_message": sanitize_error_message(result.error_message, "Analysis"),
    }


@router.get("/analyze/{analysis_id}")
@limiter.limit("50/minute")
@handle_service_errors(service_name="Analysis service")
def get_analysis(analysis_id: UUID, request: Request) -> dict:
    """Retrieve a completed analysis by ID.

    Returns same core fields as POST /analyze/{ticker} (minus cost/token metadata).
    Used by the frontend to reload a completed analysis via URL persistence.
    """
    user_id = request.state.user["id"]
    admin = get_supabase_admin()
    resp = (
        admin.table("analysis_runs")
        .select("id, ticker, status, fundamental_out, confidence, recommendation")
        .eq("id", str(analysis_id))
        .eq("user_id", user_id)
        .execute()
    )

    if not resp.data:
        raise HTTPException(status_code=404, detail="Analysis not found")

    row = resp.data[0]

    # Guard: only expose completed/partial analyses that have fundamental_out
    if row["status"] not in ("completed", "partial") or row["fundamental_out"] is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return {
        "analysis_id": row["id"],
        "ticker": row["ticker"],
        "status": row["status"],
        "fundamental_out": row["fundamental_out"],
    }
