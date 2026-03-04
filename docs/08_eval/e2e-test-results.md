# E2E Smoke Test Results — Step 15

**Date:** 2026-03-04
**Environment:** Local dev (backend: uvicorn --reload, frontend: npm run dev)
**Tester:** Claude Code (automated + manual verification)

---

## Positive Test: AAPL Full Flow

| # | Step | Expected | Status | Notes |
|---|------|----------|--------|-------|
| 1 | Login with email/password | Redirect to /dashboard | PENDING | |
| 2 | Pre-Policy check (AAPL) | passed: true | PENDING | |
| 3 | Data Collection (AAPL) | fundamentals + prices stored | PENDING | |
| 4 | Fundamental Analysis | analysis_run created, fundamental_out populated | PENDING | |
| 5 | Claim Extraction | claims[] in DB, count > 0 | PENDING | |
| 6 | Verification | verification_results in DB, mixed statuses | PENDING | |
| 7 | Investment Note visible | Recommendation + confidence on /analyse page | PENDING | |
| 8 | Trade Propose | trade_log entry with status=proposed | PENDING | |
| 9 | Trade Approve | status changes to approved→executed | PENDING | |
| 10 | Alpaca Paper execution | broker_order_id populated | PENDING | |
| 11 | Audit Trail complete | analysis_runs, claims, verification_results, trade_log all linked | PENDING | |
| 12 | agent_cost_log entries | fundamental_analyst + claim_extractor logged | PENDING | |
| 13 | Budget widget shows correct % | utilization_pct > 0, Progress bar reflects spend | PENDING | |
| 14 | Verification Score visible | Shown on dashboard without clicking "System prüfen" | PENDING | |
| 15 | Error Rate + Latency visible | Pipeline metrics shown on System-Status card | PENDING | |

## Negative Tests

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| N1 | Pre-Policy blocks "BTC" | violation: forbidden instrument type | PENDING | |
| N2 | Pre-Policy blocks "TQQQ" | violation: leveraged ETF | PENDING | |
| N3 | Full-Policy blocks oversized position | violation: max_single_position exceeded | PENDING | |
| N4 | Verification produces non-verified claim | At least 1 claim with status != verified | PENDING | |
| N5 | Kill-Switch blocks new trades | activate → try trade propose → rejected | PENDING | |

## Circuit Breaker

Covered by 50+ unit tests in `test_kill_switch.py`. Not re-tested manually.

---

## Summary

| Category | Total | Pass | Fail | Pending |
|----------|-------|------|------|---------|
| Positive | 15 | 0 | 0 | 15 |
| Negative | 5 | 0 | 0 | 5 |

**Overall:** PENDING — to be filled after local E2E run.

**Note:** This E2E test is manual. 645 backend + 26 frontend automated tests cover logic.
The E2E verifies integration and UI display correctness.
