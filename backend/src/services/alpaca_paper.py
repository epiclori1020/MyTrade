"""Alpaca Paper Trading adapter (Stufe 1).

CRITICAL SAFETY — three protection layers prevent live trading:
1. Constructor check: paper_mode=False -> immediate ConfigurationError.
2. _ensure_paper_mode(): Re-checks get_settings().alpaca_paper_mode before
   every API call. Note: get_settings() is @lru_cache — this catches init
   errors but does NOT detect runtime env changes (cached instance reused).
3. Hardcoded PAPER_BASE_URL: Even if checks 1+2 fail, no request goes to
   the live API — there is no LIVE_BASE_URL in this class.

The primary safeguard is point 3 (hardcoded URL). Points 1+2 are
defence-in-depth.
"""

import logging
from functools import lru_cache

import httpx

from src.config import get_settings
from src.services.broker_adapter import (
    AccountInfo,
    BrokerAdapter,
    Order,
    OrderResult,
    Position,
)
from src.services.error_logger import log_error
from src.services.exceptions import BrokerError, ConfigurationError
from src.services.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class AlpacaPaperAdapter(BrokerAdapter):
    """Alpaca Paper Trading adapter for Stufe 1."""

    PAPER_BASE_URL = "https://paper-api.alpaca.markets"
    # LIVE_BASE_URL does NOT exist in this class — by design

    def __init__(self, api_key: str, secret_key: str, paper_mode: bool):
        if not paper_mode:
            raise ConfigurationError(
                "ALPACA_PAPER_MODE must be true. Live trading is not allowed in Stufe 1."
            )
        if not api_key:
            raise ConfigurationError("Alpaca API key not configured")
        if not secret_key:
            raise ConfigurationError("Alpaca secret key not configured")
        self._api_key = api_key
        self._secret_key = secret_key
        self._base_url = self.PAPER_BASE_URL

    def _ensure_paper_mode(self):
        """Defence-in-depth: re-check paper mode setting."""
        settings = get_settings()
        if not settings.alpaca_paper_mode:
            raise ConfigurationError("ALPACA_PAPER_MODE is not enabled in settings")

    def _headers(self) -> dict:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._secret_key,
            "Content-Type": "application/json",
        }

    def submit_order(self, order: Order) -> OrderResult:
        """Submit order to Alpaca Paper API.

        IMPORTANT: No retry_with_backoff() — a retry could cause double
        order execution. On connection errors, BrokerError is raised and
        the trade is set to 'failed'. The user can then manually re-approve.
        """
        self._ensure_paper_mode()

        payload = {
            "symbol": order.ticker,
            "qty": str(order.shares),
            "side": order.action.lower(),
            "type": order.order_type.lower(),
            "time_in_force": "day",
        }
        if order.order_type.upper() == "LIMIT":
            payload["limit_price"] = str(order.price)

        try:
            resp = httpx.post(
                f"{self._base_url}/v2/orders",
                headers=self._headers(),
                json=payload,
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return OrderResult(
                success=True,
                broker_order_id=data.get("id"),
                executed_price=float(data["filled_avg_price"]) if data.get("filled_avg_price") else None,
                executed_at=data.get("filled_at"),
            )
        except httpx.HTTPStatusError as exc:
            try:
                error_body = exc.response.json() if exc.response.content else {}
            except Exception:
                error_body = {}
            error_msg = error_body.get("message", str(exc.response.status_code))
            logger.error("Alpaca order rejected: %s", error_msg)
            return OrderResult(
                success=False,
                error_message=error_msg,
            )
        except httpx.RequestError as exc:
            logger.error("Alpaca connection error: %s", exc)
            raise BrokerError("alpaca", "Connection failed") from exc

    def get_positions(self) -> list[Position]:
        """Get current positions from Alpaca Paper account.

        Uses retry_with_backoff() — read-only, safe to retry.
        """
        self._ensure_paper_mode()

        def _fetch():
            try:
                resp = httpx.get(
                    f"{self._base_url}/v2/positions",
                    headers=self._headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                raise BrokerError(
                    "alpaca", f"HTTP {exc.response.status_code}", status_code=exc.response.status_code
                ) from exc
            except httpx.RequestError as exc:
                raise BrokerError("alpaca", "Connection failed") from exc

        data = retry_with_backoff(
            _fetch,
            max_retries=3,
            provider="alpaca",
            on_error=lambda exc, attempt: log_error(
                "broker", "positions_fetch_failed", str(exc), retry_count=attempt
            ),
        )

        return [
            Position(
                ticker=p["symbol"],
                shares=float(p["qty"]),
                avg_price=float(p["avg_entry_price"]),
                current_price=float(p["current_price"]),
                market_value=float(p["market_value"]),
            )
            for p in data
        ]

    def get_account(self) -> AccountInfo:
        """Get Alpaca Paper account summary.

        Uses retry_with_backoff() — read-only, safe to retry.
        """
        self._ensure_paper_mode()

        def _fetch():
            try:
                resp = httpx.get(
                    f"{self._base_url}/v2/account",
                    headers=self._headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                raise BrokerError(
                    "alpaca", f"HTTP {exc.response.status_code}", status_code=exc.response.status_code
                ) from exc
            except httpx.RequestError as exc:
                raise BrokerError("alpaca", "Connection failed") from exc

        data = retry_with_backoff(
            _fetch,
            max_retries=3,
            provider="alpaca",
            on_error=lambda exc, attempt: log_error(
                "broker", "account_fetch_failed", str(exc), retry_count=attempt
            ),
        )

        return AccountInfo(
            total_value=float(data["portfolio_value"]),
            cash=float(data["cash"]),
            buying_power=float(data["buying_power"]),
        )


@lru_cache
def get_broker_adapter() -> BrokerAdapter:
    """Singleton factory for the broker adapter.

    Uses @lru_cache like get_settings(). Call
    get_broker_adapter.cache_clear() in test teardown.
    """
    settings = get_settings()
    return AlpacaPaperAdapter(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
        paper_mode=settings.alpaca_paper_mode,
    )
