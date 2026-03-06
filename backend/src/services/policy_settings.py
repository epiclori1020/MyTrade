"""Policy Settings service — business logic for user policy management.

Extracted from routes/policy.py (T-009 SoC refactoring).
The route handler validates input (Pydantic) and calls these functions.
"""

import logging
from datetime import datetime, timedelta, timezone

from src.services.policy_engine import CONSTRAINTS
from src.services.supabase import get_supabase_admin

logger = logging.getLogger(__name__)


class OverrideValidationError(ValueError):
    """Raised when advanced override values are invalid."""


def validate_overrides(
    policy_mode: str, overrides: dict[str, int | float]
) -> dict[str, int | float]:
    """Validate and resolve overrides.

    For ADVANCED mode: validates each key/value against CONSTRAINTS.
    For non-ADVANCED: returns empty dict (overrides cleared).

    Raises:
        OverrideValidationError: If key is unknown or value out of range.
    """
    if policy_mode != "ADVANCED":
        return {}

    for key, value in overrides.items():
        if key not in CONSTRAINTS:
            raise OverrideValidationError(f"Unknown override key: {key}")
        c = CONSTRAINTS[key]
        if not (c["min"] <= value <= c["max"]):
            raise OverrideValidationError(
                f"Override '{key}' value {value} is outside "
                f"allowed range [{c['min']}, {c['max']}]"
            )

    return overrides


def update_user_policy(
    user_id: str,
    policy_mode: str,
    preset_id: str,
    effective_overrides: dict,
) -> dict:
    """Read current policy, calculate cooldown, upsert, and write change log.

    Returns:
        Dict with {policy_mode, preset_id, policy_overrides, cooldown_until}.
    """
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
    preset_changed = old_preset != preset_id
    mode_changed = policy_mode != old_mode
    if preset_changed or mode_changed:
        cooldown_until = (
            datetime.now(timezone.utc) + timedelta(hours=24)
        ).isoformat()

    # Upsert user_policy
    row = {
        "user_id": user_id,
        "policy_mode": policy_mode,
        "preset_id": preset_id,
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
        "new_mode": policy_mode,
        "old_preset": old_preset,
        "new_preset": preset_id,
        "old_overrides": old_overrides,
        "new_overrides": effective_overrides,
    }).execute()

    return {
        "policy_mode": policy_mode,
        "preset_id": preset_id,
        "policy_overrides": effective_overrides,
        "cooldown_until": cooldown_until,
    }
