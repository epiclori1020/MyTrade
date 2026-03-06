# Datenbank-Schema — MyTrade

> **Quelle:** Architektur-Spezifikation v2.1, Sektion 9
> **Engine:** Supabase PostgreSQL (EU Region)

---

## Übersicht

Alle persistenten Daten leben in PostgreSQL via Supabase. Alle Tabellen sind über Foreign Keys verbunden. RLS ist auf allen User-bezogenen Tabellen aktiv.

| Tabelle | Zweck | Definiert in |
|---------|-------|-------------|
| `user_policy` | IPS-Einstellungen pro User (3-Tier Settings, **MVP primär**) | @docs/02_policy/settings-spec.md |
| `policy_change_log` | Audit-Trail für Policy-Änderungen | @docs/02_policy/settings-spec.md |
| `investment_policy` | ~~Investment-Regeln (Architektur-Spec)~~ **LEGACY — ersetzt durch user_policy** | Dieses Dokument |
| `portfolio_holdings` | Aktuelle Positionen | Dieses Dokument |
| `stock_fundamentals` | Fundamentaldaten pro Ticker/Periode | Dieses Dokument |
| `analysis_runs` | Analyse-Durchläufe mit Agent-Outputs | Dieses Dokument |
| `claims` | Extrahierte Claims aus Agent-Outputs (claim-schema.json) | Dieses Dokument |
| `verification_results` | Verification-Ergebnisse pro Claim | Dieses Dokument |
| `trade_log` | Trade-Vorschläge und Ausführungen | Dieses Dokument |
| `stock_prices` | Historische + aktuelle Kurse | Dieses Dokument |
| `macro_indicators` | Makrodaten (GDP, CPI, etc.) | Dieses Dokument |
| `error_log` | System-Fehler | Dieses Dokument |
| `agent_cost_log` | API-Kosten-Tracking | Dieses Dokument |
| `learning_progress` | ~~Lern-Modus Fortschritt~~ **FUTURE — nicht im MVP implementiert** | Dieses Dokument |

---

## Grundregeln

- RLS (Row Level Security) aktiv auf allen User-bezogenen Tabellen
- `service_role` Key nur im Backend, mit expliziter `user_id`-Validierung
- Alle Timestamps in UTC (`TIMESTAMPTZ`)
- UUIDs als Primary Keys
- Foreign Keys für referentielle Integrität

---

## Schema-Definitionen

### investment_policy

```sql
CREATE TABLE investment_policy (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  max_drawdown DECIMAL(5,2) NOT NULL DEFAULT 20.00,       -- %
  max_position DECIMAL(5,2) NOT NULL DEFAULT 5.00,         -- % of portfolio
  max_sector DECIMAL(5,2) NOT NULL DEFAULT 25.00,          -- %
  core_pct DECIMAL(5,2) NOT NULL DEFAULT 80.00,            -- Core allocation
  satellite_pct DECIMAL(5,2) NOT NULL DEFAULT 20.00,       -- Satellite
  target_alloc JSONB NOT NULL DEFAULT '{}',
  forbidden TEXT[] DEFAULT '{}',                            -- e.g. {'options','leverage','crypto'}
  rebalance_days INTEGER NOT NULL DEFAULT 90,
  maturity_stage INTEGER NOT NULL DEFAULT 0,                -- 0-3
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT valid_allocation CHECK (core_pct + satellite_pct = 100)
);

CREATE INDEX idx_ips_user ON investment_policy(user_id);
```

> **Hinweis:** Diese Tabelle stammt aus der Architektur-Spec v2.1. Sie wird durch `user_policy` (siehe settings-spec.md) ersetzt, die ein flexibleres Preset-System mit Overrides unterstützt. **Im MVP wird `investment_policy` NICHT erstellt** — nur `user_policy` + `policy_change_log`.

---

### claims

```sql
CREATE TABLE claims (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_id UUID NOT NULL REFERENCES analysis_runs(id),
  claim_id VARCHAR(50) NOT NULL,
  claim_text TEXT NOT NULL,
  claim_type VARCHAR(20) NOT NULL CHECK (claim_type IN ('number', 'ratio', 'event', 'opinion', 'forecast')),
  value DECIMAL(20,4),
  unit VARCHAR(20),
  ticker VARCHAR(10),
  period VARCHAR(20),
  source_primary JSONB NOT NULL,                           -- {provider, endpoint, retrieved_at}
  tier VARCHAR(5) NOT NULL CHECK (tier IN ('A', 'B', 'C')),
  required_tier VARCHAR(10) NOT NULL,
  trade_critical BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_claims_analysis ON claims(analysis_id);
CREATE INDEX idx_claims_ticker ON claims(ticker);
```

---

### verification_results

```sql
CREATE TABLE verification_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id UUID NOT NULL REFERENCES claims(id),
  source_verification JSONB NOT NULL,                      -- {provider, value, deviation_pct, retrieved_at}
  status VARCHAR(20) NOT NULL CHECK (status IN ('verified', 'consistent', 'unverified', 'disputed', 'manual_check')),
  confidence_adjustment INTEGER DEFAULT 0,
  verified_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_verification_claim ON verification_results(claim_id);
CREATE INDEX idx_verification_status ON verification_results(status);
```

---

### portfolio_holdings

```sql
CREATE TABLE portfolio_holdings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  ticker VARCHAR(10) NOT NULL,
  shares DECIMAL(12,4) NOT NULL,
  avg_price DECIMAL(12,4) NOT NULL,                        -- in USD
  current_price DECIMAL(12,4),
  weight_pct DECIMAL(5,2),
  entry_date DATE NOT NULL,
  stop_loss DECIMAL(12,4),
  thesis TEXT,
  asset_class VARCHAR(20) DEFAULT 'equity',                -- equity, etf, bond
  is_core BOOLEAN DEFAULT false,
  status VARCHAR(10) DEFAULT 'active',                     -- active, sold, stopped_out
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_holdings_user ON portfolio_holdings(user_id);
CREATE INDEX idx_holdings_ticker ON portfolio_holdings(ticker);
```

---

### stock_fundamentals

```sql
CREATE TABLE stock_fundamentals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker VARCHAR(10) NOT NULL,
  period VARCHAR(7) NOT NULL,                              -- e.g. '2025-Q3'
  revenue BIGINT,                                          -- in USD
  net_income BIGINT,
  free_cash_flow BIGINT,
  total_debt BIGINT,
  total_equity BIGINT,
  eps DECIMAL(10,4),
  pe_ratio DECIMAL(10,2),
  pb_ratio DECIMAL(10,2),
  ev_ebitda DECIMAL(10,2),
  roe DECIMAL(8,4),
  roic DECIMAL(8,4),
  f_score INTEGER CHECK (f_score BETWEEN 0 AND 9),
  z_score DECIMAL(6,3),
  source VARCHAR(50) NOT NULL,                             -- 'finnhub', 'edgar', 'alpha_vantage'
  fetched_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(ticker, period, source)
);

CREATE INDEX idx_fund_ticker ON stock_fundamentals(ticker, period);
```

---

### analysis_runs

```sql
CREATE TABLE analysis_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  ticker VARCHAR(10) NOT NULL,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  status VARCHAR(20) DEFAULT 'running',                    -- running, completed, failed, partial
  macro_output JSONB,
  fundamental_out JSONB,
  technical_out JSONB,
  sentiment_out JSONB,
  risk_output JSONB,
  devil_output JSONB,
  synthesis_out JSONB,
  verification JSONB,                                      -- {verified: 12, unverified: 2, disputed: 1}
  recommendation VARCHAR(20),
  confidence INTEGER CHECK (confidence BETWEEN 0 AND 100),
  trade_proposed BOOLEAN DEFAULT false,
  total_tokens INTEGER,
  total_cost_usd DECIMAL(8,4),
  error_log JSONB DEFAULT '[]'
);

CREATE INDEX idx_runs_user_ticker ON analysis_runs(user_id, ticker);
CREATE INDEX idx_runs_date ON analysis_runs(started_at DESC);
```

---

### trade_log

```sql
CREATE TABLE trade_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  analysis_id UUID REFERENCES analysis_runs(id),
  ticker VARCHAR(10) NOT NULL,
  action VARCHAR(4) NOT NULL,                              -- 'BUY' or 'SELL'
  shares DECIMAL(12,4) NOT NULL,
  price DECIMAL(12,4) NOT NULL,
  order_type VARCHAR(10) DEFAULT 'LIMIT',
  stop_loss DECIMAL(12,4),
  status VARCHAR(15) NOT NULL,                             -- proposed, approved, rejected, executed, failed
  broker VARCHAR(10),                                      -- 'alpaca', 'ibkr'
  broker_order_id VARCHAR(50),
  proposed_at TIMESTAMPTZ DEFAULT NOW(),
  approved_at TIMESTAMPTZ,
  executed_at TIMESTAMPTZ,
  rejection_reason TEXT
);

CREATE INDEX idx_trades_user ON trade_log(user_id, proposed_at DESC);
```

---

### Weitere Tabellen

```sql
-- Historische + aktuelle Kurse
CREATE TABLE stock_prices (
  ticker VARCHAR(10) NOT NULL,
  date DATE NOT NULL,
  open DECIMAL(12,4),
  high DECIMAL(12,4),
  low DECIMAL(12,4),
  close DECIMAL(12,4),
  volume BIGINT,
  rsi DECIMAL(6,2),
  macd DECIMAL(10,4),
  atr DECIMAL(10,4),
  source VARCHAR(50) NOT NULL,
  PRIMARY KEY (ticker, date)
);

-- Makrodaten
CREATE TABLE macro_indicators (
  date DATE NOT NULL,
  gdp DECIMAL(15,2),
  cpi DECIMAL(8,4),
  fed_rate DECIMAL(5,4),
  yield_spread DECIMAL(6,4),
  pmi DECIMAL(6,2),
  unemployment DECIMAL(5,2),
  source VARCHAR(50) NOT NULL,
  fetched_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (date, source)
);

-- System-Fehler
CREATE TABLE error_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_id UUID REFERENCES analysis_runs(id),
  timestamp TIMESTAMPTZ DEFAULT NOW(),
  component VARCHAR(50) NOT NULL,
  error_type VARCHAR(50) NOT NULL,
  message TEXT NOT NULL,
  retry_count INTEGER DEFAULT 0,
  resolved BOOLEAN DEFAULT false
);

-- API-Kosten-Tracking (3-Tier Model-Mix)
CREATE TABLE agent_cost_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_id UUID REFERENCES analysis_runs(id),
  timestamp TIMESTAMPTZ DEFAULT NOW(),
  agent_name VARCHAR(50) NOT NULL,
  model VARCHAR(50) NOT NULL,                              -- e.g. 'claude-sonnet-4-6', 'claude-opus-4-6', 'claude-haiku-4-5'
  tier VARCHAR(10) NOT NULL CHECK (tier IN ('heavy', 'standard', 'light')),
  effort VARCHAR(10) DEFAULT 'medium' CHECK (effort IN ('low', 'medium', 'high')),
  input_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL,
  cache_read_tokens INTEGER DEFAULT 0,                     -- Tokens aus Prompt Cache (90% günstiger)
  cost_usd DECIMAL(8,4) NOT NULL,
  fallback_from VARCHAR(50),                               -- NULL = Default-Modell, sonst: z.B. 'claude-haiku-4-5' (Quality-Fallback)
  degraded BOOLEAN DEFAULT false                           -- true = Budget-Fallback aktiv
);

-- FUTURE: Lern-Modus Fortschritt (nicht im MVP implementiert, keine Migration vorhanden)
-- DO NOT copy into a migration — this table is not part of MVP.
-- CREATE TABLE learning_progress (
--   id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
--   user_id UUID NOT NULL REFERENCES auth.users(id),
--   concept VARCHAR(100) NOT NULL,
--   status VARCHAR(20) DEFAULT 'in_progress',              -- learned, in_progress
--   quiz_score INTEGER,
--   last_session TIMESTAMPTZ DEFAULT NOW()
-- );
```

---

## Row-Level Security Policies

### Kritischer Hinweis: service_role und auth.uid()

Supabase `service_role` bypassed RLS komplett. Wenn das Backend mit `service_role` schreibt, ist `auth.uid()` nicht verfügbar. Zwei Optionen:

**Option A (empfohlen): Backend leitet User-JWT an Supabase weiter.**

```sql
ALTER TABLE portfolio_holdings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own holdings"
  ON portfolio_holdings FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users update own holdings"
  ON portfolio_holdings FOR UPDATE
  USING (auth.uid() = user_id);

ALTER TABLE trade_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own trades"
  ON trade_log FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can approve or reject proposed trades"
  ON trade_log FOR UPDATE
  USING (auth.uid() = user_id AND status = 'proposed')
  WITH CHECK (status IN ('approved', 'rejected'));
```

**Option B (für Agent-Writes): Backend nutzt service_role mit expliziter Validierung.**

```python
async def save_analysis(user_id: str, analysis: dict):
    if user_id != request.state.authenticated_user_id:
        raise HTTPException(403, "User ID mismatch")
    supabase_admin.table("analysis_runs").insert({
        "user_id": user_id,
        **analysis
    }).execute()
```

---

## Referenzen
- Settings-System (user_policy + policy_change_log): @docs/02_policy/settings-spec.md
- Claim-Schema für Verification: @docs/04_verification/claim-schema.json
- Error Handling: @docs/03_architecture/error-handling.md
