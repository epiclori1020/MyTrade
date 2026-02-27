"""Data Collector — orchestrates fetching from providers and writing to Supabase.

Deterministic (no LLM). Fetches fundamentals, prices, news, and insider data
for a single ticker. Writes to stock_fundamentals and stock_prices tables.
"""

import logging
from dataclasses import dataclass, field

from src.constants import is_valid_ticker
from src.services.alpha_vantage import AlphaVantageClient
from src.services.error_logger import log_error
from src.services.exceptions import DataProviderError
from src.services.finnhub import FinnhubClient
from src.services.retry import retry_with_backoff
from src.services.supabase import get_supabase_admin

logger = logging.getLogger(__name__)

# Columns that exist in stock_fundamentals table (for filtering before DB write)
# Includes fetched_at so upserts update the timestamp on re-fetch.
FUNDAMENTALS_DB_COLUMNS = {
    "ticker", "period", "revenue", "net_income", "free_cash_flow",
    "total_debt", "total_equity", "eps", "pe_ratio", "pb_ratio",
    "ev_ebitda", "roe", "roic", "f_score", "z_score", "source",
    "fetched_at",
}

# Columns that exist in stock_prices table
PRICES_DB_COLUMNS = {
    "ticker", "date", "open", "high", "low", "close", "volume", "source",
}

# Batch size for stock_prices upserts
PRICES_BATCH_SIZE = 100


@dataclass
class CollectionResult:
    """Result of a data collection run for a single ticker."""
    ticker: str
    status: str  # "success" | "partial" | "error"
    fundamentals: dict | None = None
    prices_count: int = 0
    news: list[dict] = field(default_factory=list)
    insider_trades: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def collect_ticker_data(ticker: str) -> CollectionResult:
    """Collect all available data for a ticker.

    Flow:
    1. Validate ticker in MVP_UNIVERSE
    2. Fetch company profile (for shareOutstanding)
    3. Fetch fundamentals (Finnhub primary → AV fallback)
    4. Fetch candles (1yr historical OHLCV)
    5. Fetch current quote
    6. Fetch news (non-critical)
    7. Fetch insider transactions (non-critical)
    8. Write fundamentals + prices to DB
    """
    ticker = ticker.upper()
    if not is_valid_ticker(ticker):
        return CollectionResult(
            ticker=ticker,
            status="error",
            errors=[f"{ticker} is not in the MVP universe"],
        )

    result = CollectionResult(ticker=ticker, status="success")
    finnhub = FinnhubClient()

    try:
        # Step 1: Fetch company profile (non-critical, single attempt)
        profile = _fetch_profile(finnhub, ticker, result)

        # Step 2: Fetch fundamentals (Finnhub → AV fallback)
        fundamentals = _fetch_fundamentals(finnhub, ticker, profile, result)
        result.fundamentals = fundamentals

        # Step 3: Fetch candles (Finnhub only, no AV fallback for OHLCV)
        candles = _fetch_candles(finnhub, ticker, result)

        # Step 4: Fetch current quote (Finnhub only)
        quote = _fetch_quote(finnhub, ticker, result)

        # Step 5: Fetch news (non-critical, single attempt)
        result.news = _fetch_news(finnhub, ticker, result)

        # Step 6: Fetch insider transactions (non-critical, single attempt)
        result.insider_trades = _fetch_insider_transactions(finnhub, ticker, result)

    finally:
        finnhub.close()

    # Step 7: Write to database
    _write_fundamentals(fundamentals, result)
    _write_prices(candles, quote, result)

    # Determine final status
    if result.errors:
        result.status = "partial" if result.fundamentals or result.prices_count > 0 else "error"

    return result


def _fetch_profile(finnhub: FinnhubClient, ticker: str, result: CollectionResult) -> dict | None:
    """Fetch company profile (single attempt, non-critical)."""
    try:
        return finnhub.get_profile(ticker)
    except Exception as exc:
        msg = f"Profile fetch failed: {exc}"
        logger.warning(msg)
        result.errors.append(msg)
        log_error("data_collector", "profile_fetch_failed", str(exc))
        return None


def _fetch_fundamentals(
    finnhub: FinnhubClient,
    ticker: str,
    profile: dict | None,
    result: CollectionResult,
) -> dict | None:
    """Fetch fundamentals: Finnhub primary → Alpha Vantage fallback."""
    # Try Finnhub first (3 retries)
    try:
        return retry_with_backoff(
            lambda: finnhub.get_fundamentals(ticker, profile),
            provider="finnhub",
            on_error=lambda exc, attempt: log_error(
                "data_collector", "finnhub_fundamentals_retry",
                str(exc), retry_count=attempt,
            ),
        )
    except DataProviderError as finnhub_exc:
        result.errors.append(f"Finnhub fundamentals failed: {finnhub_exc}")

    # Fallback to Alpha Vantage (1 retry only — 25/day limit)
    av = AlphaVantageClient()
    try:
        return retry_with_backoff(
            lambda: av.get_fundamentals(ticker),
            max_retries=1,
            provider="alpha_vantage",
            on_error=lambda exc, attempt: log_error(
                "data_collector", "av_fundamentals_retry",
                str(exc), retry_count=attempt,
            ),
        )
    except DataProviderError as av_exc:
        result.errors.append(f"Alpha Vantage fundamentals failed: {av_exc}")
        log_error("data_collector", "fundamentals_all_failed",
                  f"Both providers failed for {ticker}")
        return None
    finally:
        av.close()


def _fetch_candles(
    finnhub: FinnhubClient, ticker: str, result: CollectionResult,
) -> list[dict]:
    """Fetch historical candles (Finnhub only, no AV fallback for OHLCV)."""
    try:
        return retry_with_backoff(
            lambda: finnhub.get_candles(ticker),
            provider="finnhub",
            on_error=lambda exc, attempt: log_error(
                "data_collector", "finnhub_candles_retry",
                str(exc), retry_count=attempt,
            ),
        )
    except DataProviderError as exc:
        result.errors.append(f"Candles fetch failed: {exc}")
        return []


def _fetch_quote(
    finnhub: FinnhubClient, ticker: str, result: CollectionResult,
) -> dict | None:
    """Fetch current quote (Finnhub only)."""
    try:
        return retry_with_backoff(
            lambda: finnhub.get_quote(ticker),
            provider="finnhub",
            on_error=lambda exc, attempt: log_error(
                "data_collector", "finnhub_quote_retry",
                str(exc), retry_count=attempt,
            ),
        )
    except DataProviderError as exc:
        result.errors.append(f"Quote fetch failed: {exc}")
        return None


def _fetch_news(
    finnhub: FinnhubClient, ticker: str, result: CollectionResult,
) -> list[dict]:
    """Fetch news (single attempt, non-critical)."""
    try:
        return finnhub.get_news(ticker)
    except Exception as exc:
        msg = f"News fetch failed: {exc}"
        logger.warning(msg)
        result.errors.append(msg)
        return []


def _fetch_insider_transactions(
    finnhub: FinnhubClient, ticker: str, result: CollectionResult,
) -> list[dict]:
    """Fetch insider transactions (single attempt, non-critical)."""
    try:
        return finnhub.get_insider_transactions(ticker)
    except Exception as exc:
        msg = f"Insider transactions fetch failed: {exc}"
        logger.warning(msg)
        result.errors.append(msg)
        return []


def _write_fundamentals(fundamentals: dict | None, result: CollectionResult) -> None:
    """Write fundamentals to stock_fundamentals table."""
    if not fundamentals:
        return

    # Strip internal fields (keys starting with _)
    row = {k: v for k, v in fundamentals.items() if k in FUNDAMENTALS_DB_COLUMNS}

    try:
        admin = get_supabase_admin()
        admin.table("stock_fundamentals").upsert(
            row, on_conflict="ticker,period,source"
        ).execute()
    except Exception as exc:
        msg = f"DB write (stock_fundamentals) failed: {exc}"
        logger.error(msg)
        result.errors.append(msg)
        log_error("data_collector", "db_write_fundamentals_failed", str(exc))


def _write_prices(
    candles: list[dict], quote: dict | None, result: CollectionResult,
) -> None:
    """Write candles + quote to stock_prices table in batches."""
    if not candles and not quote:
        return

    admin = get_supabase_admin()
    total_written = 0

    # Write candles in batches
    for i in range(0, len(candles), PRICES_BATCH_SIZE):
        batch = candles[i:i + PRICES_BATCH_SIZE]
        # Filter to DB columns only
        batch = [{k: v for k, v in row.items() if k in PRICES_DB_COLUMNS} for row in batch]
        try:
            admin.table("stock_prices").upsert(
                batch, on_conflict="ticker,date"
            ).execute()
            total_written += len(batch)
        except Exception as exc:
            msg = f"DB write (stock_prices batch {i}) failed: {exc}"
            logger.error(msg)
            result.errors.append(msg)
            log_error("data_collector", "db_write_prices_failed", str(exc))

    # Write quote (after candles so today's quote overwrites candle close)
    if quote:
        row = {k: v for k, v in quote.items() if k in PRICES_DB_COLUMNS}
        try:
            admin.table("stock_prices").upsert(
                row, on_conflict="ticker,date"
            ).execute()
            total_written += 1
        except Exception as exc:
            msg = f"DB write (stock_prices quote) failed: {exc}"
            logger.error(msg)
            result.errors.append(msg)
            log_error("data_collector", "db_write_quote_failed", str(exc))

    result.prices_count = total_written
