"""Policy Engine — deterministic gate for trade validation.

Two-stage validation:
- Pre-Policy (before Agent call): Blocks forbidden tickers to save LLM tokens.
- Full-Policy (after Verification, before execution): Validates sizing/exposure
  on verified numbers.

NO LLM calls — pure deterministic Python. All policy values come from
get_effective_policy() which reads the user_policy table with preset resolution,
advanced overrides, and cooldown enforcement.

Architecture:
- Pure helpers (_calculate_*) have NO DB access → testable without mocks.
- Orchestrators (run_pre_policy, run_full_policy) read DB via get_supabase_admin.
- get_effective_policy() is the only policy reader — never hardcode thresholds.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from src.constants import MVP_UNIVERSE
from src.services.exceptions import ConfigurationError
from src.services.kill_switch import is_kill_switch_active
from src.services.supabase import get_supabase_admin

logger = logging.getLogger(__name__)


# --- Constants (from settings-spec.md) ---

PRESETS: dict[str, dict] = {
    "beginner": {
        "core_pct": 80,
        "satellite_pct": 20,
        "max_drawdown_pct": 15,
        "max_single_position_pct": 5,
        "max_sector_concentration_pct": 25,
        "max_trades_per_month": 4,
        "stop_loss_flag_pct": 10,
        "em_cap_pct": 10,
        "cash_reserve_pct": 10,
        "rebalance_trigger_pct": 3,
    },
    "balanced": {
        "core_pct": 70,
        "satellite_pct": 30,
        "max_drawdown_pct": 20,
        "max_single_position_pct": 5,
        "max_sector_concentration_pct": 30,
        "max_trades_per_month": 8,
        "stop_loss_flag_pct": 15,
        "em_cap_pct": 15,
        "cash_reserve_pct": 5,
        "rebalance_trigger_pct": 5,
    },
    "active": {
        "core_pct": 60,
        "satellite_pct": 40,
        "max_drawdown_pct": 25,
        "max_single_position_pct": 8,
        "max_sector_concentration_pct": 35,
        "max_trades_per_month": 10,
        "stop_loss_flag_pct": 20,
        "em_cap_pct": 20,
        "cash_reserve_pct": 3,
        "rebalance_trigger_pct": 8,
    },
}

CONSTRAINTS: dict[str, dict[str, int | float]] = {
    "satellite_pct": {"min": 10, "max": 40},
    "max_drawdown_pct": {"min": 10, "max": 30},
    "max_single_position_pct": {"min": 3, "max": 10},
    "max_sector_concentration_pct": {"min": 20, "max": 40},
    "max_trades_per_month": {"min": 2, "max": 12},
    "stop_loss_flag_pct": {"min": 5, "max": 25},
    "em_cap_pct": {"min": 0, "max": 25},
    "cash_reserve_pct": {"min": 0, "max": 15},
    "rebalance_trigger_pct": {"min": 2, "max": 10},
}

ALWAYS_FORBIDDEN: frozenset[str] = frozenset([
    "options",
    "futures",
    "crypto",
    "leveraged_etf",
    "inverse_etf",
    "penny_stock",
    "spac",
])


# --- Models ---


class EffectivePolicy(BaseModel):
    """Resolved policy values that the Policy Engine reads."""

    core_pct: int | float
    satellite_pct: int | float
    max_drawdown_pct: int | float
    max_single_position_pct: int | float
    max_sector_concentration_pct: int | float
    max_trades_per_month: int
    stop_loss_flag_pct: int | float
    em_cap_pct: int | float
    cash_reserve_pct: int | float
    rebalance_trigger_pct: int | float
    # Hard constraints (non-overridable)
    forbidden_types: list[str]
    em_instruments: list[str]
    maturity_stage: int
    human_confirm_required: bool


class TradeProposal(BaseModel):
    """Input for Full-Policy validation.

    Financial fields (shares, price, stop_loss) use Decimal for precision.
    Pydantic v2 auto-coerces float/int/str inputs to Decimal.
    """

    ticker: str
    action: str  # "BUY" or "SELL"
    shares: Decimal
    price: Decimal
    analysis_id: str
    sector: str | None = None
    is_live_order: bool = False
    stop_loss: Decimal | None = None


@dataclass
class PolicyViolation:
    """A single policy violation."""

    rule: str
    message: str
    severity: Literal["blocking", "warning"]
    current_value: float | int | str | None = None
    limit_value: float | int | str | None = None


@dataclass
class PolicyResult:
    """Result of a policy check."""

    passed: bool
    violations: list[PolicyViolation] = field(default_factory=list)
    policy_snapshot: dict | None = None


# --- get_effective_policy ---


def get_effective_policy(user_id: str) -> EffectivePolicy:
    """Resolve the active policy from user_policy table.

    Resolution order:
    1. Read user_policy row (no row → Beginner preset)
    2. Cooldown enforcement (if active, use old preset)
    3. ADVANCED mode: apply overrides within constraints
    4. Always attach hard constraints

    Raises:
        ConfigurationError: If DB is unreachable.
    """
    try:
        admin = get_supabase_admin()
        resp = (
            admin.table("user_policy")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to read user_policy: %s", exc)
        # TODO: YAML-Fallback (ips-template.yaml) für Production-Resilience
        raise ConfigurationError("Policy database unavailable") from exc

    # No row → Beginner preset (default for new users)
    if not resp.data:
        return _build_effective_policy(PRESETS["beginner"])

    row = resp.data[0]
    preset_id = row.get("preset_id", "beginner")
    policy_mode = row.get("policy_mode", "BEGINNER")

    # Validate preset_id — fallback to beginner if invalid
    if preset_id not in PRESETS:
        logger.warning("Invalid preset_id '%s' for user %s, falling back to beginner", preset_id, user_id)
        preset_id = "beginner"

    # Cooldown enforcement: if cooldown_until > now, use old preset
    effective_preset_id = _resolve_cooldown(admin, user_id, row, preset_id)

    base = dict(PRESETS[effective_preset_id])

    # ADVANCED mode: apply overrides within constraints
    if policy_mode == "ADVANCED":
        overrides = row.get("policy_overrides") or {}
        for key, value in overrides.items():
            if key in CONSTRAINTS and _is_within_constraints(key, value):
                base[key] = value
            elif key not in CONSTRAINTS:
                logger.debug("Ignoring unknown override key '%s'", key)

        # Keep core_pct + satellite_pct = 100
        if "satellite_pct" in overrides and _is_within_constraints("satellite_pct", overrides["satellite_pct"]):
            base["core_pct"] = 100 - base["satellite_pct"]

    return _build_effective_policy(base)


def _resolve_cooldown(
    admin, user_id: str, policy_row: dict, current_preset_id: str
) -> str:
    """Check cooldown_until and return the effective preset_id.

    If cooldown is active (future timestamp), look up the previous preset
    from policy_change_log. If no log entry exists, use current preset
    (graceful fallback).
    """
    cooldown_until = policy_row.get("cooldown_until")
    if cooldown_until is None:
        return current_preset_id

    # Handle both string and datetime from DB
    if isinstance(cooldown_until, str):
        try:
            cooldown_dt = datetime.fromisoformat(cooldown_until)
        except ValueError:
            return current_preset_id
    elif isinstance(cooldown_until, datetime):
        cooldown_dt = cooldown_until
    else:
        return current_preset_id

    # Ensure timezone-aware comparison
    if cooldown_dt.tzinfo is None:
        cooldown_dt = cooldown_dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    if cooldown_dt <= now:
        # Cooldown expired — use current preset
        return current_preset_id

    # Cooldown active — look up old preset from change log
    try:
        log_resp = (
            admin.table("policy_change_log")
            .select("old_preset")
            .eq("user_id", user_id)
            .order("changed_at", desc=True)
            .limit(1)
            .execute()
        )
        if log_resp.data and log_resp.data[0].get("old_preset"):
            old_preset = log_resp.data[0]["old_preset"]
            if old_preset in PRESETS:
                return old_preset
    except Exception as exc:
        logger.warning("Failed to read policy_change_log for cooldown: %s", exc)

    # Graceful fallback: use current preset if no log entry
    return current_preset_id


def _is_within_constraints(key: str, value) -> bool:
    """Check if an override value is within the allowed constraints."""
    if key not in CONSTRAINTS:
        return False
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return False
    return CONSTRAINTS[key]["min"] <= numeric_value <= CONSTRAINTS[key]["max"]


def _build_effective_policy(base: dict) -> EffectivePolicy:
    """Build EffectivePolicy from base dict, attaching hard constraints."""
    return EffectivePolicy(
        core_pct=base["core_pct"],
        satellite_pct=base["satellite_pct"],
        max_drawdown_pct=base["max_drawdown_pct"],
        max_single_position_pct=base["max_single_position_pct"],
        max_sector_concentration_pct=base["max_sector_concentration_pct"],
        max_trades_per_month=base["max_trades_per_month"],
        stop_loss_flag_pct=base["stop_loss_flag_pct"],
        em_cap_pct=base["em_cap_pct"],
        cash_reserve_pct=base["cash_reserve_pct"],
        rebalance_trigger_pct=base["rebalance_trigger_pct"],
        # Hard constraints — always enforced, never overridable
        forbidden_types=sorted(ALWAYS_FORBIDDEN),
        em_instruments=["etf"],
        maturity_stage=1,  # Stufe 1 = Paper Trading
        human_confirm_required=True,
    )


# --- Pre-Policy ---


def run_pre_policy(ticker: str, user_id: str) -> PolicyResult:
    """Pre-Policy check — runs BEFORE agent call to save LLM tokens.

    Validates:
    1. Ticker in MVP_UNIVERSE
    2. Kill-Switch (stub)
    3. Maturity Stage (stub)
    4. Instrument Type (stub)
    5. Region (stub)

    Returns PolicyResult (never raises PreconditionError).
    """
    policy = get_effective_policy(user_id)
    violations: list[PolicyViolation] = []

    # 1. Ticker in MVP_UNIVERSE
    if ticker.upper() not in MVP_UNIVERSE:
        violations.append(PolicyViolation(
            rule="asset_universe",
            message=f"Ticker '{ticker.upper()}' is not in the allowed asset universe",
            severity="blocking",
            current_value=ticker.upper(),
            limit_value=", ".join(MVP_UNIVERSE),
        ))

    # 2. Kill-Switch aktiv?
    if is_kill_switch_active():
        violations.append(PolicyViolation(
            rule="kill_switch",
            message="Kill-Switch is active — system is in Advisory-Only mode. No new trades allowed.",
            severity="blocking",
            current_value=True,
            limit_value=False,
        ))

    # 3. Maturity Stage
    # MVP: Stufe 1 = Paper Trading. Alle Analysen erlaubt.
    # Kein Check nötig da Pre-Policy keine live_order Flag hat.

    # 4. Instrument-Typ erlaubt?
    # MVP: Stub — alle MVP_UNIVERSE Ticker sind vorab geprüft (keine
    # verbotenen Instrumente im hardcoded Universum).
    # TODO: Dynamisches Universum mit instrument_type Check (Phase 2+)

    # 5. Region erlaubt für Instrument-Typ?
    # MVP: Stub — alle MVP_UNIVERSE Ticker sind US-listed.
    # TODO: Regionen-Check wenn EU/EM Ticker hinzukommen (Phase 2+)

    passed = not any(v.severity == "blocking" for v in violations)
    return PolicyResult(
        passed=passed,
        violations=violations,
        policy_snapshot=policy.model_dump(),
    )


# --- Full-Policy ---


def run_full_policy(trade_proposal: TradeProposal, user_id: str) -> PolicyResult:
    """Full-Policy check — runs AFTER verification, BEFORE execution.

    Validates sizing, exposure, and execution constraints on verified numbers.
    Returns PolicyResult (never raises PreconditionError).
    """
    policy = get_effective_policy(user_id)
    admin = get_supabase_admin()
    violations: list[PolicyViolation] = []

    # --- Check 0: has_blocking_disputed from verification ---
    _check_blocking_verification(admin, trade_proposal, user_id, violations)

    # --- Check 1: Forbidden instrument type ---
    # MVP: Stub — TradeProposal has no instrument_type field.
    # All MVP_UNIVERSE tickers are pre-vetted equities/ETFs.
    # TODO: Add instrument_type to TradeProposal for Phase 2+

    trade_value = trade_proposal.shares * trade_proposal.price
    is_buy = trade_proposal.action.upper() == "BUY"

    # Fetch portfolio holdings for sizing checks
    holdings = _fetch_holdings(admin, user_id)
    portfolio_value = _calculate_portfolio_value(holdings)

    # --- Check 2: Max single position (BUY only) ---
    if is_buy and portfolio_value > 0:
        position_pct = (trade_value / portfolio_value) * 100
        if position_pct > policy.max_single_position_pct:
            violations.append(PolicyViolation(
                rule="max_single_position",
                message=(
                    f"Position size {position_pct:.1f}% exceeds "
                    f"limit of {policy.max_single_position_pct}%"
                ),
                severity="blocking",
                current_value=float(round(position_pct, 1)),
                limit_value=policy.max_single_position_pct,
            ))

    # --- Check 3: Max sector concentration ---
    # MVP: Stub — portfolio_holdings has no sector field.
    # TODO: Add sector tracking to portfolio_holdings (Phase 2+)

    # --- Check 4: Max trades per month ---
    monthly_trades = _count_monthly_trades(admin, user_id)
    if monthly_trades >= policy.max_trades_per_month:
        violations.append(PolicyViolation(
            rule="max_trades_per_month",
            message=(
                f"Monthly trade count {monthly_trades} has reached "
                f"limit of {policy.max_trades_per_month}"
            ),
            severity="blocking",
            current_value=monthly_trades,
            limit_value=policy.max_trades_per_month,
        ))

    # --- Check 5: Cash reserve (BUY only) ---
    # MVP: Stub — Cash Reserve Check braucht den totalen Account-Wert (Holdings + Cash)
    # vom Broker API. Aktuell ist portfolio_value = invested_value (beide aus Holdings),
    # daher ist der Cash-Anteil nicht bestimmbar.
    # Die pure Helper-Funktion _calculate_remaining_cash_pct() existiert bereits und ist getestet.
    # TODO: Account-Balance von Broker API lesen (Step 9 Alpaca/IBKR Integration)

    # --- Check 6: Drawdown kill-switch ---
    # Read highwater mark from system_state
    try:
        state_resp = admin.table("system_state").select("highwater_mark_value").limit(1).execute()
        highwater = (
            Decimal(str(state_resp.data[0]["highwater_mark_value"]))
            if state_resp.data and state_resp.data[0].get("highwater_mark_value")
            else Decimal("0")
        )
    except (KeyError, ValueError, TypeError):
        highwater = Decimal("0")  # No highwater → no drawdown check (fail-open for full-policy)

    drawdown = _calculate_portfolio_drawdown(holdings, highwater)
    if drawdown >= policy.max_drawdown_pct:
        violations.append(PolicyViolation(
            rule="drawdown_kill_switch",
            message=(
                f"Portfolio drawdown {drawdown:.1f}% has reached "
                f"kill-switch threshold of {policy.max_drawdown_pct}%"
            ),
            severity="blocking",
            current_value=float(round(drawdown, 1)),
            limit_value=policy.max_drawdown_pct,
        ))

    # --- Check 7: Region ---
    # MVP: Stub — alle MVP_UNIVERSE Ticker sind US-listed.
    # TODO: Region validation when EU/EM tickers are added (Phase 2+)

    # --- Check 8: Maturity stage vs is_live_order ---
    if trade_proposal.is_live_order and policy.maturity_stage < 2:
        violations.append(PolicyViolation(
            rule="maturity_stage",
            message=(
                f"Live orders require maturity stage 2+, "
                f"current stage is {policy.maturity_stage}"
            ),
            severity="blocking",
            current_value=policy.maturity_stage,
            limit_value=2,
        ))

    # --- STOP-LOSS SOFT FLAG (Warning, nicht Blocking) ---
    # stop_loss_flag_pct ist ein WARNING, kein Trade-Blocker.
    # Für MVP: Stub — wird erst relevant wenn portfolio_holdings Echtzeit-P&L hat.
    # TODO: Stop-Loss Monitoring in Step 11 (Monitoring & Scheduler)

    passed = not any(v.severity == "blocking" for v in violations)
    return PolicyResult(
        passed=passed,
        violations=violations,
        policy_snapshot=policy.model_dump(),
    )


# --- DB helpers ---


def _check_blocking_verification(
    admin, trade_proposal: TradeProposal, user_id: str,
    violations: list[PolicyViolation],
) -> None:
    """Check if analysis has blocking verification issues (disputed or manual_check)."""
    try:
        resp = (
            admin.table("analysis_runs")
            .select("user_id, verification")
            .eq("id", trade_proposal.analysis_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to read analysis_runs: %s", exc)
        violations.append(PolicyViolation(
            rule="analysis_not_found",
            message="Could not verify analysis run",
            severity="blocking",
        ))
        return

    if not resp.data:
        violations.append(PolicyViolation(
            rule="analysis_not_found",
            message="Analysis run not found",
            severity="blocking",
        ))
        return

    run_row = resp.data[0]

    # Ownership check — same message for not-found and wrong-user (no info leak)
    if run_row.get("user_id") != user_id:
        violations.append(PolicyViolation(
            rule="analysis_not_found",
            message="Analysis run not found",
            severity="blocking",
        ))
        return

    verification = run_row.get("verification")
    if verification and verification.get("has_blocking_disputed"):
        violations.append(PolicyViolation(
            rule="blocking_disputed_claims",
            message="Trade-critical claims are disputed — trade blocked",
            severity="blocking",
        ))
    if verification and verification.get("has_blocking_manual_check"):
        violations.append(PolicyViolation(
            rule="blocking_manual_check",
            message="Trade-critical claims need Tier A verification — trade blocked",
            severity="blocking",
        ))


def _fetch_holdings(admin, user_id: str) -> list[dict]:
    """Fetch active portfolio holdings for a user."""
    try:
        resp = (
            admin.table("portfolio_holdings")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        return resp.data or []
    except Exception as exc:
        logger.warning("Failed to fetch portfolio_holdings: %s", exc)
        return []


def _count_monthly_trades(admin, user_id: str) -> int:
    """Count trade_log entries for the current month."""
    first_of_month = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    try:
        resp = (
            admin.table("trade_log")
            .select("id")
            .eq("user_id", user_id)
            .gte("proposed_at", first_of_month)
            .neq("status", "rejected")
            .execute()
        )
        return len(resp.data) if resp.data else 0
    except Exception as exc:
        logger.warning("Failed to count monthly trades: %s", exc)
        return 0


# --- Pure helpers (no DB access, testable without mocks) ---


def _calculate_portfolio_value(holdings: list[dict]) -> Decimal:
    """Sum of shares * current_price for all holdings.

    Returns Decimal for precision. Skips holdings with None current_price.
    """
    total = Decimal("0")
    for h in holdings:
        price = h.get("current_price")
        shares = h.get("shares")
        if price is not None and shares is not None:
            total += Decimal(str(shares)) * Decimal(str(price))
    return total


def _calculate_remaining_cash_pct(
    trade_value: float | Decimal, holdings: list[dict], portfolio_value: float | Decimal,
) -> Decimal:
    """Calculate remaining cash percentage after a trade.

    Returns Decimal for precision. Coerces float inputs to Decimal.
    MVP simplification: Assumes no existing cash position tracked.
    Cash = portfolio_value - sum(positions) - trade_value.
    """
    if not isinstance(trade_value, Decimal):
        trade_value = Decimal(str(trade_value))
    if not isinstance(portfolio_value, Decimal):
        portfolio_value = Decimal(str(portfolio_value))
    invested = _calculate_portfolio_value(holdings)
    cash = portfolio_value - invested
    remaining_cash = cash - trade_value
    if portfolio_value == 0:
        return Decimal("0")
    return (remaining_cash / portfolio_value) * 100


def _calculate_portfolio_drawdown(holdings: list[dict], highwater: float | Decimal) -> Decimal:
    """Calculate portfolio drawdown percentage from highwater mark.

    Returns Decimal for precision. Coerces float highwater to Decimal.
    Pure helper — no DB access. Takes highwater as parameter.
    Returns Decimal("0") if no highwater or no current value (fail-open).
    """
    if not isinstance(highwater, Decimal):
        highwater = Decimal(str(highwater))
    if highwater <= 0:
        return Decimal("0")

    current_value = _calculate_portfolio_value(holdings)
    if current_value <= 0:
        return Decimal("0")

    if current_value >= highwater:
        return Decimal("0")

    return ((highwater - current_value) / highwater) * 100
