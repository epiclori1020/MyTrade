# Kill-Switch & Circuit Breaker — MyTrade

## Kill-Switch (Portfolio-Ebene)

### Automatische Aktivierung
1. Portfolio Drawdown ≥ **20%** vom Höchststand
2. Verification-Rate fällt unter **70%**
3. User aktiviert manuell

### Was passiert
- Alle neuen Order-Vorschläge gestoppt
- System wechselt in Advisory-Only (Stufe 0)
- Bestehende Positionen bleiben (kein Panik-Verkauf)
- User wird sofort benachrichtigt
- Manuelle Reaktivierung erforderlich

## Circuit Breaker (API-Ebene)

### Aktivierung
- 5 aufeinanderfolgende API-Fehler → 60s Pause
- Gilt pro Provider (Finnhub, Alpaca, etc.)

### Retry-Strategie
- Exponential Backoff: 2s → 4s → 8s → 16s → give up
- Fallback auf alternativen Provider wenn verfügbar
- Broker API: KEIN Auto-Retry für Orders (nur für Reads)

## Budget-Cap
- Wenn Monatsbudget für Opus erreicht → automatisch Sonnet
- Hard Cap: System lehnt neue Analysen ab wenn Budget erschöpft
