# Audit-Fix Progress — MyTrade MVP

> **Quelle:** memory/audit-synthesis.md (Multi-Model Audit, 34 Tickets)
> **Start:** 2026-03-05

---

## Batch 1: P0 Deploy Blockers + Quick Wins

- [x] **T-003:** "expired" aus VALID_TRADE_STATUSES entfernen
- [x] **T-026:** agno Dependency entfernen
- [x] **T-021:** .env.example bereinigen (Legacy entfernen)
- [x] **T-002:** Admin-Guard für Kill-Switch Endpoints
- [x] **T-001:** Serverseitiges Full-Policy Gate

## Batch 2: P1 Kern-Fixes

- [x] **T-004:** Float → Decimal in Finanzberechnungen
- [x] **T-005:** Backend Dependency Pinning (nach T-026)
- [x] **T-007:** Health Endpoint Readiness (503 bei DB-Down)

## Batch 3: P1 Trade-Sicherheit → umgesetzt in Batch 2 Trade-Hardening

- [x] **T-006:** manual_check + trade_critical als Blocking
- [x] **T-008:** Orphaned Trade Cleanup (nach T-024)
- [x] **T-027:** Kill-Switch Check auch im Approve-Flow (nach T-001)

## Batch 4: P2 Code-Qualität

- [x] **T-009:** SoC-Refactoring policy.py Route
- [x] **T-010:** Error-Handler Decorator
- [x] **T-025:** Bare except → spezifische Exceptions (nach T-010)

## Batch 5: P2 Observability

- [x] **T-013:** SELECT(*) → explizite Spalten
- [x] **T-014:** Strukturiertes Logging
- [x] **T-012:** Graceful Shutdown

## Batch 6: Quick-Wins + Security

- [x] **T-034:** CORS allow_credentials Prod-Guard
- [x] **T-020:** policy_change_log INSERT-RLS entfernen
- [x] **T-029:** Composite Index (status, proposed_at/approved_at) auf trade_log
- [x] **T-031:** use-push-subscription.ts entfernen
- [x] **T-022:** Docs SSOT (learning_progress als FUTURE markieren)
- [x] **T-015:** Budget Manager In-Memory Cache
- [x] **T-028:** a11y Verbesserungen (Label/Input, PresetCards Space-Key)
- [x] **T-030:** Security Headers (X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy)

## Batch 7: P3 Remaining

- [x] **T-011:** Frontend Tests erweitern (52 total, 13 Dateien)
- [ ] **T-016:** Portfolio Holdings Sync (Broker → DB) — deferred post-deploy
- [x] **T-017:** Circuit Breaker Persistence (persist/restore + system_state CB columns)
- [x] **T-019:** Claim Provenance deterministisch (hardcoded finnhub, LLM source ignored)
- [x] **T-023:** Idempotency für Trade-Propose (5-eq SELECT before INSERT)
- [x] **T-024:** CircuitBreakerOpenError in Approve-Flow catchen → umgesetzt in Batch 2 Trade-Hardening
- [x] **T-032:** Große Funktionen aufteilen (alle ≤100 Zeilen)
- [ ] **T-018:** E2E Browser Tests (Playwright, 5 Flows) — deferred post-deploy
- [x] **T-033:** API Response-Envelope (request_id in errors, count in lists, positions-table fix)

---

## Status

| Batch | Tickets | Erledigt | Status |
|-------|:-------:|:--------:|--------|
| 1 | 5 | 5 | DONE |
| 2 | 3 | 3 | DONE |
| 3 | 3 | 3 | DONE (in Batch 2 Trade-Hardening) |
| 4 | 3 | 3 | DONE |
| 5 | 3 | 3 | DONE |
| 6 | 8 | 8 | DONE |
| 7 | 9 | 7 | T-016, T-018 deferred post-deploy |
| **Total** | **34** | **32** | 2 deferred (T-016, T-018) |
