"""Tests for the Trade API routes (src/routes/trades.py).

All tests use auth_client fixture and mock the service layer.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services.broker_adapter import AccountInfo, Position
from src.services.exceptions import (
    BrokerError,
    CircuitBreakerOpenError,
    ConfigurationError,
    PreconditionError,
)
from src.services.policy_engine import PolicyResult, PolicyViolation
from tests.conftest import FAKE_USER


# ---------------------------------------------------------------------------
# Helpers for propose tests (Kill-Switch + Full-Policy gates)
# ---------------------------------------------------------------------------

POLICY_PASSED = PolicyResult(passed=True, violations=[], policy_snapshot={})

POLICY_FAILED_POSITION = PolicyResult(
    passed=False,
    violations=[
        PolicyViolation(
            rule="max_single_position",
            message="Position size 12.5% exceeds limit of 5%",
            severity="blocking",
            current_value=12.5,
            limit_value=5,
        ),
    ],
    policy_snapshot={},
)

POLICY_FAILED_OWNERSHIP = PolicyResult(
    passed=False,
    violations=[
        PolicyViolation(
            rule="analysis_not_found",
            message="Analysis run not found",
            severity="blocking",
        ),
    ],
    policy_snapshot={},
)


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

VALID_TRADE_ID = "12345678-1234-5678-1234-567812345678"

TRADE_PROPOSAL_BODY = {
    "ticker": "AAPL",
    "action": "BUY",
    "shares": 10,
    "price": 150.0,
    "analysis_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
}

PROPOSED_ROW = {
    "id": VALID_TRADE_ID,
    "status": "proposed",
    "ticker": "AAPL",
    "action": "BUY",
    "shares": 10.0,
    "price": 150.0,
    "proposed_at": "2026-03-02T10:00:00+00:00",
}


# ---------------------------------------------------------------------------
# POST /api/trades/propose
# ---------------------------------------------------------------------------


class TestProposeEndpoint:
    """Tests for POST /api/trades/propose.

    The route enforces two server-side gates before writing to trade_log:
    1. Kill-Switch check (403 if active)
    2. Full-Policy check (400 if violations)
    """

    @patch("src.routes.trades.propose_trade")
    @patch("src.routes.trades.run_full_policy", return_value=POLICY_PASSED)
    @patch("src.routes.trades.is_kill_switch_active", return_value=False)
    def test_200_success_returns_trade_fields(
        self, mock_ks, mock_policy, mock_propose, auth_client
    ):
        mock_propose.return_value = PROPOSED_ROW

        resp = auth_client.post("/api/trades/propose", json=TRADE_PROPOSAL_BODY)

        assert resp.status_code == 200
        data = resp.json()
        assert data["trade_id"] == VALID_TRADE_ID
        assert data["status"] == "proposed"
        assert data["ticker"] == "AAPL"
        assert data["action"] == "BUY"
        assert data["shares"] == 10.0
        assert data["price"] == 150.0
        # Verify gates were called
        mock_ks.assert_called_once()
        mock_policy.assert_called_once()

    def test_422_invalid_body_missing_required_fields(self, auth_client):
        resp = auth_client.post("/api/trades/propose", json={"ticker": "AAPL"})

        assert resp.status_code == 422

    # --- Kill-Switch gate tests ---

    @patch("src.routes.trades.is_kill_switch_active", return_value=True)
    def test_403_kill_switch_active_blocks_trade(self, mock_ks, auth_client):
        resp = auth_client.post("/api/trades/propose", json=TRADE_PROPOSAL_BODY)

        assert resp.status_code == 403
        assert "Kill-Switch" in resp.json()["detail"]

    @patch("src.routes.trades.run_full_policy")
    @patch("src.routes.trades.is_kill_switch_active", return_value=True)
    def test_403_kill_switch_does_not_call_policy(
        self, mock_ks, mock_policy, auth_client
    ):
        """When Kill-Switch is active, policy engine should never be called."""
        auth_client.post("/api/trades/propose", json=TRADE_PROPOSAL_BODY)

        mock_policy.assert_not_called()

    # --- Full-Policy gate tests ---

    @patch("src.routes.trades.run_full_policy", return_value=POLICY_FAILED_POSITION)
    @patch("src.routes.trades.is_kill_switch_active", return_value=False)
    def test_400_policy_violation_returns_violations_list(
        self, mock_ks, mock_policy, auth_client
    ):
        resp = auth_client.post("/api/trades/propose", json=TRADE_PROPOSAL_BODY)

        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["message"] == "Policy check failed"
        assert len(detail["violations"]) == 1
        violation = detail["violations"][0]
        assert violation["rule"] == "max_single_position"
        assert violation["severity"] == "blocking"

    @patch("src.routes.trades.run_full_policy", return_value=POLICY_FAILED_OWNERSHIP)
    @patch("src.routes.trades.is_kill_switch_active", return_value=False)
    def test_400_ownership_failure_returns_analysis_not_found(
        self, mock_ks, mock_policy, auth_client
    ):
        resp = auth_client.post("/api/trades/propose", json=TRADE_PROPOSAL_BODY)

        assert resp.status_code == 400
        detail = resp.json()["detail"]
        violations = detail["violations"]
        assert any(v["rule"] == "analysis_not_found" for v in violations)

    @patch("src.routes.trades.propose_trade")
    @patch("src.routes.trades.run_full_policy", return_value=POLICY_FAILED_POSITION)
    @patch("src.routes.trades.is_kill_switch_active", return_value=False)
    def test_400_policy_violation_does_not_write_trade(
        self, mock_ks, mock_policy, mock_propose, auth_client
    ):
        """When policy fails, propose_trade must NOT be called."""
        auth_client.post("/api/trades/propose", json=TRADE_PROPOSAL_BODY)

        mock_propose.assert_not_called()

    @patch("src.routes.trades.run_full_policy")
    @patch("src.routes.trades.is_kill_switch_active", return_value=False)
    def test_400_violation_does_not_leak_internal_values(
        self, mock_ks, mock_policy, auth_client
    ):
        """Violation response should NOT include current_value or limit_value."""
        mock_policy.return_value = POLICY_FAILED_POSITION

        resp = auth_client.post("/api/trades/propose", json=TRADE_PROPOSAL_BODY)

        assert resp.status_code == 400
        violation = resp.json()["detail"]["violations"][0]
        assert "current_value" not in violation
        assert "limit_value" not in violation

    # --- Policy engine error tests ---

    @patch("src.routes.trades.run_full_policy")
    @patch("src.routes.trades.is_kill_switch_active", return_value=False)
    def test_503_policy_engine_configuration_error(
        self, mock_ks, mock_policy, auth_client
    ):
        mock_policy.side_effect = ConfigurationError("DB unavailable")

        resp = auth_client.post("/api/trades/propose", json=TRADE_PROPOSAL_BODY)

        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]
        assert "DB" not in resp.json()["detail"]

    @patch("src.routes.trades.run_full_policy")
    @patch("src.routes.trades.is_kill_switch_active", return_value=False)
    def test_503_policy_engine_unexpected_error(
        self, mock_ks, mock_policy, auth_client
    ):
        mock_policy.side_effect = RuntimeError("unexpected crash")

        resp = auth_client.post("/api/trades/propose", json=TRADE_PROPOSAL_BODY)

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]
        assert "crash" not in resp.json()["detail"]

    # --- propose_trade error tests ---

    @patch("src.routes.trades.propose_trade")
    @patch("src.routes.trades.run_full_policy", return_value=POLICY_PASSED)
    @patch("src.routes.trades.is_kill_switch_active", return_value=False)
    def test_503_propose_trade_configuration_error(
        self, mock_ks, mock_policy, mock_propose, auth_client
    ):
        mock_propose.side_effect = ConfigurationError("Supabase not configured")

        resp = auth_client.post("/api/trades/propose", json=TRADE_PROPOSAL_BODY)

        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]
        assert "Supabase" not in resp.json()["detail"]

    # --- Auth tests ---

    def test_401_no_auth(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            from fastapi.testclient import TestClient

            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.post("/api/trades/propose", json=TRADE_PROPOSAL_BODY)
            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig


# ---------------------------------------------------------------------------
# POST /api/trades/{trade_id}/approve
# ---------------------------------------------------------------------------


class TestApproveEndpoint:
    @patch("src.routes.trades.approve_trade")
    def test_200_executed_returns_broker_order_id(self, mock_approve, auth_client):
        mock_approve.return_value = {
            "trade_id": VALID_TRADE_ID,
            "status": "executed",
            "broker_order_id": "alpaca-order-abc123",
            "executed_price": 149.85,
        }

        resp = auth_client.post(f"/api/trades/{VALID_TRADE_ID}/approve")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "executed"
        assert data["broker_order_id"] == "alpaca-order-abc123"

    @patch("src.routes.trades.approve_trade")
    def test_200_failed_broker_rejection_has_rejection_reason(
        self, mock_approve, auth_client
    ):
        mock_approve.return_value = {
            "trade_id": VALID_TRADE_ID,
            "status": "failed",
            "rejection_reason": "insufficient buying power",
        }

        resp = auth_client.post(f"/api/trades/{VALID_TRADE_ID}/approve")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["rejection_reason"] == "insufficient buying power"

    @patch("src.routes.trades.approve_trade")
    def test_404_trade_not_found(self, mock_approve, auth_client):
        mock_approve.side_effect = PreconditionError("Trade not found")

        resp = auth_client.post(f"/api/trades/{VALID_TRADE_ID}/approve")

        assert resp.status_code == 404
        assert "Trade not found" in resp.json()["detail"]

    @patch("src.routes.trades.approve_trade")
    def test_404_wrong_user_same_message_as_not_found(self, mock_approve, auth_client):
        # The route intentionally returns the same 404 for wrong-user
        # as for not-found (no info leak).
        mock_approve.side_effect = PreconditionError("Trade not found")

        resp = auth_client.post(f"/api/trades/{VALID_TRADE_ID}/approve")

        assert resp.status_code == 404
        assert "Trade not found" in resp.json()["detail"]

    @patch("src.routes.trades.approve_trade")
    def test_502_broker_error(self, mock_approve, auth_client):
        mock_approve.side_effect = BrokerError("alpaca", "Connection failed")

        resp = auth_client.post(f"/api/trades/{VALID_TRADE_ID}/approve")

        assert resp.status_code == 502
        assert "temporarily unavailable" in resp.json()["detail"]
        assert "alpaca" not in resp.json()["detail"].lower()

    @patch("src.routes.trades.approve_trade")
    def test_503_generic_exception(self, mock_approve, auth_client):
        mock_approve.side_effect = Exception("unexpected internal error")

        resp = auth_client.post(f"/api/trades/{VALID_TRADE_ID}/approve")

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]
        assert "internal" not in resp.json()["detail"].lower()

    # --- T-024: CircuitBreakerOpenError defense-in-depth ---

    @patch("src.routes.trades.approve_trade")
    def test_503_circuit_breaker_open_error(self, mock_approve, auth_client):
        """T-024: CircuitBreakerOpenError must return 503 before BrokerError handler."""
        mock_approve.side_effect = CircuitBreakerOpenError("alpaca")

        resp = auth_client.post(f"/api/trades/{VALID_TRADE_ID}/approve")

        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert "circuit breaker" in detail.lower()
        # Must not leak the internal provider name
        assert "alpaca" not in detail.lower()

    # --- T-027: Kill-Switch gate in approve flow ---

    @patch("src.routes.trades.is_kill_switch_active", return_value=True)
    def test_403_kill_switch_blocks_approve(self, mock_ks, auth_client):
        """T-027: Active Kill-Switch must block the approve endpoint with 403."""
        resp = auth_client.post(f"/api/trades/{VALID_TRADE_ID}/approve")

        assert resp.status_code == 403
        assert "Kill-Switch" in resp.json()["detail"]

    @patch("src.routes.trades.approve_trade")
    @patch("src.routes.trades.is_kill_switch_active", return_value=True)
    def test_kill_switch_does_not_call_approve_trade(
        self, mock_ks, mock_approve, auth_client
    ):
        """T-027: When Kill-Switch is active, approve_trade must never be called."""
        auth_client.post(f"/api/trades/{VALID_TRADE_ID}/approve")

        mock_approve.assert_not_called()

    @patch("src.routes.trades.approve_trade")
    @patch("src.routes.trades.is_kill_switch_active", return_value=False)
    def test_kill_switch_inactive_allows_approve(
        self, mock_ks, mock_approve, auth_client
    ):
        """T-027: Inactive Kill-Switch must let the approve flow proceed normally."""
        mock_approve.return_value = {
            "trade_id": VALID_TRADE_ID,
            "status": "executed",
            "broker_order_id": "alpaca-order-xyz",
            "executed_price": 150.0,
        }

        resp = auth_client.post(f"/api/trades/{VALID_TRADE_ID}/approve")

        assert resp.status_code == 200
        assert resp.json()["status"] == "executed"
        mock_approve.assert_called_once()

    def test_401_no_auth(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            from fastapi.testclient import TestClient

            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.post(f"/api/trades/{VALID_TRADE_ID}/approve")
            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig


# ---------------------------------------------------------------------------
# POST /api/trades/{trade_id}/reject
# ---------------------------------------------------------------------------


class TestRejectEndpoint:
    @patch("src.routes.trades.reject_trade")
    def test_200_success_returns_rejected_status(self, mock_reject, auth_client):
        mock_reject.return_value = {
            "trade_id": VALID_TRADE_ID,
            "status": "rejected",
            "rejection_reason": None,
        }

        resp = auth_client.post(f"/api/trades/{VALID_TRADE_ID}/reject")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"
        assert data["trade_id"] == VALID_TRADE_ID

    @patch("src.routes.trades.reject_trade")
    def test_200_with_reason_sets_rejection_reason(self, mock_reject, auth_client):
        mock_reject.return_value = {
            "trade_id": VALID_TRADE_ID,
            "status": "rejected",
            "rejection_reason": "Too expensive at current price",
        }

        resp = auth_client.post(
            f"/api/trades/{VALID_TRADE_ID}/reject",
            json={"reason": "Too expensive at current price"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"
        assert data["rejection_reason"] == "Too expensive at current price"
        # Verify the reason was forwarded to the service
        mock_reject.assert_called_once()
        _, _, forwarded_reason = mock_reject.call_args.args
        assert forwarded_reason == "Too expensive at current price"

    @patch("src.routes.trades.reject_trade")
    def test_404_trade_not_found(self, mock_reject, auth_client):
        mock_reject.side_effect = PreconditionError("Trade not found")

        resp = auth_client.post(f"/api/trades/{VALID_TRADE_ID}/reject")

        assert resp.status_code == 404
        assert "Trade not found" in resp.json()["detail"]

    def test_401_no_auth(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            from fastapi.testclient import TestClient

            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.post(f"/api/trades/{VALID_TRADE_ID}/reject")
            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig


# ---------------------------------------------------------------------------
# GET /api/trades
# ---------------------------------------------------------------------------


class TestListTradesEndpoint:
    def _make_admin_mock(self, rows: list) -> MagicMock:
        """Build a mock supabase admin client for list_trades query chain."""
        mock_admin = MagicMock()
        chain = mock_admin.table.return_value.select.return_value
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.execute.return_value = SimpleNamespace(data=rows)
        return mock_admin

    @patch("src.routes.trades.expire_stale_trades")
    @patch("src.routes.trades.get_supabase_admin")
    def test_200_returns_list_of_trades(
        self, mock_get_admin, mock_expire, auth_client
    ):
        rows = [PROPOSED_ROW, {**PROPOSED_ROW, "id": "other-trade-id", "status": "executed"}]
        mock_get_admin.return_value = self._make_admin_mock(rows)

        resp = auth_client.get("/api/trades")

        assert resp.status_code == 200
        data = resp.json()
        assert "trades" in data
        assert len(data["trades"]) == 2
        mock_expire.assert_called_once()

    @patch("src.routes.trades.expire_stale_trades")
    @patch("src.routes.trades.get_supabase_admin")
    def test_200_empty_list_when_no_trades(
        self, mock_get_admin, mock_expire, auth_client
    ):
        mock_get_admin.return_value = self._make_admin_mock([])

        resp = auth_client.get("/api/trades")

        assert resp.status_code == 200
        data = resp.json()
        assert data["trades"] == []

    @patch("src.routes.trades.expire_stale_trades")
    @patch("src.routes.trades.get_supabase_admin")
    def test_200_with_valid_status_filter(
        self, mock_get_admin, mock_expire, auth_client
    ):
        """A valid status filter (e.g. 'proposed') must be accepted and return 200."""
        rows = [PROPOSED_ROW]
        mock_get_admin.return_value = self._make_admin_mock(rows)

        resp = auth_client.get("/api/trades?status=proposed")

        assert resp.status_code == 200
        data = resp.json()
        assert "trades" in data

    def test_400_invalid_status_filter(self, auth_client):
        """An invalid status filter must return 400 with allowed values listed."""
        resp = auth_client.get("/api/trades?status=invalid_status")

        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "invalid_status" in detail
        assert "proposed" in detail  # At least one valid status listed

    def test_400_another_invalid_status(self, auth_client):
        """Different invalid status values must all return 400."""
        resp = auth_client.get("/api/trades?status=deleted")

        assert resp.status_code == 400

    def test_401_no_auth(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            from fastapi.testclient import TestClient

            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.get("/api/trades")
            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig


# ---------------------------------------------------------------------------
# GET /api/trades/positions
# ---------------------------------------------------------------------------


class TestGetPositionsEndpoint:
    @patch("src.routes.trades.get_broker_adapter")
    def test_200_returns_positions_list(self, mock_get_adapter, auth_client):
        mock_adapter = MagicMock()
        mock_adapter.get_positions.return_value = [
            Position(
                ticker="AAPL",
                shares=10.0,
                avg_price=150.0,
                current_price=155.0,
                market_value=1550.0,
            ),
            Position(
                ticker="MSFT",
                shares=5.0,
                avg_price=300.0,
                current_price=310.0,
                market_value=1550.0,
            ),
        ]
        mock_get_adapter.return_value = mock_adapter

        resp = auth_client.get("/api/trades/positions")

        assert resp.status_code == 200
        data = resp.json()
        assert "positions" in data
        assert len(data["positions"]) == 2
        first = data["positions"][0]
        assert first["ticker"] == "AAPL"
        assert first["shares"] == 10.0
        assert first["avg_price"] == 150.0
        assert first["current_price"] == 155.0
        assert first["market_value"] == 1550.0

    @patch("src.routes.trades.get_broker_adapter")
    def test_503_broker_not_configured(self, mock_get_adapter, auth_client):
        mock_get_adapter.side_effect = ConfigurationError(
            "Alpaca API key not configured"
        )

        resp = auth_client.get("/api/trades/positions")

        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]
        assert "Alpaca" not in resp.json()["detail"]

    def test_401_no_auth(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            from fastapi.testclient import TestClient

            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.get("/api/trades/positions")
            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig


# ---------------------------------------------------------------------------
# GET /api/trades/account
# ---------------------------------------------------------------------------


class TestGetAccountEndpoint:
    @patch("src.routes.trades.get_broker_adapter")
    def test_200_returns_account_info(self, mock_get_adapter, auth_client):
        mock_adapter = MagicMock()
        mock_adapter.get_account.return_value = AccountInfo(
            total_value=100_000.0,
            cash=25_000.0,
            buying_power=50_000.0,
        )
        mock_get_adapter.return_value = mock_adapter

        resp = auth_client.get("/api/trades/account")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_value"] == 100_000.0
        assert data["cash"] == 25_000.0
        assert data["buying_power"] == 50_000.0

    @patch("src.routes.trades.get_broker_adapter")
    def test_503_broker_not_configured(self, mock_get_adapter, auth_client):
        mock_get_adapter.side_effect = ConfigurationError(
            "Alpaca API key not configured"
        )

        resp = auth_client.get("/api/trades/account")

        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]
        assert "Alpaca" not in resp.json()["detail"]

    def test_401_no_auth(self, auth_client):
        from src.dependencies.auth import get_current_user
        from src.main import app

        orig = app.dependency_overrides.pop(get_current_user, None)
        try:
            from fastapi.testclient import TestClient

            unauth_client = TestClient(app, raise_server_exceptions=False)
            resp = unauth_client.get("/api/trades/account")
            assert resp.status_code in (401, 403)
        finally:
            if orig is not None:
                app.dependency_overrides[get_current_user] = orig


# ---------------------------------------------------------------------------
# UUID validation (FastAPI auto-validates path parameters)
# ---------------------------------------------------------------------------


class TestUUIDValidation:
    def test_422_invalid_trade_id_format_on_approve(self, auth_client):
        resp = auth_client.post("/api/trades/not-a-valid-uuid/approve")

        assert resp.status_code == 422
