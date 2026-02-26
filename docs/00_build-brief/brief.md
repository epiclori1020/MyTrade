# Build Brief — MyTrade Stufe 1 MVP

## Ziel
Ein **Vertical Slice MVP** das einen kompletten Investment-Analyse-Flow durchläuft:

```
Asset Universe → Daten holen → Opus analysiert → Policy Gate → Verification →
Trade Plan → Paper Execute → Log/Audit
```

Alles minimal, aber alles verbunden. End-to-End in einem Flow.

## Stufe
**Stufe 1 (Paper Trading)** mit Human-Confirm für alles was später live wäre.

## Nicht-Ziele
- Kein Live-Trading, kein Auto-Execute
- Kein vollständiges Dashboard (1 Seite reicht)
- Keine 8 Agents (1 Fundamental Analyst reicht für MVP)
- Keine Multi-Provider-Daten (1 Provider reicht)
- Keine Mobile App
- Keine Anlageberatung — das System ist Decision Support

## Erfolgsmetriken (Definition of Done)
1. **End-to-End Run:** User klickt "Analyze AAPL" → analysis_run created → Claims extracted → Verification Status gesetzt → Trade Plan generated → Paper Trade geloggt
2. **Policy Engine blockt:** Trade der gegen IPS verstößt wird rejected (nicht nur gewarnt)
3. **Verification funktioniert:** Min. 1 Claim hat Status != verified (z.B. unverified/manual_check/disputed) ODER disputed wird korrekt erkannt falls Abweichung > Threshold
4. **JSON-Outputs validiert:** Agent-Output matcht claim-schema.json (automatischer Schema-Test)
5. **Audit Trail:** Jede Entscheidung nachvollziehbar in Supabase (analysis_runs, claims, verification_results, trade_log)
6. **Reproduzierbar:** Gleiche Inputs → strukturell gleiche Ergebnisse

## MVP-Scope pro Komponente
| Komponente | MVP | Später |
|-----------|-----|--------|
| Universe | Hardcoded: 5 US-Aktien + 2 ETFs | Dynamisch aus IPS + Asset Universe |
| Daten | 1 Provider (Finnhub free) | Multi-Provider mit Fallback |
| Analyse | 1 Agent (Fundamental, vereinfacht) | 8 spezialisierte Agents |
| Policy | Pre-Policy + Full-Policy, liest aus DB | Vollständige IPS-Validierung |
| Settings | 3 Presets + Advanced mit Constraints | Cooldown-Timer, Change-Reason |
| Verification | 2 Datenpunkte gegen 2. Quelle | Vollständiges Tier A/B/C |
| Trade Plan | JSON: buy/sell/hold + Begründung | Vollständig mit Sizing, Stop-Loss |
| Execution | Log in Supabase (+ Alpaca Paper) | IBKR Live mit Human-Confirm |
| Frontend | 2 Seiten: Analyse + Settings | Multi-Page Dashboard |

## Security Hard Rules
- API Keys nur in Environment Variables (Railway)
- Broker Keys NIEMALS im Frontend
- Supabase RLS aktiv auf allen Tabellen
- service_role Key nur im Backend, mit expliziter user_id Validierung
