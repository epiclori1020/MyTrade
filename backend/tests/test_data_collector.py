"""Tests for data_collector orchestrator."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.data_collector import CollectionResult, collect_ticker_data
from src.services.exceptions import ProviderUnavailableError


@pytest.fixture(autouse=True)
def _no_sleep():
    """Prevent real sleeping during retries in all collector tests."""
    with patch("src.services.retry.time.sleep"):
        yield


def _mock_fundamentals(source="finnhub"):
    return {
        "ticker": "AAPL", "period": "2026-TTM", "revenue": 394000000000,
        "net_income": 100000000000, "free_cash_flow": 110000000000,
        "total_debt": None, "total_equity": None, "eps": 6.73,
        "pe_ratio": 28.5, "pb_ratio": 40.2, "ev_ebitda": None,
        "roe": 1.56, "roic": 0.34, "f_score": None, "z_score": None,
        "source": source, "_raw_metric_count": 50,
    }


def _mock_candles():
    return [
        {"ticker": "AAPL", "date": "2026-01-01", "open": 180.0, "high": 185.0,
         "low": 178.0, "close": 183.0, "volume": 50000000, "source": "finnhub"},
    ]


def _mock_quote():
    return {"ticker": "AAPL", "date": "2026-02-28", "open": 182.0, "high": 186.0,
            "low": 180.0, "close": 184.5, "volume": None, "source": "finnhub"}


@patch("src.services.data_collector.get_supabase_admin")
@patch("src.services.data_collector.log_error")
@patch("src.services.data_collector.AlphaVantageClient")
@patch("src.services.data_collector.FinnhubClient")
class TestCollectTickerData:
    def test_full_success(self, MockFinnhub, MockAV, mock_log_error, mock_admin):
        """All data sources succeed — status should be 'success'."""
        finnhub = MockFinnhub.return_value
        finnhub.get_profile.return_value = {"share_outstanding": 15000.0}
        finnhub.get_fundamentals.return_value = _mock_fundamentals()
        finnhub.get_candles.return_value = _mock_candles()
        finnhub.get_quote.return_value = _mock_quote()
        finnhub.get_news.return_value = [{"headline": "test"}]
        finnhub.get_insider_transactions.return_value = [{"name": "CEO"}]

        mock_table = MagicMock()
        mock_admin.return_value.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = None

        result = collect_ticker_data("AAPL")
        assert result.status == "success"
        assert result.fundamentals is not None
        assert result.prices_count == 2  # 1 candle + 1 quote
        assert len(result.news) == 1
        assert len(result.insider_trades) == 1
        assert result.errors == []
        finnhub.close.assert_called_once()

    def test_finnhub_fails_av_fallback(self, MockFinnhub, MockAV, mock_log_error, mock_admin):
        """When Finnhub fundamentals fail, Alpha Vantage should be used."""
        finnhub = MockFinnhub.return_value
        finnhub.get_profile.return_value = None
        finnhub.get_fundamentals.side_effect = ProviderUnavailableError("finnhub", "down")
        finnhub.get_candles.return_value = _mock_candles()
        finnhub.get_quote.return_value = _mock_quote()
        finnhub.get_news.return_value = []
        finnhub.get_insider_transactions.return_value = []

        av = MockAV.return_value
        av.get_fundamentals.return_value = _mock_fundamentals("alpha_vantage")

        mock_table = MagicMock()
        mock_admin.return_value.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = None

        result = collect_ticker_data("AAPL")
        # "partial" because Finnhub errors are recorded even though AV succeeded
        assert result.status == "partial"
        assert result.fundamentals["source"] == "alpha_vantage"
        av.close.assert_called_once()

    def test_both_providers_fail(self, MockFinnhub, MockAV, mock_log_error, mock_admin):
        """When both providers fail, fundamentals should be None."""
        finnhub = MockFinnhub.return_value
        finnhub.get_profile.return_value = None
        finnhub.get_fundamentals.side_effect = ProviderUnavailableError("finnhub", "down")
        finnhub.get_candles.return_value = _mock_candles()
        finnhub.get_quote.return_value = _mock_quote()
        finnhub.get_news.return_value = []
        finnhub.get_insider_transactions.return_value = []

        av = MockAV.return_value
        av.get_fundamentals.side_effect = ProviderUnavailableError("alpha_vantage", "down")

        mock_table = MagicMock()
        mock_admin.return_value.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = None

        result = collect_ticker_data("AAPL")
        assert result.status == "partial"  # Candles still succeeded
        assert result.fundamentals is None
        assert len(result.errors) >= 2

    def test_invalid_ticker(self, MockFinnhub, MockAV, mock_log_error, mock_admin):
        """Invalid ticker should return error status immediately."""
        result = collect_ticker_data("BTC")
        assert result.status == "error"
        assert "not in the MVP universe" in result.errors[0]
        MockFinnhub.assert_not_called()

    def test_news_failure_non_critical(self, MockFinnhub, MockAV, mock_log_error, mock_admin):
        """News failure should not affect overall status."""
        finnhub = MockFinnhub.return_value
        finnhub.get_profile.return_value = {"share_outstanding": 15000.0}
        finnhub.get_fundamentals.return_value = _mock_fundamentals()
        finnhub.get_candles.return_value = _mock_candles()
        finnhub.get_quote.return_value = _mock_quote()
        finnhub.get_news.side_effect = Exception("news API down")
        finnhub.get_insider_transactions.return_value = []

        mock_table = MagicMock()
        mock_admin.return_value.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = None

        result = collect_ticker_data("AAPL")
        # News failure adds to errors → status is "partial" (fundamentals+prices still present)
        assert result.status == "partial"
        assert result.fundamentals is not None
        assert result.news == []

    def test_db_write_failure(self, MockFinnhub, MockAV, mock_log_error, mock_admin):
        """DB write failure should be logged but not crash."""
        finnhub = MockFinnhub.return_value
        finnhub.get_profile.return_value = {"share_outstanding": 15000.0}
        finnhub.get_fundamentals.return_value = _mock_fundamentals()
        finnhub.get_candles.return_value = []
        finnhub.get_quote.return_value = None
        finnhub.get_news.return_value = []
        finnhub.get_insider_transactions.return_value = []

        mock_table = MagicMock()
        mock_admin.return_value.table.return_value = mock_table
        mock_table.upsert.return_value.execute.side_effect = Exception("DB error")

        result = collect_ticker_data("AAPL")
        assert result.status == "partial"
        assert any("DB write" in e for e in result.errors)

    def test_case_insensitive_ticker(self, MockFinnhub, MockAV, mock_log_error, mock_admin):
        """Lowercase ticker should be normalized to uppercase."""
        finnhub = MockFinnhub.return_value
        finnhub.get_profile.return_value = {"share_outstanding": 15000.0}
        finnhub.get_fundamentals.return_value = _mock_fundamentals()
        finnhub.get_candles.return_value = []
        finnhub.get_quote.return_value = None
        finnhub.get_news.return_value = []
        finnhub.get_insider_transactions.return_value = []

        mock_table = MagicMock()
        mock_admin.return_value.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = None

        result = collect_ticker_data("aapl")
        assert result.ticker == "AAPL"
