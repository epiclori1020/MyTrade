# Stufe 1 Constraints — MyTrade (Paper Trading)
> Authoritative source: docs/05_risk/execution-contract.md | Conflicts: docs wins.

## What IS allowed
- Generate analysis memos (full pipeline)
- Generate trade plans (JSON with ticker, direction, size, reasoning)
- Call Alpaca Paper API (simulated trades only)
- Create paper orders via Alpaca
- Read paper portfolio state
- Log everything to Supabase

## What is NOT allowed
- Create real broker orders — FORBIDDEN
- Access live portfolio (Flatex, IBKR) — NO access configured
- Transfer money — FORBIDDEN
- Auto-execute trades — every trade needs human confirmation
- Skip verification for trade-critical claims

## Technical Safeguards
- Alpaca Paper API key in environment (NOT live key)
- Backend checks ALPACA_PAPER_MODE=true before every API call
- No IBKR credentials configured
- Kill-Switch can halt all activity instantly

## Graduation to Stufe 2 requires
- Min. 3 months paper trading
- Pipeline error rate < 5%
- Verification rate > 85%
- IPS compliance: 100%
- Security audit passed
- IBKR account configured

## Decision Support Disclaimer
This system provides decision support, NOT investment advice.
All investment decisions rest with the user. No liability claims against the system.
