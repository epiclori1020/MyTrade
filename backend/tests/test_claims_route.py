"""Tests for the Claims API route (src/routes/claims.py).

All tests use auth_client fixture and mock the orchestrator.
"""

from unittest.mock import patch

import pytest

from src.services.claim_extraction import ClaimExtractionResult
from src.services.exceptions import ConfigurationError, PreconditionError
from tests.conftest import FAKE_USER


SAMPLE_CLAIMS = [
    {
        "analysis_id": "analysis-uuid-789",
        "claim_id": "analysis-uuid-789_001",
        "claim_text": "AAPL Revenue TTM: $394.3B",
        "claim_type": "number",
        "value": 394_328_000_000,
        "unit": "USD",
        "ticker": "AAPL",
        "period": "TTM",
        "source_primary": {
            "provider": "finnhub",
            "endpoint": "/stock/metric",
            "retrieved_at": "2026-02-27T14:30:00Z",
        },
        "tier": "B",
        "required_tier": "A",
        "trade_critical": True,
    }
]

SUCCESS_RESULT = ClaimExtractionResult(
    analysis_id="analysis-uuid-789",
    status="completed",
    claims_count=1,
    claims=SAMPLE_CLAIMS,
    tokens_used=1300,
    cost_usd=0.0026,
)

FAILED_RESULT = ClaimExtractionResult(
    analysis_id="analysis-uuid-789",
    status="failed",
    tokens_used=2400,
    cost_usd=0.003,
    error_message="All extraction attempts failed",
)


class TestExtractClaimsEndpoint:
    @patch("src.routes.claims.run_claim_extraction")
    def test_success_returns_200(self, mock_run, auth_client):
        mock_run.return_value = SUCCESS_RESULT

        resp = auth_client.post("/api/extract-claims/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["analysis_id"] == "analysis-uuid-789"
        assert data["claims_count"] == 1
        assert len(data["claims"]) == 1
        assert data["tokens_used"] == 1300
        assert data["cost_usd"] == 0.0026

    @patch("src.routes.claims.run_claim_extraction")
    def test_response_contains_all_fields(self, mock_run, auth_client):
        mock_run.return_value = SUCCESS_RESULT

        resp = auth_client.post("/api/extract-claims/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        data = resp.json()
        expected_fields = {"status", "analysis_id", "claims_count", "claims", "tokens_used", "cost_usd", "error_message"}
        assert set(data.keys()) == expected_fields

    def test_invalid_uuid_returns_422(self, auth_client):
        resp = auth_client.post("/api/extract-claims/not-a-valid-uuid")

        assert resp.status_code == 422

    @patch("src.routes.claims.run_claim_extraction")
    def test_precondition_error_returns_400(self, mock_run, auth_client):
        mock_run.side_effect = PreconditionError("Analysis run not found")

        resp = auth_client.post("/api/extract-claims/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()

    @patch("src.routes.claims.run_claim_extraction")
    def test_configuration_error_returns_503_sanitized(self, mock_run, auth_client):
        mock_run.side_effect = ConfigurationError("ANTHROPIC_API_KEY not configured")

        resp = auth_client.post("/api/extract-claims/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        assert resp.status_code == 503
        assert "ANTHROPIC_API_KEY" not in resp.json()["detail"]
        assert "temporarily unavailable" in resp.json()["detail"]

    @patch("src.routes.claims.run_claim_extraction")
    def test_unexpected_error_returns_503_sanitized(self, mock_run, auth_client):
        mock_run.side_effect = Exception("connection refused to database")

        resp = auth_client.post("/api/extract-claims/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]
        assert "connection" not in resp.json()["detail"]

    def test_no_auth_returns_401(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            from fastapi.testclient import TestClient
            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.post("/api/extract-claims/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig

    @patch("src.routes.claims.run_claim_extraction")
    def test_failed_extraction_returns_200_with_failed_status(self, mock_run, auth_client):
        mock_run.return_value = FAILED_RESULT

        resp = auth_client.post("/api/extract-claims/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["tokens_used"] == 2400

    @patch("src.routes.claims.run_claim_extraction")
    def test_error_message_sanitized(self, mock_run, auth_client):
        """Error messages should not contain internal details."""
        mock_run.return_value = ClaimExtractionResult(
            analysis_id="analysis-uuid-789",
            status="failed",
            error_message="API error (500): Internal server error from anthropic SDK",
        )

        resp = auth_client.post("/api/extract-claims/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        data = resp.json()
        assert "500" not in data["error_message"]
        assert "anthropic" not in data["error_message"]
        assert "SDK" not in data["error_message"]

    @patch("src.routes.claims.run_claim_extraction")
    def test_user_id_passed_from_auth(self, mock_run, auth_client):
        mock_run.return_value = SUCCESS_RESULT

        auth_client.post("/api/extract-claims/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        mock_run.assert_called_once_with(
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            FAKE_USER["id"],
        )
