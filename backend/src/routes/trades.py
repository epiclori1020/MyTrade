"""Trade API endpoints — propose, approve, reject, list, positions, account."""

from uuid import UUID

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel

from src.dependencies.auth import authenticated_router
from src.dependencies.error_handler import handle_service_errors
from src.dependencies.rate_limit import limiter
from src.services.alpaca_paper import get_broker_adapter
from src.services.kill_switch import is_kill_switch_active
from src.services.policy_engine import TradeProposal, run_full_policy
from src.services.supabase import get_supabase_admin
from src.services.trade_execution import (
    approve_trade,
    propose_trade,
    reject_trade,
    run_lazy_maintenance,
)

router = authenticated_router(prefix="/api/trades", tags=["trades"])

VALID_TRADE_STATUSES = frozenset({
    "proposed", "approved", "rejected", "executed", "failed",
})


class RejectBody(BaseModel):
    """Request body for trade rejection."""

    reason: str | None = None


@router.post("/propose")
@limiter.limit("50/minute")
@handle_service_errors(service_name="Trade service")
def propose(request: Request, trade_proposal: TradeProposal) -> dict:
    """Create a trade proposal after Kill-Switch + Full-Policy checks.

    Server-side enforcement: even if the frontend skips policy checks,
    this endpoint validates Kill-Switch and Full-Policy before writing
    to trade_log.  TradeProposal fields `sector` and `is_live_order`
    are policy-only and not written to trade_log.

    Returns: {trade_id, status, ticker, action, shares, price, proposed_at}
    """
    user_id = request.state.user["id"]

    # --- Gate 1: Kill-Switch ---
    if is_kill_switch_active():
        raise HTTPException(
            status_code=403,
            detail="System is paused — Kill-Switch is active",
        )

    # --- Gate 2: Full-Policy ---
    policy_result = run_full_policy(trade_proposal, user_id)

    if not policy_result.passed:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Policy check failed",
                "violations": [
                    {
                        "rule": v.rule,
                        "message": v.message,
                        "severity": v.severity,
                    }
                    for v in policy_result.violations
                ],
            },
        )

    # --- Gate passed: write trade proposal ---
    row = propose_trade(user_id, trade_proposal)

    return {
        "trade_id": row["id"],
        "status": row["status"],
        "ticker": row["ticker"],
        "action": row["action"],
        "shares": row["shares"],
        "price": row["price"],
        "proposed_at": row.get("proposed_at"),
    }


@router.post("/{trade_id}/approve")
@limiter.limit("50/minute")
@handle_service_errors(service_name="Trade service", precondition_status=404)
def approve(trade_id: UUID, request: Request) -> dict:
    """User approves a proposed trade -> executes via broker.

    Returns: {trade_id, status, broker_order_id?, executed_price?, rejection_reason?}

    Status after call:
    - 'executed': Order successfully sent to Alpaca
    - 'failed': Broker rejected the order (reason in rejection_reason)

    Note: PreconditionError -> 404 (deliberate deviation from codebase 400 pattern).
    In trades, PreconditionError means "trade resource not found" or "wrong user",
    which is semantically a 404 (not found), not a 400 (bad request).
    """
    user_id = request.state.user["id"]

    # --- Gate: Kill-Switch ---
    if is_kill_switch_active():
        raise HTTPException(
            status_code=403,
            detail="System is paused — Kill-Switch is active",
        )

    result = approve_trade(str(trade_id), user_id)
    return result


@router.post("/{trade_id}/reject")
@limiter.limit("50/minute")
@handle_service_errors(service_name="Trade service", precondition_status=404)
def reject(trade_id: UUID, request: Request, body: RejectBody | None = None) -> dict:
    """User rejects a proposed trade.

    Optional body: {"reason": "Too expensive"}
    Returns: {trade_id, status: 'rejected', rejection_reason}
    """
    user_id = request.state.user["id"]
    reason = body.reason if body else None
    result = reject_trade(str(trade_id), user_id, reason)
    return result


@router.get("")
@limiter.limit("100/minute")
@handle_service_errors(service_name="Trade service")
def list_trades(
    request: Request,
    status: str | None = Query(default=None, description="Filter by status"),
) -> dict:
    """List user's trades (most recent first).

    Optional: ?status=proposed (filter by status).
    Returns: {trades: [...]}
    """
    user_id = request.state.user["id"]

    if status and status not in VALID_TRADE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status filter '{status}'. "
            f"Allowed: {', '.join(sorted(VALID_TRADE_STATUSES))}",
        )

    # Lazy maintenance before listing
    run_lazy_maintenance()

    admin = get_supabase_admin()
    query = (
        admin.table("trade_log")
        .select("*")
        .eq("user_id", user_id)
        .order("proposed_at", desc=True)
    )
    if status:
        query = query.eq("status", status)
    resp = query.execute()

    trades = resp.data or []
    return {"trades": trades, "count": len(trades)}


@router.get("/positions")
@limiter.limit("30/minute")
@handle_service_errors(service_name="Trade service")
def get_positions(request: Request) -> dict:
    """Get current positions from broker (Paper Trading).

    Returns: {positions: [{ticker, shares, avg_price, current_price, market_value}]}
    """
    adapter = get_broker_adapter()
    positions = adapter.get_positions()

    positions_list = [
        {
            "ticker": p.ticker,
            "shares": p.shares,
            "avg_price": p.avg_price,
            "current_price": p.current_price,
            "market_value": p.market_value,
        }
        for p in positions
    ]
    return {"positions": positions_list, "count": len(positions_list)}


@router.get("/account")
@limiter.limit("30/minute")
@handle_service_errors(service_name="Trade service")
def get_account(request: Request) -> dict:
    """Get broker account info (Paper Trading).

    Returns: {total_value, cash, buying_power}
    """
    adapter = get_broker_adapter()
    account = adapter.get_account()

    return {
        "total_value": account.total_value,
        "cash": account.cash,
        "buying_power": account.buying_power,
    }
