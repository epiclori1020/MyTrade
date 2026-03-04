"""Trade lifecycle orchestrator — propose, approve, reject, expire.

Manages the trade_log state machine:
    proposed -> approved -> executed
        |          |
        v          v
    rejected     failed

    proposed -> rejected (expired after 24h)

All DB operations use service_role via get_supabase_admin() with
explicit user_id validation. The RLS UPDATE policy on trade_log only
allows user-JWT to set proposed->approved/rejected. Backend transitions
(approved->executed, approved->failed) require service_role.
"""

import logging
from datetime import datetime, timedelta, timezone

from src.services.alpaca_paper import get_broker_adapter
from src.services.broker_adapter import Order
from src.services.error_logger import log_error
from src.services.exceptions import BrokerError, PreconditionError
from src.services.supabase import get_supabase_admin

logger = logging.getLogger(__name__)


def propose_trade(user_id: str, trade_proposal) -> dict:
    """Write trade proposal to trade_log with status='proposed'.

    Called AFTER Full-Policy has passed. TradeProposal fields `sector`
    and `is_live_order` are policy-only — not written to trade_log.

    Returns: trade_log row dict (including generated id).
    """
    admin = get_supabase_admin()
    row = {
        "user_id": user_id,
        "analysis_id": trade_proposal.analysis_id,
        "ticker": trade_proposal.ticker,
        "action": trade_proposal.action.upper(),
        "shares": float(trade_proposal.shares),
        "price": float(trade_proposal.price),
        "order_type": "LIMIT",
        "stop_loss": float(trade_proposal.stop_loss) if trade_proposal.stop_loss is not None else None,
        "status": "proposed",
        "broker": "alpaca",
    }

    resp = admin.table("trade_log").insert(row).execute()
    if not resp.data:
        logger.error("trade_log insert returned empty data for user %s", user_id)
        raise RuntimeError("Failed to create trade proposal")
    return resp.data[0]


def approve_trade(trade_id: str, user_id: str) -> dict:
    """User approves a proposed trade -> execute via broker.

    7-step flow:
    1. Expire stale trades (prevents approving an expired trade)
    2. Read trade from trade_log
    3. Ownership check (same message for not-found and wrong-user)
    4. Status guard (must be 'proposed')
    5. Atomic update status -> 'approved' + approved_at
       (conditional on status='proposed' to prevent TOCTOU race)
    6. Verify atomic update succeeded (concurrent modification check)
    7. Call broker submit_order() -> 'executed' or 'failed'

    Known limitation (MVP-acceptable): If the server crashes between
    step 5 (status='approved') and step 7 (broker call), the trade
    stays permanently in 'approved' status with no recovery mechanism.
    Step 11 (Monitoring) should add a cleanup job for orphaned 'approved'
    trades older than 1 hour.

    All DB operations via service_role with explicit user_id validation.

    Raises:
        PreconditionError: Trade not found, wrong user, or wrong status.
    """
    expire_stale_trades()

    admin = get_supabase_admin()

    # Read trade
    resp = admin.table("trade_log").select("*").eq("id", trade_id).execute()
    data = resp.data

    # Ownership check — same message for not-found and wrong-user (no info leak)
    if not data or data[0].get("user_id") != user_id:
        raise PreconditionError("Trade not found")

    trade = data[0]

    # Status guard
    if trade["status"] != "proposed":
        raise PreconditionError("Trade is not in proposed status")

    # Atomic update to approved — .eq("status", "proposed") prevents TOCTOU race
    now_iso = datetime.now(timezone.utc).isoformat()
    update_resp = (
        admin.table("trade_log")
        .update({"status": "approved", "approved_at": now_iso})
        .eq("id", trade_id)
        .eq("status", "proposed")
        .execute()
    )

    if not update_resp.data:
        raise PreconditionError("Trade is not in proposed status")

    # Execute via broker
    order = Order(
        ticker=trade["ticker"],
        action=trade["action"],
        shares=float(trade["shares"]),
        price=float(trade["price"]),
        order_type=trade.get("order_type", "LIMIT"),
        stop_loss=float(trade["stop_loss"]) if trade.get("stop_loss") is not None else None,
    )

    try:
        result = get_broker_adapter().submit_order(order)
    except BrokerError as exc:
        logger.error("Broker error during trade execution: %s", exc)
        log_error("broker", "order_submission_failed", str(exc))
        admin.table("trade_log").update({
            "status": "failed",
            "rejection_reason": "Broker connection failed",
        }).eq("id", trade_id).execute()
        return {
            "trade_id": trade_id,
            "status": "failed",
            "rejection_reason": "Broker connection failed",
        }

    if result.success:
        executed_at = result.executed_at or datetime.now(timezone.utc).isoformat()
        update_data = {
            "status": "executed",
            "broker_order_id": result.broker_order_id,
            "executed_at": executed_at,
        }
        if result.executed_price is not None:
            update_data["executed_price"] = float(result.executed_price)
        admin.table("trade_log").update(update_data).eq("id", trade_id).execute()
        return {
            "trade_id": trade_id,
            "status": "executed",
            "broker_order_id": result.broker_order_id,
            "executed_price": result.executed_price,
        }
    else:
        admin.table("trade_log").update({
            "status": "failed",
            "rejection_reason": result.error_message,
        }).eq("id", trade_id).execute()
        return {
            "trade_id": trade_id,
            "status": "failed",
            "rejection_reason": result.error_message,
        }


def reject_trade(trade_id: str, user_id: str, reason: str | None = None) -> dict:
    """User rejects a proposed trade.

    Atomic conditional update — ownership, status guard, and update happen
    in a single DB call via .eq("user_id", ...).eq("status", "proposed").
    This prevents TOCTOU races. All failure cases (not found, wrong user,
    wrong status) return the same "Trade not found" message (no info leak).

    No broker call needed.

    Raises:
        PreconditionError: Trade not found, wrong user, or not in proposed status.
    """
    expire_stale_trades()

    admin = get_supabase_admin()

    update = {"status": "rejected"}
    if reason:
        update["rejection_reason"] = reason

    resp = (
        admin.table("trade_log")
        .update(update)
        .eq("id", trade_id)
        .eq("user_id", user_id)
        .eq("status", "proposed")
        .execute()
    )

    if not resp.data:
        raise PreconditionError("Trade not found")

    return {
        "trade_id": trade_id,
        "status": "rejected",
        "rejection_reason": reason,
    }


def expire_stale_trades() -> int:
    """Expire trades that have been 'proposed' for > 24 hours.

    Best-effort: if DB fails, log warning and return 0.
    Called lazily from approve, reject, and list endpoints.

    Returns: count of expired trades.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    try:
        admin = get_supabase_admin()
        resp = (
            admin.table("trade_log")
            .select("id")
            .eq("status", "proposed")
            .lt("proposed_at", cutoff)
            .execute()
        )
    except Exception as exc:
        logger.warning("Failed to query stale trades: %s", exc)
        return 0

    if not resp.data:
        return 0

    count = 0
    for row in resp.data:
        try:
            admin.table("trade_log").update({
                "status": "rejected",
                "rejection_reason": "Expired after 24 hours",
            }).eq("id", row["id"]).execute()
            count += 1
        except Exception as exc:
            logger.warning("Failed to expire trade %s: %s", row["id"], exc)

    return count
