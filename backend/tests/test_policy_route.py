"""Tests for the Policy API routes (src/routes/policy.py).

All tests use auth_client fixture and mock the service layer.
"""

from unittest.mock import patch

import pytest

from src.services.exceptions import ConfigurationError
from src.services.policy_engine import (
    EffectivePolicy,
    PolicyResult,
    PolicyViolation,
    _build_effective_policy,
    PRESETS,
)
from tests.conftest import FAKE_USER


PASSED_RESULT = PolicyResult(
    passed=True,
    violations=[],
    policy_snapshot=_build_effective_policy(PRESETS["balanced"]).model_dump(),
)

BLOCKED_RESULT = PolicyResult(
    passed=False,
    violations=[
        PolicyViolation(
            rule="asset_universe",
            message="Ticker 'BTC' is not in the allowed asset universe",
            severity="blocking",
            current_value="BTC",
            limit_value="AAPL, MSFT, JNJ, JPM, PG, VOO, VWO",
        ),
    ],
    policy_snapshot=_build_effective_policy(PRESETS["balanced"]).model_dump(),
)

EFFECTIVE_POLICY = _build_effective_policy(PRESETS["balanced"])


class TestPreCheckEndpoint:
    @patch("src.routes.policy.run_pre_policy")
    def test_200_passed(self, mock_run, auth_client):
        mock_run.return_value = PASSED_RESULT

        resp = auth_client.post("/api/policy/pre-check/AAPL")

        assert resp.status_code == 200
        data = resp.json()
        assert data["passed"] is True
        assert data["violations"] == []
        assert data["policy_snapshot"] is not None

    @patch("src.routes.policy.run_pre_policy")
    def test_200_blocked(self, mock_run, auth_client):
        mock_run.return_value = BLOCKED_RESULT

        resp = auth_client.post("/api/policy/pre-check/BTC")

        assert resp.status_code == 200
        data = resp.json()
        assert data["passed"] is False
        assert len(data["violations"]) == 1
        assert data["violations"][0]["rule"] == "asset_universe"

    @patch("src.routes.policy.run_pre_policy")
    def test_503_configuration_error(self, mock_run, auth_client):
        mock_run.side_effect = ConfigurationError("Policy database unavailable")

        resp = auth_client.post("/api/policy/pre-check/AAPL")

        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]
        assert "database" not in resp.json()["detail"].lower()

    @patch("src.routes.policy.run_pre_policy")
    def test_503_unexpected_exception(self, mock_run, auth_client):
        mock_run.side_effect = Exception("connection refused")

        resp = auth_client.post("/api/policy/pre-check/AAPL")

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]
        assert "connection" not in resp.json()["detail"]

    def test_401_no_auth(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            from fastapi.testclient import TestClient
            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.post("/api/policy/pre-check/AAPL")
            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig


class TestFullCheckEndpoint:
    TRADE_PROPOSAL = {
        "ticker": "AAPL",
        "action": "BUY",
        "shares": 10,
        "price": 150.0,
        "analysis_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    }

    @patch("src.routes.policy.run_full_policy")
    def test_200_passed(self, mock_run, auth_client):
        mock_run.return_value = PASSED_RESULT

        resp = auth_client.post("/api/policy/full-check", json=self.TRADE_PROPOSAL)

        assert resp.status_code == 200
        data = resp.json()
        assert data["passed"] is True
        assert data["violations"] == []

    @patch("src.routes.policy.run_full_policy")
    def test_200_blocked(self, mock_run, auth_client):
        blocked = PolicyResult(
            passed=False,
            violations=[
                PolicyViolation(
                    rule="max_single_position",
                    message="Position size 15.0% exceeds limit of 5%",
                    severity="blocking",
                    current_value=15.0,
                    limit_value=5,
                ),
            ],
            policy_snapshot=EFFECTIVE_POLICY.model_dump(),
        )
        mock_run.return_value = blocked

        resp = auth_client.post("/api/policy/full-check", json=self.TRADE_PROPOSAL)

        assert resp.status_code == 200
        data = resp.json()
        assert data["passed"] is False
        assert len(data["violations"]) == 1
        assert data["violations"][0]["rule"] == "max_single_position"

    def test_422_invalid_body(self, auth_client):
        resp = auth_client.post("/api/policy/full-check", json={"ticker": "AAPL"})

        assert resp.status_code == 422

    @patch("src.routes.policy.run_full_policy")
    def test_503_configuration_error(self, mock_run, auth_client):
        mock_run.side_effect = ConfigurationError("Policy database unavailable")

        resp = auth_client.post("/api/policy/full-check", json=self.TRADE_PROPOSAL)

        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]

    @patch("src.routes.policy.run_full_policy")
    def test_503_unexpected_exception(self, mock_run, auth_client):
        mock_run.side_effect = Exception("unexpected error")

        resp = auth_client.post("/api/policy/full-check", json=self.TRADE_PROPOSAL)

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]

    def test_401_no_auth(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            from fastapi.testclient import TestClient
            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.post("/api/policy/full-check", json=self.TRADE_PROPOSAL)
            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig


class TestEffectiveEndpoint:
    @patch("src.routes.policy.get_effective_policy")
    def test_200_returns_policy_dict(self, mock_get_policy, auth_client):
        mock_get_policy.return_value = EFFECTIVE_POLICY

        resp = auth_client.get("/api/policy/effective")

        assert resp.status_code == 200
        data = resp.json()
        assert data["core_pct"] == 70
        assert data["satellite_pct"] == 30
        assert data["maturity_stage"] == 1
        assert "forbidden_types" in data

    @patch("src.routes.policy.get_effective_policy")
    def test_503_configuration_error(self, mock_get_policy, auth_client):
        mock_get_policy.side_effect = ConfigurationError("Policy database unavailable")

        resp = auth_client.get("/api/policy/effective")

        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]

    @patch("src.routes.policy.get_effective_policy")
    def test_503_unexpected_exception(self, mock_get_policy, auth_client):
        mock_get_policy.side_effect = Exception("unexpected error")

        resp = auth_client.get("/api/policy/effective")

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]

    def test_401_no_auth(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            from fastapi.testclient import TestClient
            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.get("/api/policy/effective")
            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig
