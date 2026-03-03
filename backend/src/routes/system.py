"""System API endpoints — Kill-Switch status + Budget status."""

import logging

from fastapi import HTTPException, Request
from pydantic import BaseModel

from src.dependencies.auth import authenticated_router
from src.dependencies.rate_limit import limiter
from src.services.budget_manager import get_budget_status
from src.services.kill_switch import (
    activate_kill_switch,
    deactivate_kill_switch,
    evaluate_kill_switch_triggers,
    get_kill_switch_status,
)

logger = logging.getLogger(__name__)

router = authenticated_router(prefix="/api/system", tags=["system"])


class ActivateBody(BaseModel):
    """Request body for Kill-Switch activation."""

    reason: str = "manual"


@router.get("/kill-switch")
@limiter.limit("30/minute")
def get_kill_switch(request: Request) -> dict:
    """Get current Kill-Switch status.

    Returns: {active, reason, activated_at}
    """
    try:
        return get_kill_switch_status()
    except Exception as exc:
        logger.error("Failed to get kill-switch status: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="System service temporarily unavailable",
        )


@router.post("/kill-switch/activate")
@limiter.limit("10/minute")
def activate(request: Request, body: ActivateBody | None = None) -> dict:
    """Manually activate the Kill-Switch.

    Optional body: {"reason": "manual explanation"}
    Returns: {active: true, reason, activated_at}
    """
    reason = body.reason if body else "manual"

    try:
        return activate_kill_switch(reason)
    except Exception as exc:
        logger.error("Failed to activate kill-switch: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="System service temporarily unavailable",
        )


@router.post("/kill-switch/deactivate")
@limiter.limit("10/minute")
def deactivate(request: Request) -> dict:
    """Manually deactivate the Kill-Switch.

    Returns: {active: false, reason: null, activated_at: null}
    """
    try:
        return deactivate_kill_switch()
    except Exception as exc:
        logger.error("Failed to deactivate kill-switch: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="System service temporarily unavailable",
        )


@router.post("/kill-switch/evaluate")
@limiter.limit("10/minute")
def evaluate(request: Request) -> dict:
    """On-demand evaluation of all Kill-Switch triggers.

    Checks: drawdown, broker CB, verification rate.
    If any trigger fires, Kill-Switch is activated.

    Returns: {triggered, triggers: {drawdown: {...}, broker_cb: {...}, verification_rate: {...}}}
    """
    user_id = request.state.user["id"]

    try:
        return evaluate_kill_switch_triggers(user_id)
    except Exception as exc:
        logger.error("Failed to evaluate kill-switch triggers: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="System service temporarily unavailable",
        )


@router.get("/budget")
@limiter.limit("30/minute")
def budget(request: Request) -> dict:
    """Get current monthly budget status per tier.

    Returns: {tiers: {heavy: {...}, standard: {...}, light: {...}},
              total_spend, total_cap, warnings: [...]}
    """
    try:
        return get_budget_status()
    except Exception as exc:
        logger.error("Failed to get budget status: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="System service temporarily unavailable",
        )
