"""Tests for data collection API routes."""

from unittest.mock import patch

from src.services.data_collector import CollectionResult


class TestCollectEndpoint:
    def test_valid_ticker_success(self, auth_client):
        """POST /api/collect/AAPL should return 200 with data."""
        mock_result = CollectionResult(
            ticker="AAPL",
            status="success",
            fundamentals={"ticker": "AAPL", "eps": 6.73, "source": "finnhub"},
            prices_count=252,
            news=[{"headline": "test"}],
            insider_trades=[{"name": "CEO"}],
        )
        with patch("src.routes.data.collect_ticker_data", return_value=mock_result):
            response = auth_client.post("/api/collect/AAPL")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["ticker"] == "AAPL"
        assert data["fundamentals"]["eps"] == 6.73
        assert data["prices_count"] == 252
        assert len(data["news"]) == 1

    def test_invalid_ticker_400(self, auth_client):
        """Invalid ticker should return 400."""
        response = auth_client.post("/api/collect/BTC")
        assert response.status_code == 400
        assert "MVP universe" in response.json()["detail"]

    def test_no_auth_401(self):
        """Request without auth should return 401."""
        from fastapi.testclient import TestClient
        from src.main import app
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/collect/AAPL")
        assert response.status_code in (401, 403)

    def test_case_insensitive(self, auth_client):
        """Lowercase ticker should work."""
        mock_result = CollectionResult(
            ticker="AAPL", status="success", prices_count=100,
        )
        with patch("src.routes.data.collect_ticker_data", return_value=mock_result):
            response = auth_client.post("/api/collect/aapl")
        assert response.status_code == 200

    def test_partial_success_200(self, auth_client):
        """Partial failure should return 200 with errors list."""
        mock_result = CollectionResult(
            ticker="AAPL",
            status="partial",
            fundamentals={"ticker": "AAPL", "source": "alpha_vantage"},
            prices_count=0,
            errors=["Candles fetch failed: timeout"],
        )
        with patch("src.routes.data.collect_ticker_data", return_value=mock_result):
            response = auth_client.post("/api/collect/AAPL")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "partial"
        assert len(data["errors"]) == 1

    def test_total_failure_502(self, auth_client):
        """When collection completely fails, should return 502."""
        mock_result = CollectionResult(
            ticker="AAPL",
            status="error",
            errors=["All providers down"],
        )
        with patch("src.routes.data.collect_ticker_data", return_value=mock_result):
            response = auth_client.post("/api/collect/AAPL")

        assert response.status_code == 502

    def test_internal_fields_stripped(self, auth_client):
        """Fields starting with _ should be stripped from response."""
        mock_result = CollectionResult(
            ticker="AAPL",
            status="success",
            fundamentals={
                "ticker": "AAPL", "eps": 6.73,
                "_raw_metric_count": 50, "_debug": "internal",
            },
            prices_count=100,
        )
        with patch("src.routes.data.collect_ticker_data", return_value=mock_result):
            response = auth_client.post("/api/collect/AAPL")

        data = response.json()
        assert "_raw_metric_count" not in data["fundamentals"]
        assert "_debug" not in data["fundamentals"]
        assert data["fundamentals"]["eps"] == 6.73
