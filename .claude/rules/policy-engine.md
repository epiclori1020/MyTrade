# Policy Engine Rules — MyTrade
> Authoritative source: docs/05_risk/policy-engine.md + docs/02_policy/ips-template.yaml | Conflicts: docs win.

## Core Principle
The Policy Engine is **deterministic Python** — NO LLM calls, ever.

## Two-Stage Validation

### Pre-Policy (BEFORE Agent Call)
Runs before spending Opus/Sonnet tokens. Blocks immediately if:
- Instrument type is forbidden (options, futures, crypto, leveraged ETF, inverse ETF, penny stock, SPAC)
- Ticker not in allowed Asset Universe
- Region not allowed for instrument type (e.g. EM single stocks blocked)
- Kill-Switch is active
- System is in wrong maturity stage

### Full-Policy (AFTER Verification, BEFORE Execution)
Runs on verified numbers only. All thresholds come from `get_effective_policy()` (see ips-template.yaml for defaults):
- Max single position (default: 5% of Satellite)
- Max sector concentration (default: 30% of Satellite)
- Max trades per month (default: 10)
- Cash reserve minimum (default: 5% of Satellite)
- Portfolio drawdown Kill-Switch (default: 20%)
- Stop-loss soft flag (default: 15%)

Never hardcode these values — always read from effective policy. User presets (Beginner/Balanced/Active) change them.

## Policy Source
- Primary: `user_policy` table via `get_effective_policy()`
- Fallback: `ips-template.yaml` (if DB unreachable)
- Hard constraints (non-overridable): forbidden types, EM ETF-only, execution stage

## Kill-Switch Triggers
1. Portfolio drawdown >= 20%
2. 5 consecutive broker API failures
3. Verification rate < 70%
4. Manual user activation
