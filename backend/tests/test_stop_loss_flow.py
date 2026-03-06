"""Tests for stop_loss flow through propose -> approve pipeline.

Verifies that stop_loss propagates from TradeProposal -> trade_log -> Order.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services.broker_adapter import Order, OrderResult
from src.services.exceptions import PreconditionError
from src.services.policy_engine import TradeProposal
from src.services.trade_execution import approve_trade, propose_trade


FAKE_USER_ID = "test-user-id-123"
FAKE_TRADE_ID = "trade-id-abc-123"
FAKE_ANALYSIS_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def _make_proposal(stop_loss=None):
    """Create a TradeProposal with optional stop_loss."""
    return TradeProposal(
        ticker="AAPL",
        action="BUY",
        shares=10,
        price=150.0,
        analysis_id=FAKE_ANALYSIS_ID,
        stop_loss=stop_loss,
    )


def _make_mock_admin_for_propose(stop_loss=None):
    """Mock admin for propose_trade."""
    admin = MagicMock()
    row = {
        "id": FAKE_TRADE_ID,
        "user_id": FAKE_USER_ID,
        "ticker": "AAPL",
        "action": "BUY",
        "shares": 10.0,
        "price": 150.0,
        "stop_loss": stop_loss,
        "order_type": "LIMIT",
        "status": "proposed",
        "broker": "alpaca",
    }
    admin.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
        data=[row]
    )
    # Idempotency check: 5-eq SELECT chain returns empty (no duplicate)
    eq5 = admin.table.return_value.select.return_value
    for _ in range(5):
        eq5 = eq5.eq.return_value
    eq5.execute.return_value = SimpleNamespace(data=[])
    return admin


def _make_mock_admin_for_approve(stop_loss=None):
    """Mock admin for approve_trade with all required chain methods."""
    admin = MagicMock()

    trade_row = {
        "id": FAKE_TRADE_ID,
        "user_id": FAKE_USER_ID,
        "ticker": "AAPL",
        "action": "BUY",
        "shares": 10.0,
        "price": 150.0,
        "stop_loss": stop_loss,
        "order_type": "LIMIT",
        "status": "proposed",
        "broker": "alpaca",
    }

    # .select("*").eq("id", trade_id).execute() — read trade
    admin.table.return_value.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[trade_row]
    )

    # .update(...).eq("id", ...).eq("status", "proposed").execute() — atomic approve
    admin.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[{"id": FAKE_TRADE_ID}]
    )

    # expire_stale_trades: .select("id").eq("status", ...).lt(...).execute()
    admin.table.return_value.select.return_value.eq.return_value.lt.return_value.execute.return_value = SimpleNamespace(
        data=[]
    )

    return admin


class TestProposeWithStopLoss:
    @patch("src.services.trade_execution.get_supabase_admin")
    def test_propose_with_stop_loss_in_row(self, mock_admin_fn):
        """stop_loss value appears in the trade_log insert row."""
        admin = _make_mock_admin_for_propose(stop_loss=127.5)
        mock_admin_fn.return_value = admin

        result = propose_trade(FAKE_USER_ID, _make_proposal(stop_loss=127.5))

        # Verify the insert was called with stop_loss
        insert_args = admin.table.return_value.insert.call_args[0][0]
        assert insert_args["stop_loss"] == 127.5
        assert result["stop_loss"] == 127.5

    @patch("src.services.trade_execution.get_supabase_admin")
    def test_propose_without_stop_loss_null_in_row(self, mock_admin_fn):
        """No stop_loss results in null in trade_log."""
        admin = _make_mock_admin_for_propose(stop_loss=None)
        mock_admin_fn.return_value = admin

        result = propose_trade(FAKE_USER_ID, _make_proposal(stop_loss=None))

        insert_args = admin.table.return_value.insert.call_args[0][0]
        assert insert_args["stop_loss"] is None
        assert result["stop_loss"] is None


class TestApproveWithStopLoss:
    @patch("src.services.trade_execution.get_broker_adapter")
    @patch("src.services.trade_execution.get_supabase_admin")
    def test_approve_passes_stop_loss_to_order(self, mock_admin_fn, mock_broker_fn):
        """stop_loss from trade_log row is passed to Order."""
        admin = _make_mock_admin_for_approve(stop_loss=127.5)
        mock_admin_fn.return_value = admin

        mock_adapter = MagicMock()
        mock_adapter.submit_order.return_value = OrderResult(
            success=True,
            broker_order_id="alpaca-order-123",
            executed_price=150.0,
        )
        mock_broker_fn.return_value = mock_adapter

        result = approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

        assert result["status"] == "executed"
        # Verify Order was created with stop_loss
        order_arg = mock_adapter.submit_order.call_args[0][0]
        assert isinstance(order_arg, Order)
        assert order_arg.stop_loss == 127.5

    @patch("src.services.trade_execution.get_broker_adapter")
    @patch("src.services.trade_execution.get_supabase_admin")
    def test_approve_without_stop_loss_order_has_none(self, mock_admin_fn, mock_broker_fn):
        """No stop_loss in trade_log results in Order.stop_loss=None."""
        admin = _make_mock_admin_for_approve(stop_loss=None)
        mock_admin_fn.return_value = admin

        mock_adapter = MagicMock()
        mock_adapter.submit_order.return_value = OrderResult(
            success=True,
            broker_order_id="alpaca-order-456",
            executed_price=150.0,
        )
        mock_broker_fn.return_value = mock_adapter

        result = approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

        assert result["status"] == "executed"
        order_arg = mock_adapter.submit_order.call_args[0][0]
        assert order_arg.stop_loss is None
