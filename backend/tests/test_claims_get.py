"""Tests for GET /api/claims/{analysis_id} endpoint (src/routes/claims.py).

All tests use auth_client fixture and mock get_supabase_admin at the route level.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services.exceptions import ConfigurationError
from tests.conftest import FAKE_USER


FAKE_USER_ID = FAKE_USER["id"]
FAKE_ANALYSIS_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
FAKE_CLAIM_ID = "claim-uuid-001"
FAKE_VERIFICATION_ID = "verif-uuid-001"

SAMPLE_CLAIM = {
    "id": FAKE_CLAIM_ID,
    "analysis_id": FAKE_ANALYSIS_ID,
    "claim_id": f"{FAKE_ANALYSIS_ID}_001",
    "claim_text": "AAPL Revenue TTM: $394.3B",
    "claim_type": "number",
    "value": 394_328_000_000,
    "unit": "USD",
    "ticker": "AAPL",
    "period": "TTM",
    "tier": "B",
    "required_tier": "A",
    "trade_critical": True,
}

SAMPLE_VERIFICATION = {
    "id": FAKE_VERIFICATION_ID,
    "claim_id": FAKE_CLAIM_ID,
    "source_verification": {
        "provider": "alpha_vantage",
        "value": 394_500_000_000,
        "deviation_pct": 0.04,
    },
    "status": "consistent",
    "confidence_adjustment": 0,
}


def _make_mock_admin(
    analysis_data=None,
    claims_data=None,
    verification_data=None,
):
    """Create a mock Supabase admin with specific table routing."""
    admin = MagicMock()
    tables = {}

    def table_factory(name):
        if name in tables:
            return tables[name]

        mock_table = MagicMock()

        if name == "analysis_runs":
            # .select("id").eq("id", ...).eq("user_id", ...).execute()
            chain = mock_table.select.return_value.eq.return_value.eq.return_value
            chain.execute.return_value = SimpleNamespace(
                data=analysis_data if analysis_data is not None else []
            )

        elif name == "claims":
            # .select("*").eq("analysis_id", ...).execute()
            chain = mock_table.select.return_value.eq.return_value
            chain.execute.return_value = SimpleNamespace(
                data=claims_data if claims_data is not None else []
            )

        elif name == "verification_results":
            # .select("*").in_("claim_id", [...]).execute()
            chain = mock_table.select.return_value.in_.return_value
            chain.execute.return_value = SimpleNamespace(
                data=verification_data if verification_data is not None else []
            )

        tables[name] = mock_table
        return mock_table

    admin.table = MagicMock(side_effect=table_factory)
    return admin


class TestGetClaims:
    @patch("src.routes.claims.get_supabase_admin")
    def test_success_with_claims_and_verification(self, mock_admin_fn, auth_client):
        admin = _make_mock_admin(
            analysis_data=[{"id": FAKE_ANALYSIS_ID}],
            claims_data=[SAMPLE_CLAIM],
            verification_data=[SAMPLE_VERIFICATION],
        )
        mock_admin_fn.return_value = admin

        resp = auth_client.get(f"/api/claims/{FAKE_ANALYSIS_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["claims"]) == 1
        claim = data["claims"][0]
        assert claim["claim_text"] == "AAPL Revenue TTM: $394.3B"
        assert claim["verification"] is not None
        assert claim["verification"]["status"] == "consistent"

    @patch("src.routes.claims.get_supabase_admin")
    def test_404_analysis_not_found(self, mock_admin_fn, auth_client):
        admin = _make_mock_admin(analysis_data=[])
        mock_admin_fn.return_value = admin

        resp = auth_client.get(f"/api/claims/{FAKE_ANALYSIS_ID}")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @patch("src.routes.claims.get_supabase_admin")
    def test_404_wrong_user(self, mock_admin_fn, auth_client):
        """analysis_runs row not returned because user_id filter doesn't match."""
        admin = _make_mock_admin(analysis_data=[])
        mock_admin_fn.return_value = admin

        resp = auth_client.get(f"/api/claims/{FAKE_ANALYSIS_ID}")

        assert resp.status_code == 404

    @patch("src.routes.claims.get_supabase_admin")
    def test_empty_claims_returns_empty_array(self, mock_admin_fn, auth_client):
        admin = _make_mock_admin(
            analysis_data=[{"id": FAKE_ANALYSIS_ID}],
            claims_data=[],
        )
        mock_admin_fn.return_value = admin

        resp = auth_client.get(f"/api/claims/{FAKE_ANALYSIS_ID}")

        assert resp.status_code == 200
        assert resp.json()["claims"] == []

    @patch("src.routes.claims.get_supabase_admin")
    def test_claim_without_verification(self, mock_admin_fn, auth_client):
        """Claim with no matching verification result has verification=null."""
        admin = _make_mock_admin(
            analysis_data=[{"id": FAKE_ANALYSIS_ID}],
            claims_data=[SAMPLE_CLAIM],
            verification_data=[],
        )
        mock_admin_fn.return_value = admin

        resp = auth_client.get(f"/api/claims/{FAKE_ANALYSIS_ID}")

        assert resp.status_code == 200
        claim = resp.json()["claims"][0]
        assert claim["verification"] is None

    @patch("src.routes.claims.get_supabase_admin")
    def test_503_db_error(self, mock_admin_fn, auth_client):
        mock_admin_fn.side_effect = Exception("DB connection failed")

        resp = auth_client.get(f"/api/claims/{FAKE_ANALYSIS_ID}")

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]
        assert "DB" not in resp.json()["detail"]

    def test_422_invalid_uuid(self, auth_client):
        resp = auth_client.get("/api/claims/not-a-uuid")

        assert resp.status_code == 422
