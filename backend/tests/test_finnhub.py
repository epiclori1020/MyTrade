"""Tests for FinnhubClient."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.services.exceptions import (
    DataProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
)
from src.services.finnhub import FinnhubClient, _safe_float


@pytest.fixture
def client():
    """FinnhubClient with mocked rate limiter."""
    with patch("src.services.finnhub.finnhub_limiter") as mock_limiter:
        mock_limiter.acquire = MagicMock()
        with patch("src.services.finnhub.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(finnhub_api_key="test-key")
            c = FinnhubClient()
            yield c
            c.close()


class TestFinnhubGetFundamentals:
    @patch.object(httpx.Client, "get")
    def test_success_with_profile(self, mock_get, client):
        """Should compute absolute values when profile is available."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "metric": {
                "peTTM": 28.5,
                "pb": 40.2,
                "eps": 6.73,
                "roeTTM": 1.56,
                "roicTTM": 0.34,
                "salesPerShare": 25.0,
                "fcfPerShareTTM": 7.0,
            }
        }
        mock_get.return_value = mock_response

        profile = {"share_outstanding": 15000.0}  # 15B shares (in millions)
        result = client.get_fundamentals("AAPL", profile)

        assert result["ticker"] == "AAPL"
        assert result["eps"] == 6.73
        assert result["pe_ratio"] == 28.5
        assert result["pb_ratio"] == 40.2
        assert result["revenue"] == int(25.0 * 15000.0 * 1_000_000)
        assert result["free_cash_flow"] == int(7.0 * 15000.0 * 1_000_000)
        assert result["ev_ebitda"] is None  # Correctly NULL
        assert result["source"] == "finnhub"

    @patch.object(httpx.Client, "get")
    def test_without_profile_absolute_values_null(self, mock_get, client):
        """Absolute values should be NULL when profile is unavailable."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"metric": {"peTTM": 28.5, "eps": 6.73}}
        mock_get.return_value = mock_response

        result = client.get_fundamentals("AAPL", profile=None)
        assert result["revenue"] is None
        assert result["net_income"] is None
        assert result["free_cash_flow"] is None
        assert result["pe_ratio"] == 28.5


class TestFinnhubGetQuote:
    @patch.object(httpx.Client, "get")
    def test_success(self, mock_get, client):
        """Should return OHLC with NULL volume."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"o": 180.0, "h": 185.0, "l": 178.0, "c": 183.5}
        mock_get.return_value = mock_response

        result = client.get_quote("AAPL")
        assert result["ticker"] == "AAPL"
        assert result["open"] == 180.0
        assert result["close"] == 183.5
        assert result["volume"] is None


class TestFinnhubGetCandles:
    @patch.object(httpx.Client, "get")
    def test_success(self, mock_get, client):
        """Should parse OHLCV candle arrays."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "s": "ok",
            "t": [1704067200, 1704153600],
            "o": [180.0, 181.0],
            "h": [185.0, 186.0],
            "l": [178.0, 179.0],
            "c": [183.0, 184.0],
            "v": [50000000, 45000000],
        }
        mock_get.return_value = mock_response

        result = client.get_candles("AAPL", days=30)
        assert len(result) == 2
        assert result[0]["ticker"] == "AAPL"
        assert result[0]["volume"] == 50000000

    @patch.object(httpx.Client, "get")
    def test_no_data(self, mock_get, client):
        """Should return empty list when no candle data available."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"s": "no_data"}
        mock_get.return_value = mock_response

        result = client.get_candles("AAPL")
        assert result == []


class TestFinnhubGetNews:
    @patch.object(httpx.Client, "get")
    def test_success(self, mock_get, client):
        """Should return parsed news items."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"headline": "AAPL beats earnings", "source": "Reuters", "url": "https://r.com/1",
             "datetime": 1704067200, "summary": "Apple reported..."}
        ]
        mock_get.return_value = mock_response

        result = client.get_news("AAPL")
        assert len(result) == 1
        assert result[0]["headline"] == "AAPL beats earnings"


class TestFinnhubGetInsiderTransactions:
    @patch.object(httpx.Client, "get")
    def test_success(self, mock_get, client):
        """Should return parsed insider transactions."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"name": "Tim Cook", "share": 100000, "change": -50000,
                 "transactionType": "S-Sale", "filingDate": "2026-01-15"}
            ]
        }
        mock_get.return_value = mock_response

        result = client.get_insider_transactions("AAPL")
        assert len(result) == 1
        assert result[0]["name"] == "Tim Cook"


class TestFinnhubErrorHandling:
    @patch.object(httpx.Client, "get")
    def test_rate_limit_429(self, mock_get, client):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response
        with pytest.raises(RateLimitError):
            client.get_quote("AAPL")

    @patch.object(httpx.Client, "get")
    def test_server_error_503(self, mock_get, client):
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_get.return_value = mock_response
        with pytest.raises(ProviderUnavailableError):
            client.get_quote("AAPL")

    @patch.object(httpx.Client, "get")
    def test_timeout(self, mock_get, client):
        mock_get.side_effect = httpx.ReadTimeout("timeout")
        with pytest.raises(ProviderTimeoutError):
            client.get_quote("AAPL")

    @patch.object(httpx.Client, "get")
    def test_malformed_json(self, mock_get, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("bad json")
        mock_get.return_value = mock_response
        with pytest.raises(DataProviderError, match="Invalid JSON"):
            client.get_quote("AAPL")


class TestSafeFloat:
    def test_none(self):
        assert _safe_float(None) is None

    def test_number(self):
        assert _safe_float(28.5) == 28.5

    def test_nan(self):
        assert _safe_float(float("nan")) is None

    def test_invalid_string(self):
        assert _safe_float("not_a_number") is None
