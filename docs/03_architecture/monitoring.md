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

## Budget-Caps und Fallback (3-Tier)

### Monatliche Budget-Limits pro Tier

| Tier | Modell | Typisch | Soft Cap (80%) | Hard Cap (100%) | Bei Hard Cap |
|------|--------|---------|---------------|----------------|-------------|
| Heavy | Opus 4.6 | ~$15/Mo | $24 → Warning | $30 → Degradiert | → Sonnet |
| Standard | Sonnet 4.6 | ~$10/Mo | $16 → Warning | $20 → Degradiert | → Haiku |
| Light | Haiku 4.5 | ~$3/Mo | $4 → Warning | $5 → System-Pause | User informieren |
| **Gesamt API** | | **~$28/Mo** | **$44** | **$55 Hard Cap** | Kill-Switch prüfen |

### Degradierungs-Logik

```
Opus Budget 80% erreicht:
  → Dashboard Warning: "Opus-Budget bei 80%, X Analysen verbleibend"
  → Kein automatischer Eingriff

Opus Budget 100% erreicht:
  → Devil's Advocate + Synthesizer degradieren zu Sonnet
  → Qualitätshinweis im Dashboard: "⚠️ Analyse läuft mit reduzierter Tiefe"

Sonnet Budget 100% erreicht:
  → Analyse-Agents degradieren zu Haiku
  → Warnung: "⚠️ Nur Light-Analyse verfügbar"

Gesamt-API Hard Cap erreicht:
  → Keine weiteren LLM-Calls bis Monatsende
  → Portfolio-Monitoring läuft weiter (deterministisch, kein LLM)
  → User erhält E-Mail
```

### Kosten-Schätzung (Phase 2: 20 Analysen/Monat, alle Agents)

| Posten | Geschätzt | Anmerkung |
|--------|----------|-----------|
| Opus API (Devil's Advocate + Synthesizer) | $8-12 | 2 Calls × 20 Analysen |
| Sonnet API (5 Analyse-Agents) | $8-14 | 5 Calls × 20 Analysen |
| Haiku API (Extraction + Verification) | $1-3 | 2 Calls × 20 Analysen |
| Prompt Caching Ersparnis | -$3 bis -$5 | ~15K cached Tokens/Analyse |
| **Netto API-Kosten** | **$14-24/Monat** | |
| Hosting (Vercel + Supabase Free) | $0 | Free Tier reicht |
| Datenprovider (Finnhub + AV) | $0 | Free Tier reicht |
| **GESAMT Betrieb** | **~$14-24/Monat** | |

> **Wichtig:** Diese Zahlen sind Schätzungen. Nach 1 Woche Betrieb liefert `agent_cost_log` echte Telemetrie. Dann werden Budget-Caps angepasst.

### Telemetrie-basierte Optimierung

Nach 1 Woche Betrieb prüfen:
1. **Welche Agents verbrauchen am meisten?** → Token-Budget anpassen oder Effort-Parameter senken
2. **Wie oft triggered der Quality-Fallback?** → Wenn Haiku >10% Schema-Fails hat → Haiku-Prompt optimieren oder auf Sonnet wechseln
3. **Cache Hit Rate?** → Unter 60% → System-Prompts konsolidieren
4. **Opus vs Sonnet Qualitätsunterschied?** → Wenn kaum messbar → Opus-Agents zu Sonnet degradieren (permanente Kostensenkung)

---

## Referenzen
- Eval-Metriken: @docs/08_eval/metrics.md
- Error Handling: @docs/03_architecture/error-handling.md
- Kill-Switch: @docs/05_risk/kill-switch.md
