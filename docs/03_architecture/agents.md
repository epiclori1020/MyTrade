# Agent-Spezifikationen — MyTrade

> **Quelle:** Architektur-Spezifikation v2.1, Sektion 8
> **Framework:** Agno (coordinate mode)

---

## Übersicht

Das System verwendet 10 spezialisierte Agenten, organisiert als Agno-Team mit dem Portfolio Synthesizer als Team Leader. Die Agenten nutzen einen **3-Tier Model-Mix** für optimale Kosten/Qualität:

- **Heavy (Opus):** High-Stakes Reasoning — Gegenargumente, finale Synthese
- **Standard (Sonnet):** Workhorse — Analyse-Agenten mit solidem Reasoning
- **Light (Haiku):** Strukturierte Subtasks — Extraktion, Verification, Klassifikation
- **Kein LLM:** Deterministische Code-Logik — Policy Engine, Data Collector, Monitoring-Checks

| # | Agent | Modell (API-String) | Tier | Token-Budget | Rolle |
|---|-------|-------------------|------|-------------|-------|
| 1 | Data Collector | — (deterministisch) | Kein LLM | 0 | API-Calls, Daten in DB schreiben |
| 2 | Macro Analyst | `claude-sonnet-4-6` | Standard | ~15K | Makro-Regime, Sektor-Bewertung |
| 3 | Fundamental Analyst | `claude-sonnet-4-6` | Standard | ~30K | Geschäftsmodell, Finanzen, Bewertung |
| 4 | Technical Analyst | `claude-sonnet-4-6` | Standard | ~10K | Trend, Indikatoren, Levels |
| 5 | Sentiment Analyst | `claude-sonnet-4-6` | Standard | ~8K | News, Insider, Analyst-Consensus |
| 6 | Risk Manager | `claude-sonnet-4-6` | Standard | ~12K | IPS-Prüfung, Positionsgröße, Risiken |
| 7 | Devil's Advocate | `claude-opus-4-6` | Heavy | ~15K | Gegenargumente, Worst-Case |
| 8 | Portfolio Synthesizer | `claude-opus-4-6` | Heavy | ~10K | Investment Note, Empfehlung (Team Leader) |
| 9 | Claim Extractor | `claude-haiku-4-5` | Light | ~5K | Claims aus Agent-Outputs extrahieren (JSON) |
| 10 | Verification Agent | `claude-haiku-4-5` | Light | ~3K | Cross-Check Zahlen gegen 2. Quelle |

**Gesamt pro Analyse:** ~110K Token verteilt auf 8 LLM-Calls + 2 deterministische Steps

> **Begründung 3-Tier:** Opus für Tasks die nuanciertes Gegenargument-Reasoning brauchen (Devil's Advocate muss die Investment-These "zerstören", Synthesizer muss alle Perspektiven abwägen). Sonnet für Analyse-Agents die solides Reasoning brauchen aber keine extreme Tiefe. Haiku für strukturierte, schema-gebundene Extraktion und Zahlenvergleiche wo Geschwindigkeit und Kosten wichtiger sind als Reasoning-Tiefe.

---

## Agent 1: Data Collector (Deterministisch)

| Eigenschaft | Spezifikation |
|-------------|---------------|
| Typ | Deterministisch (kein LLM) — reine API-Logik |
| Trigger | On-Demand (User-Request) oder Scheduled (Cron: täglich 18:00 UTC) |
| Datenquellen | Finnhub (Echtzeit, 60/Min), Alpha Vantage (Indikatoren, 25/Tag), SEC EDGAR (Filings), FRED (Makro) |
| Output | JSON in Supabase: `stock_fundamentals`, `stock_prices`, `macro_indicators`, `news_feed` |
| Error Handling | Retry mit exponential backoff (3 Versuche, 2s/4s/8s). Fallback auf alternative Quelle. Fehler in `error_log` |
| Rate Limit | Queue-basiert: max. 55 Finnhub-Calls/Min, max. 20 AV-Calls/Tag |

---

## Agent 2: Macro Analyst

**System-Prompt (Kern):**
> Du bist ein Senior-Makroökonom. Analysiere die makroökonomischen Bedingungen und bewerte Auswirkungen auf Sektoren und Regionen. Berücksichtige: GDP-Wachstum, Inflation (CPI/PPI), Leitzinsen, Yield Curve, PMI, Arbeitsmarktdaten, Geopolitik. Denke Schritt für Schritt. Jede Zahl muss mit {value, source, timestamp} referenziert werden. Gib strukturiertes JSON aus.

| Eigenschaft | Spezifikation |
|-------------|---------------|
| LLM / Budget | Claude Sonnet 4.6 (`claude-sonnet-4-6`) / ~15.000 Token |
| Input | Makro-Indikatoren aus `macro_indicators` Tabelle |
| Output | `{market_regime, sector_ratings[], regional_outlook[], risk_factors[], confidence, sources[]}` |

---

## Agent 3: Fundamental Analyst

**System-Prompt (Kern):**
> Du bist ein leitender Equity-Research-Analyst. Führe eine Fundamentalanalyse durch: 1) Geschäftsmodell (Umsatz nach Segment, Moat), 2) Finanzen (Revenue Growth, Margen, FCF, ROIC vs WACC), 3) Bewertung (DCF, P/E vs Peers, EV/EBITDA, PEG, FCF Yield), 4) Qualität (Piotroski F-Score, Altman Z-Score). JEDE Zahl muss Format {value, source, timestamp} haben. Erfinde KEINE Zahlen.

| Eigenschaft | Spezifikation |
|-------------|---------------|
| LLM / Budget | Claude Sonnet 4.6 (`claude-sonnet-4-6`) / ~30.000 Token |
| Input | `stock_fundamentals` (3-5 Jahre) + Peer-Daten aus Supabase |
| Output | `{business_model, financials{}, valuation{dcf, multiples{}}, quality{f_score, z_score}, moat_rating, score, sources[]}` |
| Verification | Alle numerischen Outputs werden durch Verification Layer gegen SEC EDGAR geprüft |

---

## Agent 4: Technical Analyst

> **Hinweis: Optional für Langfrist-Strategie.** Für Buy-and-Hold ist technische Analyse NICHT zwingend erforderlich. Dieser Agent ist primär für den Satellite-Anteil relevant (Timing für Einzelaktien-Käufe). Seine Outputs sind als "supplementary" markiert — ein fehlender Technical Score blockiert keine Empfehlung.

| Eigenschaft | Spezifikation |
|-------------|---------------|
| LLM / Budget | Claude Sonnet 4.6 (`claude-sonnet-4-6`) / ~10.000 Token |
| Input | `stock_prices` (1J Daily, 5J Weekly) + berechnete Indikatoren |
| Output | `{trend, levels{support[], resistance[]}, indicators{rsi, macd, bollinger}, atr_stop, signal_strength}` |

---

## Agent 5: Sentiment Analyst

| Eigenschaft | Spezifikation |
|-------------|---------------|
| LLM / Budget | Claude Sonnet 4.6 (`claude-sonnet-4-6`) / ~8.000 Token |
| Input | `news_feed` (30 Tage) + Insider-Trades + Analyst-Ratings |
| Output | `{sentiment (-100 bis +100), news_score, insider_activity{}, analyst_consensus, catalysts[]}` |

---

## Agent 6: Risk Manager

**System-Prompt (Kern):**
> Du bist Chief Risk Officer. 1) Prüfe gegen IPS (Policy Engine hat Vor-Check gemacht, du machst die qualitative Bewertung). 2) Berechne Positionsgröße (1-2%-Regel). 3) Bewerte Risiken: Business, Valuation, Liquidity, FX, Regulatory, Concentration. 4) Prüfe Korrelationen. 5) Definiere Stop-Loss + Exit. Sei konservativ. Im Zweifel: NICHT investieren.

| Eigenschaft | Spezifikation |
|-------------|---------------|
| LLM / Budget | Claude Sonnet 4.6 (`claude-sonnet-4-6`) / ~12.000 Token |
| Input | Outputs Agent 3+4+5 (nach Verification) + IPS + `portfolio_holdings` |
| Output | `{ips_ok, position_eur, position_pct, risks[], portfolio_impact{}, stop_loss, exit_criteria[], risk_score, go_no_go}` |

---

## Agent 7: Devil's Advocate

**System-Prompt (Kern):**
> Du bist ein erfahrener Short Seller. Zerstöre die Investment-These: 1) Top-3 Gegenargumente. 2) Historische Parallelen zu gescheiterten Investments. 3) Hidden Risks. 4) Worst-Case mit quantifiziertem Downside. Sei schonungslos.

| Eigenschaft | Spezifikation |
|-------------|---------------|
| LLM / Budget | Claude Opus 4.6 (`claude-opus-4-6`) / ~15.000 Token |
| Input | These (Agent 3) + Risiken (Agent 6) |
| Output | `{bear_args[], parallels[], hidden_risks[], worst_case{scenario, probability, downside_pct}, thesis_survival (0-100)}` |

---

## Agent 8: Portfolio Synthesizer (Team Leader)

**System-Prompt (Kern):**
> Du bist Portfolio Manager. Synthetisiere alle Perspektiven zu einer Investment-Entscheidung. Erstelle 1-Seite Investment Note (These, Risiken, Daten, Positionsgröße, Monitoring-Regel). Empfehlung: STRONG BUY / BUY / HOLD / SELL / STRONG SELL / NO ACTION. Confidence (0-100). Trade-Vorschlag NUR bei Confidence > 70 UND Risk go = true.

| Eigenschaft | Spezifikation |
|-------------|---------------|
| LLM / Budget | Claude Opus 4.6 (`claude-opus-4-6`) / ~10.000 Token |
| Agno-Rolle | Team Leader (coordinate mode) |
| Input | Komprimierte Outputs aller Agenten (~10K Token) |
| Output | `{recommendation, confidence, note{thesis[], risks[], data[], position, monitoring, exit}, trade_proposal}` |

---

## Agent-Orchestrierung (Agno coordinate mode)

```
User Request
    │
    ▼
Data Collector (parallel API-Calls)
    │
    ▼
Policy Engine Vor-Check (deterministisch)
    │
    ▼
┌───┴───────────────────────────┐
│  Macro Analyst                │
│  Fundamental Analyst    ◄─── PARALLEL (Agno async)
│  Technical Analyst            │
│  Sentiment Analyst            │
└───┬───────────────────────────┘
    │
    ▼
Verification Layer (Cross-Check)
    │
    ▼
Risk Manager
    │
    ▼
Devil's Advocate
    │
    ▼
Portfolio Synthesizer → Investment Note
    │
    ▼
Policy Engine Full-Check (deterministisch)
    │
    ▼
Frontend (Approve/Reject bei Stufe 2)
```

---

## Agent 9: Claim Extractor (Haiku)

| Eigenschaft | Spezifikation |
|-------------|---------------|
| LLM / Budget | Claude Haiku 4.5 (`claude-haiku-4-5`) / ~5.000 Token |
| Tier | Light — strukturierte Extraktion, kein Deep Reasoning |
| Input | Agent-Outputs (JSON) + Claim-Schema (@docs/04_verification/claim-schema.json) |
| Output | `claims[]` gemäß Schema: `{claim_id, claim_text, claim_type, value, unit, ticker, period, source_primary, tier, trade_critical}` |
| Fallback | Schema-Validierung → FAIL → 1x Retry Haiku → FAIL → Sonnet 4.6 Fallback |

> **Warum Haiku:** Claim-Extraktion ist schema-gebunden (kurzer Input, strukturierter JSON-Output). Braucht keine Interpretation, nur präzises Pattern Matching. Haiku ist dafür 3-5x schneller und 60-70% günstiger als Sonnet.

---

## Agent 10: Verification Agent (Haiku)

| Eigenschaft | Spezifikation |
|-------------|---------------|
| LLM / Budget | Claude Haiku 4.5 (`claude-haiku-4-5`) / ~3.000 Token |
| Tier | Light — Zahlenvergleich, keine Interpretation |
| Input | `claims[]` + Daten von 2. Quelle (Alpha Vantage / SEC EDGAR) |
| Output | `verification_results[]`: `{claim_id, source_verification, status, confidence_adjustment}` |
| Status-Logik | Abweichung ≤2% → `verified`, ≤5% → `consistent`, >5% → `disputed`, keine 2. Quelle → `unverified` |
| Fallback | Schema-Validierung → FAIL → 1x Retry Haiku → FAIL → Sonnet 4.6 Fallback |

> **Warum Haiku:** "Ist P/E 24.5 ≈ 24.3?" ist Zahlenvergleich, kein Reasoning. Für die Interpretation *warum* Zahlen abweichen → Sonnet/Opus (das macht der Risk Manager).

---

## Model-Routing und Fallback-Logik

### Bidirektionale Fallback-Kette

```
QUALITY FALLBACK (nach oben bei Fehler):
┌──────────┐     Schema-Fail      ┌──────────┐     Schema-Fail      ┌──────────┐
│  Haiku   │ ──── 1x Retry ────► │  Sonnet  │ ──── 1x Retry ────► │  Opus    │
│  (Light) │                      │(Standard)│                      │ (Heavy)  │
└──────────┘                      └──────────┘                      └──────────┘

BUDGET FALLBACK (nach unten bei Kosten):
┌──────────┐    Budget 80%        ┌──────────┐    Budget 95%        ┌──────────┐
│  Opus    │ ──── degradiert ───► │  Sonnet  │ ──── degradiert ───► │  Haiku   │
│ (Heavy)  │                      │(Standard)│                      │  (Light) │
└──────────┘                      └──────────┘                      └──────────┘
```

### Routing-Regeln

1. **Default-Routing:** Jeder Agent hat ein festes Default-Modell (siehe Tabelle oben)
2. **Quality-Fallback:** Bei Schema-Validierungsfehler oder JSON-Parse-Error → 1x Retry mit gleichem Modell → dann nächsthöheres Modell
3. **Budget-Fallback:** Wenn Monatsbudget für ein Tier erreicht → automatisch nächstniedrigeres Tier. Der User wird im Dashboard informiert
4. **Effort-Parameter:** Sonnet und Opus unterstützen `effort: low/medium/high`. Default: `medium` für Analyse-Agents, `high` für Devil's Advocate und Synthesizer
5. **Kein LLM bei deterministischen Tasks:** Policy Engine (Pre/Full-Check), Monitoring-Cron (Drawdown-Check, Trade-Count, Limit-Prüfungen) bleiben pure Code-Logik

### Prompt Caching Strategie

Folgende Prompt-Teile sind bei jeder Analyse identisch und werden gecacht:
- System-Prompts aller Agents (~8K Token gesamt)
- IPS/Policy-Regeln aus `user_policy` (~2K Token, invalidiert bei Policy-Änderung)
- Output-Schemas (Claim-Schema, Agent-Output-Formate) (~3K Token)
- Tool-Definitionen (~2K Token)

**Geschätztes Caching-Potenzial:** ~15K Token pro Analyse werden aus Cache gelesen statt neu gesendet. Bei Opus: $5/MTok → $0.50/MTok = 90% Ersparnis auf diesen Anteil.

---

## Referenzen
- System-Übersicht: @docs/03_architecture/system-overview.md
- Verification Layer: @docs/04_verification/tier-system.md
- Claim-Schema: @docs/04_verification/claim-schema.json
- Policy Engine: @docs/05_risk/policy-engine.md
