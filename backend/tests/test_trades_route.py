"""Tests for the Trade API routes (src/routes/trades.py).

All tests use auth_client fixture and mock the service layer.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services.broker_adapter import AccountInfo, Position
from src.services.exceptions import BrokerError, ConfigurationError, PreconditionError
from tests.conftest import FAKE_USER


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
    @patch("src.routes.trades.propose_trade")
    def test_200_success_returns_trade_fields(self, mock_propose, auth_client):
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

    def test_422_invalid_body_missing_required_fields(self, auth_client):
        resp = auth_client.post("/api/trades/propose", json={"ticker": "AAPL"})

        assert resp.status_code == 422

    @patch("src.routes.trades.propose_trade")
    def test_503_configuration_error(self, mock_propose, auth_client):
        mock_propose.side_effect = ConfigurationError("Supabase not configured")

        resp = auth_client.post("/api/trades/propose", json=TRADE_PROPOSAL_BODY)

        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]
        assert "Supabase" not in resp.json()["detail"]

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
