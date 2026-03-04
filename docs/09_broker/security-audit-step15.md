# Security Audit — Step 15 (Final MVP)

**Date:** 2026-03-04
**Auditor:** security-reviewer agent (Opus)
**Scope:** Full codebase — backend + frontend + infra config
**Commit:** feature/step-15-monitoring-deploy (based on main 44f6bcb)

---

## Results

| # | Check | Result | Details |
|---|-------|--------|---------|
| 1 | No API keys in frontend | PASS | Grepped `SUPABASE_SERVICE_ROLE`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ANTHROPIC_API_KEY`, `ALPHA_VANTAGE`, `FINNHUB` in `frontend/src/` — 0 matches |
| 2 | No secrets in NEXT_PUBLIC_* | PASS | Only 3 NEXT_PUBLIC_ vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `API_URL` — all safe for browser |
| 3 | RLS active on all tables | PASS | 13/13 tables in migrations have `ENABLE ROW LEVEL SECURITY`. `learning_progress` not in MVP migrations (documented) |
| 4 | CORS strict origins | PASS | Default `http://localhost:3000`, production via `CORS_ORIGINS` env var. No wildcards. Methods restricted to `GET,POST,PUT,DELETE` |
| 5 | ALPACA_PAPER_MODE check | PASS | Double validation: constructor check + `_ensure_paper_mode()` before every broker call. Default `True` (fail-safe) |
| 6 | service_role only in backend | PASS | 1 match in `frontend/src/lib/supabase/server.ts` — documentation comment warning, not actual usage |
| 7 | .env in .gitignore | PASS | Root `.gitignore` + frontend `.gitignore` both exclude `.env*`. Claude Code settings deny `.env` file reading |
| 8 | Rate limiting on routes | PASS | 24/25 endpoints have `@limiter.limit()`. Exception: `GET /health` (intentionally public for Railway health checks) |
| 9 | No hardcoded API keys | PASS | Grepped `sk-`, `api_key =`, `apiKey:`, `secret_key =` — 0 real matches. All credentials via Pydantic `BaseSettings` |
| 10 | PostToolUse hook active | PASS | Hook scans `frontend/` for 6 secret patterns on every Write/Edit. PreToolUse blocks destructive bash commands |

---

## Overall: 10/10 PASS

Defense-in-depth layers:
1. **Secrets isolation** — all credentials from env vars via Pydantic, never hardcoded
2. **RLS enforcement** — all 13 DB tables protected
3. **Paper mode safety** — double-checked before every broker API call
4. **CORS lockdown** — explicit origin list, no wildcards
5. **Frontend cleanliness** — only safe public vars exposed to browser
6. **Dev-time guardrails** — PostToolUse hooks + PreToolUse hooks + .env deny rules
