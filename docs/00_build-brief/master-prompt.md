# MyTrade — Initial Master Prompt für Claude Code (v4)

Kopiere alles unterhalb dieser Linie in Claude Code:

---

## Wer ich bin
Ich bin Arwin, 33, Österreicher, Solo-Founder und Entwickler. Ich baue "MyTrade" — ein AI-gestütztes Investment-Analyse-System für mich als Langfrist-Investor. Ich bin kein professioneller Entwickler sondern nutze AI-gestütztes "Vibe-Coding". Ich brauche klare Erklärungen bei Architektur-Entscheidungen und bevorzuge es, wenn du selbstständig arbeitest und mir fertige, lauffähige Ergebnisse lieferst statt Optionen aufzuzählen.

## Was wir bauen
Ein **Multi-Agent AI Investment System** das:
1. Aktien-Daten aus APIs holt (Finnhub, Alpha Vantage, SEC EDGAR)
2. Ein Claude Opus Agent die Daten analysiert (Fundamental Analysis)
3. Numerische Claims strukturiert extrahiert und gegen eine 2. Quelle geprüft werden (Verification Layer)
4. Alles gegen mein Investment Policy Statement validiert wird (Policy Engine — deterministisches Python, kein LLM)
5. Einen Trade Plan generiert (buy/sell/hold mit Begründung)
6. Den Trade im Paper-Modus ausführt (Alpaca Paper API)
7. Alles in Supabase loggt (Audit Trail)

**Aktuell: Stufe 1 (Paper Trading)** — es darf KEIN echtes Geld bewegt werden.

## Mein Portfolio-Setup
- **70% Core:** VWCE + CSPX ETFs auf Flatex.at (Sparplan, AUSSERHALB dieses Systems)
- **30% Satellite:** System-managed, US Large Cap Aktien + ETFs
- Steuer: Österreich, KESt 27.5% (Tax-Logik im MVP nur als optionales/estimiertes Overlay kennzeichnen; exakte Steuerengine später.)

## Dein Repo — Lies bitte JETZT diese Dateien

### Pflichtlektüre (in dieser Reihenfolge)
1. **CLAUDE.md** — Deine Hauptreferenz. Tech Stack, Commands, Critical Rules, MCP Usage Rules.
2. **docs/00_build-brief/brief.md** — Ziel, Nicht-Ziele, Definition of Done, MVP-Scope pro Komponente.
3. **docs/02_policy/ips-template.yaml** — Machine-readable Investment Policy Statement. Fallback/Defaults. Die Policy Engine liest primär aus der DB (`user_policy` Tabelle). Enthält 15 kodierte Investmententscheidungen (70/30 Split, 5% max Position, 30% Sektor-Cap, 20% Drawdown Kill-Switch, 10 Trades/Monat, 15% Soft-Stop-Loss, verbotene Instrumente, etc.)
4. **docs/02_policy/settings-spec.md** — 3-Ebenen Settings System (Einsteiger/Presets/Advanced). Presets, Constraints, Datenmodell (`user_policy` + `policy_change_log`), Cooldown-Regel, Microcopy. Policy Engine liest die "effective policy" aus DB.
5. **docs/05_risk/execution-contract.md** — Was das System in Stufe 0/1/2/3 darf und was nicht. Stufe 1 = Paper Trading only. Kill-Switch Regeln.
6. **docs/04_verification/claim-schema.json** — JSON Schema für VerifiedClaim. Agent-Outputs (Claims) müssen diesem Schema entsprechen. Tier A/B/C Klassifikation.

### Weitere SSOT-Dokumente (lies nach Bedarf)
- **docs/01_vision/zielbild.md**
- **docs/02_policy/asset-universe.md** — MVP-Startuniversum: AAPL, MSFT, JNJ, JPM, PG, VOO, VWO
- **docs/02_policy/austria-tax.md**
- **docs/04_verification/tier-system.md**
- **docs/05_risk/policy-engine.md**
- **docs/05_risk/kill-switch.md**
- **docs/06_data/providers.md**
- **docs/07_compliance/decision-support-rules.md**
- **docs/08_eval/metrics.md**
- **docs/09_broker/broker-router.md**
- **docs/09_broker/security.md**
- **docs/03_architecture/system-overview.md** — Vollständige Architektur-Spec (40 Seiten, 16 Sektionen)

### Deine Subagents (.claude/agents/)
Du hast 5 spezialisierte Subagents zur Verfügung:
- **backend-dev** (Opus) — FastAPI, Agno Agents, Policy Engine, Verification Layer, Broker Adapter
- **frontend-dev** (Sonnet) — Next.js, React, shadcn/ui. Hat Zugriff auf shadcn MCP, Context7 MCP, Figma MCP
- **db-architect** (Sonnet) — Supabase Schema, Migrations, RLS Policies
- **security-reviewer** (Opus) — Security Audit für API Keys, RLS, CORS, Secrets
- **test-writer** (Sonnet) — Tests für Policy Engine, Verification Layer, Execution Rules

### Deine Skills (.claude/skills/)
- **/frontend-design** — Premium fintech aesthetic, Verification-Status-Farben (grün/gelb/rot), shadcn-first. Kein generischer AI-Look.
- **/new-agno-agent** — Template + Checklist zum Erstellen neuer Agno Agents inkl. Claim-Output
- **/db-migrate** — Erstellt Supabase Migrations mit Timestamp, RLS, Indexes
- **/security-check** — Security Audit: API Keys in Frontend? RLS aktiv? CORS korrekt?

### MCP Server (.mcp.json — automatisch verbunden)
- **shadcn** — Component Registry. IMMER zuerst checken ob ein Component existiert.
- **Context7** — Live-Docs für Next.js, Supabase, Tailwind, Agno. Append `use context7`.
- **Figma** — Bidirektionaler Design ↔ Code Sync.

### Hooks (.claude/settings.json)
- **PostToolUse Hook:** Nach jedem File-Write wird automatisch geprüft ob API Keys im Frontend gelandet sind.
- **Permissions:** .env Dateien sind vom Lesen ausgeschlossen.

## Dein Auftrag: Vertical Slice MVP

Baue einen **Vertical Slice MVP** — ein einziger End-to-End-Flow:

```
User klickt "Analyze AAPL"
  → Pre-Policy prüft: Instrument erlaubt? (spart Opus-Tokens wenn verboten)
    → Finnhub API holt Daten
      → Opus Agent analysiert
        → Claims werden extrahiert (claim-schema.json)
          → Verification Layer prüft gegen 2. Quelle (Tier-System)
            → Full-Policy validiert Sizing/Exposure auf verifizierten Zahlen
              → Trade Plan wird generiert
                → Alpaca Paper API führt Paper Order aus
                  → Alles geloggt in Supabase
```

**Alles minimal, aber alles verbunden.**

## Policy & Verification Reihenfolge (wichtig, um Scope zu halten)

### Policy Engine (deterministisch, kein LLM)
- **Pre-Policy (vor Agent Call):** blocke sofort, wenn Instrument/Typ/Region laut Asset Universe verboten ist oder der Run generell nicht erlaubt ist.
- **Full-Policy (nach Analyse, vor Execution):** prüfe Positionsgröße, Sektor-Cap, Trades/Monat, Cash-Reserve, Drawdown/Kill-Switch, etc. und blocke Execution, wenn Regeln verletzt sind.

### Verification Layer
- **Trade-entscheidende numerische Claims** müssen mindestens den im Claim geforderten `required_tier` erreichen (Tier A oder A+B je nach Claim/Regel).
- **UI darf Claims anzeigen, die unverified/manual_check sind**, aber immer mit klarer Ampel-Markierung und ohne sie als harte Grundlage für eine Execution zu verwenden.

## Wie du vorgehen sollst

### Phase 1: Foundation (Steps 1-5)
1. **Docs lesen:** Lies ZUERST die 6 Pflichtdokumente oben. Verstehe den vollständigen Flow.
2. **Agno recherchieren:** Nutze einen Subagent um Agno's aktuelle API-Patterns zu recherchieren (`use context7`). Prüfe: Agent-Erstellung, coordinate-Mode, Tool-Integration, PostgreSQL-Storage.
3. **Supabase + Auth + DB:** Erstelle das Supabase-Projekt (EU Region). Konfiguriere Supabase Auth (Email/Password für MVP). Erstelle alle DB-Tabellen inkl. `user_policy` + `policy_change_log` (siehe settings-spec.md) + RLS Policies. Auth MUSS vor den Tabellen stehen, weil RLS `auth.uid()` braucht.
4. **Backend-Scaffold:** Erstelle das FastAPI Backend mit Supabase Connection, CORS-Konfiguration (nur Vercel-Domain + localhost), Auth Middleware (JWT-Validierung), und API Rate Limiting (100 req/min/user). Siehe: docs/09_broker/security.md.
5. **Data Collector:** Implementiere den Data Collector (deterministisch, kein LLM): Finnhub API-Integration mit Rate Limiting (max. 55 calls/min), Exponential Backoff (2s→4s→8s, 3 Retries), Queue-System. Daten schreiben in `stock_fundamentals`, `stock_prices`, `macro_indicators`. Siehe: docs/06_data/providers.md.

### Phase 2: Agents + Verification (Steps 6-8)
6. **Fundamental Analyst Agent:** Implementiere den ersten Agno Agent (Fundamental Analyst, Sonnet 4.6). System-Prompt aus docs/03_architecture/agents.md. Input: `stock_fundamentals`. Output: strukturiertes JSON mit `{value, source, timestamp}` für jede Zahl.
7. **Claim Extractor + Schema Validation:** Implementiere den Claim Extractor (Haiku 4.5) als separaten Agent. Extrahiert numerische Claims aus Agent-Output gemäß `claim-schema.json`. Automatischer Schema-Test (JSON Schema Validation). Fallback: Schema-Fail → 1x Retry Haiku → Sonnet Fallback.
8. **Verification Layer:** Baue den Verification Layer: Cross-Check Claims gegen 2. Quelle (Alpha Vantage / SEC EDGAR). Status-Logik: ≤2% → `verified`, ≤5% → `consistent`, >5% → `disputed`, keine 2. Quelle → `unverified`. Ergebnisse in `verification_results` Tabelle. Siehe: docs/04_verification/tier-system.md.

### Phase 3: Policy + Execution (Steps 9-11)
9. **Policy Engine:** Implementiere `get_effective_policy()` die aus DB liest (Fallback: `ips-template.yaml`). Implementiere **Pre-Policy** (Universe/Verbote — blockt VOR Agent-Call) und **Full-Policy** (Sizing/Exposure — prüft NACH Verification auf verifizierten Zahlen). Deterministisches Python, KEIN LLM. Siehe: docs/05_risk/policy-engine.md.
10. **Alpaca Paper API:** Verbinde Alpaca Paper API (Paper only). Implementiere den Broker-Adapter (abstraktes Interface für später IBKR). Prüfe `ALPACA_PAPER_MODE=true` vor jedem Call. Trade-Vorschläge in `trade_log` loggen. Siehe: docs/09_broker/broker-router.md.
11. **Error Handling:** Implementiere Circuit Breaker Pattern (5 Failures → 60s Pause), JSON Repair (json_repair Library), Partial Results (System läuft weiter wenn 1 Agent fehlschlägt, Confidence reduziert). Fehler in `error_log` loggen. Siehe: docs/03_architecture/error-handling.md.

### Phase 4: Frontend + Mobile (Steps 12-13)
12. **Frontend:** Baue das Frontend mit Next.js + Tailwind + shadcn/ui. Nutze `/frontend-design` Skill für Premium-Aesthetic. **Responsive/Mobile-First Layout** (funktioniert auf 375px Viewport). Zwei Seiten:
    - **Analyse-Seite:** "Analyze [Ticker]" Button → Ergebnis mit Investment Note + Claim-Ampel (grün/gelb/rot) + Trade-Plan
    - **Settings-Seite:** 3 Ebenen (Einsteiger/Presets/Advanced mit Microcopy-Tooltips)
    - Touch-optimierte Approve/Reject Buttons für Mobile
13. **PWA Setup:** Konfiguriere Progressive Web App: `manifest.json` (App-Name, Icons, Theme-Color), Service Worker (Offline-Cache für Dashboard), Meta-Tags für iOS/Android Homescreen-Installation. Push-Notification Infrastruktur vorbereiten (nicht implementieren im MVP, aber Setup ready). Siehe: Architektur-Spec v2.1, Sektion 5.3.

### Phase 5: Monitoring + E2E (Steps 14-15)
14. **Monitoring:** Implementiere `agent_cost_log` Tracking (Tokens, Kosten, Latenz pro Agent-Call). Budget-Caps aus docs/03_architecture/monitoring.md (Opus $30/Monat, Sonnet $20/Monat, Haiku $5/Monat). Budget-Fallback: Opus→Sonnet bei 100% Cap. Einfache Monitoring-Anzeige im Dashboard (Kosten MTD, Verification-Score, Agent-Health).
15. **E2E Test + Security:** Teste den vollständigen Flow: "Analyze AAPL" → Claims → Verification → Policy → Paper Trade → Supabase Log. Führe `/security-check` Skill aus. Prüfe: keine API Keys im Frontend, RLS aktiv, CORS korrekt.

## Definition of Done (DoD)
- [ ] End-to-End Run funktioniert (AAPL Analyse → Paper Order → Supabase Log)
- [ ] Policy Engine blockt einen IPS-Verstoß (reject + logged), nicht nur warnen
- [ ] Verification erzeugt mind. 1 Claim mit Status != verified (z.B. unverified/manual_check/disputed) ODER erkennt disputed falls Abweichung > Threshold
- [ ] Agent-Output matcht `claim-schema.json` (automatischer Schema-Test)
- [ ] Audit Trail vollständig in Supabase (analysis_run, claims, verification, trade_log)
- [ ] Security Hook findet keine API Keys im Frontend
- [ ] PWA installierbar auf Mobile (manifest.json + Service Worker registriert)
- [ ] Responsive Layout funktioniert auf Mobile (375px Viewport getestet)

## Kritische Regeln
- NIEMALS echte Broker-Orders erstellen (Stufe 1 = Paper only)
- NIEMALS API Keys im Frontend
- Policy Engine = deterministisches Python, KEIN LLM
- Trade-entscheidende Claims müssen verifiziert sein (Tier-Regeln), bevor Execution erlaubt ist
- Im Frontend zeigen alle Zahlen/Claims ihren Verification-Status (grün/gelb/rot)
- KESt 27.5%: im MVP nur als optionales/estimiertes Overlay kennzeichnen (keine steuerliche Voll-Engine im Vertical Slice)

## Start
Beginne mit Phase 1, Step 1. Arbeite die 5 Phasen (15 Steps) sequenziell ab. Jeder Step sollte lauffähig sein bevor du zum nächsten gehst. Frage mich, wenn etwas unklar ist.
