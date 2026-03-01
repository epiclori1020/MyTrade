"""Policy Engine API endpoints."""

import logging

from fastapi import HTTPException, Request

from src.dependencies.auth import authenticated_router
from src.dependencies.rate_limit import limiter
from src.services.exceptions import ConfigurationError
from src.services.policy_engine import (
    TradeProposal,
    get_effective_policy,
    run_full_policy,
    run_pre_policy,
)

logger = logging.getLogger(__name__)

router = authenticated_router(prefix="/api/policy", tags=["policy"])


def _violations_to_dicts(violations) -> list[dict]:
    """Convert PolicyViolation dataclass instances to dicts."""
    return [
        {
            "rule": v.rule,
            "message": v.message,
            "severity": v.severity,
            "current_value": v.current_value,
            "limit_value": v.limit_value,
        }
        for v in violations
    ]


@router.post("/pre-check/{ticker}")
@limiter.limit("100/minute")
def pre_check(ticker: str, request: Request) -> dict:
    """Pre-Policy check before agent call.

    Validates ticker against asset universe and policy constraints.
    Returns 200 with passed=True/False and violations list.
    Returns 503 for server misconfiguration.
    """
    user_id = request.state.user["id"]

    try:
        result = run_pre_policy(ticker, user_id)
    except ConfigurationError as exc:
        logger.error("Configuration error in pre-check: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Policy service temporarily unavailable",
        )
    except Exception as exc:
        logger.error("Unexpected error in pre-check for %s: %s", ticker, exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Policy service temporarily unavailable",
        )

    return {
        "passed": result.passed,
        "violations": _violations_to_dicts(result.violations),
        "policy_snapshot": result.policy_snapshot,
    }


@router.post("/full-check")
@limiter.limit("50/minute")
def full_check(trade_proposal: TradeProposal, request: Request) -> dict:
    """Full-Policy check after verification, before execution.

    Validates sizing, exposure, and execution constraints.
    Returns 200 with passed=True/False and violations list.
    Returns 422 for invalid TradeProposal (automatic via FastAPI/Pydantic).
    Returns 503 for server misconfiguration.
    """
    user_id = request.state.user["id"]

    try:
        result = run_full_policy(trade_proposal, user_id)
    except ConfigurationError as exc:
        logger.error("Configuration error in full-check: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Policy service temporarily unavailable",
        )
    except Exception as exc:
        logger.error(
            "Unexpected error in full-check for %s: %s",
            trade_proposal.ticker, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Policy service temporarily unavailable",
        )

    return {
        "passed": result.passed,
        "violations": _violations_to_dicts(result.violations),
        "policy_snapshot": result.policy_snapshot,
    }


@router.get("/effective")
@limiter.limit("30/minute")
def get_effective(request: Request) -> dict:
    """Get the current effective policy for the authenticated user.

    Returns the resolved policy values (preset + overrides + hard constraints).
    Returns 503 for server misconfiguration.
    """
    user_id = request.state.user["id"]

    try:
        policy = get_effective_policy(user_id)
    except ConfigurationError as exc:
        logger.error("Configuration error getting effective policy: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Policy service temporarily unavailable",
        )
    except Exception as exc:
        logger.error("Unexpected error getting effective policy: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Policy service temporarily unavailable",
        )

    return policy.model_dump()
