"""Policy Engine API endpoints."""

from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel

from src.dependencies.auth import authenticated_router
from src.dependencies.error_handler import handle_service_errors
from src.dependencies.rate_limit import limiter
from src.services.policy_engine import (
    CONSTRAINTS,
    PRESETS,
    TradeProposal,
    get_effective_policy,
    run_full_policy,
    run_pre_policy,
)
from src.services.policy_settings import (
    OverrideValidationError,
    update_user_policy,
    validate_overrides,
)
from src.services.supabase import get_supabase_admin

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


@router.get("/presets")
@limiter.limit("30/minute")
def get_presets(request: Request) -> dict:
    """Return preset definitions and constraint ranges for the settings UI."""
    return {"presets": PRESETS, "constraints": CONSTRAINTS}


@router.post("/pre-check/{ticker}")
@limiter.limit("100/minute")
@handle_service_errors(service_name="Policy service")
def pre_check(ticker: str, request: Request) -> dict:
    """Pre-Policy check before agent call.

    Validates ticker against asset universe and policy constraints.
    Returns 200 with passed=True/False and violations list.
    """
    user_id = request.state.user["id"]
    result = run_pre_policy(ticker, user_id)

    return {
        "passed": result.passed,
        "violations": _violations_to_dicts(result.violations),
        "policy_snapshot": result.policy_snapshot,
    }


@router.post("/full-check")
@limiter.limit("50/minute")
@handle_service_errors(service_name="Policy service")
def full_check(trade_proposal: TradeProposal, request: Request) -> dict:
    """Full-Policy check after verification, before execution.

    Validates sizing, exposure, and execution constraints.
    Returns 200 with passed=True/False and violations list.
    """
    user_id = request.state.user["id"]
    result = run_full_policy(trade_proposal, user_id)

    return {
        "passed": result.passed,
        "violations": _violations_to_dicts(result.violations),
        "policy_snapshot": result.policy_snapshot,
    }


@router.get("/effective")
@limiter.limit("30/minute")
@handle_service_errors(service_name="Policy service")
def get_effective(request: Request) -> dict:
    """Get the current effective policy for the authenticated user.

    Returns the resolved policy values (preset + overrides + hard constraints).
    """
    user_id = request.state.user["id"]
    policy = get_effective_policy(user_id)
    return policy.model_dump()


class PolicySettingsUpdate(BaseModel):
    """Request body for updating policy settings."""

    policy_mode: Literal["BEGINNER", "PRESET", "ADVANCED"]
    preset_id: Literal["beginner", "balanced", "active"]
    policy_overrides: dict[str, int | float] = {}


@router.get("/settings")
@limiter.limit("30/minute")
@handle_service_errors(service_name="Policy service")
def get_settings_endpoint(request: Request) -> dict:
    """Get raw user_policy row for Settings page.

    Returns default values if no policy row exists.
    """
    user_id = request.state.user["id"]
    admin = get_supabase_admin()
    resp = (
        admin.table("user_policy")
        .select("policy_mode, preset_id, policy_overrides, cooldown_until")
        .eq("user_id", user_id)
        .execute()
    )

    if not resp.data:
        return {
            "policy_mode": "BEGINNER",
            "preset_id": "beginner",
            "policy_overrides": {},
            "cooldown_until": None,
        }
    return resp.data[0]


@router.put("/settings")
@limiter.limit("10/minute")
@handle_service_errors(service_name="Policy service")
def update_settings(request: Request, body: PolicySettingsUpdate) -> dict:
    """Save policy mode/preset/overrides.

    Validates advanced overrides against CONSTRAINTS. Writes policy_change_log.
    Sets 24h cooldown on preset changes.

    Returns updated settings (same shape as GET /settings).
    Returns 400 for validation errors.
    """
    user_id = request.state.user["id"]

    try:
        effective_overrides = validate_overrides(
            body.policy_mode, body.policy_overrides
        )
    except OverrideValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return update_user_policy(
        user_id=user_id,
        policy_mode=body.policy_mode,
        preset_id=body.preset_id,
        effective_overrides=effective_overrides,
    )
