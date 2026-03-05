"""Tests for the trade lifecycle orchestrator (src/services/trade_execution.py).

All tests mock DB calls and broker adapter — NO real API calls.

Structure:
- propose_trade tests (6)
- approve_trade tests (11)
- reject_trade tests (7)
- expire_stale_trades tests (5)
- run_lazy_maintenance called from approve/reject tests (2)
- run_lazy_maintenance throttle tests (4)
- T-024: CircuitBreakerOpenError in approve_trade (1)
- T-008: cleanup_orphaned_trades tests (4)
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from src.services.broker_adapter import OrderResult
from src.services.exceptions import BrokerError, CircuitBreakerOpenError, PreconditionError
from src.services.policy_engine import TradeProposal
from src.services.trade_execution import (
    approve_trade,
    cleanup_orphaned_trades,
    expire_stale_trades,
    propose_trade,
    reject_trade,
    run_lazy_maintenance,
)

FAKE_USER_ID = "test-user-id-123"
FAKE_TRADE_ID = "trade-id-abc-123"
FAKE_ANALYSIS_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


# --- Mock factory ---


def _mock_admin_table():
    """Create a mock Supabase admin client with chainable table calls.

    Chains needed for trade_execution:
    - trade_log: .insert(row).execute()
    - trade_log: .select("*").eq("id", id).execute()
    - trade_log: .update(data).eq("id", id).execute()
    - trade_log: .update(data).eq("id", id).eq("status", "proposed").execute()
    - trade_log: .update(data).eq("id", id).eq("user_id", uid).eq("status", "proposed").execute()
    - trade_log: .select("id").eq("status", ...).lt("proposed_at", ...).execute()
    """
    admin = MagicMock()
    tables = {}

    def table_factory(name):
        if name in tables:
            return tables[name]

        mock_table = MagicMock()

        # .insert(row).execute() — for propose_trade
        mock_table.insert.return_value.execute.return_value = SimpleNamespace(
            data=[{
                "id": FAKE_TRADE_ID,
                "user_id": FAKE_USER_ID,
                "analysis_id": FAKE_ANALYSIS_ID,
                "ticker": "AAPL",
                "action": "BUY",
                "shares": 10.0,
                "price": 150.0,
                "order_type": "LIMIT",
                "status": "proposed",
                "broker": "alpaca",
            }]
        )

        # .select("*").eq("id", id).execute() — for ownership reads
        chain_eq = mock_table.select.return_value.eq.return_value
        chain_eq.execute.return_value = SimpleNamespace(data=[])

        # .update(data).eq("id", id).execute() — for non-atomic status updates
        mock_table.update.return_value.eq.return_value.execute.return_value = SimpleNamespace(data=[])

        # .update(data).eq("id", id).eq("status", "proposed").execute()
        # — for atomic approve (2-eq chain, defaults to success)
        mock_table.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": FAKE_TRADE_ID}]
        )

        # .update(data).eq("id", id).eq("user_id", uid).eq("status", "proposed").execute()
        # — for atomic reject (3-eq chain, defaults to success)
        mock_table.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": FAKE_TRADE_ID}]
        )

        # .select("id").eq("status", "proposed").lt("proposed_at", cutoff).execute()
        # for expire_stale_trades
        chain_lt = chain_eq.lt.return_value
        chain_lt.execute.return_value = SimpleNamespace(data=[])

        tables[name] = mock_table
        return mock_table

    admin.table = MagicMock(side_effect=table_factory)
    admin._tables = tables
    return admin


# --- Helpers ---


def _make_trade_proposal(**overrides) -> TradeProposal:
    """Create a default TradeProposal with optional overrides."""
    defaults = {
        "ticker": "AAPL",
        "action": "BUY",
        "shares": 10.0,
        "price": 150.0,
        "analysis_id": FAKE_ANALYSIS_ID,
        "sector": None,
        "is_live_order": False,
    }
    defaults.update(overrides)
    return TradeProposal(**defaults)


def _make_proposed_trade(**overrides) -> dict:
    """Create a trade_log row in 'proposed' status."""
    base = {
        "id": FAKE_TRADE_ID,
        "user_id": FAKE_USER_ID,
        "analysis_id": FAKE_ANALYSIS_ID,
        "ticker": "AAPL",
        "action": "BUY",
        "shares": 10.0,
        "price": 150.0,
        "order_type": "LIMIT",
        "status": "proposed",
        "broker": "alpaca",
    }
    base.update(overrides)
    return base


# ============================================================
# propose_trade Tests
# ============================================================


class TestProposeTrade:
    @patch("src.services.trade_execution.get_supabase_admin")
    def test_success_returns_row_with_id(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        proposal = _make_trade_proposal()
        result = propose_trade(FAKE_USER_ID, proposal)

        assert result["id"] == FAKE_TRADE_ID

    @patch("src.services.trade_execution.get_supabase_admin")
    def test_correct_fields_written(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")

        proposal = _make_trade_proposal(action="buy")  # lowercase — should be uppercased
        propose_trade(FAKE_USER_ID, proposal)

        # Inspect the row that was inserted
        inserted_row = trade_table.insert.call_args[0][0]
        assert inserted_row["user_id"] == FAKE_USER_ID
        assert inserted_row["analysis_id"] == FAKE_ANALYSIS_ID
        assert inserted_row["ticker"] == "AAPL"
        assert inserted_row["action"] == "BUY"  # uppercased
        assert inserted_row["shares"] == 10.0
        assert inserted_row["price"] == 150.0

    @patch("src.services.trade_execution.get_supabase_admin")
    def test_broker_always_set_to_alpaca(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")

        propose_trade(FAKE_USER_ID, _make_trade_proposal())

        inserted_row = trade_table.insert.call_args[0][0]
        assert inserted_row["broker"] == "alpaca"

    @patch("src.services.trade_execution.get_supabase_admin")
    def test_order_type_always_limit(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")

        propose_trade(FAKE_USER_ID, _make_trade_proposal())

        inserted_row = trade_table.insert.call_args[0][0]
        assert inserted_row["order_type"] == "LIMIT"

    @patch("src.services.trade_execution.get_supabase_admin")
    def test_db_error_propagates(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        admin.table("trade_log").insert.return_value.execute.side_effect = Exception("DB connection failed")

        with pytest.raises(Exception, match="DB connection failed"):
            propose_trade(FAKE_USER_ID, _make_trade_proposal())

    @patch("src.services.trade_execution.get_supabase_admin")
    def test_empty_insert_response_raises_runtime_error(self, mock_admin_fn):
        """Guard against Supabase returning empty data on insert."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        admin.table("trade_log").insert.return_value.execute.return_value = SimpleNamespace(data=[])

        with pytest.raises(RuntimeError, match="Failed to create trade proposal"):
            propose_trade(FAKE_USER_ID, _make_trade_proposal())


# ============================================================
# approve_trade Tests
# ============================================================


class TestApproveTrade:
    @patch("src.services.trade_execution.get_broker_adapter")
    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_success_returns_executed_status(self, mock_maint, mock_admin_fn, mock_broker_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        trade_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[_make_proposed_trade()]
        )

        broker = MagicMock()
        broker.submit_order.return_value = OrderResult(
            success=True,
            broker_order_id="broker-ord-001",
            executed_price=150.5,
            executed_at="2026-03-02T10:00:00Z",
        )
        mock_broker_fn.return_value = broker

        result = approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

        assert result["status"] == "executed"
        assert result["trade_id"] == FAKE_TRADE_ID
        assert result["broker_order_id"] == "broker-ord-001"

    @patch("src.services.trade_execution.get_broker_adapter")
    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_success_executed_at_and_price_set(self, mock_maint, mock_admin_fn, mock_broker_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        trade_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[_make_proposed_trade()]
        )

        broker = MagicMock()
        broker.submit_order.return_value = OrderResult(
            success=True,
            broker_order_id="broker-ord-001",
            executed_price=150.5,
            executed_at="2026-03-02T10:00:00Z",
        )
        mock_broker_fn.return_value = broker

        approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

        # The update call for status=executed should include executed_at and executed_price
        update_calls = trade_table.update.call_args_list
        executed_update = None
        for update_call in update_calls:
            update_data = update_call[0][0]
            if update_data.get("status") == "executed":
                executed_update = update_data
                break

        assert executed_update is not None
        assert "executed_at" in executed_update
        assert executed_update["executed_at"] == "2026-03-02T10:00:00Z"
        assert "executed_price" in executed_update
        assert executed_update["executed_price"] == 150.5

    @patch("src.services.trade_execution.get_broker_adapter")
    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_executed_price_none_not_written_to_db(self, mock_maint, mock_admin_fn, mock_broker_fn):
        """When executed_price is None, it must NOT be included in the DB update."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        trade_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[_make_proposed_trade()]
        )

        broker = MagicMock()
        broker.submit_order.return_value = OrderResult(
            success=True,
            broker_order_id="broker-ord-001",
            executed_price=None,
            executed_at="2026-03-02T10:00:00Z",
        )
        mock_broker_fn.return_value = broker

        approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

        update_calls = trade_table.update.call_args_list
        executed_update = None
        for update_call in update_calls:
            update_data = update_call[0][0]
            if update_data.get("status") == "executed":
                executed_update = update_data
                break

        assert executed_update is not None
        assert "executed_price" not in executed_update

    @patch("src.services.trade_execution.get_broker_adapter")
    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_approved_at_set_before_broker_call(self, mock_maint, mock_admin_fn, mock_broker_fn):
        """approved_at must be set in DB update before broker is called."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        trade_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[_make_proposed_trade()]
        )

        call_order = []

        def record_update(data):
            call_order.append(("update", data))
            return trade_table.update.return_value

        def record_broker_call(order):
            call_order.append(("broker",))
            return OrderResult(success=True, broker_order_id="b-001", executed_price=150.0)

        trade_table.update.side_effect = record_update
        broker = MagicMock()
        broker.submit_order.side_effect = record_broker_call
        mock_broker_fn.return_value = broker

        approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

        # First call to update should be the "approved" update
        assert call_order[0][0] == "update"
        assert call_order[0][1].get("status") == "approved"
        assert "approved_at" in call_order[0][1]
        # Broker is called after the approved update
        assert call_order[1][0] == "broker"

    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_not_found_raises_precondition_error(self, mock_maint, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        # Default mock returns empty data (not found)

        with pytest.raises(PreconditionError, match="Trade not found"):
            approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_wrong_user_same_message_as_not_found(self, mock_maint, mock_admin_fn):
        """Ownership check must use same message for not-found and wrong-user (no info leak)."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        trade_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[_make_proposed_trade(user_id="different-user-id")]
        )

        with pytest.raises(PreconditionError, match="Trade not found"):
            approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_already_approved_raises_precondition_error(self, mock_maint, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        trade_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[_make_proposed_trade(status="approved")]
        )

        with pytest.raises(PreconditionError, match="Trade is not in proposed status"):
            approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_already_rejected_raises_precondition_error(self, mock_maint, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        trade_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[_make_proposed_trade(status="rejected")]
        )

        with pytest.raises(PreconditionError, match="Trade is not in proposed status"):
            approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_already_executed_raises_precondition_error(self, mock_maint, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        trade_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[_make_proposed_trade(status="executed")]
        )

        with pytest.raises(PreconditionError, match="Trade is not in proposed status"):
            approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

    @patch("src.services.trade_execution.get_broker_adapter")
    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_broker_rejects_order_returns_failed(self, mock_maint, mock_admin_fn, mock_broker_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        trade_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[_make_proposed_trade()]
        )

        broker = MagicMock()
        broker.submit_order.return_value = OrderResult(
            success=False,
            error_message="Insufficient buying power",
        )
        mock_broker_fn.return_value = broker

        result = approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

        assert result["status"] == "failed"
        assert result["rejection_reason"] == "Insufficient buying power"

    @patch("src.services.trade_execution.log_error")
    @patch("src.services.trade_execution.get_broker_adapter")
    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_broker_error_exception_returns_failed_and_logs(
        self, mock_maint, mock_admin_fn, mock_broker_fn, mock_log_error
    ):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        trade_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[_make_proposed_trade()]
        )

        broker = MagicMock()
        broker.submit_order.side_effect = BrokerError("alpaca", "Connection timed out")
        mock_broker_fn.return_value = broker

        result = approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

        assert result["status"] == "failed"
        assert result["rejection_reason"] == "Broker connection failed"
        mock_log_error.assert_called_once()

    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_concurrent_status_change_raises_precondition_error(
        self, mock_maint, mock_admin_fn
    ):
        """TOCTOU guard: SELECT returns proposed, but atomic UPDATE finds status already changed."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")

        # SELECT returns proposed trade (passes ownership + status guards)
        trade_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[_make_proposed_trade()]
        )
        # Atomic UPDATE returns empty (concurrent request changed status between SELECT and UPDATE)
        trade_table.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )

        with pytest.raises(PreconditionError, match="Trade is not in proposed status"):
            approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

    # T-024: CircuitBreakerOpenError is caught BEFORE BrokerError (they are siblings)
    @patch("src.services.trade_execution.log_error")
    @patch("src.services.trade_execution.get_broker_adapter")
    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_circuit_breaker_open_marks_trade_failed(
        self, mock_maint, mock_admin_fn, mock_broker_fn, mock_log_error
    ):
        """CircuitBreakerOpenError must mark the trade failed and call log_error.

        CircuitBreakerOpenError inherits DataProviderError, NOT BrokerError —
        they are siblings. The except block for CircuitBreakerOpenError must
        appear before BrokerError in approve_trade so it is caught correctly.
        """
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        trade_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[_make_proposed_trade()]
        )

        broker = MagicMock()
        broker.submit_order.side_effect = CircuitBreakerOpenError("alpaca")
        mock_broker_fn.return_value = broker

        result = approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

        assert result["status"] == "failed"
        assert "circuit breaker" in result["rejection_reason"].lower()
        mock_log_error.assert_called_once()


# ============================================================
# reject_trade Tests
# ============================================================


class TestRejectTrade:
    """Tests for reject_trade — uses atomic conditional UPDATE.

    reject_trade uses .update().eq("id", ...).eq("user_id", ...).eq("status", "proposed")
    so ownership, status guard, and update are atomic (no TOCTOU race).
    All failure cases return "Trade not found" (no info leak).
    """

    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_success_returns_rejected_status(self, mock_maint, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        # 3-eq chain defaults to success in factory

        result = reject_trade(FAKE_TRADE_ID, FAKE_USER_ID)

        assert result["status"] == "rejected"
        assert result["trade_id"] == FAKE_TRADE_ID

    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_with_reason_sets_rejection_reason(self, mock_maint, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        # 3-eq chain defaults to success in factory

        result = reject_trade(FAKE_TRADE_ID, FAKE_USER_ID, reason="Market conditions changed")

        assert result["rejection_reason"] == "Market conditions changed"
        # Verify reason was included in the DB update payload
        updated_data = trade_table.update.call_args[0][0]
        assert updated_data.get("rejection_reason") == "Market conditions changed"

    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_without_reason_rejection_reason_is_none(self, mock_maint, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        # 3-eq chain defaults to success in factory

        result = reject_trade(FAKE_TRADE_ID, FAKE_USER_ID)

        assert result["rejection_reason"] is None
        # Verify rejection_reason not included in DB update when no reason given
        updated_data = trade_table.update.call_args[0][0]
        assert "rejection_reason" not in updated_data

    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_not_found_raises_precondition_error(self, mock_maint, mock_admin_fn):
        """Atomic update returns empty when trade doesn't exist."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        # Override 3-eq chain to return empty (no matching row)
        trade_table.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )

        with pytest.raises(PreconditionError, match="Trade not found"):
            reject_trade(FAKE_TRADE_ID, FAKE_USER_ID)

    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_wrong_user_same_message_as_not_found(self, mock_maint, mock_admin_fn):
        """No info leak — wrong user_id in .eq() causes empty result, same error as not-found."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        # Atomic update with wrong user_id returns empty
        trade_table.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )

        with pytest.raises(PreconditionError, match="Trade not found"):
            reject_trade(FAKE_TRADE_ID, FAKE_USER_ID)

    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_already_approved_raises_precondition_error(self, mock_maint, mock_admin_fn):
        """Atomic update with .eq("status", "proposed") won't match already-approved trades."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        trade_table.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )

        with pytest.raises(PreconditionError, match="Trade not found"):
            reject_trade(FAKE_TRADE_ID, FAKE_USER_ID)

    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_already_executed_raises_precondition_error(self, mock_maint, mock_admin_fn):
        """Atomic update with .eq("status", "proposed") won't match already-executed trades."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        trade_table.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )

        with pytest.raises(PreconditionError, match="Trade not found"):
            reject_trade(FAKE_TRADE_ID, FAKE_USER_ID)


# ============================================================
# expire_stale_trades Tests
# ============================================================


class TestExpireStaleTrades:
    @patch("src.services.trade_execution.get_supabase_admin")
    def test_no_old_trades_returns_zero(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        # Default mock: .select().eq().lt().execute() returns empty data

        result = expire_stale_trades()

        assert result == 0

    @patch("src.services.trade_execution.get_supabase_admin")
    def test_old_proposed_trades_are_expired(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")

        stale_trade_ids = [
            {"id": "stale-trade-001"},
            {"id": "stale-trade-002"},
        ]
        trade_table.select.return_value.eq.return_value.lt.return_value.execute.return_value = SimpleNamespace(
            data=stale_trade_ids
        )

        result = expire_stale_trades()

        assert result == 2
        # Verify each stale trade was updated with rejection reason
        update_calls = trade_table.update.call_args_list
        assert len(update_calls) == 2
        for update_call in update_calls:
            update_data = update_call[0][0]
            assert update_data["status"] == "rejected"
            assert update_data["rejection_reason"] == "Expired after 24 hours"

    @patch("src.services.trade_execution.get_supabase_admin")
    def test_recent_proposed_trades_untouched(self, mock_admin_fn):
        """Trades proposed less than 24 hours ago must not be expired.

        The query filters by .lt("proposed_at", cutoff) — only old trades
        are returned. This test verifies the query chain is called correctly
        and that no updates are made when no stale trades are found.
        """
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")

        # Recent trade not returned by the stale query
        trade_table.select.return_value.eq.return_value.lt.return_value.execute.return_value = SimpleNamespace(
            data=[]  # no stale trades
        )

        result = expire_stale_trades()

        assert result == 0
        trade_table.update.assert_not_called()

    @patch("src.services.trade_execution.get_supabase_admin")
    def test_non_proposed_trades_untouched(self, mock_admin_fn):
        """Trades with status != 'proposed' must not be expired.

        The query filters by .eq("status", "proposed") — only proposed
        trades are returned. This test verifies the query chain uses
        eq("status", "proposed") before the lt() filter.
        """
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")

        # Simulate query returning empty because of status filter
        trade_table.select.return_value.eq.return_value.lt.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )

        result = expire_stale_trades()

        assert result == 0
        # Verify the query included a status filter (.eq called with "status", "proposed")
        eq_call_args = trade_table.select.return_value.eq.call_args
        assert eq_call_args[0][0] == "status"
        assert eq_call_args[0][1] == "proposed"

    @patch("src.services.trade_execution.get_supabase_admin")
    def test_db_failure_returns_zero_best_effort(self, mock_admin_fn):
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")

        # Simulate DB failure on the query
        trade_table.select.return_value.eq.return_value.lt.return_value.execute.side_effect = Exception(
            "DB connection lost"
        )

        result = expire_stale_trades()

        # Best-effort: returns 0 without raising
        assert result == 0


# ============================================================
# run_lazy_maintenance called from approve/reject Tests
# ============================================================


class TestMaintenanceCalledFromOperations:
    @patch("src.services.trade_execution.get_broker_adapter")
    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_approve_calls_run_lazy_maintenance(
        self, mock_maint, mock_admin_fn, mock_broker_fn
    ):
        """approve_trade must call run_lazy_maintenance before processing."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")
        trade_table.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[_make_proposed_trade()]
        )

        broker = MagicMock()
        broker.submit_order.return_value = OrderResult(
            success=True,
            broker_order_id="b-001",
            executed_price=150.0,
        )
        mock_broker_fn.return_value = broker

        approve_trade(FAKE_TRADE_ID, FAKE_USER_ID)

        mock_maint.assert_called_once()

    @patch("src.services.trade_execution.get_supabase_admin")
    @patch("src.services.trade_execution.run_lazy_maintenance")
    def test_reject_calls_run_lazy_maintenance(self, mock_maint, mock_admin_fn):
        """reject_trade must call run_lazy_maintenance before processing."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin

        reject_trade(FAKE_TRADE_ID, FAKE_USER_ID)

        mock_maint.assert_called_once()


# ============================================================
# run_lazy_maintenance throttle Tests
# ============================================================


class TestRunLazyMaintenance:
    """Tests for the 60s process-level throttle on maintenance."""

    @patch("src.services.trade_execution.cleanup_orphaned_trades")
    @patch("src.services.trade_execution.expire_stale_trades")
    @patch("src.services.trade_execution.time")
    def test_first_call_runs_maintenance(self, mock_time, mock_expire, mock_cleanup):
        """First call (last_maintenance_at=0) must always run."""
        import src.services.trade_execution as mod
        mod._last_maintenance_at = 0.0
        mock_time.monotonic.return_value = 100.0

        run_lazy_maintenance()

        mock_expire.assert_called_once()
        mock_cleanup.assert_called_once()

    @patch("src.services.trade_execution.cleanup_orphaned_trades")
    @patch("src.services.trade_execution.expire_stale_trades")
    @patch("src.services.trade_execution.time")
    def test_second_call_within_interval_skips(self, mock_time, mock_expire, mock_cleanup):
        """Call within 60s of last run must skip maintenance."""
        import src.services.trade_execution as mod
        mod._last_maintenance_at = 100.0
        mock_time.monotonic.return_value = 130.0  # 30s later

        run_lazy_maintenance()

        mock_expire.assert_not_called()
        mock_cleanup.assert_not_called()

    @patch("src.services.trade_execution.cleanup_orphaned_trades")
    @patch("src.services.trade_execution.expire_stale_trades")
    @patch("src.services.trade_execution.time")
    def test_call_after_interval_runs_again(self, mock_time, mock_expire, mock_cleanup):
        """Call after 60s interval must run maintenance again."""
        import src.services.trade_execution as mod
        mod._last_maintenance_at = 100.0
        mock_time.monotonic.return_value = 161.0  # 61s later

        run_lazy_maintenance()

        mock_expire.assert_called_once()
        mock_cleanup.assert_called_once()

    @patch("src.services.trade_execution.cleanup_orphaned_trades")
    @patch("src.services.trade_execution.expire_stale_trades")
    @patch("src.services.trade_execution.time")
    def test_updates_last_maintenance_timestamp(self, mock_time, mock_expire, mock_cleanup):
        """After running, _last_maintenance_at must be updated to current time."""
        import src.services.trade_execution as mod
        mod._last_maintenance_at = 0.0
        mock_time.monotonic.return_value = 200.0

        run_lazy_maintenance()

        assert mod._last_maintenance_at == 200.0


# ============================================================
# T-008: cleanup_orphaned_trades Tests
# ============================================================


class TestCleanupOrphanedTrades:
    """Tests for cleanup_orphaned_trades (T-008).

    cleanup_orphaned_trades queries approved trades older than max_age_hours
    and sets their status to 'failed'. Pattern is identical to expire_stale_trades:
    best-effort, per-row updates, logs errors, returns count.

    The query chain is: .select("id").eq("status", "approved").lt("approved_at", cutoff)
    which maps to the same chain_lt path in _mock_admin_table().
    """

    @patch("src.services.trade_execution.get_supabase_admin")
    def test_no_orphaned_trades_returns_zero(self, mock_admin_fn):
        """When no approved trades are older than the cutoff, returns 0."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        # Default mock: .select().eq().lt().execute() returns empty data

        result = cleanup_orphaned_trades()

        assert result == 0

    @patch("src.services.trade_execution.log_error")
    @patch("src.services.trade_execution.get_supabase_admin")
    def test_orphaned_trades_set_to_failed(self, mock_admin_fn, mock_log_error):
        """Two orphaned approved trades must each be updated to status='failed'."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")

        orphaned_trade_ids = [
            {"id": "orphan-trade-001"},
            {"id": "orphan-trade-002"},
        ]
        trade_table.select.return_value.eq.return_value.lt.return_value.execute.return_value = SimpleNamespace(
            data=orphaned_trade_ids
        )

        result = cleanup_orphaned_trades()

        assert result == 2
        # Each orphaned trade must be updated to status="failed"
        update_calls = trade_table.update.call_args_list
        assert len(update_calls) == 2
        for update_call in update_calls:
            update_data = update_call[0][0]
            assert update_data["status"] == "failed"

        mock_log_error.assert_called_once_with(
            "trade_execution",
            "orphaned_trades_cleaned",
            "Cleaned up 2 orphaned trade(s)",
        )

    @patch("src.services.trade_execution.get_supabase_admin")
    def test_db_failure_returns_zero(self, mock_admin_fn):
        """When get_supabase_admin() raises, returns 0 without propagating."""
        mock_admin_fn.side_effect = Exception("DB connection lost")

        result = cleanup_orphaned_trades()

        assert result == 0

    @patch("src.services.trade_execution.get_supabase_admin")
    def test_db_query_failure_returns_zero(self, mock_admin_fn):
        """When the DB query itself raises, returns 0 (best-effort)."""
        admin = _mock_admin_table()
        mock_admin_fn.return_value = admin
        trade_table = admin.table("trade_log")

        trade_table.select.return_value.eq.return_value.lt.return_value.execute.side_effect = Exception(
            "DB connection lost"
        )

        result = cleanup_orphaned_trades()

        assert result == 0
