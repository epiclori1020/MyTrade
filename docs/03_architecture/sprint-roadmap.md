# Sprint-Roadmap — MyTrade Stufe 1 MVP

> **SSOT:** Dieses Dokument ist die **einzige autoritative Quelle** für die Implementierungsreihenfolge.
> Die master-prompt.md verweist hierher. Die Architektur-Spec v2.1 Sektion 15 ist durch dieses Dokument ersetzt.
>
> **Ansatz:** Vertical Slice MVP — ein kompletter End-to-End Flow, nicht Layer für Layer.
> **Ziel:** User klickt "Analyze AAPL" → Daten → Agent → Claims → Verification → Policy → Trade Plan → Paper Execute → Supabase Log.
> **Quellen:** Alle Docs im `/docs` Verzeichnis. Bei Widersprüchen gelten die Docs.

---

## Phase 1: Foundation (Steps 1-5)

### Step 1: Docs lesen + Agno recherchieren

- [x] Lies die 6 Pflichtdokumente (siehe master-prompt.md "Dein Repo")
- [x] Recherchiere Agno's aktuelle API via Context7 MCP (`use context7`):
  - Agent-Erstellung (System-Prompt, Tools, Model-Parameter)
  - `coordinate` Mode (Team Leader + Member Agents)
  - Tool-Integration (Supabase, HTTP APIs)
  - PostgreSQL-Storage für Agent Memory/Sessions
- [x] Dokumentiere API-Patterns in einer kurzen Notiz für spätere Steps

### Step 2: Supabase-Projekt + Auth + DB-Migrationen

**Quelle:** @docs/03_architecture/database-schema.md, @docs/02_policy/settings-spec.md, @docs/09_broker/security.md

**Auth Setup:**
- [x] Supabase-Projekt erstellen (EU Frankfurt Region)
- [x] Supabase Auth konfigurieren: Email/Password für MVP
- [x] Auth MUSS vor den Tabellen stehen (RLS braucht `auth.uid()`)

**DB-Migrationen — alle 12 MVP-Tabellen:**

| # | Tabelle | Quelle | Zweck |
|---|---------|--------|-------|
| 1 | `user_policy` | settings-spec.md | IPS-Einstellungen (3-Tier: Beginner/Preset/Advanced) |
| 2 | `policy_change_log` | settings-spec.md | Audit-Trail für Policy-Änderungen |
| 3 | `stock_fundamentals` | database-schema.md | Fundamentaldaten pro Ticker/Periode |
| 4 | `stock_prices` | database-schema.md | Historische + aktuelle Kurse |
| 5 | `macro_indicators` | database-schema.md | Makrodaten (GDP, CPI, Fed Rate) |
| 6 | `analysis_runs` | database-schema.md | Analyse-Durchläufe mit Agent-Outputs |
| 7 | `claims` | database-schema.md | Extrahierte Claims aus Agent-Outputs |
| 8 | `verification_results` | database-schema.md | Verification-Ergebnisse pro Claim |
| 9 | `trade_log` | database-schema.md | Trade-Vorschläge und Ausführungen |
| 10 | `portfolio_holdings` | database-schema.md | Aktuelle Positionen |
| 11 | `error_log` | database-schema.md | System-Fehler |
| 12 | `agent_cost_log` | database-schema.md | API-Kosten-Tracking (3-Tier) |

> **Nicht im MVP:** `investment_policy` (Legacy, ersetzt durch `user_policy`), `learning_progress` (Lern-Modus = Phase 2+)

**RLS Policies:**
- [x] RLS aktivieren auf allen User-bezogenen Tabellen
- [x] `auth.uid() = user_id` Policies für SELECT/UPDATE
- [x] `trade_log`: User kann nur eigene Trades sehen + status von `proposed` auf `approved`/`rejected` ändern
- [x] Entscheidung: Hybrid — Option A (auth.uid()) für 5 User-Tabellen + Option B (service_role) für 4 Backend-Tabellen + Shared-Data RLS (authenticated SELECT) für 3 Datentabellen

**Indexes:**
- [x] Alle Indexes aus database-schema.md erstellen

### Step 3: Backend-Scaffold

**Quelle:** @docs/03_architecture/system-overview.md, @docs/09_broker/security.md

- [x] FastAPI Projekt-Struktur erstellen (`backend/src/`)
- [x] Supabase Connection einrichten (Supabase Python Client)
- [x] Health-Endpoint: `GET /health` mit DB-Connection-Test
- [x] CORS-Konfiguration: nur `localhost:3000` + Vercel-Domain (keine Wildcards)
- [x] Auth Middleware: JWT-Validierung auf allen geschützten Endpoints
- [x] API Rate Limiting: 100 requests/min/user (FastAPI Middleware)
- [x] Basis Error-Response Format (konsistent für alle Endpoints)
- [x] `.env` Werte laden: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`

### Step 4: Data Collector

**Quelle:** @docs/06_data/providers.md, @docs/03_architecture/agents.md (Agent 1)

Der Data Collector ist **deterministisch** (kein LLM) — reine API-Logik.

- [x] Finnhub API-Client implementieren
  - `/stock/metric?symbol=X` → Fundamentals (Revenue, EPS, P/E)
  - `/stock/profile2?symbol=X` → shareOutstanding (für absolute Werte)
  - `/quote?symbol=X` → Aktienkurs
  - `/stock/candle?symbol=X` → Historische OHLCV (1 Jahr)
  - `/company-news?symbol=X` → News
  - `/stock/insider-transactions?symbol=X` → Insider-Trades
- [x] Rate Limiting: max. 55 calls/min (Sliding Window, thread-safe)
- [x] Retry-Logik: Exponential Backoff (2s → 4s → 8s, max. 3 Retries)
- [x] Fallback-Quelle: Alpha Vantage Client als Backup wenn Finnhub down
- [x] Fehler in `error_log` Tabelle schreiben (best-effort, on_error callback pro Retry)
- [x] Daten schreiben in:
  - `stock_fundamentals` (Ticker, Periode, Revenue, EPS, P/E, etc.)
  - `stock_prices` (OHLCV, batch upsert 100 rows)
- [x] MVP-Universe hardcoded: `AAPL, MSFT, JNJ, JPM, PG, VOO, VWO`
- [x] API-Endpoint: `POST /api/collect/{ticker}` (auth + rate-limited)
- [x] 54 Tests (8 bestehend + 46 neu) alle grün

### Step 5: Fundamental Analyst Agent

**Quelle:** @docs/03_architecture/agents.md (Agent 3)

- [x] Fundamental Analyst Agent erstellen (Direct Anthropic SDK, `claude-sonnet-4-6`)
  - Modell: `claude-sonnet-4-6` (Standard-Tier, ~30K Token Budget)
  - System-Prompt aus agents.md (Geschäftsmodell, Finanzen, Bewertung, Qualität)
  - Direct Anthropic SDK statt Agno (Agno coordinate mode deferred auf Step 8+)
  - `messages.parse()` für native Pydantic Structured Output
- [x] Input: `stock_fundamentals` aus Supabase (TTM-Daten)
- [x] Output: Strukturiertes JSON mit `{value, unit, source, period, retrieved_at}` pro Zahl
  - `{business_model, financials{}, valuation{}, quality{}, moat_rating, score, risks[], sources[]}`
- [x] Agent-Output in `analysis_runs.fundamental_out` speichern
- [x] Token-Verbrauch + Kosten in `agent_cost_log` loggen
- [x] API-Endpoint: `POST /api/analyze/{ticker}` (startet Analyse)
- [x] 91 Tests (54 bestehend + 37 neu) alle grün

#### Phase 1 — Definition of Done
- [x] Supabase Auth funktioniert (Login/Signup)
- [x] Alle 12 DB-Tabellen existieren mit RLS
- [x] `GET /health` gibt 200 + DB-Status zurück
- [x] Data Collector holt AAPL-Daten von Finnhub und schreibt in DB
- [x] Fundamental Analyst analysiert AAPL und liefert strukturiertes JSON
- [x] `analysis_runs` Eintrag mit `fundamental_out` existiert in Supabase

---

## Phase 2: Verification Pipeline (Steps 6-8)

### Step 6: Claim Extractor

**Quelle:** @docs/03_architecture/agents.md (Agent 9), @docs/04_verification/claim-schema.json

- [x] Claim Extractor Agent erstellen (Direct Anthropic SDK, `claude-haiku-4-5`)
  - Modell: `claude-haiku-4-5` (Light-Tier, ~5K Token Budget)
  - System-Prompt: "Extrahiere alle numerischen Claims aus dem Agent-Output gemäß Schema"
- [x] Input: `analysis_runs.fundamental_out` (JSON)
- [x] Output: `claims[]` gemäß `claim-schema.json`:
  - `{claim_id, claim_text, claim_type, value, unit, ticker, period, source_primary, tier, required_tier, trade_critical}`
- [x] Deterministic post-processing: tier, required_tier, trade_critical via keyword matching
- [x] Fallback-Chain bei Schema-Fehler:
  1. 1x Retry mit Haiku (verschärfter Prompt mit Error-Kontext)
  2. Sonnet 4.6 Fallback (mit original Prompt)
- [x] Claims in `claims` Tabelle schreiben (batch insert)
- [x] MVP: Revenue, EPS, P/E, Net Income, FCF, EV/EBITDA als `trade_critical: true` Claims
- [x] Token-Verbrauch + Kosten in `agent_cost_log` loggen (akkumuliert über Fallback-Chain)
- [x] API-Endpoint: `POST /api/extract-claims/{analysis_id}` (auth + rate-limited)
- [x] 162 Tests (89 bestehend + 73 neu) alle grün

### Step 7: Verification Layer

**Quelle:** @docs/04_verification/tier-system.md, @docs/04_verification/claim-schema.json

- [x] Alpha Vantage API-Client wiederverwendet (bereits aus Step 4, `services/alpha_vantage.py`)
  - Rate Limit: max. 25 calls/Tag (free Tier)
- [x] Cross-Check Logik implementieren:
  - Revenue: Claim-Wert vs. Alpha Vantage-Wert
  - P/E Ratio, EPS, EV/EBITDA, P/B, ROE: Claim-Wert vs. AV-Wert
- [x] Status-Logik:
  - Abweichung ≤ 5% → `consistent` (MVP: kein `verified` ohne Tier A/SEC EDGAR)
  - Abweichung > 5% → `disputed` (RED FLAG)
  - Keine 2. Quelle verfügbar → `unverified` (keine DB-Zeile)
  - Trade-kritisch + nur Tier B → `manual_check`
- [x] Ergebnisse in `verification_results` Tabelle schreiben (batch insert)
- [x] Disputed + trade_critical → `has_blocking_disputed=true` in Summary
- [x] Verification Summary in `analysis_runs.verification` speichern
- [x] Idempotenz-Check: Re-Verification wird geblockt wenn bereits Ergebnisse existieren
- [x] API-Endpoint: `POST /api/verify/{analysis_id}` (auth + rate-limited)
- [x] 232 Tests (174 bestehend + 58 neu) alle grün
- [x] Security Review: F1 (DB error string leak) gefixt, alle Checks PASS

### Step 8: Policy Engine

**Quelle:** @docs/05_risk/policy-engine.md, @docs/02_policy/settings-spec.md, @docs/02_policy/ips-template.yaml

Die Policy Engine ist **deterministisches Python** — KEIN LLM.

**`get_effective_policy()`:**
- [x] Primär: `user_policy` Tabelle lesen
- [x] ~~Fallback: `ips-template.yaml` laden wenn DB nicht erreichbar~~ → ConfigurationError bei DB-Fehler (MVP); TODO: YAML-Fallback für Production-Resilience
- [x] Preset-Resolution: Beginner/Balanced/Active → konkrete Werte
- [x] Advanced-Overrides: Validierung gegen Constraint-Tabelle (Min/Max aus settings-spec.md)
- [x] Hard Constraints immer erzwungen: verbotene Typen, EM nur ETF, Execution Stage
- [x] Cooldown-Enforcement: `cooldown_until` Timestamp prüfen bei Policy-Read (Mode-Wechsel erst nach 24h aktiv)

**Pre-Policy (VOR Agent-Call):**
- [x] Instrument-Typ erlaubt? (MVP: Stub — MVP_UNIVERSE ist vorab geprüft, keine verbotenen Instrumente)
- [x] Ticker im MVP-Universe?
- [x] Region erlaubt? (MVP: Stub — alle MVP_UNIVERSE Ticker sind US)
- [x] Kill-Switch aktiv? (MVP: Stub — kein dedizierter State, TODO Step 11)
- [x] Maturity Stage korrekt? (Pre-Policy: Stub, Full-Policy: aktiv für is_live_order)
- [x] Bei Reject: sofortige Antwort + Grund loggen (spart LLM-Tokens)

**Full-Policy (NACH Verification, VOR Execution):**
- [x] Max Single Position (default: 5% Satellite)
- [x] Max Sektor-Konzentration (MVP: Stub — portfolio_holdings hat kein sector Feld)
- [x] Max Trades pro Monat (default: 10)
- [x] Cash Reserve Minimum (MVP: Aktiv wenn Broker-Kontostand verfügbar, Phase 2+)
- [x] Portfolio Drawdown Kill-Switch (default: 20%)
- [x] Stop-Loss Soft Flag (MVP: Stub/Warning — TODO Step 11 Monitoring)
- [x] Alle Werte aus `get_effective_policy()` — NIEMALS hardcoden

**Tests (Policy Engine):**
- [x] Unit Test: Pre-Policy blockt verbotene Instrumente (Ticker nicht in MVP_UNIVERSE)
- [x] Unit Test: Pre-Policy blockt Ticker außerhalb Universe
- [x] Unit Test: Full-Policy blockt Position > max_single_position
- [x] Unit Test: Full-Policy blockt wenn Drawdown Kill-Switch aktiv (mock `_calculate_portfolio_drawdown`)
- [x] Unit Test: `get_effective_policy()` merged Preset + Overrides korrekt
- [x] 53 Policy Engine Tests + 15 Route Tests = 68 neue Tests, 301 gesamt alle grün

**API-Endpoints:**
- [x] `POST /api/policy/pre-check/{ticker}` (100/min rate limit)
- [x] `POST /api/policy/full-check` (50/min rate limit, TradeProposal body)
- [x] `GET /api/policy/effective` (30/min rate limit)

#### Phase 2 — Definition of Done
- [x] Claim Extractor extrahiert min. 5 Claims aus AAPL-Analyse (Schema-valid) — Step 6
- [x] Verification zeigt min. 1 Claim mit Status != `verified` (z.B. unverified oder disputed) — Step 7
- [x] Pre-Policy blockt einen verbotenen Ticker (z.B. Bitcoin-ETF) — `test_invalid_ticker_blocked`
- [x] Full-Policy blockt eine zu große Position — `test_max_single_position_exceeded`
- [x] Schema-Validation Test passed (Claims gegen claim-schema.json) — Step 6
- [x] Policy Engine Unit Tests: 5/5 passed

---

## Phase 3: Execution + Resilience (Steps 9-11)

### Step 9: Alpaca Paper API + Broker-Adapter

**Quelle:** @docs/09_broker/broker-router.md, @docs/05_risk/execution-contract.md

- [x] Abstraktes `BrokerAdapter` Interface implementieren:
  - `submit_order(order) → OrderResult`
  - `get_positions() → list[Position]`
  - `get_account() → AccountInfo`
- [x] `AlpacaPaperAdapter` implementieren (Stufe 1)
- [x] Prüfung: `ALPACA_PAPER_MODE=true` vor JEDEM API-Call
- [x] Trade-Vorschlag in `trade_log` schreiben (Status: `proposed`)
- [x] Trade-Ausführung: Status `proposed` → `executed` (Paper)
- [x] Broker-Fehler: Order Rejected → Grund in `trade_log.rejection_reason` loggen
- [x] API-Endpoint: `POST /api/trades/{trade_id}/approve` (User-JWT, nicht service_role)
- [x] API-Endpoint: `POST /api/trades/{trade_id}/reject`
- [x] Unbestätigte Orders verfallen nach 24 Stunden

### Step 10: Error Handling

**Quelle:** @docs/03_architecture/error-handling.md

- [x] Circuit Breaker Pattern implementieren:
  - 5 Failures hintereinander → 60s Pause (Open)
  - 1 Probe-Call nach 60s (Half-Open)
  - Erfolg → Closed / Fehler → 120s warten
  - Pro Provider (Finnhub, Alpha Vantage, Alpaca)
- [x] JSON Repair: `json_repair` Library für malformed Agent-Outputs
- [x] Partial Results: Wenn 1 Agent fehlschlägt:
  - `analysis_runs.status` = `partial`
  - Vorhandene Outputs normal weiterverarbeiten
  - Confidence-Score automatisch reduzieren
  - Fehlender Agent in `error_log` dokumentieren
- [x] LLM Retry: 1x Retry mit verschärftem Prompt bei JSON-Fehler
- [x] Supabase Write Failure: 3x Retry, dann In-Memory-Queue
- [x] Alle Fehler in `error_log` Tabelle loggen (component, error_type, message, retry_count)

### Step 11: Kill-Switch + Budget-Fallback

**Quelle:** @docs/05_risk/kill-switch.md, @docs/03_architecture/monitoring.md

**Kill-Switch:**
- [x] Automatische Aktivierung bei:
  1. Portfolio Drawdown ≥ 20%
  2. 5 aufeinanderfolgende Broker-API-Fehler
  3. Verification-Rate < 70%
  4. Manuell durch User
- [x] Kill-Switch Effekt: System wechselt in Advisory-Only (Stufe 0)
  - Keine neuen Order-Vorschläge
  - Bestehende Positionen bleiben (kein Panik-Verkauf)
  - User-Notification
  - Manuelle Reaktivierung erforderlich
- [x] Kill-Switch Status in DB persistieren

**Budget-Fallback (3-Tier):**
- [x] Budget-Tracking pro Tier in `agent_cost_log`:
  - Heavy (Opus): $30/Monat Hard Cap
  - Standard (Sonnet): $20/Monat Hard Cap
  - Light (Haiku): $5/Monat Hard Cap
  - Gesamt: $55/Monat Hard Cap
- [x] Degradierungs-Logik:
  - Opus 100% → Devil's Advocate + Synthesizer degradieren zu Sonnet
  - Sonnet 100% → Analyse-Agents degradieren zu Haiku
  - Gesamt Hard Cap → Keine weiteren LLM-Calls bis Monatsende
- [x] `agent_cost_log.degraded = true` wenn Budget-Fallback aktiv

#### Phase 3 — Definition of Done
- [x] Paper Order für AAPL wird via Alpaca Paper API ausgeführt
- [x] `trade_log` Eintrag mit Status `executed` existiert
- [x] Circuit Breaker stoppt Calls nach 5 Failures
- [x] Partial Result: Analyse läuft weiter wenn 1 Agent fehlschlägt
- [x] Kill-Switch aktiviert sich bei simuliertem 20% Drawdown

---

## Phase 4: Frontend + Mobile (Steps 12-14)

### Step 12: Frontend Foundation

**Quelle:** @docs/03_architecture/system-overview.md, @docs/09_broker/security.md

**Projekt-Setup:**
- [x] Next.js Projekt erstellen (App Router, Next.js 16 + Tailwind v4)
- [x] Tailwind CSS konfigurieren (CSS-first @theme inline)
- [x] shadcn/ui installieren (button, card, input, label, sonner, separator, skeleton, avatar, badge, sidebar)
- [x] CSS Variables für Theming (Dark Mode Support) — MyTrade Design System
- [x] `/frontend-design` Skill ausführen vor UI-Arbeit (Anti-AI-Slop)
- [x] Design System Spec erstellt: `docs/06_frontend/design-system.md`

**Auth Pages:**
- [x] Login-Seite (Email/Password, deutsche Labels)
- [x] Signup-Seite (mit Passwort-Bestätigung)
- [x] Supabase Auth Client-Integration (@supabase/ssr, Browser + Server Client)
- [x] Protected Routes (Middleware mit getUser(), Redirect zu Login)
- [x] JWT Token Handling (Bearer Token für API-Calls via ApiClient)
- [x] PKCE Auth Callback (`/auth/callback/route.ts`)

**Layout + Navigation:**
- [x] App Shell: Sidebar (Desktop) / Bottom Nav (Mobile)
- [x] Navigation Items: Dashboard, Analyse, Einstellungen
- [x] Responsive Breakpoints: Mobile (375px), Tablet (768px), Desktop (1280px)
- [x] Dark Mode Toggle (System-default + manuell, next-themes)

**API Client:**
- [x] Zentraler API-Client mit Base URL + Auth Headers
- [x] Error Handling: ApiError Klasse + Toast-Notifications Pattern
- [x] Loading States: Skeleton-Loader Pattern (loading.tsx pro Route)
- [x] Error Boundaries: error.tsx pro Route mit "Erneut versuchen"

**Security:**
- [x] Security-Review bestanden (12/12 Checks PASS)
- [x] Keine Secrets in Frontend-Code
- [x] docs/09_broker/security.md aktualisiert (NEXTAUTH_* entfernt, NEXT_PUBLIC_* dokumentiert)

### Step 13: Frontend Screens

**Quelle:** @docs/02_policy/settings-spec.md, @docs/04_verification/tier-system.md, @docs/07_compliance/decision-support-rules.md

---

#### 13a: Analyse-Seite

**Ticker-Eingabe:**
- [ ] Suchfeld mit Autocomplete/Dropdown (MVP Universe: AAPL, MSFT, JNJ, JPM, PG, VOO, VWO)
- [ ] "Analyze" Button (prominent, primary action)
- [ ] Pre-Policy Feedback: sofortige Meldung wenn Ticker verboten (z.B. "BTC ist nicht im erlaubten Universum")

**Analyse Loading State (Dauer: 2-5 Minuten):**
- [ ] Progress-Indikator mit Schritten:
  1. "Daten werden geladen..." (Data Collector)
  2. "Analyse läuft..." (Fundamental Agent)
  3. "Claims werden extrahiert..." (Claim Extractor)
  4. "Verification läuft..." (Cross-Check)
  5. "Policy-Check..." (Full-Policy)
  6. "Trade Plan wird generiert..."
- [ ] User kann Seite verlassen und zurückkehren (Analyse läuft im Backend)
- [ ] Polling oder WebSocket für Status-Updates

**Analyse-Ergebnis — Investment Note:**
- [ ] Recommendation Badge: STRONG BUY / BUY / HOLD / SELL / STRONG SELL / NO ACTION
- [ ] Confidence-Score Anzeige (0-100, visuell als Gauge oder Balken)
- [ ] These: Kernargumente für die Empfehlung (Bullet Points)
- [ ] Risiken: Identifizierte Risikofaktoren (Bullet Points)
- [ ] Daten-Tabelle: Key Financials (Revenue, EPS, P/E, FCF, etc.)

**Claim-Liste mit Ampel-Badges:**
- [ ] Jeder Claim als Zeile mit:
  - Claim-Text (z.B. "AAPL Revenue FY2025: $394.3B")
  - Status-Badge: grün (`verified`/`consistent`), gelb (`unverified`/`manual_check`), rot (`disputed`)
  - Quelle + Verification-Quelle (z.B. "Finnhub → Alpha Vantage, Abweichung 0.2%")
- [ ] Disputed Claims visuell hervorgehoben (roter Rahmen/Hintergrund)
- [ ] Expandable: Klick zeigt Details (Primärwert, Verification-Wert, Abweichung)

**Trade-Plan:**
- [ ] Ticker, Richtung (BUY/SELL/HOLD), Shares, Preis, Order-Typ
- [ ] Begründung (1-2 Sätze)
- [ ] Stop-Loss Level
- [ ] Approve / Reject Buttons:
  - Touch-optimiert (min. 44px Höhe)
  - Approve = grün, Reject = rot
  - Confirm-Dialog bei Approve ("Bist du sicher?")
- [ ] Disclaimer: "Dies ist keine Anlageberatung. Alle Investmententscheidungen liegen bei dir."

**States:**
- [ ] Empty State: "Noch keine Analyse durchgeführt. Wähle einen Ticker."
- [ ] Error State: "Analyse fehlgeschlagen: [Grund]. Bitte erneut versuchen."
- [ ] Partial State: "Analyse teilweise abgeschlossen. [Agent-Name] nicht verfügbar."

**Responsiveness:**
- [ ] Desktop: 2-Spalten Layout (Ticker-Input links, Ergebnis rechts)
- [ ] Mobile (375px): 1-Spalte, vertikal gestapelt, scrollbar
- [ ] Approve/Reject Buttons auf Mobile: Full-Width, sticky am unteren Rand

---

#### 13b: Settings-Seite

**Quelle:** @docs/02_policy/settings-spec.md (vollständige Spezifikation)

**Ebene 1 — Einsteiger (Default):**
- [ ] Profil-Card: "Profil: Einsteiger" + kurze Erklärung
- [ ] Keine editierbaren Regler
- [ ] Hinweis: "Du kannst dein Profil in den erweiterten Einstellungen ändern"

**Ebene 2 — Presets:**
- [ ] 3 Preset-Cards nebeneinander (Desktop) / gestapelt (Mobile):
  - Einsteiger (80/20, konservativ)
  - Balanced (70/30, moderat) — empfohlen
  - Aktiv (60/40, höheres Risiko)
- [ ] Vergleichstabelle mit allen 9 Werten (aus settings-spec.md)
- [ ] Info-Panel bei Preset-Wechsel: "Was ändert sich?" + "Risiko steigt/sinkt"
- [ ] Risiko-Indikator (visuell: niedrig/mittel/hoch)
- [ ] Cooldown-Hinweis: "Wechsel aktiv ab [Zeitpunkt]" (24h Cooldown für Mode-Wechsel)

**Ebene 3 — Advanced:**
- [ ] Toggle "Erweiterte Einstellungen" mit Danger-Zone-UI (roter Rahmen)
- [ ] Bestätigungs-Checkbox: "Ich verstehe, dass höhere Aktivität/mehr Satellite Risiko erhöht"
- [ ] 9 Slider mit Microcopy-Tooltips (Texte aus settings-spec.md):

| Regler | Min | Max | Microcopy |
|--------|-----|-----|-----------|
| Core/Satellite | 60/40 | 90/10 | "Mehr Satellite = mehr Schwankung" |
| Max Drawdown | 10% | 30% | "Stoppt alle neuen Trades bei diesem Verlust" |
| Max Single Position | 3% | 10% | "Begrenzt einzelne Aktien im Satellite" |
| Max Sektor | 20% | 40% | "Verhindert Tech-only-Portfolio" |
| Trades/Monat | 2 | 12 | "Mehr Trades = höhere Kosten" |
| Stop-Loss Flag | 5% | 25% | "Warnt ab diesem Verlust" |
| EM Cap | 0% | 25% | "Emerging Markets Limit" |
| Cash-Reserve | 0% | 15% | "Trockenpulver für Kaufgelegenheiten" |
| Rebalancing-Trigger | 2% | 10% | "Ab dieser Drift → Vorschlag" |

- [ ] Inline Validation: grün/rot Feedback sofort beim Schieben
- [ ] Werte die Constraints verletzen: Slider stoppt am Limit + Tooltip-Erklärung
- [ ] "Änderungen speichern" Button → API Call → `policy_change_log` Eintrag

**States:**
- [ ] Loading State: Skeleton-Loader beim Laden der aktuellen Policy
- [ ] Success State: Toast "Einstellungen gespeichert"
- [ ] Error State: Toast "Speichern fehlgeschlagen"

**Responsiveness:**
- [ ] Desktop: Preset-Cards nebeneinander, Slider in 2 Spalten
- [ ] Mobile (375px): Cards gestapelt, Slider full-width

---

#### 13c: Dashboard / Home

- [ ] Portfolio-Übersicht:
  - Gesamtwert (Satellite-Anteil)
  - Positionen-Liste (Ticker, Shares, Aktueller Wert, P&L %, Status)
  - Wenn keine Positionen: "Noch keine Paper-Trades ausgeführt"
- [ ] Letzte Analysen:
  - Ticker, Datum, Recommendation Badge, Confidence
  - Klick → navigiert zur Analyse-Detail-Seite
  - Wenn keine Analysen: "Starte deine erste Analyse"
- [ ] Status-Widgets (Sidebar oder Top-Bar):
  - Verification-Score: % verifizierte Claims (>85% grün, 70-85% gelb, <70% rot)
  - Kill-Switch Status: aktiv/inaktiv + manueller Toggle
  - Kosten MTD: API-Kosten diesen Monat vs. Budget
- [ ] System-Health:
  - Letzte erfolgreiche Analyse (Timestamp)
  - Offene Trade-Vorschläge (Anzahl)

**States:**
- [ ] Empty State: Willkommensmeldung + "Starte mit einer Analyse"
- [ ] Loading State: Skeleton-Loader
- [ ] Kill-Switch aktiv: Banner oben "System pausiert — Kill-Switch aktiv"

**Responsiveness:**
- [ ] Desktop: Grid-Layout (Widgets nebeneinander)
- [ ] Mobile (375px): Vertikal gestapelt, wichtigste Info oben

### Step 14: PWA + Mobile Optimization

**Quelle:** Architektur-Spec v2.1, Sektion 5.3

- [ ] `manifest.json`:
  - App-Name: "MyTrade"
  - Theme-Color, Background-Color
  - Icons (192px, 512px)
  - Display: `standalone`
  - Start-URL: `/dashboard`
- [ ] Service Worker:
  - Offline-Cache für Dashboard-Shell (App Shell Pattern)
  - Cache-Strategy: Network-First für API-Calls, Cache-First für Static Assets
- [ ] Meta-Tags für iOS/Android:
  - `<meta name="apple-mobile-web-app-capable">`
  - `<meta name="apple-mobile-web-app-status-bar-style">`
  - `<link rel="apple-touch-icon">`
- [ ] Touch-Optimierung:
  - Alle interaktiven Elemente min. 44px Höhe
  - Swipe-Gesten vermeiden (Standard-Scroll)
  - Approve/Reject Buttons: Full-Width auf Mobile
- [ ] Push-Notification Infrastruktur:
  - Service Worker registered
  - Push-Subscription-Endpoint vorbereiten (nicht im MVP senden, aber Setup ready)

#### Phase 4 — Definition of Done
- [ ] Login/Signup funktioniert
- [ ] Analyse-Seite: AAPL Analyse starten → Investment Note + Claims + Trade Plan anzeigen
- [ ] Settings-Seite: Preset wechseln → Policy in DB aktualisiert
- [ ] Dashboard: Portfolio + letzte Analysen + Status-Widgets
- [ ] PWA installierbar auf Mobile (manifest.json + Service Worker registriert)
- [ ] Responsive Layout funktioniert auf 375px Viewport
- [ ] Dark Mode Toggle funktioniert
- [ ] Keine API Keys im Frontend-Code (Security Hook prüft)

---

## Phase 5: Monitoring + E2E + Deploy (Step 15)

### Step 15a: Monitoring Dashboard

**Quelle:** @docs/03_architecture/monitoring.md, @docs/08_eval/metrics.md

- [ ] `agent_cost_log` Tracking pro Agent-Call:
  - `agent_name`, `model`, `tier`, `input_tokens`, `output_tokens`, `cost_usd`
  - `fallback_from` (NULL = Default-Modell, sonst Quality-Fallback)
  - `degraded` (true = Budget-Fallback aktiv)
- [ ] Monitoring-Widgets im Dashboard (oder separate Seite):
  - Kosten MTD vs. Budget-Cap (Opus $30, Sonnet $20, Haiku $5, Gesamt $55)
  - Verification-Score (% verifizierte Claims über alle Analysen)
  - Agent-Health: Grün/Gelb/Rot pro Agent (basierend auf Error Rate)
  - Pipeline Error-Rate (Ziel: < 5%)
  - Agent-Latenz (Ziel: < 60s)

### Step 15b: End-to-End Test

**Quelle:** @docs/00_build-brief/brief.md (Definition of Done)

Teste den **vollständigen Flow** mit AAPL:
- [ ] User klickt "Analyze AAPL"
- [ ] Pre-Policy prüft: AAPL erlaubt
- [ ] Data Collector holt Daten von Finnhub → `stock_fundamentals` in DB
- [ ] Fundamental Analyst analysiert → `analysis_runs.fundamental_out` in DB
- [ ] Claim Extractor extrahiert Claims → `claims` in DB (Schema-valid)
- [ ] Verification prüft gegen Alpha Vantage → `verification_results` in DB
- [ ] Full-Policy prüft Sizing
- [ ] Trade Plan generiert → `trade_log` (Status: `proposed`)
- [ ] User klickt "Approve" → Alpaca Paper Order → `trade_log` (Status: `executed`)
- [ ] Alles in Supabase nachvollziehbar (Audit Trail)

**Negativ-Tests:**
- [ ] Pre-Policy blockt verbotenen Ticker (z.B. BTC, TQQQ)
- [ ] Full-Policy blockt zu große Position
- [ ] Verification produziert min. 1 Claim mit Status != `verified`
- [ ] Kill-Switch aktiviert bei simuliertem Drawdown
- [ ] Circuit Breaker stoppt nach 5 API-Failures

### Step 15c: Security Check

- [ ] `/security-check` Skill ausführen
- [ ] Prüfe: keine API Keys in Frontend-Code
- [ ] Prüfe: RLS aktiv auf allen User-Tabellen
- [ ] Prüfe: CORS nur erlaubte Origins
- [ ] Prüfe: `ALPACA_PAPER_MODE=true` Validierung im Code
- [ ] Prüfe: kein `service_role` Key im Frontend
- [ ] Prüfe: `.env` in `.gitignore`

### Step 15d: Deployment

- [ ] Backend auf Railway deployen (EU Region):
  - Environment Variables setzen (alle `.env` Werte)
  - Health-Check konfigurieren (`/health`)
  - Auto-Deploy von `main` Branch
- [ ] Frontend auf Vercel deployen:
  - Environment Variables: `NEXT_PUBLIC_API_URL` (Railway URL)
  - Kein `NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY`
  - Domain konfigurieren
- [ ] CORS im Backend aktualisieren: Vercel-Domain hinzufügen
- [ ] Smoke-Test: Login → Analyse starten → Ergebnis sehen → Approve → Paper Trade

#### Phase 5 — Definition of Done (= MVP Complete)

Die vollständige DoD aus @docs/00_build-brief/brief.md:

- [ ] **End-to-End Run:** AAPL Analyse → Claims → Verification → Policy → Paper Trade → Supabase Log
- [ ] **Policy Engine blockt:** Trade der gegen IPS verstößt wird rejected (nicht nur gewarnt)
- [ ] **Verification funktioniert:** Min. 1 Claim mit Status != `verified`
- [ ] **JSON-Outputs validiert:** Agent-Output matcht `claim-schema.json`
- [ ] **Audit Trail vollständig:** analysis_run, claims, verification, trade_log in Supabase
- [ ] **Security Hook:** Keine API Keys im Frontend
- [ ] **PWA installierbar:** manifest.json + Service Worker
- [ ] **Responsive:** 375px Viewport getestet
- [ ] **Deployed:** Backend auf Railway, Frontend auf Vercel, DB auf Supabase EU

---

## Nach Phase 5: Paper Trading Betrieb

> **Minimum 3 Monate Paper Trading (Stufe 1).** Das System läuft erst 3-6 Monate ausschließlich mit Paper Trading. Erst wenn die Pipeline stabil ist und der User die Outputs sicher interpretieren kann, wird auf Stufe 2 (Human Confirms mit echtem Geld) umgestellt. Das ist nicht optional.

### Gate-Kriterien für Stufe 2
- [ ] Min. 3 Monate Paper Trading
- [ ] Pipeline-Fehlerrate < 5%
- [ ] Verification-Rate > 85%
- [ ] IPS-Compliance: 100%
- [ ] User versteht und kann Outputs interpretieren
- [ ] Security Audit bestanden
- [ ] IBKR Account eröffnet und API konfiguriert
- [ ] **NICHT:** Profitables Paper Trading (marktabhängig, kein Qualitätskriterium)

---

## Phase 2+ Erweiterungen (nach MVP)

Nicht Teil des Vertical Slice, aber geplant:

- [ ] Weitere Agents: Macro, Technical, Sentiment, Risk Manager, Devil's Advocate, Synthesizer
- [ ] Multi-Provider Daten: Finnhub + Alpha Vantage + FRED + SEC EDGAR (vollständig)
- [ ] Vollständiges Verification Tier-System (A/B/C für alle Agents)
- [ ] Portfolio-Monitoring Cron-Job (wöchentlich)
- [ ] Lern-Modus (Opus als Finanz-Professor, `learning_progress` Tabelle)
- [ ] Steuer-Report (AT: KESt 27.5%, W-8BEN) — Overlay
- [ ] Analyse-Archiv mit Performance-Tracking
- [ ] Prompt Caching Optimierung (~15K Token/Analyse Ersparnis)
- [ ] IBKR Integration (Stufe 2)

---

## Referenzen

| Dokument | Relevant für Steps |
|----------|-------------------|
| @docs/00_build-brief/brief.md | DoD, MVP-Scope |
| @docs/00_build-brief/master-prompt.md | Gesamt-Anleitung, 15-Step Zusammenfassung |
| @docs/02_policy/settings-spec.md | Step 8, Step 13b |
| @docs/02_policy/ips-template.yaml | Step 8 |
| @docs/02_policy/asset-universe.md | Step 4, Step 8 |
| @docs/02_policy/austria-tax.md | Phase 2+ (Tax Overlay) |
| @docs/03_architecture/system-overview.md | Step 3, Step 12 |
| @docs/03_architecture/database-schema.md | Step 2 |
| @docs/03_architecture/agents.md | Step 5, Step 6, Step 7 |
| @docs/03_architecture/error-handling.md | Step 10 |
| @docs/03_architecture/monitoring.md | Step 11, Step 15a |
| @docs/03_architecture/workflows.md | Gesamter Flow |
| @docs/04_verification/tier-system.md | Step 7 |
| @docs/04_verification/claim-schema.json | Step 6, Step 7 |
| @docs/05_risk/policy-engine.md | Step 8 |
| @docs/05_risk/execution-contract.md | Step 9 |
| @docs/05_risk/kill-switch.md | Step 11 |
| @docs/06_data/providers.md | Step 4 |
| @docs/07_compliance/decision-support-rules.md | Step 13a (Disclaimer) |
| @docs/08_eval/metrics.md | Step 15a, Gate-Kriterien |
| @docs/09_broker/broker-router.md | Step 9 |
| @docs/09_broker/security.md | Step 3, Step 15c |
