# Workflows — MyTrade

> **Quelle:** Architektur-Spezifikation v2.1, Sektion 13

---

## Workflow A: Aktien-Analyse (On-Demand)

**Trigger:** User gibt Ticker ein.
**Gesamtdauer:** ~2-5 Minuten.

1. **Data Collector** holt Fundamentaldaten, Kurse, News, Insider-Trades, Makrodaten (parallel)
2. **Pre-Policy:** Ist die Aktie überhaupt IPS-konform? Blockt verbotene Instrumente/Typen/Regionen → spart Opus-Tokens
3. **Macro Analyst** bewertet Sektor-Kontext
4. **Fundamental, Technical, Sentiment Analyst** laufen PARALLEL (Agno async)
5. **Verification Layer** prüft alle numerischen Claims gegen zweite Quellen
6. **Full-Policy:** Prüft Sizing/Exposure auf Basis **verifizierter** Zahlen → blockt wenn IPS verletzt
7. **Risk Manager** erhält verifizierte + policy-geprüfte Outputs + Portfolio-State
8. **Devil's Advocate** greift die These an
9. **Portfolio Synthesizer** erstellt Investment Note + Trade Plan
10. **Frontend** zeigt Note mit Approve/Reject (bei Stufe 2) oder nur Dokument (Stufe 0-1)

---

## Workflow B: Portfolio-Monitoring (Scheduled)

**Trigger:** Cron-Job alle 7 Tage (konfigurierbar).

1. Data Collector aktualisiert alle Holdings-Daten
2. Für jede Position: Mini-Analyse (Sonnet) — These noch intakt?
3. Risk Manager: IPS-Compliance, Concentration, Drawdown-Check
4. Rebalancing-Check: Gewichtungen > 5% Abweichung von Ziel?
5. Alert-Report im Dashboard

---

## Workflow C: IPS-Setup (Settings System)

**Trigger:** Erster Login oder quartalsweises Review.

1. Neuer User startet mit **Einsteiger-Preset** (80/20, konservativ)
2. Settings-Page zeigt 3 Ebenen: Einsteiger → Presets → Advanced
3. Preset-Wechsel zeigt Info-Panel "Was ändert sich?" + Risiko-Indikator
4. Advanced-Mode: Einzelregler mit Microcopy-Tooltips, innerhalb Constraints
5. Mode-Wechsel hat 24h Cooldown (Panik-Schutz)
6. Jede Änderung wird in `policy_change_log` geloggt
7. Policy Engine liest immer die "effective policy" aus `user_policy`

> Siehe @docs/02_policy/settings-spec.md für vollständige Spezifikation.

---

## Workflow D: Lern-Modus

1. Opus als Finanz-Professor: Konzepte, Quiz, Feedback
2. Reale Daten: "Erkläre das KGV von Apple mit aktuellen Zahlen"
3. Paper-Trading-Challenges mit Fortschritts-Tracking (`learning_progress`)

---

## Workflow E: Steuer-Optimierung (Österreich)

1. Realisierte/unrealisierte Gewinne berechnen
2. Tax-Loss-Harvesting-Möglichkeiten identifizieren
3. KESt-Prognose (27,5%) + Quellensteuer (W-8BEN)
4. OeKB-Meldefonds-Status prüfen

---

## Guide-Mapping

Alle 10 Teile des konsolidierten Trading-Guides sind in der Architektur abgebildet:

| Teil | Implementierung |
|------|----------------|
| Teil 1 (Psychologie) | Devil's Advocate + Policy Engine + Red Teaming |
| Teil 2 (Mathematik) | Fundamental + Technical Analyst + Lern-Modus |
| Teil 3 (Risiko) | Risk Manager + Position Sizing + Stop-Loss |
| Teil 4 (Märkte) | Macro Analyst + Steuer-Agent + UCITS-DB |
| Teil 5 (Opus) | Alle Agenten mit spezialisierten Prompts |
| Teil 6 (Tools) | Data Collector + Verification Layer |
| Teil 7 (Fahrplan) | IPS-Setup + Workflows |
| Teil 8 (Architektur) | System-Übersicht + dieses Dokument |
| Teil 9 (Vergleich) | Multi-LLM (Opus + Sonnet) |
| Teil 10 (Ressourcen) | Alle APIs integriert |

---

## Referenzen
- Agent-Spezifikationen: @docs/03_architecture/agents.md
- Policy Engine: @docs/05_risk/policy-engine.md
- Execution Contract: @docs/05_risk/execution-contract.md
