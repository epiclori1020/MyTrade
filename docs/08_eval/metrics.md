# Evaluation Metriken — MyTrade

## Laufende Metriken (Monitoring Dashboard)

| Metrik | Ziel | Alert-Schwelle | Messung |
|--------|------|---------------|---------|
| Pipeline Error-Rate | < 5% | > 10% | Fehlgeschlagene Analysen / Gesamt |
| Verification-Rate | > 85% | < 70% (Kill-Switch!) | Verified+Consistent Claims / Gesamt |
| IPS-Compliance | 100% | < 100% | Policy-Verstöße die durchgerutscht sind |
| API-Kosten MTD | < Budget-Cap | > 80% Cap | Summe Anthropic + Provider Kosten |
| Agent-Latenz | < 60s | > 120s | Zeit pro Agent-Aufruf |
| Token-Verbrauch | < 50K/Analyse | > 80K | Input + Output Tokens pro Run |

## Gate-Kriterien (für Stufenwechsel)

### Stufe 1 → Stufe 2
Alle müssen erfüllt sein über min. 3 Monate Paper Trading:
- Pipeline Error-Rate < 5%
- Verification-Rate > 85%
- IPS-Compliance = 100%
- User versteht Outputs (subjektiv, User-Bestätigung)
- Security Audit bestanden

### NICHT als Gate-Kriterium:
- ~~Profitables Paper Trading~~ (marktabhängig, kein Qualitätsmerkmal)
- ~~Outperformance vs. Benchmark~~ (das System soll korrekt sein, nicht profitabel)

## Quartals-Review Metriken
- Performance vs. VWCE Benchmark (informativ, nicht als Gate)
- Portfolio-Drift vs. IPS-Target
- Sektor-Konzentration innerhalb Limits?
- Drawdown-Historie
- Anzahl Kill-Switch-Aktivierungen
- Kosten pro Quartal vs. Budget
