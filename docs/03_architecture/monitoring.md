# Monitoring und Observability — MyTrade

> **Quelle:** Architektur-Spezifikation v2.1, Sektion 12

---

## Agent-Performance-Tracking

Jeder Agent-Call wird in `agent_cost_log` geloggt:

| Metrik | Zweck | Alert-Schwelle |
|--------|-------|---------------|
| Tokens (Input + Output) | Kosten-Kontrolle | > 50K Token für einzelnen Call |
| Latenz (ms) | Performance | > 60s für einen Agent |
| Verification-Rate | Halluzination-Monitoring | < 80% verified Datenpunkte |
| Cost per Analysis | Budget-Kontrolle | > $5 für eine Analyse |
| Error Rate | Zuverlässigkeit | > 10% fehlgeschlagene Calls pro Tag |

---

## Dashboard-Metriken (Frontend)

- Gesamtkosten MTD (Month-to-Date) für API-Calls
- Anzahl durchgeführter Analysen diese Woche
- Verification-Score: % der verifizierten Datenpunkte
- Agent-Health: Grün/Gelb/Rot pro Agent (basierend auf Error Rate)
- Portfolio-Performance vs. Benchmark (z.B. VWCE)

---

## Alerting

**Push-Notification bei:**
- Analyse fertig
- Trade-Vorschlag
- Rebalancing-Bedarf
- Risiko-Warning

**E-Mail bei:**
- Agent-Fehler
- Broker-Disconnect
- Kosten-Überschreitung
- Kill-Switch aktiviert

---

## Budget-Caps und Fallback

| Posten | Typical | Budget-Cap |
|--------|---------|-----------|
| Anthropic Opus | $50/Monat (15 Analysen) | $100/Monat |
| Anthropic Sonnet | $10/Monat | $20/Monat |
| Hosting (Vercel + Railway) | $15/Monat | $50/Monat |
| **GESAMT** | **~$75/Monat** | **$170/Monat Hard Cap** |

Wenn das Monatsbudget für Opus erreicht ist, schaltet das System auf Sonnet um (geringere Qualität, aber Kostenschutz). Das Monitoring-Dashboard zeigt Kosten-Verbrauch in Echtzeit.

---

## Referenzen
- Eval-Metriken: @docs/08_eval/metrics.md
- Error Handling: @docs/03_architecture/error-handling.md
- Kill-Switch: @docs/05_risk/kill-switch.md
