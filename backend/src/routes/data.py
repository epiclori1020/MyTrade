"""Data collection API endpoints."""

from fastapi import HTTPException, Request

from src.constants import MVP_UNIVERSE, is_valid_ticker
from src.dependencies.auth import authenticated_router
from src.dependencies.rate_limit import limiter
from src.services.data_collector import collect_ticker_data

router = authenticated_router(prefix="/api", tags=["data"])


@router.post("/collect/{ticker}")
@limiter.limit("20/minute")
def collect_data(ticker: str, request: Request) -> dict:
    """Collect financial data for a ticker from external providers.

    Fetches fundamentals, prices, news, and insider data from Finnhub
    (primary) with Alpha Vantage fallback for fundamentals.

    Returns 200 on success or partial success, 400 for invalid ticker,
    502 when all data fetching fails completely.
    """
    if not is_valid_ticker(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Ticker '{ticker.upper()}' is not in the MVP universe. "
                   f"Allowed: {', '.join(MVP_UNIVERSE)}",
        )

    result = collect_ticker_data(ticker)

    if result.status == "error":
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"Data collection failed for {result.ticker}",
                "errors": result.errors,
            },
        )

    return {
        "status": result.status,
        "ticker": result.ticker,
        "fundamentals": _clean_fundamentals(result.fundamentals),
        "prices_count": result.prices_count,
        "news": result.news,
        "insider_trades": result.insider_trades,
        "errors": result.errors,
    }


def _clean_fundamentals(fundamentals: dict | None) -> dict | None:
    """Strip internal fields (keys starting with _) before response."""
    if not fundamentals:
        return None
    return {k: v for k, v in fundamentals.items() if not k.startswith("_")}
