"""Tests for AlphaVantageClient."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.services.alpha_vantage import AlphaVantageClient, _safe_float
from src.services.exceptions import (
    DataProviderError,
    ProviderTimeoutError,
    RateLimitError,
)


@pytest.fixture
def client():
    """AlphaVantageClient with mocked rate limiter."""
    with patch("src.services.alpha_vantage.alpha_vantage_limiter") as mock_limiter:
        mock_limiter.acquire = MagicMock()
        with patch("src.services.alpha_vantage.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(alpha_vantage_api_key="test-key")
            c = AlphaVantageClient()
            yield c
            c.close()


class TestAlphaVantageGetFundamentals:
    @patch.object(httpx.Client, "get")
    def test_success(self, mock_get, client):
        """Should map OVERVIEW fields to stock_fundamentals columns."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Symbol": "AAPL",
            "RevenueTTM": "394328000000",
            "EPS": "6.73",
            "PERatio": "28.12",
            "PriceToBookRatio": "40.20",
            "EVToEBITDA": "22.5",
            "ReturnOnEquityTTM": "1.56",
            "MarketCapitalization": "2800000000000",
        }
        mock_get.return_value = mock_response

        result = client.get_fundamentals("AAPL")
        assert result["ticker"] == "AAPL"
        assert result["revenue"] == 394328000000
        assert result["eps"] == 6.73
        assert result["pe_ratio"] == 28.12
        assert result["ev_ebitda"] == 22.5  # AV has this, Finnhub doesn't
        assert result["source"] == "alpha_vantage"
        assert result["net_income"] is None  # Not in OVERVIEW
        assert result["roic"] is None  # Not in OVERVIEW

    @patch.object(httpx.Client, "get")
    def test_rate_limit_via_note_key(self, mock_get, client):
        """AV returns rate limits as HTTP 200 with 'Note' key."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Note": "Thank you for using Alpha Vantage! API call frequency limit..."
        }
        mock_get.return_value = mock_response
        with pytest.raises(RateLimitError):
            client.get_fundamentals("AAPL")

    @patch.object(httpx.Client, "get")
    def test_no_data(self, mock_get, client):
        """Should raise when OVERVIEW returns empty/no Symbol."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response
        with pytest.raises(DataProviderError, match="No overview data"):
            client.get_fundamentals("AAPL")

    @patch.object(httpx.Client, "get")
    def test_timeout(self, mock_get, client):
        mock_get.side_effect = httpx.ReadTimeout("timeout")
        with pytest.raises(ProviderTimeoutError):
            client.get_fundamentals("AAPL")


class TestAlphaVantageSafeFloat:
    def test_string_number(self):
        assert _safe_float("28.12") == 28.12

    def test_dash(self):
        assert _safe_float("-") is None

    def test_none_string(self):
        assert _safe_float("None") is None

    def test_zero_string(self):
        assert _safe_float("0") is None

    def test_real_zero_int(self):
        """Int 0 should return 0.0 (not None — that's only for string "0")."""
        assert _safe_float(0) == 0.0
