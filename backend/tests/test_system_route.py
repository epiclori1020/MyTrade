"""Tests for the System API routes (src/routes/system.py).

Covers Kill-Switch status, activate, deactivate, evaluate, budget, and metrics endpoints.
All tests use auth_client fixture and mock the service layer — no real DB or LLM calls.

Mocking target: src.routes.system.<function_name>
  (mock where it is imported, not where it is defined)
"""

from unittest.mock import patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from src.config import Settings, get_settings
from src.dependencies.auth import get_current_user
from src.main import app
from tests.conftest import FAKE_USER


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

INACTIVE_STATUS = {
    "active": False,
    "reason": None,
    "activated_at": None,
}

ACTIVE_STATUS = {
    "active": True,
    "reason": "drawdown_exceeded",
    "activated_at": "2026-03-03T08:00:00+00:00",
}

BUDGET_RESPONSE = {
    "tiers": {
        "heavy": {
            "spend": 5.0,
            "cap": 30.0,
            "remaining": 25.0,
            "utilization_pct": 16.7,
            "model": "claude-opus-4-6",
        },
        "standard": {
            "spend": 2.5,
            "cap": 20.0,
            "remaining": 17.5,
            "utilization_pct": 12.5,
            "model": "claude-sonnet-4-6",
        },
        "light": {
            "spend": 0.1,
            "cap": 5.0,
            "remaining": 4.9,
            "utilization_pct": 2.0,
            "model": "claude-haiku-4-5",
        },
    },
    "total_spend": 7.6,
    "total_cap": 55.0,
    "remaining": 47.4,
    "utilization_pct": 13.8,
    "warnings": [],
}

NO_TRIGGER_RESULT = {
    "triggered": False,
    "triggers": {
        "drawdown": {"triggered": False, "detail": "No highwater mark set"},
        "broker_cb": {"triggered": False, "cb_state": "closed", "failure_count": 0},
        "verification_rate": {"triggered": False, "detail": "No analyses found"},
    },
}

TRIGGER_FIRED_RESULT = {
    "triggered": True,
    "triggers": {
        "drawdown": {
            "triggered": True,
            "drawdown_pct": 21.5,
            "threshold_pct": 20.0,
            "current_value": 78500.0,
            "highwater_value": 100000.0,
        },
        "broker_cb": {"triggered": False, "cb_state": "closed", "failure_count": 2},
        "verification_rate": {"triggered": False, "detail": "No analyses found"},
    },
}


# ---------------------------------------------------------------------------
# GET /api/system/kill-switch
# ---------------------------------------------------------------------------


class TestGetKillSwitch:
    @patch("src.routes.system.get_kill_switch_status")
    def test_200_returns_inactive_status(self, mock_status, auth_client):
        mock_status.return_value = INACTIVE_STATUS

        resp = auth_client.get("/api/system/kill-switch")

        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is False
        assert data["reason"] is None
        assert data["activated_at"] is None

    @patch("src.routes.system.get_kill_switch_status")
    def test_200_returns_active_status_with_reason_and_timestamp(
        self, mock_status, auth_client
    ):
        mock_status.return_value = ACTIVE_STATUS

        resp = auth_client.get("/api/system/kill-switch")

        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is True
        assert data["reason"] == "drawdown_exceeded"
        assert data["activated_at"] == "2026-03-03T08:00:00+00:00"

    @patch("src.routes.system.get_kill_switch_status")
    def test_503_on_service_error(self, mock_status, auth_client):
        mock_status.side_effect = Exception("DB connection lost")

        resp = auth_client.get("/api/system/kill-switch")

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]
        # Internal error detail must not leak
        assert "DB" not in resp.json()["detail"]
        assert "connection" not in resp.json()["detail"].lower()

    def test_401_without_auth(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.get("/api/system/kill-switch")
            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig


# ---------------------------------------------------------------------------
# POST /api/system/kill-switch/activate
# ---------------------------------------------------------------------------


class TestActivateKillSwitch:
    @patch("src.routes.system.activate_kill_switch")
    def test_200_activates_with_default_manual_reason(self, mock_activate, auth_client):
        mock_activate.return_value = {
            "active": True,
            "reason": "manual",
            "activated_at": "2026-03-03T09:00:00+00:00",
        }

        # Omit body entirely — default reason is "manual"
        resp = auth_client.post("/api/system/kill-switch/activate")

        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is True
        assert data["reason"] == "manual"
        # Verify the default reason was forwarded to the service
        mock_activate.assert_called_once_with("manual")

    @patch("src.routes.system.activate_kill_switch")
    def test_200_activates_with_custom_reason_in_body(self, mock_activate, auth_client):
        mock_activate.return_value = {
            "active": True,
            "reason": "drawdown_exceeded",
            "activated_at": "2026-03-03T09:15:00+00:00",
        }

        resp = auth_client.post(
            "/api/system/kill-switch/activate",
            json={"reason": "drawdown_exceeded"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is True
        assert data["reason"] == "drawdown_exceeded"
        # Verify the custom reason was forwarded to the service
        mock_activate.assert_called_once_with("drawdown_exceeded")

    @patch("src.routes.system.activate_kill_switch")
    def test_503_on_service_error(self, mock_activate, auth_client):
        mock_activate.side_effect = Exception("Supabase write failed")

        resp = auth_client.post(
            "/api/system/kill-switch/activate",
            json={"reason": "manual"},
        )

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]
        assert "Supabase" not in resp.json()["detail"]

    def test_401_without_auth(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.post("/api/system/kill-switch/activate")
            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig


# ---------------------------------------------------------------------------
# POST /api/system/kill-switch/deactivate
# ---------------------------------------------------------------------------


class TestDeactivateKillSwitch:
    @patch("src.routes.system.deactivate_kill_switch")
    def test_200_deactivates_and_clears_fields(self, mock_deactivate, auth_client):
        mock_deactivate.return_value = INACTIVE_STATUS

        resp = auth_client.post("/api/system/kill-switch/deactivate")

        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is False
        assert data["reason"] is None
        assert data["activated_at"] is None
        mock_deactivate.assert_called_once()

    @patch("src.routes.system.deactivate_kill_switch")
    def test_503_on_service_error(self, mock_deactivate, auth_client):
        mock_deactivate.side_effect = Exception("DB write error")

        resp = auth_client.post("/api/system/kill-switch/deactivate")

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]

    def test_401_without_auth(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.post("/api/system/kill-switch/deactivate")
            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig


# ---------------------------------------------------------------------------
# POST /api/system/kill-switch/evaluate
# ---------------------------------------------------------------------------


class TestEvaluateKillSwitch:
    @patch("src.routes.system.evaluate_kill_switch_triggers")
    def test_200_no_triggers_returns_triggered_false(self, mock_evaluate, auth_client):
        mock_evaluate.return_value = NO_TRIGGER_RESULT

        resp = auth_client.post("/api/system/kill-switch/evaluate")

        assert resp.status_code == 200
        data = resp.json()
        assert data["triggered"] is False
        assert "triggers" in data
        assert data["triggers"]["drawdown"]["triggered"] is False
        assert data["triggers"]["broker_cb"]["triggered"] is False
        assert data["triggers"]["verification_rate"]["triggered"] is False

    @patch("src.routes.system.evaluate_kill_switch_triggers")
    def test_200_trigger_fires_returns_triggered_true_with_detail(
        self, mock_evaluate, auth_client
    ):
        mock_evaluate.return_value = TRIGGER_FIRED_RESULT

        resp = auth_client.post("/api/system/kill-switch/evaluate")

        assert resp.status_code == 200
        data = resp.json()
        assert data["triggered"] is True
        drawdown = data["triggers"]["drawdown"]
        assert drawdown["triggered"] is True
        assert drawdown["drawdown_pct"] == 21.5
        assert drawdown["threshold_pct"] == 20.0

    @patch("src.routes.system.evaluate_kill_switch_triggers")
    def test_evaluate_forwards_authenticated_user_id(self, mock_evaluate, auth_client):
        """The route reads user_id from request.state.user and passes it to the service."""
        mock_evaluate.return_value = NO_TRIGGER_RESULT

        auth_client.post("/api/system/kill-switch/evaluate")

        mock_evaluate.assert_called_once_with(FAKE_USER["id"])

    @patch("src.routes.system.evaluate_kill_switch_triggers")
    def test_503_on_service_error(self, mock_evaluate, auth_client):
        mock_evaluate.side_effect = Exception("Policy service unavailable")

        resp = auth_client.post("/api/system/kill-switch/evaluate")

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]
        assert "Policy" not in resp.json()["detail"]

    def test_401_without_auth(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.post("/api/system/kill-switch/evaluate")
            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig


# ---------------------------------------------------------------------------
# GET /api/system/budget
# ---------------------------------------------------------------------------


class TestGetBudget:
    @patch("src.routes.system.get_budget_status")
    def test_200_returns_all_three_tiers_and_totals(self, mock_budget, auth_client):
        mock_budget.return_value = BUDGET_RESPONSE

        resp = auth_client.get("/api/system/budget")

        assert resp.status_code == 200
        data = resp.json()
        assert "tiers" in data
        assert set(data["tiers"].keys()) == {"heavy", "standard", "light"}
        assert "total_spend" in data
        assert "total_cap" in data
        assert "remaining" in data
        assert "utilization_pct" in data
        assert "warnings" in data

    @patch("src.routes.system.get_budget_status")
    def test_200_tier_fields_are_correct(self, mock_budget, auth_client):
        mock_budget.return_value = BUDGET_RESPONSE

        resp = auth_client.get("/api/system/budget")

        heavy = resp.json()["tiers"]["heavy"]
        assert heavy["spend"] == 5.0
        assert heavy["cap"] == 30.0
        assert heavy["remaining"] == 25.0
        assert heavy["utilization_pct"] == 16.7
        assert heavy["model"] == "claude-opus-4-6"

    @patch("src.routes.system.get_budget_status")
    def test_200_empty_warnings_when_under_soft_cap(self, mock_budget, auth_client):
        mock_budget.return_value = BUDGET_RESPONSE

        resp = auth_client.get("/api/system/budget")

        assert resp.json()["warnings"] == []

    @patch("src.routes.system.get_budget_status")
    def test_200_warnings_present_when_tier_near_cap(self, mock_budget, auth_client):
        near_cap_response = {
            **BUDGET_RESPONSE,
            "warnings": ["heavy tier at 85% of budget ($25.50/$30.00)"],
        }
        mock_budget.return_value = near_cap_response

        resp = auth_client.get("/api/system/budget")

        assert resp.status_code == 200
        warnings = resp.json()["warnings"]
        assert len(warnings) == 1
        assert "heavy" in warnings[0]

    @patch("src.routes.system.get_budget_status")
    def test_503_on_service_error(self, mock_budget, auth_client):
        mock_budget.side_effect = Exception("agent_cost_log table not found")

        resp = auth_client.get("/api/system/budget")

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]
        # Internal table name must not leak
        assert "agent_cost_log" not in resp.json()["detail"]

    def test_401_without_auth(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.get("/api/system/budget")
            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig


# ---------------------------------------------------------------------------
# GET /api/system/metrics
# ---------------------------------------------------------------------------

METRICS_RESPONSE = {
    "pipeline_error_rate": {
        "rate_pct": 5.0,
        "failed": 1,
        "total": 20,
        "detail": "1/20 runs failed (30d)",
    },
    "avg_latency_seconds": {
        "value": 45.0,
        "total_runs": 19,
        "detail": "Avg 45.0s over 19 completed runs",
    },
    "verification_score": {
        "rate_pct": 88.5,
        "verified": 46,
        "total": 52,
        "detail": "46/52 claims verified/consistent",
    },
}


class TestGetMetrics:
    @patch("src.routes.system.get_system_metrics")
    def test_200_returns_all_metric_sections(self, mock_metrics, auth_client):
        mock_metrics.return_value = METRICS_RESPONSE

        resp = auth_client.get("/api/system/metrics")

        assert resp.status_code == 200
        data = resp.json()
        assert "pipeline_error_rate" in data
        assert "avg_latency_seconds" in data
        assert "verification_score" in data
        assert data["pipeline_error_rate"]["rate_pct"] == 5.0
        assert data["verification_score"]["rate_pct"] == 88.5

    @patch("src.routes.system.get_system_metrics")
    def test_200_empty_returns_zeros(self, mock_metrics, auth_client):
        empty = {
            "pipeline_error_rate": {"rate_pct": 0.0, "failed": 0, "total": 0, "detail": "0/0 runs failed (30d)"},
            "avg_latency_seconds": {"value": 0.0, "total_runs": 0, "detail": "Avg 0.0s over 0 completed runs"},
            "verification_score": {"rate_pct": 0.0, "verified": 0, "total": 0, "detail": "0/0 claims verified/consistent"},
        }
        mock_metrics.return_value = empty

        resp = auth_client.get("/api/system/metrics")

        assert resp.status_code == 200
        assert resp.json()["pipeline_error_rate"]["total"] == 0

    @patch("src.routes.system.get_system_metrics")
    def test_forwards_authenticated_user_id(self, mock_metrics, auth_client):
        mock_metrics.return_value = METRICS_RESPONSE

        auth_client.get("/api/system/metrics")

        mock_metrics.assert_called_once_with(FAKE_USER["id"])

    @patch("src.routes.system.get_system_metrics")
    def test_503_on_service_error(self, mock_metrics, auth_client):
        mock_metrics.side_effect = Exception("DB unavailable")

        resp = auth_client.get("/api/system/metrics")

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]
        assert "DB" not in resp.json()["detail"]

    def test_401_without_auth(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.get("/api/system/metrics")
            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig


# ---------------------------------------------------------------------------
# Admin-Guard Integration Tests (T-002)
# ---------------------------------------------------------------------------

NON_ADMIN_USER = {"id": "non-admin-user-id-456", "email": "nonadmin@example.com"}


def _make_non_admin_settings() -> Settings:
    """Settings where FAKE_USER is admin but NON_ADMIN_USER is not."""
    return Settings(
        supabase_url="https://test.supabase.co",
        supabase_anon_key="test-anon-key",
        supabase_service_role_key="test-service-role-key",
        cors_origins="http://localhost:3000",
        finnhub_api_key="test-finnhub-key",
        alpha_vantage_api_key="test-av-key",
        anthropic_api_key="test-anthropic-key",
        alpaca_api_key="test-alpaca-key",
        alpaca_secret_key="test-alpaca-secret",
        admin_user_ids="test-user-id-123",
    )


def _non_admin_get_current_user(request: Request) -> dict:
    """Override that sets a non-admin user."""
    request.state.user = NON_ADMIN_USER
    return NON_ADMIN_USER


@pytest.fixture
def non_admin_client():
    """Authenticated test client where the user is NOT an admin."""
    from src.dependencies.rate_limit import limiter

    app.dependency_overrides[get_current_user] = _non_admin_get_current_user
    app.dependency_overrides[get_settings] = _make_non_admin_settings

    patcher_supabase = patch("src.services.supabase.create_client")
    patcher_supabase.start()

    # Patch get_settings at the admin dependency import location
    patcher_admin_settings = patch(
        "src.dependencies.admin.get_settings",
        return_value=_make_non_admin_settings(),
    )
    patcher_admin_settings.start()

    limiter.reset()

    client = TestClient(app, raise_server_exceptions=False)
    yield client

    patcher_admin_settings.stop()
    patcher_supabase.stop()
    app.dependency_overrides.clear()


class TestAdminGuardActivate:
    """Activate endpoint requires admin role."""

    def test_403_for_non_admin_user(self, non_admin_client):
        resp = non_admin_client.post(
            "/api/system/kill-switch/activate",
            json={"reason": "manual"},
        )

        assert resp.status_code == 403
        assert "Admin access required" in resp.json()["detail"]

    @patch("src.routes.system.activate_kill_switch")
    def test_200_for_admin_user(self, mock_activate, auth_client):
        """Existing auth_client has FAKE_USER which IS in admin_user_ids."""
        mock_activate.return_value = {
            "active": True,
            "reason": "manual",
            "activated_at": "2026-03-05T10:00:00+00:00",
        }

        resp = auth_client.post("/api/system/kill-switch/activate")

        assert resp.status_code == 200
        assert resp.json()["active"] is True


class TestAdminGuardDeactivate:
    """Deactivate endpoint requires admin role."""

    def test_403_for_non_admin_user(self, non_admin_client):
        resp = non_admin_client.post("/api/system/kill-switch/deactivate")

        assert resp.status_code == 403
        assert "Admin access required" in resp.json()["detail"]

    @patch("src.routes.system.deactivate_kill_switch")
    def test_200_for_admin_user(self, mock_deactivate, auth_client):
        mock_deactivate.return_value = INACTIVE_STATUS

        resp = auth_client.post("/api/system/kill-switch/deactivate")

        assert resp.status_code == 200
        assert resp.json()["active"] is False


class TestAdminGuardNotApplied:
    """Verify that non-admin endpoints are NOT guarded."""

    @patch("src.routes.system.get_kill_switch_status")
    def test_get_kill_switch_accessible_to_non_admin(
        self, mock_status, non_admin_client
    ):
        mock_status.return_value = INACTIVE_STATUS

        resp = non_admin_client.get("/api/system/kill-switch")

        assert resp.status_code == 200

    @patch("src.routes.system.evaluate_kill_switch_triggers")
    def test_evaluate_accessible_to_non_admin(self, mock_evaluate, non_admin_client):
        mock_evaluate.return_value = NO_TRIGGER_RESULT

        resp = non_admin_client.post("/api/system/kill-switch/evaluate")

        assert resp.status_code == 200

    @patch("src.routes.system.get_budget_status")
    def test_budget_accessible_to_non_admin(self, mock_budget, non_admin_client):
        mock_budget.return_value = BUDGET_RESPONSE

        resp = non_admin_client.get("/api/system/budget")

        assert resp.status_code == 200

    @patch("src.routes.system.get_system_metrics")
    def test_metrics_accessible_to_non_admin(self, mock_metrics, non_admin_client):
        mock_metrics.return_value = METRICS_RESPONSE

        resp = non_admin_client.get("/api/system/metrics")

        assert resp.status_code == 200
