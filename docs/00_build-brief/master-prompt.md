# MyTrade — Master Prompt für Claude Code (v5)

---

## Wer ich bin

Ich bin der Entwickler dieses Investment-Analyse-Systems — ein AI-gestütztes Tool für Langfrist-Investoren. Arbeite selbstständig und liefere fertige, lauffähige Ergebnisse statt Optionen aufzuzählen. Erkläre Architektur-Entscheidungen kurz und klar.

## Was wir bauen

Ein Vertical Slice MVP mit diesem End-to-End Flow:

```
User klickt "Analyze AAPL"
  → Pre-Policy prüft: Instrument erlaubt? (spart LLM-Tokens wenn verboten)
    → Finnhub API holt Daten
      → Sonnet Agent analysiert (Fundamental Analysis)
        → Haiku extrahiert Claims (claim-schema.json)
          → Verification Layer prüft gegen 2. Quelle
            → Full-Policy validiert Sizing/Exposure auf verifizierten Zahlen
              → Trade Plan wird generiert
                → Alpaca Paper API führt Paper Order aus
                  → Alles geloggt in Supabase
```

**Aktuell: Stufe 1 (Paper Trading)** — KEIN echtes Geld. Kein Live-Broker.

**Portfolio:** 70% Core (VWCE+CSPX auf Flatex.at, AUSSERHALB des Systems) / 30% Satellite (system-managed).

---

## Dein Repo — Lies JETZT diese Dateien

### Pflichtlektüre (in dieser Reihenfolge)

1. **CLAUDE.md** — Tech Stack, Commands, Critical Rules, MCP Usage, Subagents, Skills. Deine Hauptreferenz.
2. **docs/00_build-brief/brief.md** — Ziel, Nicht-Ziele, Definition of Done, MVP-Scope.
3. **docs/03_architecture/sprint-roadmap.md** — **SSOT für die Implementierung.** 5 Phasen, 15 Steps mit Checkbox-Subtasks und DoD pro Phase. Arbeite diese ab.
4. **docs/02_policy/ips-template.yaml** — Machine-readable IPS. Fallback/Defaults für die Policy Engine.
5. **docs/02_policy/settings-spec.md** — 3-Tier Settings (Einsteiger/Presets/Advanced), Datenmodell, Cooldown-Regel.
6. **docs/05_risk/execution-contract.md** — Was das System pro Stufe darf. Stufe 1 = Paper only.
7. **docs/04_verification/claim-schema.json** — JSON Schema für Claims. Agent-Outputs müssen diesem Schema entsprechen.

### Weitere Docs (lies nach Bedarf pro Step)

Die sprint-roadmap.md verweist bei jedem Step auf die relevanten Docs. Lies sie wenn du den Step bearbeitest. Vollständige Liste am Ende der sprint-roadmap.md (Referenztabelle: 22 Docs → Steps).

---

## Zwei Regeln die den ganzen Flow bestimmen

### Policy Engine (deterministisch, kein LLM)
- **Pre-Policy (VOR Agent-Call):** Blockt sofort wenn Instrument/Typ/Region verboten oder Kill-Switch aktiv. Spart LLM-Tokens.
- **Full-Policy (NACH Verification, VOR Execution):** Prüft Sizing, Sektor-Cap, Trades/Monat, Cash-Reserve, Drawdown auf **verifizierten** Zahlen. Blockt Execution wenn Regeln verletzt.

### Verification Layer
- Trade-entscheidende Claims müssen ihren `required_tier` erreichen (Tier A oder A+B).
- UI darf unverified/manual_check Claims anzeigen — aber mit Ampel-Badge (grün/gelb/rot) und ohne sie als Execution-Grundlage zu nutzen.

---

## Dein Auftrag

**Arbeite die sprint-roadmap.md ab.** Sie ist die SSOT — dort stehen alle Sub-Tasks, Quellen-Verweise und DoD pro Phase.

### Fortschritt tracken

**Nach jeder erledigten Checkbox:** Markiere die Task in `docs/03_architecture/sprint-roadmap.md` als erledigt (`- [x]`). Committe die Änderung zusammen mit dem zugehörigen Code. So weiß die nächste Session exakt wo sie weitermachen soll.

### Phasen-Übersicht (Details in sprint-roadmap.md)

| Phase | Steps | Inhalt |
|-------|-------|--------|
| 1: Foundation | 1-5 | Docs lesen, Supabase + Auth + 12 Tabellen, Backend-Scaffold, Data Collector, Fundamental Analyst |
| 2: Verification | 6-8 | Claim Extractor, Verification Layer, Policy Engine + Unit Tests |
| 3: Execution | 9-11 | Alpaca Paper API, Error Handling + Circuit Breaker, Kill-Switch + Budget-Fallback |
| 4: Frontend | 12-14 | Next.js + Auth + Layout, 3 Screens (Analyse/Settings/Dashboard), PWA + Mobile |
| 5: Deploy | 15 | Monitoring, E2E Test, Security Check, Railway + Vercel Deployment |

---

## Definition of Done (MVP Complete)

Aus `docs/00_build-brief/brief.md`:

- [ ] End-to-End Run: AAPL Analyse → Claims → Verification → Policy → Paper Trade → Supabase Log
- [ ] Policy Engine blockt IPS-Verstoß (reject + logged, nicht nur warnen)
- [ ] Verification: Min. 1 Claim mit Status != `verified`
- [ ] Agent-Output matcht `claim-schema.json` (Schema-Test)
- [ ] Audit Trail vollständig in Supabase
- [ ] Keine API Keys im Frontend
- [ ] PWA installierbar (manifest.json + Service Worker)
- [ ] Responsive auf 375px Viewport
- [ ] Deployed: Railway (Backend) + Vercel (Frontend) + Supabase EU

---

## Kritische Regeln

- NIEMALS echte Broker-Orders (Stufe 1 = Paper only, `ALPACA_PAPER_MODE=true`)
- NIEMALS API Keys im Frontend oder `NEXT_PUBLIC_*`
- Policy Engine = deterministisches Python, KEIN LLM
- Disputed trade-critical Claims blocken den Trade Plan
- Alle Zahlen im Frontend zeigen Verification-Status (grün/gelb/rot)
- RLS auf allen User-Tabellen, service_role nur im Backend
- KESt 27.5%: im MVP nur als Overlay kennzeichnen (keine Steuer-Engine)
- Im Zweifel: Flag für Human Review — nie annehmen

## Start

Beginne mit Phase 1, Step 1 in der sprint-roadmap.md. Arbeite sequenziell. Jeder Step lauffähig bevor du weitergehst. Hake erledigte Tasks ab. Frage mich wenn etwas unklar ist.
