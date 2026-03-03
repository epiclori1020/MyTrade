"""Analysis API endpoints."""

import logging

from fastapi import HTTPException, Request

from src.constants import MVP_UNIVERSE, is_valid_ticker
from src.dependencies.auth import authenticated_router
from src.dependencies.rate_limit import limiter
from src.routes.helpers import sanitize_error_message
from src.services.exceptions import BudgetExhaustedError, ConfigurationError, PreconditionError
from src.services.fundamental_analysis import run_fundamental_analysis

logger = logging.getLogger(__name__)

router = authenticated_router(prefix="/api", tags=["analysis"])


@router.post("/analyze/{ticker}")
@limiter.limit("100/minute")
def analyze_ticker(ticker: str, request: Request) -> dict:
    """Run fundamental analysis for a ticker.

    Fetches data from DB (populated by POST /api/collect/{ticker}),
    calls the Fundamental Analyst LLM agent, and stores results.

    Returns 200 with status="completed" or status="failed" (agent errors).
    Returns 400 for invalid ticker or missing data.
    Returns 503 for server misconfiguration.
    """
    if not is_valid_ticker(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Ticker '{ticker.upper()}' is not in the MVP universe. "
            f"Allowed: {', '.join(MVP_UNIVERSE)}",
        )

    user_id = request.state.user["id"]

    try:
        result = run_fundamental_analysis(ticker, user_id)
    except PreconditionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except BudgetExhaustedError:
        raise HTTPException(
            status_code=503,
            detail="Monthly API budget exhausted. Try again next month.",
        )
    except ConfigurationError as exc:
        logger.error("Configuration error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Analysis service temporarily unavailable",
        )
    except Exception as exc:
        logger.error("Unexpected error analyzing %s: %s", ticker, exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Analysis service temporarily unavailable",
        )

    return {
        "status": result.status,
        "analysis_id": result.analysis_id,
        "ticker": result.ticker,
        "fundamental_out": result.fundamental_out,
        "tokens_used": result.tokens_used,
        "cost_usd": result.cost_usd,
        "error_message": sanitize_error_message(result.error_message, "Analysis"),
    }
