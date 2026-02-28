"""Tests for the Analysis API route (src/routes/analysis.py).

All tests use auth_client fixture and mock the orchestrator.
"""

from unittest.mock import patch

import pytest

from src.services.exceptions import ConfigurationError, PreconditionError
from src.services.fundamental_analysis import AnalysisResult
from tests.conftest import FAKE_USER


SUCCESS_RESULT = AnalysisResult(
    ticker="AAPL",
    analysis_id="analysis-uuid-789",
    status="completed",
    fundamental_out={"score": 72, "moat_rating": "wide"},
    tokens_used=3500,
    cost_usd=0.0345,
)

FAILED_RESULT = AnalysisResult(
    ticker="AAPL",
    analysis_id="analysis-uuid-789",
    status="failed",
    tokens_used=1500,
    cost_usd=0.0045,
    error_message="API timeout",
)


class TestAnalyzeEndpoint:
    @patch("src.routes.analysis.run_fundamental_analysis")
    def test_success_returns_200(self, mock_run, auth_client):
        mock_run.return_value = SUCCESS_RESULT

        resp = auth_client.post("/api/analyze/AAPL")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["analysis_id"] == "analysis-uuid-789"
        assert data["ticker"] == "AAPL"
        assert data["fundamental_out"]["score"] == 72
        assert data["tokens_used"] == 3500
        assert data["cost_usd"] == 0.0345

    @patch("src.routes.analysis.run_fundamental_analysis")
    def test_invalid_ticker_returns_400(self, mock_run, auth_client):
        resp = auth_client.post("/api/analyze/INVALID")

        assert resp.status_code == 400
        assert "not in the MVP universe" in resp.json()["detail"]
        mock_run.assert_not_called()

    def test_no_auth_returns_401(self, auth_client):
        # Remove the auth override to test unauthenticated
        from src.dependencies.auth import get_current_user
        from src.main import app

        app.dependency_overrides.pop(get_current_user, None)

        # TestClient without auth header
        from fastapi.testclient import TestClient
        unauth_client = TestClient(app, raise_server_exceptions=False)
        resp = unauth_client.post("/api/analyze/AAPL")

        assert resp.status_code in (401, 403)

    @patch("src.routes.analysis.run_fundamental_analysis")
    def test_no_fundamentals_returns_400(self, mock_run, auth_client):
        mock_run.side_effect = PreconditionError(
            "No fundamental data for AAPL. Run POST /api/collect/AAPL first."
        )

        resp = auth_client.post("/api/analyze/AAPL")

        assert resp.status_code == 400
        assert "collect" in resp.json()["detail"].lower()

    @patch("src.routes.analysis.run_fundamental_analysis")
    def test_no_api_key_returns_503(self, mock_run, auth_client):
        mock_run.side_effect = ConfigurationError("ANTHROPIC_API_KEY not configured")

        resp = auth_client.post("/api/analyze/AAPL")

        assert resp.status_code == 503
        # Sanitized: should NOT expose "ANTHROPIC_API_KEY" to the client
        assert "ANTHROPIC_API_KEY" not in resp.json()["detail"]

    @patch("src.routes.analysis.run_fundamental_analysis")
    def test_agent_failure_returns_200_with_failed_status(self, mock_run, auth_client):
        mock_run.return_value = FAILED_RESULT

        resp = auth_client.post("/api/analyze/AAPL")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        # Error message is sanitized — no internal details leaked
        assert "timed out" in data["error_message"].lower()
        assert data["tokens_used"] == 1500

    @patch("src.routes.analysis.run_fundamental_analysis")
    def test_response_contains_all_fields(self, mock_run, auth_client):
        mock_run.return_value = SUCCESS_RESULT

        resp = auth_client.post("/api/analyze/AAPL")

        data = resp.json()
        expected_fields = {"status", "analysis_id", "ticker", "fundamental_out", "tokens_used", "cost_usd", "error_message"}
        assert set(data.keys()) == expected_fields

    @patch("src.routes.analysis.run_fundamental_analysis")
    def test_ticker_case_insensitive(self, mock_run, auth_client):
        mock_run.return_value = SUCCESS_RESULT

        resp = auth_client.post("/api/analyze/aapl")

        assert resp.status_code == 200
        mock_run.assert_called_once_with("aapl", FAKE_USER["id"])
