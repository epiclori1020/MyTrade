# Datenprovider — MyTrade

## Provider-Übersicht

| Provider | Tier | Free Limit | Daten | Verwendung |
|----------|------|-----------|-------|-----------|
| Finnhub | B | 60 calls/min | Kurse, Fundamentals, News, Insider | Primärquelle für Echtzeit + Fundamentals |
| Alpha Vantage | B | 25 calls/Tag (free) | Kurse, Technische Indikatoren | Verification-Quelle + Technische Daten |
| FRED | A | Unbegrenzt | Makrodaten (GDP, CPI, Fed Rate) | Makro-Analyse |
| SEC EDGAR | A | Fair Use | 10-K, 10-Q, 8-K Filings | Tier A Verification für US-Filer |

## MVP: Nur Finnhub
Für den Vertical Slice reicht Finnhub als einziger Provider:
- `/stock/metric` — Fundamentals (Revenue, EPS, P/E)
- `/quote` — Aktienkurs
- `/company-news` — News-Sentiment
- `/stock/insider-transactions` — Insider-Trades

Verification gegen Alpha Vantage für 2 Datenpunkte (Revenue, P/E).

## Rate Limiting
```python
# Finnhub: max 60 calls/min
# Alpha Vantage: max 25 calls/Tag (free), 75/min (premium)
# FRED: keine harten Limits, aber Fair Use
# SEC EDGAR: max 10 requests/sec, User-Agent Header required
```

## Retry-Strategie
- Exponential Backoff: 2s → 4s → 8s → 16s → give up
- Fallback: Wenn Finnhub down → Alpha Vantage für gleichen Datenpunkt
- Circuit Breaker: 5 consecutive failures → 60s Pause

## Region-Coverage
Siehe docs/02_policy/asset-universe.md für welche Regionen erlaubt sind.
- US: Alle Provider vollständig
- EU: Finnhub eingeschränkt, Alpha Vantage okay
- EM: Nur aggregierte Daten, daher nur via ETF
