"""Alpha Vantage API client — fundamentals fallback provider.

Used when Finnhub fails for fundamental data. AV OVERVIEW has fields
that Finnhub lacks (RevenueTTM, EVToEBITDA) making it a valuable
complement even when Finnhub succeeds (for Step 7 Verification).
"""

import logging
from datetime import datetime, timezone

import httpx

from src.config import get_settings
from src.services.exceptions import (
    DataProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
)
from src.services.provider_rate_limiter import alpha_vantage_limiter

logger = logging.getLogger(__name__)

PROVIDER = "alpha_vantage"


class AlphaVantageClient:
    """Client for Alpha Vantage REST API (free tier)."""

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.alpha_vantage_api_key
        self._http = httpx.Client(
            base_url="https://www.alphavantage.co",
            timeout=15.0,  # AV can be slower than Finnhub
        )

    def close(self) -> None:
        """Release the httpx connection pool."""
        self._http.close()

    def _request(self, params: dict) -> dict:
        """Rate-limited GET request to Alpha Vantage.

        Handles AV quirk: rate limits returned as HTTP 200 with "Note" or
        "Information" key instead of a proper 429 status.
        """
        alpha_vantage_limiter.acquire()
        request_params = {"apikey": self._api_key}
        request_params.update(params)

        try:
            response = self._http.get("/query", params=request_params)
        except httpx.TimeoutException:
            raise ProviderTimeoutError(PROVIDER)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(PROVIDER, f"HTTP error: {exc}")

        if response.status_code == 429:
            raise RateLimitError(PROVIDER)
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                PROVIDER,
                f"Server error: {response.status_code}",
                status_code=response.status_code,
            )
        if response.status_code != 200:
            raise DataProviderError(
                PROVIDER,
                f"Unexpected status {response.status_code}: {response.text[:200]}",
                status_code=response.status_code,
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise DataProviderError(PROVIDER, f"Invalid JSON response: {exc}")

        # AV rate limit quirk: HTTP 200 but body contains "Note" or "Information"
        if "Note" in data or "Information" in data:
            msg = data.get("Note") or data.get("Information", "Rate limit hit")
            raise RateLimitError(PROVIDER, msg)

        return data

    def get_fundamentals(self, ticker: str) -> dict:
        """Fetch fundamental data from OVERVIEW endpoint.

        AV strengths vs Finnhub:
        - RevenueTTM: direct absolute value (Finnhub only has per-share)
        - EVToEBITDA: direct value (Finnhub free tier doesn't have it)

        NOT available in OVERVIEW: NetIncomeTTM, FreeCashFlow, ROIC.
        """
        data = self._request({
            "function": "OVERVIEW",
            "symbol": ticker,
        })

        if not data or "Symbol" not in data:
            raise DataProviderError(PROVIDER, f"No overview data for {ticker}")

        now = datetime.now(timezone.utc)
        period = f"{now.year}-TTM"

        return {
            "ticker": ticker,
            "period": period,
            "revenue": _safe_int(data.get("RevenueTTM")),
            "net_income": None,  # Not available in OVERVIEW
            "free_cash_flow": None,  # Not available in OVERVIEW
            "total_debt": None,
            "total_equity": None,
            "eps": _safe_float(data.get("EPS")),
            "pe_ratio": _safe_float(data.get("PERatio")),
            "pb_ratio": _safe_float(data.get("PriceToBookRatio")),
            "ev_ebitda": _safe_float(data.get("EVToEBITDA")),
            "roe": _safe_float(data.get("ReturnOnEquityTTM")),
            "roic": None,  # Not available in OVERVIEW
            "f_score": None,
            "z_score": None,
            "source": PROVIDER,
        }


def _safe_float(value: object) -> float | None:
    """Convert a value to float, returning None for AV's special strings."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value in ("", "-", "None", "0"):
            return None
    try:
        result = float(value)
        return result if result == result else None  # NaN check
    except (ValueError, TypeError):
        return None


def _safe_int(value: object) -> int | None:
    """Convert a value to int via float, returning None on failure."""
    f = _safe_float(value)
    return int(f) if f is not None else None
