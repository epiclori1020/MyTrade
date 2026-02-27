"""Finnhub API client — primary data provider for MyTrade.

Sync httpx.Client (supabase-py is sync; mixing async would require run_in_executor).
FastAPI runs sync handlers in a threadpool, so blocking is safe.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx

from src.config import get_settings
from src.services.exceptions import (
    DataProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
)
from src.services.provider_rate_limiter import finnhub_limiter

logger = logging.getLogger(__name__)

PROVIDER = "finnhub"


class FinnhubClient:
    """Client for Finnhub REST API (free tier)."""

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.finnhub_api_key
        self._http = httpx.Client(
            base_url="https://finnhub.io/api/v1",
            timeout=10.0,
        )

    def close(self) -> None:
        """Release the httpx connection pool."""
        self._http.close()

    def _request(self, endpoint: str, params: dict | None = None) -> dict:
        """Rate-limited GET request to Finnhub.

        Raises typed DataProviderError subtypes on failure.
        """
        finnhub_limiter.acquire()
        request_params = {"token": self._api_key}
        if params:
            request_params.update(params)
        try:
            response = self._http.get(endpoint, params=request_params)
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
            return response.json()
        except ValueError as exc:
            raise DataProviderError(PROVIDER, f"Invalid JSON response: {exc}")

    def get_profile(self, ticker: str) -> dict:
        """Fetch company profile from /stock/profile2.

        Returns dict with shareOutstanding and marketCapitalization.
        These are needed to compute absolute values (revenue, net_income, fcf)
        from per-share metrics in /stock/metric.
        """
        data = self._request("/stock/profile2", {"symbol": ticker})
        return {
            "share_outstanding": data.get("shareOutstanding"),  # in millions
            "market_cap": data.get("marketCapitalization"),  # in millions
            "industry": data.get("finnhubIndustry"),
            "name": data.get("name"),
        }

    def get_fundamentals(self, ticker: str, profile: dict | None = None) -> dict:
        """Fetch fundamental metrics from /stock/metric.

        Uses profile data (shareOutstanding) to compute absolute values.
        If profile is None, absolute values (revenue, net_income, fcf) will be NULL.

        Returns dict matching stock_fundamentals columns.
        """
        data = self._request("/stock/metric", {"symbol": ticker, "metric": "all"})
        metric = data.get("metric", {})

        # Log available metric keys for discovery (only at DEBUG level)
        logger.debug("Finnhub metric keys for %s: %s", ticker, sorted(metric.keys()))

        # Per-share metrics (directly available)
        sales_per_share = _safe_float(metric.get("salesPerShare"))
        eps = _safe_float(metric.get("eps"))
        fcf_per_share = _safe_float(metric.get("fcfPerShareTTM"))

        # Shares outstanding from profile (in millions → convert to actual)
        shares_outstanding = None
        if profile and profile.get("share_outstanding"):
            shares_outstanding = profile["share_outstanding"] * 1_000_000

        # Compute absolute values (NULL if profile unavailable)
        revenue = None
        net_income = None
        free_cash_flow = None
        if shares_outstanding:
            if sales_per_share is not None:
                revenue = int(sales_per_share * shares_outstanding)
            if eps is not None:
                net_income = int(eps * shares_outstanding)
            if fcf_per_share is not None:
                free_cash_flow = int(fcf_per_share * shares_outstanding)

        now = datetime.now(timezone.utc)
        period = f"{now.year}-TTM"

        return {
            "ticker": ticker,
            "period": period,
            "revenue": revenue,
            "net_income": net_income,
            "free_cash_flow": free_cash_flow,
            "total_debt": None,  # Not available as absolute value from /stock/metric
            "total_equity": None,  # Not directly available from /stock/metric
            "eps": eps,
            "pe_ratio": _safe_float(metric.get("peTTM")),
            "pb_ratio": _safe_float(metric.get("pb")),
            "ev_ebitda": None,  # Finnhub free tier does NOT provide EV/EBITDA
            "roe": _safe_float(metric.get("roeTTM")),
            "roic": _safe_float(metric.get("roicTTM")),
            "f_score": None,  # Not available from Finnhub free tier
            "z_score": None,  # Not available from Finnhub free tier
            "source": PROVIDER,
            "_raw_metric_count": len(metric),  # Debug field, stripped before DB write
        }

    def get_quote(self, ticker: str) -> dict:
        """Fetch current quote from /quote.

        Returns dict matching stock_prices columns for today.
        Note: /quote does not return volume — stays NULL.
        """
        data = self._request("/quote", {"symbol": ticker})
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return {
            "ticker": ticker,
            "date": today,
            "open": _safe_float(data.get("o")),
            "high": _safe_float(data.get("h")),
            "low": _safe_float(data.get("l")),
            "close": _safe_float(data.get("c")),
            "volume": None,  # /quote doesn't return volume
            "source": PROVIDER,
        }

    def get_candles(self, ticker: str, days: int = 365) -> list[dict]:
        """Fetch historical OHLCV candles from /stock/candle.

        Returns list of dicts matching stock_prices columns.
        """
        now = datetime.now(timezone.utc)
        to_ts = int(now.timestamp())
        from_ts = int((now - timedelta(days=days)).timestamp())

        data = self._request("/stock/candle", {
            "symbol": ticker,
            "resolution": "D",
            "from": from_ts,
            "to": to_ts,
        })

        if data.get("s") == "no_data" or "t" not in data:
            logger.warning("No candle data for %s", ticker)
            return []

        timestamps = data.get("t", [])
        opens = data.get("o", [])
        highs = data.get("h", [])
        lows = data.get("l", [])
        closes = data.get("c", [])
        volumes = data.get("v", [])

        candles = []
        for i in range(len(timestamps)):
            date = datetime.fromtimestamp(timestamps[i], tz=timezone.utc).strftime("%Y-%m-%d")
            candles.append({
                "ticker": ticker,
                "date": date,
                "open": _safe_float(opens[i] if i < len(opens) else None),
                "high": _safe_float(highs[i] if i < len(highs) else None),
                "low": _safe_float(lows[i] if i < len(lows) else None),
                "close": _safe_float(closes[i] if i < len(closes) else None),
                "volume": volumes[i] if i < len(volumes) else None,
                "source": PROVIDER,
            })

        return candles

    def get_news(self, ticker: str, days: int = 30) -> list[dict]:
        """Fetch company news from /company-news.

        Returns list of news dicts. NOT written to DB — returned in response.
        """
        now = datetime.now(timezone.utc)
        from_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        to_date = now.strftime("%Y-%m-%d")

        data = self._request("/company-news", {
            "symbol": ticker,
            "from": from_date,
            "to": to_date,
        })

        if not isinstance(data, list):
            return []

        return [
            {
                "headline": item.get("headline", ""),
                "source": item.get("source", ""),
                "url": item.get("url", ""),
                "datetime": item.get("datetime"),
                "summary": item.get("summary", ""),
            }
            for item in data[:50]  # Cap at 50 items
        ]

    def get_insider_transactions(self, ticker: str) -> list[dict]:
        """Fetch insider transactions from /stock/insider-transactions.

        Returns list of transaction dicts. NOT written to DB — returned in response.
        """
        data = self._request("/stock/insider-transactions", {"symbol": ticker})
        transactions = data.get("data", [])

        return [
            {
                "name": tx.get("name", ""),
                "share": tx.get("share"),
                "change": tx.get("change"),
                "transaction_type": tx.get("transactionType", ""),
                "filing_date": tx.get("filingDate", ""),
            }
            for tx in transactions[:20]  # Cap at 20 items
        ]


def _safe_float(value: object) -> float | None:
    """Convert a value to float, returning None on failure."""
    if value is None:
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
