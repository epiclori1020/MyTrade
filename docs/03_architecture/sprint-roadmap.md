# Sprint-Roadmap — MyTrade

> **Ansatz:** Vertical Slice MVP — ein kompletter Flow von A bis Z, nicht Layer für Layer.
> **Quelle:** Architektur-Spezifikation v2.1 (adaptiert für Vertical Slice)

---

## Phase 1: Vertical Slice MVP (Woche 1-3)

**Ziel:** Ein kompletter End-to-End Flow: User klickt "Analyze AAPL" → Daten → Agent → Claims → Verification → Policy → Trade Plan → Paper Execute → Supabase Log.

### Woche 1: Backend-Skelett + Datenfluss
- FastAPI Scaffold + Supabase Connection (EU Frankfurt)
- DB-Tabellen: `analysis_runs`, `claims`, `verification_results`, `trade_log`, `user_policy`, `policy_change_log`
- Data Collector: Finnhub (1 Provider, minimal)
- 1 Agno Agent (Fundamental Analyst, vereinfacht)
- Health-Endpoint mit Connection-Tests

### Woche 2: Policy + Verification + Execution
- `get_effective_policy()` — liest aus DB, Fallback YAML
- Pre-Policy (Universe/Verbote — vor Agent-Call)
- Full-Policy (Sizing/Exposure — nach Verification, auf verifizierten Zahlen)
- Verification Layer: 2 Claims gegen Alpha Vantage als 2. Quelle
- Alpaca Paper API Integration
- Claims + Verification in Supabase loggen

### Woche 3: Frontend + Settings + End-to-End
- Next.js + shadcn/ui: Analyse-Seite ("Analyze" Button + Ergebnis mit Claim-Ampel)
- Settings-Seite: 3 Ebenen (Einsteiger / Presets / Advanced) mit Microcopy
- End-to-End Test: AAPL Analyse → Policy Check → Verified Claims → Trade Plan → Paper Log
- Definition of Done validieren (siehe @docs/00_build-brief/brief.md)

---

## Phase 2: Erweiterung (Woche 4-8)

- Weitere Agents (Technical, Sentiment, Risk Manager, Devil's Advocate, Synthesizer)
- Multi-Provider Daten (Finnhub + Alpha Vantage + FRED + SEC EDGAR)
- Vollständiges Verification Tier-System (A/B/C)
- Error Handling: Circuit Breaker, JSON-Repair, Partial Results
- Portfolio-Monitoring Cron-Job
- Dashboard: Monitoring (Kosten, Agent Health, Verification Rate)
- `agent_cost_log` + Budget-Caps mit Opus→Sonnet Fallback

---

## Phase 3: Hardening (Woche 9-12)

- Security Audit (RLS-Verification, Secrets Rotation, CORS)
- Error-Simulation: Was passiert wenn Finnhub + AV gleichzeitig down sind?
- Performance-Optimierung (Caching, parallele API-Calls)
- Steuer-Report (AT: KESt 27.5%, W-8BEN) — optional/estimated overlay
- PWA-Setup für Mobile
- Analyse-Archiv mit Performance-Tracking

---

## Nach Phase 3

> **Minimum 3 Monate Paper Trading (Stufe 1).** Das System läuft erst 3-6 Monate ausschließlich mit Paper Trading. Erst wenn die Pipeline stabil ist und der User die Outputs sicher interpretieren kann, wird auf Stufe 2 (Human Confirms mit echtem Geld) umgestellt. Das ist nicht optional.

### Gate-Kriterien für Stufe 2
- Min. 3 Monate Paper Trading
- Pipeline-Fehlerrate < 5%
- Verification-Rate > 85%
- IPS-Compliance: 100%
- User versteht und kann Outputs interpretieren
- Security Audit bestanden
- IBKR Account eröffnet und API konfiguriert
- **NICHT:** Profitables Paper Trading (marktabhängig, kein Qualitätskriterium)

---

## Referenzen
- Build Brief (MVP-Scope + DoD): @docs/00_build-brief/brief.md
- Settings-System: @docs/02_policy/settings-spec.md
- Execution Contract (Stufenwechsel): @docs/05_risk/execution-contract.md
- Eval-Metriken: @docs/08_eval/metrics.md
