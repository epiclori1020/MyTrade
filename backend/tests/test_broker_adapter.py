"""Tests for AlpacaPaperAdapter (src/services/alpaca_paper.py)
and broker_adapter dataclasses (src/services/broker_adapter.py).

All tests mock httpx and get_settings — NO real API calls.

Structure:
- TestDataclasses:     Order, OrderResult, Position, AccountInfo
- TestAlpacaInit:      Constructor safety checks (paper_mode, api_key, secret_key)
- TestEnsurePaperMode: Defence-in-depth runtime check
- TestSubmitOrder:     Success, pending, HTTP errors, connection errors, payload shape
- TestGetPositions:    Success (empty + multiple), connection error
- TestGetAccount:      Success, connection error
- TestFactory:         get_broker_adapter() singleton + cache_clear
- TestURLSafety:       No LIVE_BASE_URL on class
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import httpx
import pytest

from src.services.alpaca_paper import AlpacaPaperAdapter, get_broker_adapter
from src.services.broker_adapter import AccountInfo, Order, OrderResult, Position
from src.services.exceptions import BrokerError, ConfigurationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(
    api_key: str = "test-alpaca-key",
    secret_key: str = "test-alpaca-secret",
    paper_mode: bool = True,
) -> MagicMock:
    """Return a mock settings object with Alpaca fields."""
    s = MagicMock()
    s.alpaca_api_key = api_key
    s.alpaca_secret_key = secret_key
    s.alpaca_paper_mode = paper_mode
    return s


def _make_adapter(
    api_key: str = "test-alpaca-key",
    secret_key: str = "test-alpaca-secret",
    paper_mode: bool = True,
) -> AlpacaPaperAdapter:
    """Create a valid AlpacaPaperAdapter for use in tests."""
    return AlpacaPaperAdapter(
        api_key=api_key,
        secret_key=secret_key,
        paper_mode=paper_mode,
    )


def _make_httpx_status_error(status_code: int, message: str) -> httpx.HTTPStatusError:
    """Build an httpx.HTTPStatusError with a mock response containing JSON."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.content = b'{"message": "' + message.encode() + b'"}'
    mock_response.json.return_value = {"message": message}

    mock_request = MagicMock()
    return httpx.HTTPStatusError(
        message=f"HTTP {status_code}",
        request=mock_request,
        response=mock_response,
    )


def _make_limit_order(
    ticker: str = "AAPL",
    action: str = "BUY",
    shares: float = 10.0,
    price: float = 180.0,
) -> Order:
    return Order(
        ticker=ticker,
        action=action,
        shares=shares,
        price=price,
        order_type="LIMIT",
    )


def _make_market_order(
    ticker: str = "AAPL",
    action: str = "BUY",
    shares: float = 10.0,
    price: float = 180.0,
) -> Order:
    return Order(
        ticker=ticker,
        action=action,
        shares=shares,
        price=price,
        order_type="MARKET",
    )


# ---------------------------------------------------------------------------
# TestDataclasses
# ---------------------------------------------------------------------------

class TestDataclasses:
    """Smoke tests for the shared broker_adapter dataclasses."""

    def test_order_fields(self):
        order = Order(
            ticker="MSFT",
            action="SELL",
            shares=5.0,
            price=420.0,
            order_type="LIMIT",
            stop_loss=400.0,
        )
        assert order.ticker == "MSFT"
        assert order.action == "SELL"
        assert order.shares == 5.0
        assert order.price == 420.0
        assert order.order_type == "LIMIT"
        assert order.stop_loss == 400.0

    def test_order_stop_loss_optional(self):
        order = Order(ticker="AAPL", action="BUY", shares=1.0, price=100.0, order_type="MARKET")
        assert order.stop_loss is None

    def test_order_result_success_defaults(self):
        result = OrderResult(success=True, broker_order_id="ord-123", executed_price=181.5)
        assert result.success is True
        assert result.broker_order_id == "ord-123"
        assert result.executed_price == 181.5
        assert result.error_message is None

    def test_order_result_failure_defaults(self):
        result = OrderResult(success=False, error_message="Insufficient buying power")
        assert result.success is False
        assert result.broker_order_id is None
        assert result.executed_price is None
        assert result.error_message == "Insufficient buying power"

    def test_position_fields(self):
        pos = Position(
            ticker="AAPL",
            shares=10.0,
            avg_price=175.0,
            current_price=185.0,
            market_value=1850.0,
        )
        assert pos.ticker == "AAPL"
        assert pos.market_value == 1850.0

    def test_account_info_fields(self):
        acct = AccountInfo(
            total_value=100_000.0,
            cash=15_000.0,
            buying_power=30_000.0,
        )
        assert acct.total_value == 100_000.0
        assert acct.cash == 15_000.0
        assert acct.buying_power == 30_000.0


# ---------------------------------------------------------------------------
# TestAlpacaInit
# ---------------------------------------------------------------------------

class TestAlpacaInit:
    """Constructor safety checks — three protection layers."""

    def test_paper_mode_false_raises_configuration_error(self):
        """paper_mode=False must raise ConfigurationError immediately."""
        with pytest.raises(ConfigurationError, match="ALPACA_PAPER_MODE must be true"):
            AlpacaPaperAdapter(
                api_key="key",
                secret_key="secret",
                paper_mode=False,
            )

    def test_empty_api_key_raises_configuration_error(self):
        """An empty api_key must raise ConfigurationError."""
        with pytest.raises(ConfigurationError, match="Alpaca API key not configured"):
            AlpacaPaperAdapter(api_key="", secret_key="secret", paper_mode=True)

    def test_empty_secret_key_raises_configuration_error(self):
        """An empty secret_key must raise ConfigurationError."""
        with pytest.raises(ConfigurationError, match="Alpaca secret key not configured"):
            AlpacaPaperAdapter(api_key="key", secret_key="", paper_mode=True)

    def test_valid_init_succeeds(self):
        """All required fields provided — adapter must be created without error."""
        adapter = AlpacaPaperAdapter(
            api_key="valid-key",
            secret_key="valid-secret",
            paper_mode=True,
        )
        assert isinstance(adapter, AlpacaPaperAdapter)


# ---------------------------------------------------------------------------
# TestEnsurePaperMode
# ---------------------------------------------------------------------------

class TestEnsurePaperMode:
    """Defence-in-depth: runtime re-check of alpaca_paper_mode."""

    @patch("src.services.alpaca_paper.get_settings")
    def test_passes_when_paper_mode_true(self, mock_get_settings):
        """_ensure_paper_mode() must not raise when alpaca_paper_mode=True."""
        mock_get_settings.return_value = _make_settings(paper_mode=True)
        adapter = _make_adapter()
        # Should not raise.
        adapter._ensure_paper_mode()

    @patch("src.services.alpaca_paper.get_settings")
    def test_raises_when_paper_mode_false(self, mock_get_settings):
        """_ensure_paper_mode() must raise ConfigurationError when setting is False."""
        # Bypass constructor check (only override the runtime re-check).
        mock_get_settings.return_value = _make_settings(paper_mode=False)
        adapter = _make_adapter(paper_mode=True)  # constructor OK
        with pytest.raises(ConfigurationError, match="ALPACA_PAPER_MODE is not enabled"):
            adapter._ensure_paper_mode()


# ---------------------------------------------------------------------------
# TestSubmitOrder
# ---------------------------------------------------------------------------

class TestSubmitOrder:
    """submit_order() — success paths, error paths, and payload shape."""

    @patch("src.services.alpaca_paper.get_settings")
    @patch("httpx.post")
    def test_success_returns_order_result_with_broker_id(self, mock_post, mock_get_settings):
        """Successful order: broker_order_id comes from data['id']."""
        mock_get_settings.return_value = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "alpaca-order-abc123",
            "filled_avg_price": "181.50",
            "filled_at": "2026-03-01T10:00:00Z",
        }
        mock_post.return_value = mock_resp

        adapter = _make_adapter()
        result = adapter.submit_order(_make_limit_order())

        assert result.success is True
        assert result.broker_order_id == "alpaca-order-abc123"
        assert result.executed_price == pytest.approx(181.50)
        assert result.executed_at == "2026-03-01T10:00:00Z"
        assert result.error_message is None

    @patch("src.services.alpaca_paper.get_settings")
    @patch("httpx.post")
    def test_pending_order_filled_avg_price_none(self, mock_post, mock_get_settings):
        """Pending order: filled_avg_price=None -> executed_price=None."""
        mock_get_settings.return_value = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "alpaca-order-pending",
            "filled_avg_price": None,
            "filled_at": None,
        }
        mock_post.return_value = mock_resp

        adapter = _make_adapter()
        result = adapter.submit_order(_make_limit_order())

        assert result.success is True
        assert result.broker_order_id == "alpaca-order-pending"
        assert result.executed_price is None
        assert result.executed_at is None

    @patch("src.services.alpaca_paper.get_settings")
    @patch("httpx.post")
    def test_403_insufficient_buying_power_returns_failure(self, mock_post, mock_get_settings):
        """HTTP 403: returns OrderResult(success=False) with error message."""
        mock_get_settings.return_value = _make_settings()
        mock_post.return_value = MagicMock()
        mock_post.return_value.raise_for_status.side_effect = _make_httpx_status_error(
            403, "insufficient buying power"
        )

        adapter = _make_adapter()
        result = adapter.submit_order(_make_limit_order())

        assert result.success is False
        assert result.error_message == "insufficient buying power"
        assert result.broker_order_id is None

    @patch("src.services.alpaca_paper.get_settings")
    @patch("httpx.post")
    def test_422_invalid_order_returns_failure(self, mock_post, mock_get_settings):
        """HTTP 422: returns OrderResult(success=False) with error message."""
        mock_get_settings.return_value = _make_settings()
        mock_post.return_value = MagicMock()
        mock_post.return_value.raise_for_status.side_effect = _make_httpx_status_error(
            422, "qty must be a positive integer"
        )

        adapter = _make_adapter()
        result = adapter.submit_order(_make_limit_order())

        assert result.success is False
        assert result.error_message == "qty must be a positive integer"

    @patch("src.services.alpaca_paper.get_settings")
    @patch("httpx.post")
    def test_http_error_with_non_json_body_falls_back_to_status_code(
        self, mock_post, mock_get_settings
    ):
        """HTTP error with non-JSON response body: falls back to status code as message."""
        mock_get_settings.return_value = _make_settings()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.content = b"<html>Internal Server Error</html>"
        mock_response.json.side_effect = ValueError("No JSON")
        mock_request = MagicMock()
        error = httpx.HTTPStatusError(
            message="HTTP 500", request=mock_request, response=mock_response
        )

        mock_post.return_value = MagicMock()
        mock_post.return_value.raise_for_status.side_effect = error

        adapter = _make_adapter()
        result = adapter.submit_order(_make_limit_order())

        assert result.success is False
        assert result.error_message == "500"

    @patch("src.services.alpaca_paper.get_settings")
    @patch("httpx.post")
    def test_timeout_raises_broker_error(self, mock_post, mock_get_settings):
        """Timeout on submit_order raises BrokerError (no retry)."""
        mock_get_settings.return_value = _make_settings()
        mock_post.side_effect = httpx.ReadTimeout("timed out")

        adapter = _make_adapter()
        with pytest.raises(BrokerError, match="Connection failed"):
            adapter.submit_order(_make_limit_order())

    @patch("src.services.alpaca_paper.get_settings")
    @patch("httpx.post")
    def test_connection_error_raises_broker_error(self, mock_post, mock_get_settings):
        """Connection error on submit_order raises BrokerError (no retry)."""
        mock_get_settings.return_value = _make_settings()
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        adapter = _make_adapter()
        with pytest.raises(BrokerError, match="Connection failed"):
            adapter.submit_order(_make_limit_order())

    @patch("src.services.alpaca_paper.get_settings")
    @patch("httpx.post")
    def test_limit_order_payload_contains_limit_price(self, mock_post, mock_get_settings):
        """LIMIT order must include 'limit_price' in the posted payload."""
        mock_get_settings.return_value = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "ord-1",
            "filled_avg_price": "180.00",
            "filled_at": None,
        }
        mock_post.return_value = mock_resp

        order = _make_limit_order(price=180.0)
        _make_adapter().submit_order(order)

        _, call_kwargs = mock_post.call_args
        payload = call_kwargs["json"]
        assert "limit_price" in payload
        assert payload["limit_price"] == "180.0"

    @patch("src.services.alpaca_paper.get_settings")
    @patch("httpx.post")
    def test_market_order_payload_omits_limit_price(self, mock_post, mock_get_settings):
        """MARKET order must NOT include 'limit_price' in the posted payload."""
        mock_get_settings.return_value = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "ord-2",
            "filled_avg_price": "182.00",
            "filled_at": None,
        }
        mock_post.return_value = mock_resp

        order = _make_market_order(price=182.0)
        _make_adapter().submit_order(order)

        _, call_kwargs = mock_post.call_args
        payload = call_kwargs["json"]
        assert "limit_price" not in payload

    @patch("src.services.alpaca_paper.get_settings")
    @patch("httpx.post")
    def test_buy_order_payload_side_is_buy(self, mock_post, mock_get_settings):
        """BUY order must have side='buy' (lowercase) in payload."""
        mock_get_settings.return_value = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "ord-3",
            "filled_avg_price": None,
            "filled_at": None,
        }
        mock_post.return_value = mock_resp

        order = _make_limit_order(action="BUY")
        _make_adapter().submit_order(order)

        _, call_kwargs = mock_post.call_args
        payload = call_kwargs["json"]
        assert payload["side"] == "buy"

    @patch("src.services.alpaca_paper.get_settings")
    @patch("httpx.post")
    def test_sell_order_payload_side_is_sell(self, mock_post, mock_get_settings):
        """SELL order must have side='sell' (lowercase) in payload."""
        mock_get_settings.return_value = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "ord-4",
            "filled_avg_price": None,
            "filled_at": None,
        }
        mock_post.return_value = mock_resp

        order = _make_limit_order(ticker="AAPL", action="SELL")
        _make_adapter().submit_order(order)

        _, call_kwargs = mock_post.call_args
        payload = call_kwargs["json"]
        assert payload["side"] == "sell"


# ---------------------------------------------------------------------------
# TestGetPositions
# ---------------------------------------------------------------------------

class TestGetPositions:
    """get_positions() — uses retry_with_backoff internally (read-only)."""

    @patch("src.services.alpaca_paper.get_settings")
    @patch("src.services.retry.time.sleep")
    @patch("httpx.get")
    def test_empty_positions_returns_empty_list(self, mock_get, mock_sleep, mock_get_settings):
        """Empty positions list from API returns []."""
        mock_get_settings.return_value = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        adapter = _make_adapter()
        result = adapter.get_positions()

        assert result == []

    @patch("src.services.alpaca_paper.get_settings")
    @patch("src.services.retry.time.sleep")
    @patch("httpx.get")
    def test_multiple_positions_correctly_mapped(self, mock_get, mock_sleep, mock_get_settings):
        """Multiple positions are mapped correctly to Position dataclasses."""
        mock_get_settings.return_value = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "symbol": "AAPL",
                "qty": "10",
                "avg_entry_price": "175.00",
                "current_price": "185.00",
                "market_value": "1850.00",
            },
            {
                "symbol": "MSFT",
                "qty": "5",
                "avg_entry_price": "400.00",
                "current_price": "420.00",
                "market_value": "2100.00",
            },
        ]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        adapter = _make_adapter()
        result = adapter.get_positions()

        assert len(result) == 2
        aapl = result[0]
        assert isinstance(aapl, Position)
        assert aapl.ticker == "AAPL"
        assert aapl.shares == pytest.approx(10.0)
        assert aapl.avg_price == pytest.approx(175.0)
        assert aapl.current_price == pytest.approx(185.0)
        assert aapl.market_value == pytest.approx(1850.0)

        msft = result[1]
        assert msft.ticker == "MSFT"
        assert msft.shares == pytest.approx(5.0)
        assert msft.market_value == pytest.approx(2100.0)

    @patch("src.services.alpaca_paper.get_settings")
    @patch("src.services.retry.time.sleep")
    @patch("httpx.get")
    def test_connection_error_raises_broker_error(self, mock_get, mock_sleep, mock_get_settings):
        """ConnectError inside _fetch raises BrokerError after all retries."""
        mock_get_settings.return_value = _make_settings()
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        adapter = _make_adapter()
        with pytest.raises(BrokerError, match="Connection failed"):
            adapter.get_positions()

        # retry_with_backoff fires 3 attempts (max_retries=3).
        assert mock_get.call_count == 3


# ---------------------------------------------------------------------------
# TestGetAccount
# ---------------------------------------------------------------------------

class TestGetAccount:
    """get_account() — uses retry_with_backoff internally (read-only)."""

    @patch("src.services.alpaca_paper.get_settings")
    @patch("src.services.retry.time.sleep")
    @patch("httpx.get")
    def test_valid_response_correctly_mapped(self, mock_get, mock_sleep, mock_get_settings):
        """Valid API response is mapped to AccountInfo dataclass."""
        mock_get_settings.return_value = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "portfolio_value": "105000.00",
            "cash": "20000.00",
            "buying_power": "40000.00",
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        adapter = _make_adapter()
        result = adapter.get_account()

        assert isinstance(result, AccountInfo)
        assert result.total_value == pytest.approx(105_000.0)
        assert result.cash == pytest.approx(20_000.0)
        assert result.buying_power == pytest.approx(40_000.0)

    @patch("src.services.alpaca_paper.get_settings")
    @patch("src.services.retry.time.sleep")
    @patch("httpx.get")
    def test_connection_error_raises_broker_error(self, mock_get, mock_sleep, mock_get_settings):
        """ConnectError inside _fetch raises BrokerError after all retries."""
        mock_get_settings.return_value = _make_settings()
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        adapter = _make_adapter()
        with pytest.raises(BrokerError, match="Connection failed"):
            adapter.get_account()

        # retry_with_backoff fires 3 attempts.
        assert mock_get.call_count == 3


# ---------------------------------------------------------------------------
# TestFactory
# ---------------------------------------------------------------------------

class TestFactory:
    """get_broker_adapter() singleton factory and lru_cache behaviour."""

    def teardown_method(self):
        """Clear lru_cache after every test to avoid cross-test contamination."""
        get_broker_adapter.cache_clear()

    @patch("src.services.alpaca_paper.get_settings")
    def test_factory_creates_adapter_from_settings(self, mock_get_settings):
        """Factory must produce an AlpacaPaperAdapter using settings values."""
        mock_get_settings.return_value = _make_settings(
            api_key="factory-key",
            secret_key="factory-secret",
            paper_mode=True,
        )
        adapter = get_broker_adapter()
        assert isinstance(adapter, AlpacaPaperAdapter)
        assert adapter._api_key == "factory-key"
        assert adapter._secret_key == "factory-secret"

    @patch("src.services.alpaca_paper.get_settings")
    def test_factory_returns_same_instance_on_repeated_calls(self, mock_get_settings):
        """@lru_cache must return the identical object on every call."""
        mock_get_settings.return_value = _make_settings()
        first = get_broker_adapter()
        second = get_broker_adapter()
        assert first is second

    @patch("src.services.alpaca_paper.get_settings")
    def test_factory_cache_clear_allows_new_instance(self, mock_get_settings):
        """After cache_clear(), a fresh adapter is created on the next call."""
        mock_get_settings.return_value = _make_settings()
        first = get_broker_adapter()
        get_broker_adapter.cache_clear()
        second = get_broker_adapter()
        # Two separate instances after cache invalidation.
        assert first is not second


# ---------------------------------------------------------------------------
# TestURLSafety
# ---------------------------------------------------------------------------

class TestURLSafety:
    """Hardcoded URL safety — third protection layer against live trading."""

    def test_no_live_base_url_attribute_on_class(self):
        """LIVE_BASE_URL must NOT exist on AlpacaPaperAdapter.

        This is the third protection layer: even if paper_mode checks are
        somehow bypassed, there is no live API URL to send requests to.
        """
        assert not hasattr(AlpacaPaperAdapter, "LIVE_BASE_URL")

    def test_paper_base_url_points_to_paper_domain(self):
        """PAPER_BASE_URL must point to paper-api.alpaca.markets."""
        assert "paper-api.alpaca.markets" in AlpacaPaperAdapter.PAPER_BASE_URL
