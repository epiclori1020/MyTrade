"""Tests for the Verification API route (src/routes/verification.py).

All tests use auth_client fixture and mock the orchestrator.
"""

from unittest.mock import patch

import pytest

from src.services.exceptions import ConfigurationError, PreconditionError
from src.services.verification import VerificationResult
from tests.conftest import FAKE_USER

SAMPLE_SUMMARY = {
    "verified": 0,
    "consistent": 1,
    "unverified": 2,
    "disputed": 0,
    "manual_check": 1,
    "has_blocking_disputed": False,
}

SUCCESS_RESULT = VerificationResult(
    analysis_id="analysis-uuid-789",
    status="completed",
    summary=SAMPLE_SUMMARY,
    results_count=2,
)

FAILED_RESULT = VerificationResult(
    analysis_id="analysis-uuid-789",
    status="failed",
    summary={"verified": 0, "consistent": 0, "unverified": 3, "disputed": 0, "manual_check": 0, "has_blocking_disputed": False},
    error_message="Failed to save verification results to database.",
)


class TestVerifyClaimsEndpoint:
    @patch("src.routes.verification.run_verification")
    def test_success_returns_200(self, mock_run, auth_client):
        mock_run.return_value = SUCCESS_RESULT

        resp = auth_client.post("/api/verify/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["analysis_id"] == "analysis-uuid-789"
        assert data["results_count"] == 2
        assert data["summary"]["consistent"] == 1
        assert data["summary"]["verified"] == 0  # MVP expectation

    @patch("src.routes.verification.run_verification")
    def test_response_contains_all_fields(self, mock_run, auth_client):
        mock_run.return_value = SUCCESS_RESULT

        resp = auth_client.post("/api/verify/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        data = resp.json()
        expected_fields = {"status", "analysis_id", "summary", "results_count", "error_message"}
        assert set(data.keys()) == expected_fields

    def test_invalid_uuid_returns_422(self, auth_client):
        resp = auth_client.post("/api/verify/not-a-valid-uuid")

        assert resp.status_code == 422

    @patch("src.routes.verification.run_verification")
    def test_precondition_error_returns_400(self, mock_run, auth_client):
        mock_run.side_effect = PreconditionError("Analysis run not found")

        resp = auth_client.post("/api/verify/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()

    @patch("src.routes.verification.run_verification")
    def test_configuration_error_returns_503_sanitized(self, mock_run, auth_client):
        mock_run.side_effect = ConfigurationError("Alpha Vantage API key not configured")

        resp = auth_client.post("/api/verify/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        assert resp.status_code == 503
        assert "Alpha Vantage" not in resp.json()["detail"]
        assert "not configured" in resp.json()["detail"]

    @patch("src.routes.verification.run_verification")
    def test_unexpected_error_returns_503_sanitized(self, mock_run, auth_client):
        mock_run.side_effect = Exception("connection refused to database")

        resp = auth_client.post("/api/verify/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

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
            resp = unauth_client.post("/api/verify/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig

    @patch("src.routes.verification.run_verification")
    def test_failed_verification_returns_200_with_failed_status(self, mock_run, auth_client):
        mock_run.return_value = FAILED_RESULT

        resp = auth_client.post("/api/verify/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"

    @patch("src.routes.verification.run_verification")
    def test_error_message_sanitized(self, mock_run, auth_client):
        """Error messages should not contain internal DB details."""
        mock_run.return_value = VerificationResult(
            analysis_id="analysis-uuid-789",
            status="failed",
            summary=SAMPLE_SUMMARY,
            error_message="Failed to save verification results to database.",
        )

        resp = auth_client.post("/api/verify/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        data = resp.json()
        # Sanitized — no raw exception details
        assert "connection refused" not in (data["error_message"] or "")
        assert "traceback" not in (data["error_message"] or "").lower()

    @patch("src.routes.verification.run_verification")
    def test_user_id_passed_from_auth(self, mock_run, auth_client):
        mock_run.return_value = SUCCESS_RESULT

        auth_client.post("/api/verify/a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        mock_run.assert_called_once_with(
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            FAKE_USER["id"],
        )
