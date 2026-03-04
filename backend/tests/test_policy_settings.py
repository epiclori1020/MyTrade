"""Tests for GET/PUT /api/policy/settings endpoints (src/routes/policy.py).

All tests use auth_client fixture and mock get_supabase_admin at the route level.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services.exceptions import ConfigurationError
from tests.conftest import FAKE_USER


FAKE_USER_ID = FAKE_USER["id"]

EXISTING_POLICY_ROW = {
    "policy_mode": "PRESET",
    "preset_id": "balanced",
    "policy_overrides": {},
    "cooldown_until": None,
}


def _make_mock_admin(select_data=None, upsert_data=None, insert_data=None):
    """Create a mock Supabase admin with chainable table calls."""
    admin = MagicMock()

    # .table("user_policy").select(...).eq("user_id", ...).execute()
    select_chain = (
        admin.table.return_value
        .select.return_value
        .eq.return_value
    )
    select_chain.execute.return_value = SimpleNamespace(
        data=select_data if select_data is not None else []
    )

    # .table("user_policy").upsert(...).execute()
    admin.table.return_value.upsert.return_value.execute.return_value = SimpleNamespace(
        data=upsert_data or [{}]
    )

    # .table("policy_change_log").insert(...).execute()
    admin.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
        data=insert_data or [{}]
    )

    return admin


# ---------------------------------------------------------------------------
# GET /api/policy/settings
# ---------------------------------------------------------------------------


class TestGetSettings:
    @patch("src.routes.policy.get_supabase_admin")
    def test_returns_defaults_when_no_row(self, mock_admin_fn, auth_client):
        mock_admin_fn.return_value = _make_mock_admin(select_data=[])

        resp = auth_client.get("/api/policy/settings")

        assert resp.status_code == 200
        data = resp.json()
        assert data["policy_mode"] == "BEGINNER"
        assert data["preset_id"] == "beginner"
        assert data["policy_overrides"] == {}
        assert data["cooldown_until"] is None

    @patch("src.routes.policy.get_supabase_admin")
    def test_returns_existing_row(self, mock_admin_fn, auth_client):
        mock_admin_fn.return_value = _make_mock_admin(
            select_data=[EXISTING_POLICY_ROW]
        )

        resp = auth_client.get("/api/policy/settings")

        assert resp.status_code == 200
        data = resp.json()
        assert data["policy_mode"] == "PRESET"
        assert data["preset_id"] == "balanced"

    @patch("src.routes.policy.get_supabase_admin")
    def test_503_configuration_error(self, mock_admin_fn, auth_client):
        mock_admin_fn.side_effect = ConfigurationError("DB unavailable")

        resp = auth_client.get("/api/policy/settings")

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]

    @patch("src.routes.policy.get_supabase_admin")
    def test_503_unexpected_exception(self, mock_admin_fn, auth_client):
        mock_admin_fn.side_effect = Exception("connection refused")

        resp = auth_client.get("/api/policy/settings")

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]
        assert "connection" not in resp.json()["detail"]


# ---------------------------------------------------------------------------
# PUT /api/policy/settings
# ---------------------------------------------------------------------------


class TestUpdateSettings:
    @patch("src.routes.policy.get_supabase_admin")
    def test_change_preset_sets_cooldown(self, mock_admin_fn, auth_client):
        """Changing preset_id from beginner to active sets cooldown_until."""
        admin = _make_mock_admin(select_data=[{
            "policy_mode": "PRESET",
            "preset_id": "beginner",
            "policy_overrides": {},
            "cooldown_until": None,
        }])
        mock_admin_fn.return_value = admin

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "PRESET",
            "preset_id": "active",
            "policy_overrides": {},
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["preset_id"] == "active"
        assert data["cooldown_until"] is not None

    @patch("src.routes.policy.get_supabase_admin")
    def test_same_preset_no_cooldown(self, mock_admin_fn, auth_client):
        """Same preset_id does not set cooldown."""
        admin = _make_mock_admin(select_data=[EXISTING_POLICY_ROW])
        mock_admin_fn.return_value = admin

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "PRESET",
            "preset_id": "balanced",
            "policy_overrides": {},
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["cooldown_until"] is None

    @patch("src.routes.policy.get_supabase_admin")
    def test_advanced_valid_overrides(self, mock_admin_fn, auth_client):
        """ADVANCED mode with valid overrides returns them."""
        admin = _make_mock_admin(select_data=[EXISTING_POLICY_ROW])
        mock_admin_fn.return_value = admin

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "ADVANCED",
            "preset_id": "balanced",
            "policy_overrides": {
                "satellite_pct": 35,
                "max_drawdown_pct": 25,
            },
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["policy_mode"] == "ADVANCED"
        assert data["policy_overrides"]["satellite_pct"] == 35
        assert data["policy_overrides"]["max_drawdown_pct"] == 25

    def test_advanced_constraint_violation_returns_400(self, auth_client):
        """Override value outside CONSTRAINTS returns 400."""
        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "ADVANCED",
            "preset_id": "balanced",
            "policy_overrides": {
                "satellite_pct": 99,  # max is 40
            },
        })

        assert resp.status_code == 400
        assert "satellite_pct" in resp.json()["detail"]
        assert "outside" in resp.json()["detail"].lower()

    def test_advanced_unknown_key_returns_400(self, auth_client):
        """Unknown override key returns 400."""
        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "ADVANCED",
            "preset_id": "balanced",
            "policy_overrides": {
                "nonexistent_key": 10,
            },
        })

        assert resp.status_code == 400
        assert "Unknown override key" in resp.json()["detail"]

    def test_invalid_mode_returns_422(self, auth_client):
        """Invalid policy_mode returns 422 (Pydantic validation)."""
        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "INVALID",
            "preset_id": "balanced",
        })

        assert resp.status_code == 422

    def test_invalid_preset_returns_422(self, auth_client):
        """Invalid preset_id returns 422 (Pydantic validation)."""
        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "PRESET",
            "preset_id": "nonexistent",
        })

        assert resp.status_code == 422

    @patch("src.routes.policy.get_supabase_admin")
    def test_change_log_entry_written(self, mock_admin_fn, auth_client):
        """Verifies policy_change_log insert is called with old/new values."""
        admin = _make_mock_admin(select_data=[{
            "policy_mode": "BEGINNER",
            "preset_id": "beginner",
            "policy_overrides": {},
            "cooldown_until": None,
        }])
        mock_admin_fn.return_value = admin

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "PRESET",
            "preset_id": "balanced",
            "policy_overrides": {},
        })

        assert resp.status_code == 200
        # Verify insert was called (change log)
        insert_calls = admin.table.return_value.insert.call_args_list
        assert len(insert_calls) >= 1
        log_row = insert_calls[0][0][0]
        assert log_row["user_id"] == FAKE_USER_ID
        assert log_row["old_mode"] == "BEGINNER"
        assert log_row["new_mode"] == "PRESET"
        assert log_row["old_preset"] == "beginner"
        assert log_row["new_preset"] == "balanced"

    @patch("src.routes.policy.get_supabase_admin")
    def test_beginner_mode_clears_overrides(self, mock_admin_fn, auth_client):
        """BEGINNER mode ignores and clears any overrides."""
        admin = _make_mock_admin(select_data=[EXISTING_POLICY_ROW])
        mock_admin_fn.return_value = admin

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "BEGINNER",
            "preset_id": "beginner",
            "policy_overrides": {"satellite_pct": 35},
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["policy_overrides"] == {}

    @patch("src.routes.policy.get_supabase_admin")
    def test_503_db_error(self, mock_admin_fn, auth_client):
        """DB error during upsert returns 503."""
        admin = MagicMock()
        # select succeeds
        admin.table.return_value.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[EXISTING_POLICY_ROW]
        )
        # upsert fails
        admin.table.return_value.upsert.side_effect = Exception("DB write failed")
        mock_admin_fn.return_value = admin

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "PRESET",
            "preset_id": "balanced",
            "policy_overrides": {},
        })

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]

    @patch("src.routes.policy.get_supabase_admin")
    def test_new_user_defaults_for_old_values(self, mock_admin_fn, auth_client):
        """When no existing row, old values default to BEGINNER/beginner."""
        admin = _make_mock_admin(select_data=[])
        mock_admin_fn.return_value = admin

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "PRESET",
            "preset_id": "active",
            "policy_overrides": {},
        })

        assert resp.status_code == 200
        # Preset changed from beginner to active → cooldown set
        assert resp.json()["cooldown_until"] is not None
