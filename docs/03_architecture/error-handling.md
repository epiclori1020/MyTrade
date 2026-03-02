# Error Handling und Retry-Logik — MyTrade

> **Quelle:** Architektur-Spezifikation v2.1, Sektion 10

---

## Grundsatz

Fehler sind in einem Multi-Agent-System nicht die Ausnahme, sondern der Normalfall. Jede Komponente muss unabhängig fehlschlagen können, ohne das Gesamtsystem zu blockieren.

---

## Error-Strategie pro Komponente

| Komponente | Fehler-Typ | Strategie |
|-----------|------------|-----------|
| Data Collector | API Rate Limit (429) | Exponential Backoff: 2s → 4s → 8s. Max. 3 Retries. Danach: Fallback-Quelle. Wenn beide down: Cache + Warning |
| Data Collector | API Down (500/503) | Fallback-Quelle sofort. Finnhub down → Alpha Vantage. Beide down → Cache + Warning |
| LLM Agent | Anthropic API Timeout | Retry 1x mit 30s Timeout. Danach: `partial_result` mit Outputs der bereits fertigen Agenten. User-Notification |
| LLM Agent | Malformed JSON Output | Retry 1x mit verschärftem Prompt. Danach: JSON-Repair-Versuch (`json_repair` Library). Danach: Fehler loggen, Agent überspringen [^1] |
| LLM Agent | Halluzination erkannt | Verification Layer flaggt. Datenpunkt wird als DISPUTED markiert. Confidence -10 Punkte |
| Broker API | Order Rejected | Fehler-Grund loggen. User-Notification mit Erklärung. Kein automatischer Retry für Orders |
| Broker API | Connection Lost | 3 Reconnect-Versuche à 5s. Danach: Kill-Switch aktivieren. User-Alert via Push |
| Supabase | Write Failure | Retry 3x. Danach: In-Memory-Queue. Hintergrund-Worker leert Queue bei Reconnect |

---

## Circuit Breaker Pattern

Wenn ein Service **5x hintereinander** fehlschlägt, wird der Circuit Breaker aktiviert:

1. **Open:** Keine weiteren Calls für 60 Sekunden
2. **Half-Open:** 1 Probe-Call nach 60s
3. **Closed:** Erfolgreich → normaler Betrieb
4. **Open (erweitert):** Fehlerhaft → weitere 120s warten

Das verhindert kaskadierendes Versagen und schützt API-Budgets.

---

## Partial Results

Wenn ein Agent fehlschlägt, läuft die Analyse trotzdem weiter:
- `analysis_runs.status` wird auf `partial` gesetzt
- Vorhandene Agent-Outputs werden normal verarbeitet
- Fehlender Agent wird in `error_log` dokumentiert
- Frontend zeigt Warning: "Analyse unvollständig — [Agent-Name] nicht verfügbar"
- Confidence-Score wird automatisch reduziert

---

---

[^1]: **Implementierung (Step 10):** JSON Repair wird VOR dem Retry versucht (nicht danach wie hier beschrieben). Begründung: Repair ist kostenlos (lokal), Retry kostet Token. Wenn Repair gelingt, wird ein LLM-Call gespart. Reihenfolge: `messages.parse()` → JSON Repair → Retry mit verschärftem Prompt → JSON Repair auf Retry → AgentError.

## Referenzen
- Kill-Switch: @docs/05_risk/kill-switch.md
- Agent-Spezifikationen: @docs/03_architecture/agents.md
- Monitoring: @docs/03_architecture/monitoring.md
