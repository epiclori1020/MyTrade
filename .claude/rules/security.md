# Security Rules — MyTrade
> Authoritative source: docs/09_broker/security.md | Conflicts: docs wins.

## API Keys & Secrets
- NEVER expose API keys in frontend code
- Broker keys (ALPACA_*, IBKR_*) ONLY in backend environment variables
- No secrets in NEXT_PUBLIC_* env vars
- service_role key ONLY in backend, with explicit user_id validation
- .env files are in .gitignore and denied from Claude Code reading

## Supabase RLS
- ALWAYS enable Row Level Security on new tables
- service_role bypasses RLS — auth.uid() does NOT work with service_role
- Use Option A (pass User-JWT to Supabase) or Option B (explicit user_id validation in backend)

## CORS
- No wildcard origins in production
- Only allow Vercel domain + localhost in FastAPI CORS config

## Broker Security
- Stufe 1: ONLY Alpaca Paper API — NO live trading
- Check ALPACA_PAPER_MODE=true before every broker API call
- No IBKR access configured in Stufe 1

## Frontend Security
- All API calls go through FastAPI backend — never call external APIs directly from frontend
- No secrets in client-side code, localStorage, or cookies
- Validate all user inputs server-side
