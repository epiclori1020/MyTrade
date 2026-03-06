"""Kill-Switch — system-level circuit breaker for dangerous states.

Protects against:
1. Portfolio drawdown exceeding threshold (from effective policy)
2. Alpaca broker circuit breaker in open state (5+ consecutive failures)
3. Verification rate falling below 70% (too many unverified claims)

State is stored in the single-row `system_state` table (global, not per-user).
is_kill_switch_active() is fail-closed: returns True on DB error (block trades
when state is unknown). This is the OPPOSITE of budget_manager's fail-open design.

No import of policy_engine at module level — uses lazy import inside
evaluate_kill_switch_triggers() to avoid circular dependency.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal

from src.services.error_logger import log_error
from src.services.supabase import get_supabase_admin

logger = logging.getLogger(__name__)

# Fixed UUID for the single system_state row
SYSTEM_STATE_ID = "00000000-0000-0000-0000-000000000001"

# Verification rate threshold (from rules/verification.md)
VERIFICATION_RATE_THRESHOLD = 70.0

# Number of recent analyses to evaluate for verification rate
RECENT_ANALYSES_COUNT = 5

# Default max drawdown threshold from ips-template.yaml (fallback when DB unavailable)
DEFAULT_DRAWDOWN_PCT = 20.0


def _read_system_state(admin) -> dict | None:
    """Read the single system_state row. Returns None on error."""
    try:
        resp = (
            admin.table("system_state")
            .select("kill_switch_active, kill_switch_reason, kill_switch_activated_at, highwater_mark_value")
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as exc:
        logger.error("Failed to read system_state: %s", exc)
        return None


def is_kill_switch_active() -> bool:
    """Check if the Kill-Switch is currently active.

    Fail-closed: returns True on DB error (block trades when state is unknown).
    This is safe because blocking trades is always the conservative option.
    """
    try:
        admin = get_supabase_admin()
        state = _read_system_state(admin)
        if state is None:
            logger.warning("Cannot read system_state — fail-closed: treating as active")
            return True
        return bool(state.get("kill_switch_active", False))
    except Exception as exc:
        logger.error("Kill-switch check failed — fail-closed: %s", exc)
        return True


def activate_kill_switch(reason: str) -> dict:
    """Activate the Kill-Switch. Idempotent — if already active, logs and returns.

    Returns: {active, reason, activated_at}
    """
    admin = get_supabase_admin()
    state = _read_system_state(admin)

    if state and state.get("kill_switch_active"):
        logger.info("Kill-switch already active (reason: %s)", state.get("kill_switch_reason"))
        return {
            "active": True,
            "reason": state.get("kill_switch_reason"),
            "activated_at": state.get("kill_switch_activated_at"),
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    resp = admin.table("system_state").update({
        "kill_switch_active": True,
        "kill_switch_reason": reason,
        "kill_switch_activated_at": now_iso,
        "updated_at": now_iso,
    }).eq("id", SYSTEM_STATE_ID).execute()

    if not resp.data:
        logger.error("Kill-switch activation failed — system_state row missing")
        raise RuntimeError("Failed to persist kill-switch state")

    log_error("kill_switch", "activated", f"Kill-Switch activated: {reason}")
    logger.warning("Kill-Switch ACTIVATED: %s", reason)

    return {
        "active": True,
        "reason": reason,
        "activated_at": now_iso,
    }


def deactivate_kill_switch() -> dict:
    """Deactivate the Kill-Switch. Clears reason and timestamp.

    Returns: {active: False, reason: None, activated_at: None}
    """
    admin = get_supabase_admin()
    now_iso = datetime.now(timezone.utc).isoformat()

    resp = admin.table("system_state").update({
        "kill_switch_active": False,
        "kill_switch_reason": None,
        "kill_switch_activated_at": None,
        "updated_at": now_iso,
    }).eq("id", SYSTEM_STATE_ID).execute()

    if not resp.data:
        logger.error("Kill-switch deactivation failed — system_state row missing")
        raise RuntimeError("Failed to persist kill-switch state")

    log_error("kill_switch", "deactivated", "Kill-Switch deactivated manually")
    logger.info("Kill-Switch deactivated")

    return {
        "active": False,
        "reason": None,
        "activated_at": None,
    }


def get_kill_switch_status() -> dict:
    """Pure read — return current Kill-Switch state.

    Returns: {active, reason, activated_at}
    """
    admin = get_supabase_admin()
    state = _read_system_state(admin)

    if state is None:
        return {"active": True, "reason": "system_state unreadable", "activated_at": None}

    return {
        "active": bool(state.get("kill_switch_active", False)),
        "reason": state.get("kill_switch_reason"),
        "activated_at": state.get("kill_switch_activated_at"),
    }


def update_highwater_mark(portfolio_value: float) -> None:
    """Update highwater mark if new value exceeds current. Best-effort."""
    try:
        admin = get_supabase_admin()
        state = _read_system_state(admin)
        if state is None:
            return

        current_hw = float(state.get("highwater_mark_value") or 0.0)
        if portfolio_value > current_hw:
            now_iso = datetime.now(timezone.utc).isoformat()
            admin.table("system_state").update({
                "highwater_mark_value": portfolio_value,
                "highwater_mark_at": now_iso,
                "updated_at": now_iso,
            }).eq("id", SYSTEM_STATE_ID).execute()
            logger.info("Highwater mark updated: %.2f -> %.2f", current_hw, portfolio_value)
    except Exception as exc:
        logger.warning("Failed to update highwater mark: %s", exc)


def evaluate_kill_switch_triggers(user_id: str) -> dict:
    """On-demand evaluation of all 3 automatic Kill-Switch triggers.

    Checks drawdown, broker CB, and verification rate. If any trigger
    fires, activates the Kill-Switch.

    Returns: {triggered: bool, triggers: {drawdown: {...}, broker_cb: {...}, verification_rate: {...}}}
    """
    triggers = {
        "drawdown": _check_drawdown_trigger(user_id),
        "broker_cb": _check_broker_cb_trigger(),
        "verification_rate": _check_verification_rate_trigger(user_id),
    }

    any_triggered = any(t["triggered"] for t in triggers.values())

    if any_triggered:
        reasons = [name for name, t in triggers.items() if t["triggered"]]
        reason = f"auto_{'+'.join(reasons)}"
        activate_kill_switch(reason)

    return {
        "triggered": any_triggered,
        "triggers": triggers,
    }


# --- Internal trigger checks ---


def _check_drawdown_trigger(user_id: str) -> dict:
    """Check if portfolio drawdown exceeds the policy threshold.

    Uses lazy import of get_effective_policy to avoid circular dependency.
    Fail-open: if unable to check, returns triggered=False (don't block on data issues).
    """
    try:
        admin = get_supabase_admin()

        # Read highwater mark
        state = _read_system_state(admin)
        if state is None:
            return {"triggered": False, "detail": "Cannot read system_state"}

        highwater = Decimal(str(state.get("highwater_mark_value") or 0))
        if highwater <= 0:
            return {"triggered": False, "detail": "No highwater mark set"}

        # Read current portfolio value
        resp = (
            admin.table("portfolio_holdings")
            .select("shares, current_price")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        holdings = resp.data or []
        if not holdings:
            return {"triggered": False, "detail": "No active holdings"}

        current_value = sum(
            (
                Decimal(str(h.get("shares") or 0)) * Decimal(str(h.get("current_price") or 0))
                for h in holdings
                if h.get("current_price") is not None
            ),
            Decimal("0"),
        )

        if current_value <= 0:
            return {"triggered": False, "detail": "Portfolio value is zero"}

        drawdown = ((highwater - current_value) / highwater) * 100

        # Lazy import to avoid circular dependency
        from src.services.policy_engine import get_effective_policy

        try:
            policy = get_effective_policy(user_id)
            threshold = policy.max_drawdown_pct
        except Exception as exc:  # Broad catch: policy-load failure uses YAML fallback
            logger.warning(
                "Policy load failed for drawdown check, using fallback: %s", exc,
            )
            threshold = DEFAULT_DRAWDOWN_PCT

        triggered = drawdown >= threshold
        return {
            "triggered": triggered,
            "drawdown_pct": float(round(drawdown, 2)),
            "threshold_pct": threshold,
            "current_value": float(round(current_value, 2)),
            "highwater_value": float(highwater),
        }
    except Exception as exc:
        logger.warning("Drawdown trigger check failed: %s", exc)
        return {"triggered": False, "detail": "Check failed"}


def _check_broker_cb_trigger() -> dict:
    """Check if the Alpaca circuit breaker is in open state."""
    try:
        from src.services.circuit_breaker import alpaca_breaker

        cb_state = alpaca_breaker.get_state()
        triggered = cb_state["state"] == "open"
        return {
            "triggered": triggered,
            "cb_state": cb_state["state"],
            "failure_count": cb_state["failure_count"],
        }
    except Exception as exc:
        logger.warning("Broker CB trigger check failed: %s", exc)
        return {"triggered": False, "detail": "Check failed"}


def _check_verification_rate_trigger(user_id: str) -> dict:
    """Check if verification rate has fallen below 70%.

    Looks at the most recent RECENT_ANALYSES_COUNT analyses for the user.
    Claims without verification_results are implicitly "unverified"
    (counted in denominator).
    """
    try:
        admin = get_supabase_admin()

        # Get recent analysis IDs
        resp = (
            admin.table("analysis_runs")
            .select("id")
            .eq("user_id", user_id)
            .order("started_at", desc=True)
            .limit(RECENT_ANALYSES_COUNT)
            .execute()
        )
        analysis_ids = [r["id"] for r in (resp.data or [])]

        if not analysis_ids:
            return {"triggered": False, "detail": "No analyses found"}

        # Count total claims for these analyses
        claims_resp = (
            admin.table("claims")
            .select("id")
            .in_("analysis_id", analysis_ids)
            .execute()
        )
        total_claims = len(claims_resp.data) if claims_resp.data else 0

        if total_claims == 0:
            return {"triggered": False, "detail": "No claims found"}

        # Count verified/consistent claims
        claim_ids = [c["id"] for c in claims_resp.data]
        vr_resp = (
            admin.table("verification_results")
            .select("status")
            .in_("claim_id", claim_ids)
            .execute()
        )

        verified_count = 0
        for vr in (vr_resp.data or []):
            if vr.get("status") in ("verified", "consistent"):
                verified_count += 1

        rate = (verified_count / total_claims) * 100
        triggered = rate < VERIFICATION_RATE_THRESHOLD

        return {
            "triggered": triggered,
            "rate_pct": round(rate, 2),
            "threshold_pct": VERIFICATION_RATE_THRESHOLD,
            "verified_count": verified_count,
            "total_claims": total_claims,
        }
    except Exception as exc:
        logger.warning("Verification rate trigger check failed: %s", exc)
        return {"triggered": False, "detail": "Check failed"}
