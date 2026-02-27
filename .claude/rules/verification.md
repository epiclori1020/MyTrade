# Verification Layer Rules — MyTrade
> Authoritative source: docs/04_verification/tier-system.md + docs/04_verification/claim-schema.json | Conflicts: docs win.

## Core Principle
Every LLM-generated number MUST be verified against an independent source before display or trade execution.

## Tier System
- **Tier A:** Primary/auditable source (SEC EDGAR filing, FRED official data)
- **Tier B:** Two aggregators consistent (Finnhub + Alpha Vantage agree)
- **Tier C:** Single source, no cross-check available (news sentiment, opinion)

## Verification Status
- **verified:** Tier A confirmed, deviation <= 2%
- **consistent:** Two aggregators agree, deviation <= 5%
- **unverified:** Single source only, no cross-check available
- **disputed:** Deviation > 5% — RED FLAG, blocks trade if trade_critical
- **manual_check:** Tier B available but claim is trade-critical (needs Tier A)

## Trade-Critical Claims
- Claims marked `trade_critical: true` MUST reach their `required_tier` before execution is allowed
- Disputed trade-critical claims BLOCK the trade plan entirely
- The UI may display unverified/manual_check claims but with clear amber/red badges

## Claim Schema
All claims must conform to docs/04_verification/claim-schema.json:
- Required fields: claim_id, claim_text, claim_type, value, ticker, source_primary, tier, required_tier, status
- Every number must include {value, source, timestamp}

## Verification Rate Thresholds
- **> 85%:** Green — system healthy, Stufe 2 gate criterion met
- **70-85%:** Yellow — warning, new analyses still allowed but dashboard shows alert
- **< 70%:** Red — Kill-Switch activates, system enters Advisory-Only mode

## Frontend Display
- verified/consistent = green badge
- unverified = amber badge
- disputed = red badge
- manual_check = amber badge with eye icon
