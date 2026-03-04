"""Policy Engine API endpoints."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel

from src.dependencies.auth import authenticated_router
from src.dependencies.rate_limit import limiter
from src.services.exceptions import ConfigurationError
from src.services.policy_engine import (
    CONSTRAINTS,
    PRESETS,
    TradeProposal,
    get_effective_policy,
    run_full_policy,
    run_pre_policy,
)
from src.services.supabase import get_supabase_admin

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


@router.get("/presets")
@limiter.limit("30/minute")
def get_presets(request: Request) -> dict:
    """Return preset definitions and constraint ranges for the settings UI."""
    return {"presets": PRESETS, "constraints": CONSTRAINTS}


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


class PolicySettingsUpdate(BaseModel):
    """Request body for updating policy settings."""

    policy_mode: Literal["BEGINNER", "PRESET", "ADVANCED"]
    preset_id: Literal["beginner", "balanced", "active"]
    policy_overrides: dict[str, int | float] = {}


@router.get("/settings")
@limiter.limit("30/minute")
def get_settings_endpoint(request: Request) -> dict:
    """Get raw user_policy row for Settings page.

    Returns default values if no policy row exists.
    Returns 503 for server misconfiguration.
    """
    user_id = request.state.user["id"]

    try:
        admin = get_supabase_admin()
        resp = (
            admin.table("user_policy")
            .select("policy_mode, preset_id, policy_overrides, cooldown_until")
            .eq("user_id", user_id)
            .execute()
        )
    except ConfigurationError as exc:
        logger.error("Configuration error getting settings: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Policy service temporarily unavailable",
        )
    except Exception as exc:
        logger.error("Unexpected error getting settings: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Policy service temporarily unavailable",
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
def update_settings(request: Request, body: PolicySettingsUpdate) -> dict:
    """Save policy mode/preset/overrides.

    Validates advanced overrides against CONSTRAINTS. Writes policy_change_log.
    Sets 24h cooldown on preset changes.

    Returns updated settings (same shape as GET /settings).
    Returns 400 for validation errors.
    Returns 503 for server misconfiguration.
    """
    user_id = request.state.user["id"]

    # Validate advanced overrides
    if body.policy_mode == "ADVANCED":
        for key, value in body.policy_overrides.items():
            if key not in CONSTRAINTS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown override key: {key}",
                )
            c = CONSTRAINTS[key]
            if not (c["min"] <= value <= c["max"]):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Override '{key}' value {value} is outside "
                        f"allowed range [{c['min']}, {c['max']}]"
                    ),
                )

    # Clear overrides for non-advanced modes
    effective_overrides = (
        body.policy_overrides if body.policy_mode == "ADVANCED" else {}
    )

    try:
        admin = get_supabase_admin()

        # Read current settings (for change log + cooldown logic)
        current_resp = (
            admin.table("user_policy")
            .select("policy_mode, preset_id, policy_overrides, cooldown_until")
            .eq("user_id", user_id)
            .execute()
        )
        current = current_resp.data[0] if current_resp.data else None

        old_mode = current["policy_mode"] if current else "BEGINNER"
        old_preset = current["preset_id"] if current else "beginner"
        old_overrides = current.get("policy_overrides", {}) if current else {}

        # Cooldown: if preset OR mode changed, set 24h cooldown (per spec)
        cooldown_until = None
        preset_changed = old_preset != body.preset_id
        mode_changed = body.policy_mode != old_mode
        if preset_changed or mode_changed:
            cooldown_until = (
                datetime.now(timezone.utc) + timedelta(hours=24)
            ).isoformat()

        # Upsert user_policy
        row = {
            "user_id": user_id,
            "policy_mode": body.policy_mode,
            "preset_id": body.preset_id,
            "policy_overrides": effective_overrides,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if cooldown_until is not None:
            row["cooldown_until"] = cooldown_until

        admin.table("user_policy").upsert(row, on_conflict="user_id").execute()

        # Write change log
        admin.table("policy_change_log").insert({
            "user_id": user_id,
            "old_mode": old_mode,
            "new_mode": body.policy_mode,
            "old_preset": old_preset,
            "new_preset": body.preset_id,
            "old_overrides": old_overrides,
            "new_overrides": effective_overrides,
        }).execute()

    except HTTPException:
        raise
    except ConfigurationError as exc:
        logger.error("Configuration error updating settings: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Policy service temporarily unavailable",
        )
    except Exception as exc:
        logger.error("Unexpected error updating settings: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Policy service temporarily unavailable",
        )

    return {
        "policy_mode": body.policy_mode,
        "preset_id": body.preset_id,
        "policy_overrides": effective_overrides,
        "cooldown_until": cooldown_until,
    }
