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

- [ ] **T-013:** SELECT(*) → explizite Spalten
- [ ] **T-014:** Strukturiertes Logging
- [ ] **T-012:** Graceful Shutdown

## Batch 6: P2 Frontend + Testing

- [ ] **T-011:** Frontend Tests erweitern (≥50 total)
- [ ] **T-015:** Budget Manager In-Memory Cache

## Batch 7: P3 Data Integrity

- [ ] **T-016:** Portfolio Holdings Sync (Broker → DB)
- [ ] **T-017:** Circuit Breaker Persistence
- [ ] **T-019:** Claim Provenance deterministisch
- [ ] **T-020:** policy_change_log INSERT-RLS entfernen

## Batch 8: P3 Robustness

- [ ] **T-023:** Idempotency für Trade-Propose
- [x] **T-024:** CircuitBreakerOpenError in Approve-Flow catchen → umgesetzt in Batch 2 Trade-Hardening
- [ ] **T-029:** Composite Index (status, proposed_at) auf trade_log
- [ ] **T-032:** Große Funktionen aufteilen (>100 Zeilen)

## Batch 9: P3 Hardening

- [ ] **T-018:** E2E Browser Tests (Playwright, 5 Flows)
- [ ] **T-022:** Docs SSOT (learning_progress + Legacy markieren)
- [ ] **T-028:** a11y Verbesserungen (Label/Input, PresetCards)
- [ ] **T-030:** Security Headers (CSP, frame-ancestors)
- [ ] **T-031:** use-push-subscription.ts prüfen/entfernen
- [ ] **T-033:** API Response-Envelope vereinheitlichen
- [ ] **T-034:** CORS allow_credentials Prod-Guard

---

## Status

| Batch | Tickets | Erledigt | Status |
|-------|:-------:|:--------:|--------|
| 1 | 5 | 5 | DONE |
| 2 | 3 | 3 | DONE |
| 3 | 3 | 3 | DONE (in Batch 2 Trade-Hardening) |
| 4 | 3 | 3 | DONE |
| 5 | 3 | 0 | — |
| 6 | 2 | 0 | — |
| 7 | 4 | 0 | — |
| 8 | 4 | 1 | T-024 done (in Batch 2 Trade-Hardening) |
| 9 | 7 | 0 | — |
| **Total** | **34** | **15** | |
