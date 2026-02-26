# Verification Layer — Tier-System

## Zweck
Der Verification Layer ist ein eigenständiges Python-Modul (KEIN LLM) das zwischen den
Analyse-Agenten und dem Trade Plan sitzt. Er prüft jede numerische Behauptung gegen das
abgestufte Beweis-Klassifikationssystem.

## Tier-Definitionen

| Tier | Name | Beschreibung | Beispiele |
|------|------|-------------|-----------|
| **A** | Primär, auditierbar | Offizielle Filings, regulierte Publikationen, direkte Börsendaten | SEC EDGAR (10-K/10-Q), FRED, Unternehmensberichte, Börsen-Kursdaten |
| **B** | Sekundär, konsistent | Zwei unabhängige Aggregatoren liefern übereinstimmende Werte (<5% Abweichung) | Finnhub + Alpha Vantage, OpenBB + Finnhub |
| **C** | Nur Hinweis | Einzelne Quelle, interpretativ, keine harten Zahlen | News-Sentiment, Analystenratings, Social Media |

## Regeln nach Verwendungszweck

| Verwendung | Mindest-Tier | Bei nur Tier B | Bei nur Tier C |
|-----------|-------------|---------------|---------------|
| Trade-entscheidende Zahlen (Revenue, EPS, P/E) | A oder A+B | Confidence -15 + Flag "Manual Check" | Wird NICHT für Trade-Entscheidung verwendet |
| Kontext-Zahlen (Marktgröße, Branchenwachstum) | B | Normal verarbeiten | Confidence -5 + Flag "Estimate" |
| Sentiment / qualitative Einschätzung | C | N/A | Normal verarbeiten |

## Quellen-Verfügbarkeit nach Region

| Region | Tier A Quelle | Tier B Quellen | Einschränkungen |
|--------|--------------|----------------|-----------------|
| USA | SEC EDGAR | OpenBB, Finnhub, Alpha Vantage | Vollständig |
| EU | Unternehmens-IR, nationale Register | OpenBB, Finnhub | Kein einheitliches EDGAR |
| China | HKEX-Filings (HK-listed) | Finnhub (eingeschränkt) | VIE-Strukturen, daher NUR ETF |
| India | BSE/NSE-Filings | Finnhub (eingeschränkt) | Begrenzte API-Abdeckung, NUR ETF |

## Status-Werte (siehe auch claim-schema.json)

- **verified** — Tier A bestätigt, Abweichung < 5% → Grün im Frontend
- **consistent** — 2 Aggregatoren stimmen überein → Grün im Frontend
- **unverified** — Nur 1 Quelle verfügbar → Gelb im Frontend
- **disputed** — Abweichung > 5% zwischen Quellen → ROT im Frontend, Alert
- **manual_check** — Tier B für trade-kritischen Claim → Gelb + Warnung

## MVP-Scope
Für den Vertical Slice werden nur 2 Datenpunkte verifiziert:
1. Revenue (Finnhub → SEC EDGAR cross-check)
2. P/E Ratio (Finnhub → Alpha Vantage cross-check)

Vollständiges Tier-System wird in Phase 2 implementiert.
