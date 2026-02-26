# MyTrade — Initial Master Prompt für Claude Code (v3, final)

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
1. Lies ZUERST die 6 Pflichtdokumente oben.
2. Nutze einen Subagent um Agno's aktuelle API-Patterns zu recherchieren (`use context7`).
3. Erstelle das Backend-Scaffold (FastAPI + Supabase Connection).
4. Erstelle die DB-Tabellen inkl. `user_policy` + `policy_change_log` (siehe settings-spec.md).
5. Implementiere den ersten Agno Agent (Fundamental Analyst, minimal).
6. Implementiere `get_effective_policy()` die aus DB liest (Fallback: YAML).
7. Implementiere **Pre-Policy** (Universe/Verbote) und **Full-Policy** (Sizing/Exposure).
8. Baue den Verification Layer, der `claim-schema.json` strikt erfüllt (Schema Validation in Tests).
9. Verbinde Alpaca Paper API (Paper only).
10. Baue das Frontend: Analyse-Seite (Button + Ergebnis mit Claim-Ampel) + Settings-Seite (3 Ebenen: Einsteiger/Presets/Advanced mit Microcopy).
11. Teste End-to-End.

## Definition of Done (DoD)
- [ ] End-to-End Run funktioniert (AAPL Analyse → Paper Order → Supabase Log)
- [ ] Policy Engine blockt einen IPS-Verstoß (reject + logged), nicht nur warnen
- [ ] Verification erzeugt mind. 1 Claim mit Status != verified (z.B. unverified/manual_check/disputed) ODER erkennt disputed falls Abweichung > Threshold
- [ ] Agent-Output matcht `claim-schema.json` (automatischer Schema-Test)
- [ ] Audit Trail vollständig in Supabase (analysis_run, claims, verification, trade_log)
- [ ] Security Hook findet keine API Keys im Frontend

## Kritische Regeln
- NIEMALS echte Broker-Orders erstellen (Stufe 1 = Paper only)
- NIEMALS API Keys im Frontend
- Policy Engine = deterministisches Python, KEIN LLM
- Trade-entscheidende Claims müssen verifiziert sein (Tier-Regeln), bevor Execution erlaubt ist
- Im Frontend zeigen alle Zahlen/Claims ihren Verification-Status (grün/gelb/rot)
- KESt 27.5%: im MVP nur als optionales/estimiertes Overlay kennzeichnen (keine steuerliche Voll-Engine im Vertical Slice)

## Start
Beginne damit, die 6 Pflichtdokumente zu lesen, und erstelle dann einen kurzen Implementierungsplan (max 15 Bulletpoints) bevor du Code schreibst. Frage mich, wenn etwas unklar ist.
