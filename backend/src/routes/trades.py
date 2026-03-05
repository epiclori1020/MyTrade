"""Trade API endpoints — propose, approve, reject, list, positions, account."""

import logging
from uuid import UUID

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel

from src.dependencies.auth import authenticated_router
from src.dependencies.rate_limit import limiter
from src.services.alpaca_paper import get_broker_adapter
from src.services.exceptions import BrokerError, ConfigurationError, PreconditionError
from src.services.kill_switch import is_kill_switch_active
from src.services.policy_engine import TradeProposal, run_full_policy
from src.services.supabase import get_supabase_admin
from src.services.trade_execution import (
    approve_trade,
    expire_stale_trades,
    propose_trade,
    reject_trade,
)

logger = logging.getLogger(__name__)

router = authenticated_router(prefix="/api/trades", tags=["trades"])

VALID_TRADE_STATUSES = frozenset({
    "proposed", "approved", "rejected", "executed", "failed",
})


class RejectBody(BaseModel):
    """Request body for trade rejection."""

    reason: str | None = None


@router.post("/propose")
@limiter.limit("50/minute")
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
    try:
        policy_result = run_full_policy(trade_proposal, user_id)
    except ConfigurationError as exc:
        logger.error("Policy engine configuration error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Policy service not configured",
        )
    except Exception as exc:
        logger.error("Policy engine error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Policy service temporarily unavailable",
        )

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
    try:
        row = propose_trade(user_id, trade_proposal)
    except ConfigurationError as exc:
        logger.error("Configuration error in propose: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Trade service not configured",
        )
    except Exception as exc:
        logger.error("Unexpected error in propose: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Trade service temporarily unavailable",
        )

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

    try:
        result = approve_trade(str(trade_id), user_id)
    except PreconditionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ConfigurationError as exc:
        logger.error("Configuration error in approve: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Broker service not configured",
        )
    except BrokerError as exc:
        logger.error("Broker error in approve: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Broker temporarily unavailable",
        )
    except Exception as exc:
        logger.error("Unexpected error in approve: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Trade service temporarily unavailable",
        )

    return result


@router.post("/{trade_id}/reject")
@limiter.limit("50/minute")
def reject(trade_id: UUID, request: Request, body: RejectBody | None = None) -> dict:
    """User rejects a proposed trade.

    Optional body: {"reason": "Too expensive"}
    Returns: {trade_id, status: 'rejected', rejection_reason}
    """
    user_id = request.state.user["id"]
    reason = body.reason if body else None

    try:
        result = reject_trade(str(trade_id), user_id, reason)
    except PreconditionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Unexpected error in reject: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Trade service temporarily unavailable",
        )

    return result


@router.get("")
@limiter.limit("100/minute")
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

    # Lazy expiration before listing
    expire_stale_trades()

    try:
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
    except Exception as exc:
        logger.error("Unexpected error listing trades: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Trade service temporarily unavailable",
        )

    return {"trades": resp.data or []}


@router.get("/positions")
@limiter.limit("30/minute")
def get_positions(request: Request) -> dict:
    """Get current positions from broker (Paper Trading).

    Returns: {positions: [{ticker, shares, avg_price, current_price, market_value}]}
    """
    try:
        adapter = get_broker_adapter()
        positions = adapter.get_positions()
    except ConfigurationError as exc:
        logger.error("Configuration error getting positions: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Broker service not configured",
        )
    except BrokerError as exc:
        logger.error("Broker error getting positions: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Broker temporarily unavailable",
        )
    except Exception as exc:
        logger.error("Unexpected error getting positions: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Trade service temporarily unavailable",
        )

    return {
        "positions": [
            {
                "ticker": p.ticker,
                "shares": p.shares,
                "avg_price": p.avg_price,
                "current_price": p.current_price,
                "market_value": p.market_value,
            }
            for p in positions
        ],
    }


@router.get("/account")
@limiter.limit("30/minute")
def get_account(request: Request) -> dict:
    """Get broker account info (Paper Trading).

    Returns: {total_value, cash, buying_power}
    """
    try:
        adapter = get_broker_adapter()
        account = adapter.get_account()
    except ConfigurationError as exc:
        logger.error("Configuration error getting account: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Broker service not configured",
        )
    except BrokerError as exc:
        logger.error("Broker error getting account: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Broker temporarily unavailable",
        )
    except Exception as exc:
        logger.error("Unexpected error getting account: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Trade service temporarily unavailable",
        )

    return {
        "total_value": account.total_value,
        "cash": account.cash,
        "buying_power": account.buying_power,
    }
