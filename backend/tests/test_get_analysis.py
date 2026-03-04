"""Tests for GET /api/analyze/{analysis_id} endpoint."""

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FAKE_USER


COMPLETED_ROW = {
    "id": "a1b2c3d4-0000-0000-0000-000000000001",
    "ticker": "AAPL",
    "status": "completed",
    "fundamental_out": {"score": 72, "moat_rating": "wide"},
    "confidence": 75,
    "recommendation": "BUY",
}

ANALYSIS_ID = COMPLETED_ROW["id"]


def _mock_supabase_response(data: list) -> MagicMock:
    """Build a chained Supabase query mock returning the given data."""
    mock_admin = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = data
    (
        mock_admin.table.return_value
        .select.return_value
        .eq.return_value
        .eq.return_value
        .execute.return_value
    ) = mock_resp
    return mock_admin


class TestGetAnalysis:
    @patch("src.routes.analysis.get_supabase_admin")
    def test_get_analysis_success(self, mock_get_admin, auth_client):
        """GET a completed analysis returns 200 with expected shape."""
        mock_get_admin.return_value = _mock_supabase_response([COMPLETED_ROW])

        resp = auth_client.get(f"/api/analyze/{ANALYSIS_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["analysis_id"] == ANALYSIS_ID
        assert data["ticker"] == "AAPL"
        assert data["status"] == "completed"
        assert data["fundamental_out"]["score"] == 72
        # Should NOT contain cost/token metadata
        assert "tokens_used" not in data
        assert "cost_usd" not in data

    @patch("src.routes.analysis.get_supabase_admin")
    def test_get_analysis_not_found(self, mock_get_admin, auth_client):
        """Random UUID that does not exist returns 404."""
        mock_get_admin.return_value = _mock_supabase_response([])

        resp = auth_client.get("/api/analyze/00000000-0000-0000-0000-000000000099")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Analysis not found"

    @patch("src.routes.analysis.get_supabase_admin")
    def test_get_analysis_wrong_user(self, mock_get_admin, auth_client):
        """Analysis belonging to a different user returns 404 (no info leak).

        The Supabase query filters by user_id, so a row owned by another user
        simply returns empty data -- indistinguishable from not found.
        """
        mock_get_admin.return_value = _mock_supabase_response([])

        resp = auth_client.get(f"/api/analyze/{ANALYSIS_ID}")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Analysis not found"

    @patch("src.routes.analysis.get_supabase_admin")
    def test_get_analysis_running_status(self, mock_get_admin, auth_client):
        """Analysis with status='running' is not yet ready -- returns 404."""
        running_row = {**COMPLETED_ROW, "status": "running"}
        mock_get_admin.return_value = _mock_supabase_response([running_row])

        resp = auth_client.get(f"/api/analyze/{ANALYSIS_ID}")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Analysis not found"

    def test_get_analysis_invalid_uuid(self, auth_client):
        """Non-UUID path parameter returns 422 validation error."""
        resp = auth_client.get("/api/analyze/not-a-uuid")

        assert resp.status_code == 422
