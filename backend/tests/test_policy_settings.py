"""Tests for GET/PUT /api/policy/settings endpoints (src/routes/policy.py).

GET /settings tests mock get_supabase_admin at the route level.
PUT /settings tests mock update_user_policy at the route level (T-009 SoC).
Validation tests (constraint/key) need no mocks — they fail before DB access.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.services.exceptions import ConfigurationError
from tests.conftest import FAKE_USER


FAKE_USER_ID = FAKE_USER["id"]

EXISTING_POLICY_ROW = {
    "policy_mode": "PRESET",
    "preset_id": "balanced",
    "policy_overrides": {},
    "cooldown_until": None,
}


def _make_mock_admin(select_data=None):
    """Create a mock Supabase admin for GET /settings tests."""
    admin = MagicMock()
    select_chain = (
        admin.table.return_value
        .select.return_value
        .eq.return_value
    )
    select_chain.execute.return_value = SimpleNamespace(
        data=select_data if select_data is not None else []
    )
    return admin


# ---------------------------------------------------------------------------
# GET /api/policy/presets
# ---------------------------------------------------------------------------


class TestGetPresets:
    def test_get_presets(self, auth_client):
        """GET /api/policy/presets returns presets and constraints."""
        resp = auth_client.get("/api/policy/presets")

        assert resp.status_code == 200
        data = resp.json()

        # Presets: 3 keys
        assert "presets" in data
        assert set(data["presets"].keys()) == {"beginner", "balanced", "active"}

        # Constraints: 9 keys
        assert "constraints" in data
        assert len(data["constraints"]) == 9
        # Each constraint has min and max
        for key, constraint in data["constraints"].items():
            assert "min" in constraint
            assert "max" in constraint


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
        assert "not configured" in resp.json()["detail"]

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
    @patch("src.routes.policy.update_user_policy")
    def test_change_preset_sets_cooldown(self, mock_update, auth_client):
        """Changing preset_id sets cooldown_until."""
        mock_update.return_value = {
            "policy_mode": "PRESET",
            "preset_id": "active",
            "policy_overrides": {},
            "cooldown_until": "2026-03-07T12:00:00+00:00",
        }

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "PRESET",
            "preset_id": "active",
            "policy_overrides": {},
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["preset_id"] == "active"
        assert data["cooldown_until"] is not None

    @patch("src.routes.policy.update_user_policy")
    def test_same_preset_no_cooldown(self, mock_update, auth_client):
        """Same preset_id does not set cooldown."""
        mock_update.return_value = {
            "policy_mode": "PRESET",
            "preset_id": "balanced",
            "policy_overrides": {},
            "cooldown_until": None,
        }

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "PRESET",
            "preset_id": "balanced",
            "policy_overrides": {},
        })

        assert resp.status_code == 200
        assert resp.json()["cooldown_until"] is None

    @patch("src.routes.policy.update_user_policy")
    def test_advanced_valid_overrides(self, mock_update, auth_client):
        """ADVANCED mode with valid overrides returns them."""
        mock_update.return_value = {
            "policy_mode": "ADVANCED",
            "preset_id": "balanced",
            "policy_overrides": {"satellite_pct": 35, "max_drawdown_pct": 25},
            "cooldown_until": "2026-03-07T12:00:00+00:00",
        }

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "ADVANCED",
            "preset_id": "balanced",
            "policy_overrides": {"satellite_pct": 35, "max_drawdown_pct": 25},
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
            "policy_overrides": {"satellite_pct": 99},
        })

        assert resp.status_code == 400
        assert "satellite_pct" in resp.json()["detail"]
        assert "outside" in resp.json()["detail"].lower()

    def test_advanced_unknown_key_returns_400(self, auth_client):
        """Unknown override key returns 400."""
        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "ADVANCED",
            "preset_id": "balanced",
            "policy_overrides": {"nonexistent_key": 10},
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

    @patch("src.routes.policy.update_user_policy")
    def test_beginner_mode_clears_overrides(self, mock_update, auth_client):
        """BEGINNER mode ignores and clears any overrides."""
        mock_update.return_value = {
            "policy_mode": "BEGINNER",
            "preset_id": "beginner",
            "policy_overrides": {},
            "cooldown_until": "2026-03-07T12:00:00+00:00",
        }

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "BEGINNER",
            "preset_id": "beginner",
            "policy_overrides": {"satellite_pct": 35},
        })

        assert resp.status_code == 200
        assert resp.json()["policy_overrides"] == {}
        # validate_overrides cleared the overrides → service called with {}
        call_kwargs = mock_update.call_args
        assert call_kwargs[1]["effective_overrides"] == {}

    @patch("src.routes.policy.update_user_policy")
    def test_503_db_error(self, mock_update, auth_client):
        """DB error during update returns 503."""
        mock_update.side_effect = Exception("DB write failed")

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "PRESET",
            "preset_id": "balanced",
            "policy_overrides": {},
        })

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]

    @patch("src.routes.policy.update_user_policy")
    def test_preset_to_advanced_sets_cooldown(self, mock_update, auth_client):
        """PRESET->ADVANCED sets cooldown (mode changed)."""
        mock_update.return_value = {
            "policy_mode": "ADVANCED",
            "preset_id": "balanced",
            "policy_overrides": {"satellite_pct": 35},
            "cooldown_until": "2026-03-07T12:00:00+00:00",
        }

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "ADVANCED",
            "preset_id": "balanced",
            "policy_overrides": {"satellite_pct": 35},
        })

        assert resp.status_code == 200
        assert resp.json()["cooldown_until"] is not None

    @patch("src.routes.policy.update_user_policy")
    def test_advanced_to_advanced_no_cooldown(self, mock_update, auth_client):
        """ADVANCED->ADVANCED (only override change) does not set cooldown."""
        mock_update.return_value = {
            "policy_mode": "ADVANCED",
            "preset_id": "balanced",
            "policy_overrides": {"satellite_pct": 35},
            "cooldown_until": None,
        }

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "ADVANCED",
            "preset_id": "balanced",
            "policy_overrides": {"satellite_pct": 35},
        })

        assert resp.status_code == 200
        assert resp.json()["cooldown_until"] is None

    @patch("src.routes.policy.update_user_policy")
    def test_beginner_to_advanced_sets_cooldown(self, mock_update, auth_client):
        """BEGINNER->ADVANCED sets cooldown (mode changed)."""
        mock_update.return_value = {
            "policy_mode": "ADVANCED",
            "preset_id": "beginner",
            "policy_overrides": {"satellite_pct": 25},
            "cooldown_until": "2026-03-07T12:00:00+00:00",
        }

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "ADVANCED",
            "preset_id": "beginner",
            "policy_overrides": {"satellite_pct": 25},
        })

        assert resp.status_code == 200
        assert resp.json()["cooldown_until"] is not None

    @patch("src.routes.policy.update_user_policy")
    def test_advanced_to_preset_sets_cooldown(self, mock_update, auth_client):
        """ADVANCED->PRESET (downgrade) sets cooldown (mode changed)."""
        mock_update.return_value = {
            "policy_mode": "PRESET",
            "preset_id": "balanced",
            "policy_overrides": {},
            "cooldown_until": "2026-03-07T12:00:00+00:00",
        }

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "PRESET",
            "preset_id": "balanced",
            "policy_overrides": {},
        })

        assert resp.status_code == 200
        assert resp.json()["cooldown_until"] is not None

    @patch("src.routes.policy.update_user_policy")
    def test_new_user_defaults_for_old_values(self, mock_update, auth_client):
        """When no existing row, service handles defaults."""
        mock_update.return_value = {
            "policy_mode": "PRESET",
            "preset_id": "active",
            "policy_overrides": {},
            "cooldown_until": "2026-03-07T12:00:00+00:00",
        }

        resp = auth_client.put("/api/policy/settings", json={
            "policy_mode": "PRESET",
            "preset_id": "active",
            "policy_overrides": {},
        })

        assert resp.status_code == 200
        assert resp.json()["cooldown_until"] is not None
