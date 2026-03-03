# Prompt: Step 11 — Kill-Switch + Budget-Fallback

Du arbeitest am MyTrade Projekt — ein KI-gestütztes Investment-Analyse-System.

## Aktueller Stand

- **Branch:** `main` (clean, up to date)
- **Abgeschlossene Steps:** 1-10 (Foundation → Verification Pipeline → Execution + Error Handling, Phase 1-3 Step 10 complete)
- **Tests:** 482 Tests alle grün
- **Backend Source-Dateien:** 39 Dateien in `backend/src/`
- **Backend Test-Dateien:** 27 Dateien in `backend/tests/`

---

## Bestandsaufnahme (File-Inventar)

### Bestehende Source-Dateien (relevant für Step 11):

| Datei | Zweck | Relevanz für Step 11 |
|-------|-------|---------------------|
| `src/services/policy_engine.py` | Deterministische Policy Engine — Pre-Policy + Full-Policy. Pre-Policy hat Kill-Switch-Stub (Zeile 327-330: `# TODO: Dedizierter Kill-Switch-State in DB (Step 11+)`). Full-Policy hat Drawdown-Check (Zeile 421-433) der `_calculate_portfolio_drawdown()` aufruft — die immer 0.0 zurückgibt (Zeile 586-592: Stub). | **Editieren:** Kill-Switch-Stub in Pre-Policy durch echten DB-Check ersetzen. Drawdown-Check mit Highwater-Mark-Logik verbinden. |
| `src/services/circuit_breaker.py` | Circuit Breaker für Provider APIs (Finnhub, AV, Alpaca). Singleton-Instanzen: `finnhub_breaker`, `alpha_vantage_breaker`, `alpaca_breaker`. State: closed/open/half_open. `_probe_in_flight` Flag für single-probe enforcement. | **Erweitern:** Alpaca CB-Open → Kill-Switch triggern (Bridge). Wenn `alpaca_breaker` öffnet → Kill-Switch automatisch aktivieren. |
| `src/services/trade_execution.py` | Trade Lifecycle: propose → approve → execute/fail/reject/expire. `approve_trade()` (Zeile 100-158): Nach erfolgreicher Execution schreibt Zeile 138-142 `status="executed"` + `broker_order_id` + `executed_at` in trade_log — aber **NICHT** `executed_price`. Der `executed_price` wird nur im Response-Dict (Zeile 147) zurückgegeben, nicht in die DB persistiert. `expire_stale_trades()` (cross-user, Zeile ~200+). | **Editieren:** `executed_price` in trade_log persistieren (neues Feld oder `price` überschreiben). |
| `src/agents/fundamental.py` | Fundamental Analyst Agent. Hardcoded `MODEL_ID = "claude-sonnet-4-6"` (Zeile 24). Nutzt `messages.parse()` mit Pydantic Schema. 2 Attempts + JSON Repair. | **Editieren:** Statt hardcoded `MODEL_ID` → Budget-Manager aufrufen für dynamisches Model-Routing. `degraded` Flag an Caller zurückgeben. |
| `src/agents/claim_extractor.py` | Claim Extractor Agent. Hardcoded `MODEL_HAIKU = "claude-haiku-4-5"` und `MODEL_SONNET = "claude-sonnet-4-6"` (Zeile 24-25). 3-Attempt Fallback-Chain (Haiku → Haiku Retry → Sonnet). | **Editieren:** Model-IDs über Budget-Manager auflösen statt hardcoded. |
| `src/services/fundamental_analysis.py` | Fundamental Analysis Orchestrator. 2-Phase Architektur. Loggt Kosten in `agent_cost_log` (Zeile 174-186) mit `"degraded": False` hardcoded. | **Editieren:** `degraded` Flag aus Agent-Response durchreichen an Cost-Logging. |
| `src/services/claim_extraction.py` | Claim Extraction Orchestrator. Loggt Kosten in `agent_cost_log` (Zeile 274-286) mit `"degraded": False` hardcoded. | **Editieren:** `degraded` Flag durchreichen. |
| `src/services/exceptions.py` | Exception-Hierarchie: `DataProviderError` (+ `RateLimitError`, `ProviderTimeoutError`, `ProviderUnavailableError`, `BrokerError`, `CircuitBreakerOpenError`), `PreconditionError`, `ConfigurationError`, `AgentError`. | **Erweitern:** `BudgetExhaustedError` hinzufügen. |
| `src/services/error_logger.py` | `log_error()` → best-effort INSERT in `error_log`. Fallback auf Python Logger. | **Wiederverwenden.** Alle Kill-Switch-Events und Budget-Warnings loggen. |
| `src/services/alpaca_paper.py` | Alpaca Paper Adapter. `alpaca_breaker` aus `circuit_breaker.py`. `submit_order()`, `get_positions()`, `get_account()`. | **Erweitern:** Nach CB-Open → Kill-Switch-Bridge aufrufen. |
| `src/routes/trades.py` | Trade-Endpoints. `GET /` hat optionalen `?status` Query-Parameter ohne Allowlist (beliebige Strings möglich, ergeben 0 Ergebnisse). | **Editieren:** Status-Allowlist hinzufügen. |
| `src/routes/policy.py` | Policy-Endpoints: pre-check, full-check, effective. | **Keine Änderung** — Pre-Policy ändert sich intern, Endpoint bleibt gleich. |
| `src/config.py` | Pydantic Settings — alle Env-Vars. Keine Budget-Konfiguration. | **Keine Änderung.** Budget-Caps als Code-Konstanten (nicht ENV-konfigurierbar im MVP). |
| `src/main.py` | FastAPI App — 7 Router registriert (health, data, analysis, claims, verification, policy, trades). | **Editieren:** `system` Router hinzufügen (Kill-Switch + Budget-Status). |
| `src/services/supabase.py` | `get_supabase_admin()` Singleton. | **Wiederverwenden.** |
| `src/services/verification.py` | Verification Layer. Graceful Degradation bei AV-Fehler. | **Keine Änderung** — Verification-Rate wird von Kill-Switch abgefragt, nicht umgekehrt. |
| `src/constants.py` | `MVP_UNIVERSE` Liste. | **Keine Änderung.** |
| `src/services/broker_adapter.py` | Abstraktes `BrokerAdapter` Interface + Dataclasses (Order, OrderResult, Position, AccountInfo). | **Keine Änderung.** |

### Bestehende Test-Dateien (Pattern-Referenz):

| Datei | Tests | Pattern |
|-------|-------|---------|
| `tests/conftest.py` | Fixtures: `auth_client`, `FAKE_USER`, `make_test_settings` | Wiederverwenden |
| `tests/helpers.py` | `make_test_settings()` factory mit Alpaca test-keys | Wiederverwenden |
| `tests/test_policy_engine.py` | 53 Tests für Policy Engine | **Pattern-Referenz + Erweitern** für Kill-Switch-Integration |
| `tests/test_circuit_breaker.py` | ~25 Tests für Circuit Breaker | **Pattern-Referenz** für CB-to-Kill-Switch Bridge |
| `tests/test_trade_execution.py` | ~29 Tests für Trade Lifecycle | **Erweitern** für executed_price Persistierung |
| `tests/test_fundamental_agent.py` | Tests für LLM Agent | **Erweitern** für Budget-Fallback Model-Routing |
| `tests/test_claim_extractor.py` | Tests für Fallback-Chain | **Erweitern** für Budget-Fallback Model-Routing |
| `tests/test_fundamental_analysis.py` | Tests für Orchestrator | **Erweitern** für degraded Flag |
| `tests/test_trades_route.py` | 25 Tests für Trade-Routes | **Erweitern** für Status-Allowlist |

### DB-Schema (existiert bereits in Supabase):

**agent_cost_log Tabelle** (Budget-Tracking liest hieraus):
```sql
CREATE TABLE agent_cost_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_id UUID REFERENCES analysis_runs(id),
  timestamp TIMESTAMPTZ DEFAULT NOW(),
  agent_name VARCHAR(50) NOT NULL,
  model VARCHAR(50) NOT NULL,                -- 'claude-sonnet-4-6', 'claude-opus-4-6', 'claude-haiku-4-5'
  tier VARCHAR(10) NOT NULL CHECK (tier IN ('heavy', 'standard', 'light')),
  effort VARCHAR(10) DEFAULT 'medium',
  input_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL,
  cache_read_tokens INTEGER DEFAULT 0,
  cost_usd DECIMAL(8,4) NOT NULL,
  fallback_from VARCHAR(50),                 -- NULL = Default-Modell
  degraded BOOLEAN DEFAULT false             -- true = Budget-Fallback aktiv ← STEP 11 NUTZT DIES
);
```

**trade_log Tabelle** (executed_price fehlt):
```sql
CREATE TABLE trade_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) NOT NULL,
  analysis_id UUID REFERENCES analysis_runs(id),
  ticker VARCHAR(10) NOT NULL,
  action VARCHAR(4) NOT NULL,                -- 'BUY' or 'SELL'
  shares DECIMAL(12,4) NOT NULL,
  price DECIMAL(12,4) NOT NULL,              -- vorgeschlagener Preis
  order_type VARCHAR(10) DEFAULT 'LIMIT',
  stop_loss DECIMAL(12,4),
  status VARCHAR(15) NOT NULL,               -- proposed, approved, rejected, executed, failed
  broker VARCHAR(10),
  broker_order_id VARCHAR(50),
  proposed_at TIMESTAMPTZ DEFAULT NOW(),
  approved_at TIMESTAMPTZ,
  executed_at TIMESTAMPTZ,
  rejection_reason TEXT
  -- FEHLT: executed_price ← STEP 11 MIGRATION
);
```

**verification_results Tabelle** (Verification-Rate wird hieraus berechnet):
```sql
CREATE TABLE verification_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id UUID NOT NULL REFERENCES claims(id),
  source_verification JSONB NOT NULL,
  status VARCHAR(20) NOT NULL CHECK (status IN ('verified', 'consistent', 'unverified', 'disputed', 'manual_check')),
  confidence_adjustment INTEGER DEFAULT 0,
  verified_at TIMESTAMPTZ DEFAULT now()
);
```

---

## Deine Aufgabe: Step 11 — Kill-Switch + Budget-Fallback

**Quellen:** `@docs/05_risk/kill-switch.md`, `@docs/03_architecture/monitoring.md`, `@docs/05_risk/execution-contract.md`

### Was Step 11 tut

Step 11 macht das System **selbstschützend**. Statt nur Fehler abzufangen (Step 10), erkennt das System jetzt gefährliche Zustände und deaktiviert sich selbst. Der Kill-Switch schützt vor unkontrollierten Verlusten, und der Budget-Fallback verhindert Kosten-Explosionen.

Drei Arbeitspakete:

1. **Kill-Switch System** — Automatische Erkennung gefährlicher Zustände (Drawdown ≥20%, Broker CB offen, Verification-Rate <70%) + manuelle Aktivierung. System wechselt in Advisory-Only (Stufe 0): keine neuen Trades, Analysen weiterhin möglich. DB-persistiert, manuelle Reaktivierung erforderlich.
2. **Budget-Fallback (3-Tier Model-Routing)** — Monatliche Kosten-Caps pro Tier (Heavy/Standard/Light). Wenn Budget erreicht → automatisch auf günstigeres Modell degradieren (Opus→Sonnet→Haiku). Hard Cap → keine LLM-Calls mehr. `degraded` Flag in `agent_cost_log` setzen.
3. **Open-Issue Cleanup** — `executed_price` in trade_log persistieren, `list_trades` Status-Allowlist, Drawdown-Highwater-Mark implementieren.

### Warum dieses System im Gesamtkontext?

```
Analyse-Request
    │
    ▼
[Pre-Policy] ← Kill-Switch Check (Step 11 NEU — ersetzt Stub)
    │ (Kill-Switch aktiv? → 503 "System paused")
    ▼
[Budget-Manager] ← Budget Check (Step 11 NEU)
    │ (Budget erschöpft? → 503 "Budget exhausted")
    │ (Budget Tier erreicht? → Modell degradieren)
    ▼
[Agent-Call mit Model-Routing] ← (Step 11 NEU)
    │ (MODEL_ID dynamisch statt hardcoded)
    ▼
[Cost-Logging] ← degraded Flag setzen (Step 11 NEU)
    │
    ▼
[Trade-Execution]
    │
    ▼
[Kill-Switch Monitoring] ← Nach Trade prüfen (Step 11 NEU)
    │ (Drawdown? Broker-CB? Verification-Rate?)
    ▼
[DB: system_state] ← Kill-Switch-Status persistiert (Step 11 NEU)
```

---

## Zu erstellende/ändernde Dateien

| # | Datei | Aktion | Zweck |
|---|-------|--------|-------|
| 1 | `supabase/migrations/XXXXXXXX_system_state.sql` | **Erstellen** | system_state Tabelle + executed_price Feld |
| 2 | `backend/src/services/kill_switch.py` | **Erstellen** | Kill-Switch Logik (check, activate, deactivate, evaluate triggers) |
| 3 | `backend/src/services/budget_manager.py` | **Erstellen** | Budget-Tracking + Model-Routing |
| 4 | `backend/src/routes/system.py` | **Erstellen** | System-Endpoints (Kill-Switch, Budget-Status) |
| 5 | `backend/src/services/exceptions.py` | **Editieren** | `BudgetExhaustedError` hinzufügen |
| 6 | `backend/src/services/policy_engine.py` | **Editieren** | Kill-Switch-Stub ersetzen + Drawdown-Stub ersetzen |
| 7 | `backend/src/agents/fundamental.py` | **Editieren** | Model-Routing über Budget-Manager |
| 8 | `backend/src/agents/claim_extractor.py` | **Editieren** | Model-Routing über Budget-Manager |
| 9 | `backend/src/services/fundamental_analysis.py` | **Editieren** | degraded Flag durchreichen |
| 10 | `backend/src/services/claim_extraction.py` | **Editieren** | degraded Flag durchreichen |
| 11 | `backend/src/services/trade_execution.py` | **Editieren** | executed_price persistieren |
| 12 | `backend/src/services/circuit_breaker.py` | **Editieren** | CB-Open → Kill-Switch Bridge |
| 13 | `backend/src/routes/trades.py` | **Editieren** | Status-Allowlist |
| 14 | `backend/src/main.py` | **Editieren** | system Router hinzufügen |
| 15 | `backend/tests/test_kill_switch.py` | **Erstellen** | Kill-Switch Tests (~25 Tests) |
| 16 | `backend/tests/test_budget_manager.py` | **Erstellen** | Budget-Manager Tests (~15 Tests) |
| 17 | `backend/tests/test_system_route.py` | **Erstellen** | System Route Tests (~10 Tests) |
| 18 | Bestehende Test-Dateien | **Editieren** | Anpassungen für Kill-Switch / Budget-Fallback Integration |

---

## Arbeitspaket 1: Kill-Switch System

### DB-Migration: `system_state` Tabelle

```sql
-- System-wide state (single row for MVP).
-- Kill-Switch + Highwater Mark for drawdown tracking.
-- Not user-scoped: maturity_stage is GLOBAL (see MEMORY.md).
CREATE TABLE system_state (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kill_switch_active BOOLEAN NOT NULL DEFAULT false,
  kill_switch_reason TEXT,                                  -- 'auto_drawdown', 'auto_broker_cb', 'auto_verification', 'manual'
  kill_switch_activated_at TIMESTAMPTZ,
  highwater_mark_value DECIMAL(12,4),                       -- highest observed portfolio value
  highwater_mark_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- FIX I4: Idempotent seed with fixed UUID (safe for re-runs and test environments)
INSERT INTO system_state (id)
VALUES ('00000000-0000-0000-0000-000000000001'::uuid)
ON CONFLICT (id) DO NOTHING;

-- RLS: service_role writes (backend), authenticated reads
ALTER TABLE system_state ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated users can read system state"
  ON system_state FOR SELECT
  USING (auth.role() = 'authenticated');
-- No INSERT/UPDATE policy for anon/authenticated — only service_role writes

-- Migration: Add executed_price to trade_log
ALTER TABLE trade_log ADD COLUMN executed_price DECIMAL(12,4);
```

**Hinweise:**
- `system_state` hat genau 1 Zeile — alle Reads/Writes sind auf diese Zeile. Kein INSERT nötig nach dem Seed.
- Seed INSERT nutzt feste UUID + `ON CONFLICT DO NOTHING` — sicher bei mehrfacher Ausführung (Tests, DB-Reset).
- `kill_switch_reason` ist nullable — NULL wenn Kill-Switch inaktiv.
- RLS: Nur authenticated SELECT. Schreibzugriff NUR via service_role (Backend).
- `executed_price` in `trade_log` ist nullable — bestehende Rows bekommen NULL (kein Backfill nötig).

### `kill_switch.py` — Neue Datei

```python
"""Kill-Switch system for MyTrade.

The kill-switch halts all new trade proposals when dangerous conditions
are detected. It does NOT close existing positions (no panic sell).

Triggers:
  1. Portfolio drawdown >= max_drawdown_pct (from effective policy)
  2. Alpaca circuit breaker opens (broker unreachable)
  3. Verification rate < 70% (too many unverified claims)
  4. Manual activation by user

Effect:
  - System enters Advisory-Only mode (Stufe 0 equivalent)
  - No new order proposals (propose_trade blocked)
  - Analysis still allowed (data collection + analysis run)
  - Manual reactivation required

State:
  - Persisted in system_state table (single row)
  - Pre-Policy reads kill_switch_active before every trade proposal
"""

import logging
from datetime import datetime, timezone

from src.services.error_logger import log_error
from src.services.supabase import get_supabase_admin

logger = logging.getLogger(__name__)
```

**Funktionen:**

1. **`is_kill_switch_active() -> bool`**
   - Liest `system_state.kill_switch_active` aus DB
   - Bei DB-Fehler: `True` zurückgeben (fail-safe — im Zweifel blockieren)
   - Wird von Pre-Policy aufgerufen (Zeile 327-330 in policy_engine.py)

2. **`activate_kill_switch(reason: str) -> dict`**
   - Setzt `kill_switch_active=True`, `kill_switch_reason=reason`, `kill_switch_activated_at=now()`
   - Loggt via `log_error("kill_switch", "activated", ...)`
   - Idempotent: wenn bereits aktiv, nur loggen und aktuellen State zurückgeben
   - Returns: `{"active": True, "reason": reason, "activated_at": timestamp}`

3. **`deactivate_kill_switch() -> dict`**
   - Setzt `kill_switch_active=False`, `kill_switch_reason=NULL`, `kill_switch_activated_at=NULL`
   - Loggt via `log_error("kill_switch", "deactivated", ...)`
   - Returns: `{"active": False}`

4. **`get_kill_switch_status() -> dict`**
   - Returns: `{"active": bool, "reason": str|None, "activated_at": str|None}`
   - Reine Lese-Operation, kein Side-Effect

5. **`evaluate_kill_switch_triggers(user_id: str) -> dict`**
   - Prüft alle 3 automatischen Trigger und aktiviert Kill-Switch wenn nötig
   - **Trigger 1 — Drawdown:** Berechnet aktuellen Portfolio-Wert aus `portfolio_holdings` + Broker `get_account()`. Vergleicht mit `highwater_mark_value` aus `system_state`. Wenn Drawdown ≥ `max_drawdown_pct` (aus `get_effective_policy()`) → aktivieren.
   - **Trigger 2 — Broker CB:** Prüft `alpaca_breaker.get_state()["state"]`. Wenn `"open"` → aktivieren.
   - **Trigger 3 — Verification Rate:** Berechnet Quote aus den letzten 5 Analysen (einstellbar). Wenn < 70% Claims mit Status `verified`/`consistent` → aktivieren.
   - **Highwater-Mark Update:** Wenn aktueller Portfolio-Wert > `highwater_mark_value` → Update in DB.
   - **Hinweis (FIX I5):** Diese Funktion wird on-demand aufgerufen (via API-Endpoint oder vor Trade-Proposals), NICHT automatisch nach Trade-Execution. Der Highwater-Mark wird opportunistisch von `approve_trade()` aktualisiert, aber die Trigger-Evaluation passiert erst beim nächsten Aufruf. Für automatische periodische Prüfung → Step 12 Cron-Job.
   - Returns: `{"triggered": bool, "reason": str|None, "checks": {"drawdown": {...}, "broker_cb": {...}, "verification_rate": {...}}}`

6. **`update_highwater_mark(portfolio_value: float) -> None`**
   - Aktualisiert `system_state.highwater_mark_value` wenn `portfolio_value > current_highwater`
   - Wird von `evaluate_kill_switch_triggers()` intern aufgerufen
   - Auch von `approve_trade()` aufgerufen nach erfolgreicher Execution (opportunistisches Update)

### Kill-Switch Trigger-Logik im Detail

**Trigger 1 — Portfolio Drawdown:**
```python
def _check_drawdown_trigger(user_id: str) -> dict:
    """Check if portfolio drawdown exceeds threshold.

    Portfolio value = sum of (shares * current_price) from portfolio_holdings.
    Highwater mark = highest value ever observed (from system_state).
    Drawdown = (highwater - current) / highwater * 100

    If no portfolio_holdings exist or no highwater mark → no trigger.
    """
    admin = get_supabase_admin()

    # FIX C: Fallback to YAML default (20%) if get_effective_policy() fails
    try:
        policy = get_effective_policy(user_id)
        max_drawdown_pct = policy.max_drawdown_pct
    except Exception as exc:
        logger.warning("Failed to read effective policy for drawdown check, using YAML default 20%%: %s", exc)
        max_drawdown_pct = 20.0  # ips-template.yaml default

    # Read current portfolio value from holdings
    holdings = admin.table("portfolio_holdings").select("*").eq("user_id", user_id).eq("status", "active").execute()
    portfolio_value = sum(
        float(h["shares"]) * float(h["current_price"])
        for h in (holdings.data or [])
        if h.get("current_price") and h.get("shares")
    )

    if portfolio_value == 0:
        return {"triggered": False, "drawdown_pct": 0.0, "threshold_pct": max_drawdown_pct}

    # Read highwater mark
    state = _read_system_state(admin)
    highwater = float(state.get("highwater_mark_value") or 0)

    # Update highwater if current value is higher
    if portfolio_value > highwater:
        update_highwater_mark(portfolio_value)
        highwater = portfolio_value

    if highwater == 0:
        return {"triggered": False, "drawdown_pct": 0.0, "threshold_pct": max_drawdown_pct}

    drawdown_pct = ((highwater - portfolio_value) / highwater) * 100

    return {
        "triggered": drawdown_pct >= max_drawdown_pct,
        "drawdown_pct": round(drawdown_pct, 2),
        "threshold_pct": max_drawdown_pct,
        "portfolio_value": portfolio_value,
        "highwater_mark": highwater,
    }
```

**Trigger 2 — Broker Circuit Breaker:**
```python
def _check_broker_cb_trigger() -> dict:
    """Check if Alpaca circuit breaker is open.

    Per execution-contract.md: "5 aufeinanderfolgende Broker-API-Fehler"
    → Circuit Breaker opens → Kill-Switch triggers.

    Note: We check the Alpaca CB state, not Finnhub/AV (data providers).
    Data provider failures degrade analysis quality but don't affect trading.
    Broker failures mean we can't execute trades at all.
    """
    from src.services.circuit_breaker import alpaca_breaker

    state = alpaca_breaker.get_state()
    return {
        "triggered": state["state"] == "open",
        "broker_state": state["state"],
        "failure_count": state["failure_count"],
    }
```

**Trigger 3 — Verification Rate:**
```python
VERIFICATION_LOOKBACK = 5  # Number of recent analysis runs to check

def _check_verification_rate_trigger(user_id: str) -> dict:
    """Check if verification rate is below 70%.

    Verification rate = (verified + consistent) / total_claims * 100
    from the last VERIFICATION_LOOKBACK completed analysis runs.

    If no completed analyses → no trigger (system hasn't started yet).
    """
    admin = get_supabase_admin()

    # Get recent completed analysis_run IDs
    runs = (
        admin.table("analysis_runs")
        .select("id")
        .eq("user_id", user_id)
        .in_("status", ["completed", "partial"])
        .order("started_at", desc=True)
        .limit(VERIFICATION_LOOKBACK)
        .execute()
    )
    run_ids = [r["id"] for r in (runs.data or [])]

    if not run_ids:
        return {"triggered": False, "rate_pct": 100.0, "threshold_pct": 70.0, "sample_size": 0}

    # Get all claims for these runs
    claims = (
        admin.table("claims")
        .select("id")
        .in_("analysis_id", run_ids)
        .execute()
    )
    total_claims = len(claims.data or [])

    if total_claims == 0:
        return {"triggered": False, "rate_pct": 100.0, "threshold_pct": 70.0, "sample_size": 0}

    claim_ids = [c["id"] for c in claims.data]

    # Get verification results for these claims
    verifications = (
        admin.table("verification_results")
        .select("status")
        .in_("claim_id", claim_ids)
        .execute()
    )
    verified_count = sum(
        1 for v in (verifications.data or [])
        if v["status"] in ("verified", "consistent")
    )

    # Rate = verified+consistent / total claims (not just cross-checked claims)
    # Claims without verification_results are implicitly "unverified"
    rate_pct = (verified_count / total_claims) * 100

    return {
        "triggered": rate_pct < 70.0,
        "rate_pct": round(rate_pct, 2),
        "threshold_pct": 70.0,
        "total_claims": total_claims,
        "verified_claims": verified_count,
        "sample_size": len(run_ids),
    }
```

### Integration in Pre-Policy (`policy_engine.py`)

Aktueller Stub (Zeile 327-330):
```python
    # 2. Kill-Switch aktiv?
    # MVP: Prüfe portfolio_holdings Drawdown wenn Portfolio-Daten existieren.
    # Sonst: Skip (kein Portfolio = kein Drawdown).
    # TODO: Dedizierter Kill-Switch-State in DB (Step 11+)
```

Neuer Code:
```python
    # 2. Kill-Switch aktiv?
    from src.services.kill_switch import is_kill_switch_active

    if is_kill_switch_active():
        violations.append(PolicyViolation(
            rule="kill_switch",
            # FIX I1: Nur Trades blockiert — Analysen bleiben erlaubt (Advisory-Only = Stufe 0).
            # Konsistent mit execution-contract.md Stufe 0 und kill_switch.py Docstring.
            message="Kill-Switch is active — system is in Advisory-Only mode. No new trades allowed.",
            severity="blocking",
            current_value=True,
            limit_value=False,
        ))
```

**Architektur-Hinweis:** `run_pre_policy()` wird NUR vom `/api/policy/pre-check/{ticker}` Endpoint und intern von `propose_trade()` aufgerufen — NICHT von `/api/analyze/{ticker}`. Dadurch bleiben Analysen bei aktivem Kill-Switch erlaubt. Dies ist beabsichtigt (Advisory-Only = Stufe 0, siehe execution-contract.md) und darf NICHT geändert werden.

**Hinweis zum Import:** Der Import ist INNERHALB der Funktion (lazy import), um zirkuläre Imports zu vermeiden. `kill_switch.py` importiert `get_effective_policy` aus `policy_engine.py`, und `policy_engine.py` importiert `is_kill_switch_active` aus `kill_switch.py`. Lazy Import bricht den Zirkel. Alternative: `is_kill_switch_active()` in `kill_switch.py` darf NICHT `get_effective_policy()` importieren — das macht nur `evaluate_kill_switch_triggers()`.

**Wichtig:** Prüfe ob der Zirkel tatsächlich existiert. `is_kill_switch_active()` liest nur `system_state` — kein Import von `policy_engine` nötig. Nur `evaluate_kill_switch_triggers()` braucht `get_effective_policy()` für den Drawdown-Threshold. Wenn `is_kill_switch_active()` keinen Policy-Import hat, kann der Import in `policy_engine.py` auf Top-Level sein (kein lazy Import nötig). Prüfe dies beim Implementieren.

### Integration in Drawdown-Check (Full-Policy)

Der bestehende Drawdown-Check in `run_full_policy()` (Zeile 421-433) bleibt bestehen — er prüft den Drawdown-Threshold aus der Policy. Der bestehende Stub `_calculate_portfolio_drawdown()` (Zeile 586-592) wird durch eine echte Implementierung ersetzt:

**FIX I2:** Die Funktion nimmt `highwater` als Parameter entgegen — konsistent mit dem bestehenden Pattern "Pure helpers have NO DB access" (Docstring policy_engine.py). Der DB-Read für den Highwater-Wert passiert im Caller `run_full_policy()`.

```python
def _calculate_portfolio_drawdown(holdings: list[dict], highwater: float) -> float:
    """Calculate portfolio drawdown from highwater mark.

    Pure function — no DB access. Highwater mark is passed in by caller.
    Returns 0.0 if no highwater mark exists or no holdings.
    """
    portfolio_value = _calculate_portfolio_value(holdings)
    if portfolio_value == 0 or highwater == 0:
        return 0.0

    drawdown = ((highwater - portfolio_value) / highwater) * 100
    return max(0.0, drawdown)  # No negative drawdown
```

Im Caller `run_full_policy()` (Zeile 421-433) wird der Highwater-Wert aus `system_state` gelesen und an die Funktion übergeben:

```python
    # In run_full_policy(), vor dem Drawdown-Check:
    try:
        admin = get_supabase_admin()
        state = admin.table("system_state").select("highwater_mark_value").limit(1).execute()
        highwater = float(state.data[0]["highwater_mark_value"]) if state.data and state.data[0].get("highwater_mark_value") else 0.0
    except Exception:
        highwater = 0.0  # No highwater → no drawdown check possible

    drawdown = _calculate_portfolio_drawdown(holdings, highwater)
```

### CB-to-Kill-Switch Bridge (`circuit_breaker.py`)

In `record_failure()` (Zeile 90+), wenn der Circuit Breaker für Alpaca von closed→open wechselt:

```python
    if (
        self._state == "closed"
        and self._failure_count >= FAILURE_THRESHOLD
    ):
        self._state = "open"
        self._last_failure_time = time.monotonic()
        # ...existing logging...

        # Kill-Switch Bridge: Alpaca CB open → trigger kill-switch
        if self.provider == "alpaca":
            try:
                from src.services.kill_switch import activate_kill_switch
                activate_kill_switch("auto_broker_cb")
            except Exception as exc:
                logger.warning("Failed to activate kill-switch from CB: %s", exc)
```

**Warum nur Alpaca:** Finnhub/AV CB-Open bedeutet degradierte Analyse-Qualität, aber keine Gefahr für Trades. Alpaca CB-Open bedeutet: der Broker ist nicht erreichbar → wir können keine Trades ausführen → System muss sich schützen.

**Lazy Import:** `activate_kill_switch` wird lazy importiert um den `circuit_breaker.py` → `kill_switch.py` Dependency-Chain klein zu halten. Circuit Breaker sollte minimal bleiben.

### API-Endpoints (`routes/system.py`)

Neue Route-Datei:

```python
"""System endpoints — Kill-Switch and Budget status.

These are system-level operations, not user-specific data.
For MVP (single user): all endpoints require authentication.
"""

from fastapi import APIRouter, Depends, Request

from src.dependencies.auth import require_auth
from src.dependencies.rate_limit import create_rate_limit

router = APIRouter(prefix="/api/system", tags=["system"])
```

**Endpoints:**

| Method | Path | Rate Limit | Zweck |
|--------|------|-----------|-------|
| `GET` | `/kill-switch` | 30/min | Kill-Switch-Status abfragen |
| `POST` | `/kill-switch/activate` | 10/min | Kill-Switch manuell aktivieren |
| `POST` | `/kill-switch/deactivate` | 10/min | Kill-Switch manuell deaktivieren |
| `POST` | `/kill-switch/evaluate` | 10/min | Alle Trigger prüfen (on-demand Monitoring) |
| `GET` | `/budget` | 30/min | Budget-Status pro Tier + Gesamt |

**`GET /kill-switch`:**
```python
@router.get("/kill-switch")
@create_rate_limit("30/minute")
async def get_kill_switch(request: Request, user_id: str = Depends(require_auth)):
    from src.services.kill_switch import get_kill_switch_status
    return get_kill_switch_status()
```

**`POST /kill-switch/activate`:**
```python
@router.post("/kill-switch/activate")
@create_rate_limit("10/minute")
async def activate(request: Request, user_id: str = Depends(require_auth)):
    from src.services.kill_switch import activate_kill_switch
    return activate_kill_switch("manual")
```

**`POST /kill-switch/deactivate`:**
```python
@router.post("/kill-switch/deactivate")
@create_rate_limit("10/minute")
async def deactivate(request: Request, user_id: str = Depends(require_auth)):
    from src.services.kill_switch import deactivate_kill_switch
    return deactivate_kill_switch()
```

**`POST /kill-switch/evaluate`:**
```python
@router.post("/kill-switch/evaluate")
@create_rate_limit("10/minute")
async def evaluate(request: Request, user_id: str = Depends(require_auth)):
    from src.services.kill_switch import evaluate_kill_switch_triggers
    return evaluate_kill_switch_triggers(user_id)
```

**`GET /budget`:**
```python
@router.get("/budget")
@create_rate_limit("30/minute")
async def get_budget(request: Request, user_id: str = Depends(require_auth)):
    from src.services.budget_manager import get_budget_status
    return get_budget_status()
```

---

## Arbeitspaket 2: Budget-Fallback (3-Tier Model-Routing)

### `budget_manager.py` — Neue Datei

```python
"""Budget manager for 3-Tier LLM model routing.

Tracks monthly API spend per tier (Heavy/Standard/Light) from agent_cost_log.
When a tier's budget is exhausted, requests are degraded to the next-lower tier.

Budget caps (from docs/03_architecture/monitoring.md):
  Heavy (Opus):    $30/month hard cap
  Standard (Sonnet): $20/month hard cap
  Light (Haiku):   $5/month hard cap
  Total:           $55/month hard cap

Degradation chain:
  Opus → Sonnet → Haiku → BudgetExhaustedError

MVP: Only Standard (fundamental.py) and Light (claim_extractor.py) are active.
Opus agents (Devil's Advocate, Synthesizer) are Phase 2+.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from src.services.error_logger import log_error
from src.services.exceptions import BudgetExhaustedError
from src.services.supabase import get_supabase_admin

logger = logging.getLogger(__name__)

# --- Budget Caps (from monitoring.md, not ENV-configurable in MVP) ---

BUDGET_CAPS = {
    "heavy": 30.0,    # $30/month for Opus
    "standard": 20.0, # $20/month for Sonnet
    "light": 5.0,     # $5/month for Haiku
}
TOTAL_BUDGET_CAP = 55.0  # $55/month total

# Soft cap warning threshold (80%)
SOFT_CAP_RATIO = 0.80

# Model IDs per tier
TIER_MODELS = {
    "heavy": "claude-opus-4-6",
    "standard": "claude-sonnet-4-6",
    "light": "claude-haiku-4-5",
}

# Degradation chain
DEGRADATION_CHAIN = {
    "heavy": "standard",    # Opus → Sonnet
    "standard": "light",    # Sonnet → Haiku
    # "light" has no degradation target — BudgetExhaustedError
}
```

**Datenklassen:**

```python
@dataclass
class BudgetStatus:
    """Current monthly budget status per tier."""
    heavy_spent: float
    heavy_remaining: float
    heavy_cap: float
    standard_spent: float
    standard_remaining: float
    standard_cap: float
    light_spent: float
    light_remaining: float
    light_cap: float
    total_spent: float
    total_remaining: float
    total_cap: float

@dataclass
class ModelRouting:
    """Result of model routing decision."""
    model_id: str          # The actual model to use
    tier: str              # The actual tier (may differ from requested)
    degraded: bool         # True if budget-fallback is active
    original_tier: str     # What was originally requested
```

**Funktionen:**

1. **`get_monthly_spend() -> dict[str, float]`**
   - Liest `agent_cost_log` für den aktuellen Monat
   - `SELECT tier, SUM(cost_usd) FROM agent_cost_log WHERE timestamp >= first_of_month GROUP BY tier`
   - Returns: `{"heavy": 0.0, "standard": 5.23, "light": 1.10}`

2. **`get_budget_status() -> dict`**
   - Berechnet Remaining pro Tier + Gesamt
   - Gibt Dict zurück (für API-Response)
   - Enthält `warnings[]` wenn Soft Cap (80%) erreicht

3. **`get_model_for_tier(requested_tier: str) -> ModelRouting`**
   - Kern-Funktion: Bestimmt welches Modell tatsächlich genutzt wird
   - Prüft Total Cap zuerst (wenn erschöpft → `BudgetExhaustedError`)
   - Prüft Tier Cap: wenn erschöpft → nächst-niedrigeres Tier
   - Wenn Light-Tier erschöpft → `BudgetExhaustedError`
   - Loggt Degradierung via `log_error("budget_manager", "budget_degraded", ...)`
   - Returns: `ModelRouting(model_id="claude-haiku-4-5", tier="light", degraded=True, original_tier="standard")`

```python
def get_model_for_tier(requested_tier: str) -> ModelRouting:
    """Determine which model to use based on budget availability.

    Checks total cap first, then tier cap. If tier budget is
    exhausted, degrades to next-lower tier. If no lower tier
    available (light exhausted), raises BudgetExhaustedError.

    Returns ModelRouting with actual model_id, tier, and degraded flag.
    """
    spend = get_monthly_spend()
    total_spent = sum(spend.values())

    # Hard cap: total budget exhausted
    if total_spent >= TOTAL_BUDGET_CAP:
        log_error("budget_manager", "budget_exhausted",
                  f"Total monthly budget ${TOTAL_BUDGET_CAP} exhausted (spent: ${total_spent:.2f})")
        raise BudgetExhaustedError(
            f"Monthly API budget exhausted (${total_spent:.2f}/${TOTAL_BUDGET_CAP})"
        )

    # Check requested tier
    tier = requested_tier
    degraded = False

    while tier in BUDGET_CAPS:
        tier_spent = spend.get(tier, 0.0)
        tier_cap = BUDGET_CAPS[tier]

        if tier_spent < tier_cap:
            # Budget available for this tier
            if tier != requested_tier:
                degraded = True
                logger.warning(
                    "Budget degradation: %s -> %s (spent $%.2f/$%.2f for %s)",
                    requested_tier, tier, spend.get(requested_tier, 0), BUDGET_CAPS[requested_tier], requested_tier,
                )
                log_error("budget_manager", "budget_degraded",
                          f"Degraded {requested_tier} -> {tier}")

            return ModelRouting(
                model_id=TIER_MODELS[tier],
                tier=tier,
                degraded=degraded,
                original_tier=requested_tier,
            )

        # Tier exhausted — try next lower
        next_tier = DEGRADATION_CHAIN.get(tier)
        if next_tier is None:
            # No lower tier available (light exhausted)
            log_error("budget_manager", "budget_exhausted",
                      f"All tiers exhausted (light spent: ${tier_spent:.2f}/${tier_cap})")
            raise BudgetExhaustedError(
                f"Light tier budget exhausted (${tier_spent:.2f}/${tier_cap})"
            )
        tier = next_tier
        degraded = True

    # Should never reach here
    return ModelRouting(
        model_id=TIER_MODELS[requested_tier],
        tier=requested_tier,
        degraded=False,
        original_tier=requested_tier,
    )
```

### `BudgetExhaustedError` Exception

```python
# In exceptions.py hinzufügen:

class BudgetExhaustedError(Exception):
    """Monthly API budget exhausted.

    Raised when no LLM calls are allowed until the next month.
    Not a DataProviderError — this is a system policy error, not a provider failure.
    """
    pass
```

**Warum nicht `DataProviderError`:** Budget-Erschöpfung ist kein Provider-Fehler — die API funktioniert, wir wollen sie nur nicht aufrufen. Es ist ein Policy-Fehler (ähnlich wie `ConfigurationError`). Kein Retry-Versuch sinnvoll.

### Integration in `fundamental.py`

Aktuelle Zeile 24:
```python
MODEL_ID = "claude-sonnet-4-6"
```

Änderung: `MODEL_ID` wird nicht mehr als Konstante definiert, sondern dynamisch aufgelöst:

```python
from src.services.budget_manager import get_model_for_tier

# Entferne: MODEL_ID = "claude-sonnet-4-6"

def call_fundamental_agent(ticker, fundamentals, current_price):
    """..."""
    routing = get_model_for_tier("standard")
    model_id = routing.model_id

    client = _get_client()
    user_prompt = _build_user_prompt(ticker, fundamentals, current_price)
    total_usage = {"input_tokens": 0, "output_tokens": 0}

    try:
        response = client.messages.parse(
            model=model_id,  # ← dynamisch statt hardcoded
            max_tokens=MAX_OUTPUT_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            output_format=FundamentalAnalysis,
        )
        # ...rest of existing logic...

    # Return signature erweitern um routing info:
    return response.parsed_output.model_dump(), total_usage, routing
```

**Return-Wert erweitern:** `call_fundamental_agent()` gibt jetzt ein 3-Tuple zurück: `(analysis_dict, usage, routing)`. Der Caller (`fundamental_analysis.py`) nutzt `routing.degraded` und `routing.model_id` für das Cost-Logging.

**Bestehende Error-Pfade:** `AgentError` und `anthropic.APITimeoutError` Handler müssen den `routing` weiterhin verfügbar haben (ist im Function Scope, kein Problem).

**BudgetExhaustedError:** Wird NICHT in `fundamental.py` gefangen — propagiert zum Caller (`fundamental_analysis.py`) und weiter zum Route-Handler. Route gibt 503 zurück.

### Integration in `claim_extractor.py`

Aktuelle Zeilen 24-25:
```python
MODEL_HAIKU = "claude-haiku-4-5"
MODEL_SONNET = "claude-sonnet-4-6"
```

Änderung: Dynamische Model-Resolution in `call_claim_extractor()`:

```python
from src.services.budget_manager import get_model_for_tier, ModelRouting

def call_claim_extractor(ticker, fundamental_out):
    """..."""
    # Resolve models at call time
    light_routing = get_model_for_tier("light")
    haiku_model = light_routing.model_id

    # Sonnet fallback: resolve only when needed (in _attempt_extraction)
    # to avoid unnecessary budget checks
    # ...
```

**Fallback-Chain Anpassung:**
- Attempt 1 (Haiku): Nutzt `light_routing.model_id`
- Attempt 2 (Haiku Retry): Gleiche Model-ID
- Attempt 3 (Sonnet Fallback): Ruft `get_model_for_tier("standard")` auf. Wenn Standard-Budget erschöpft → `BudgetExhaustedError` → AgentError (alle 3 Versuche fehlgeschlagen, kein Sonnet-Fallback verfügbar)

**Return-Wert erweitern:** `call_claim_extractor()` gibt jetzt ein 3-Tuple zurück: `(raw_claims_list, usage_dict, routing)`. Der `routing` Wert ist das Routing des **letzten erfolgreichen** Attempts — bei Attempt 1+2 (Light-Tier) ist es `light_routing`, bei Attempt 3 (Standard-Fallback) das Standard-Routing. Der Caller (`claim_extraction.py`) nutzt `routing.degraded` und `routing.model_id` für das Cost-Logging.

**FIX I3 — Trade-off bei Budget-Degradation:** Wenn der Standard-Tier nicht exhausted sondern nur *degradiert* ist (z.B. Standard→Light), gibt `get_model_for_tier("standard")` Haiku zurück. Das bedeutet: Attempt 3 (Quality-Fallback) nutzt dasselbe Modell wie Attempt 1+2 — die Quality-Escalation ist effektiv deaktiviert. Dies ist ein bewusster Trade-off: Budget-Schutz hat Priorität über Quality-Fallback. Im MVP akzeptabel — der Quality-Fallback greift weiterhin bei Schema-Fehlern (wenn Budget verfügbar), nur nicht bei Budget-Degradation.

**Pricing:** Die Pricing-Konstanten (`HAIKU_INPUT_PRICE`, `SONNET_INPUT_PRICE`) bleiben erhalten — sie werden für Cost-Berechnung gebraucht. Aber sie müssen zum tatsächlich genutzten Modell passen. **Lösung:** Eine Pricing-Map in `budget_manager.py`:

```python
MODEL_PRICING = {
    "claude-opus-4-6": {"input": 15.0 / 1_000_000, "output": 75.0 / 1_000_000},
    "claude-sonnet-4-6": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "claude-haiku-4-5": {"input": 0.80 / 1_000_000, "output": 4.0 / 1_000_000},
}

def get_pricing(model_id: str) -> dict:
    """Return input/output pricing for a model."""
    return MODEL_PRICING.get(model_id, MODEL_PRICING["claude-sonnet-4-6"])
```

Dann in `fundamental.py` und `claim_extractor.py`:
```python
from src.services.budget_manager import get_pricing

pricing = get_pricing(routing.model_id)
cost = (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])
```

### Integration in Cost-Logging (`fundamental_analysis.py` + `claim_extraction.py`)

**`fundamental_analysis.py` (Zeile 174-186):**

Aktuell:
```python
admin.table("agent_cost_log").insert({
    "agent_name": "fundamental_analyst",
    "model": "claude-sonnet-4-6",       # ← hardcoded
    "tier": "standard",                 # ← hardcoded
    "degraded": False,                  # ← hardcoded
    # ...
}).execute()
```

Neu (nutzt routing aus Agent-Return):
```python
admin.table("agent_cost_log").insert({
    "agent_name": "fundamental_analyst",
    "model": routing.model_id,          # ← aus Budget-Manager
    "tier": routing.tier,               # ← aus Budget-Manager
    "degraded": routing.degraded,       # ← aus Budget-Manager
    "fallback_from": routing.original_tier if routing.degraded else None,
    # ...
}).execute()
```

**`claim_extraction.py` (Zeile 274-286):** Gleiche Änderung — `model`, `tier`, `degraded`, `fallback_from` aus Routing-Info.

### BudgetExhaustedError Handling in Routes

**`routes/analysis.py`:** Muss `BudgetExhaustedError` fangen und 503 zurückgeben:
```python
from src.services.exceptions import BudgetExhaustedError

@router.post("/analyze/{ticker}")
async def analyze(ticker: str, ...):
    try:
        result = run_fundamental_analysis(ticker, user_id)
    except BudgetExhaustedError:
        raise HTTPException(503, "Monthly API budget exhausted. Try again next month.")
    # ...existing code...
```

**`routes/claims.py`:** Gleicher Handler für `extract_claims`.

---

## Arbeitspaket 3: Open-Issue Cleanup

### 3a: executed_price in trade_log persistieren

**Problem (aus MEMORY.md):** `approve_trade()` gibt `executed_price` im Response zurück (Zeile 147 trade_execution.py), schreibt es aber NICHT in die DB.

**Lösung:** DB-Migration fügt `executed_price DECIMAL(12,4)` zu `trade_log` hinzu (siehe Migration oben). `approve_trade()` schreibt es beim Update:

```python
# In trade_execution.py, Zeile 138-142:
admin.table("trade_log").update({
    "status": "executed",
    "broker_order_id": result.broker_order_id,
    "executed_at": executed_at,
    "executed_price": result.executed_price,  # ← NEU
}).eq("id", trade_id).execute()
```

### 3b: list_trades Status-Allowlist

**Problem (aus MEMORY.md):** `GET /api/trades?status=anything` akzeptiert beliebige Strings.

**Lösung:** In `routes/trades.py`, `list_trades()` Endpoint:
```python
VALID_TRADE_STATUSES = frozenset({"proposed", "approved", "rejected", "executed", "failed", "expired"})

@router.get("/")
async def list_trades(request: Request, status: str | None = None, ...):
    if status and status not in VALID_TRADE_STATUSES:
        raise HTTPException(400, f"Invalid status filter. Allowed: {', '.join(sorted(VALID_TRADE_STATUSES))}")
    # ...existing code...
```

### 3c: Drawdown-Stub ersetzen

Siehe Arbeitspaket 1 oben — `_calculate_portfolio_drawdown()` wird durch echte Highwater-Mark-Logik ersetzt.

---

## Test-Strategie

### `test_kill_switch.py` (~25 Tests)

**Unit Tests:**
- `is_kill_switch_active()` — aktiv → True
- `is_kill_switch_active()` — inaktiv → False
- `is_kill_switch_active()` — DB-Fehler → True (fail-safe)
- `activate_kill_switch("manual")` — setzt active=True, reason="manual"
- `activate_kill_switch()` — idempotent (schon aktiv → kein Fehler)
- `deactivate_kill_switch()` — setzt active=False, reason=NULL
- `get_kill_switch_status()` — gibt korrektes Dict zurück

**Trigger Tests:**
- `_check_drawdown_trigger()` — Drawdown 25% ≥ 20% Threshold → triggered=True
- `_check_drawdown_trigger()` — Drawdown 15% < 20% → triggered=False
- `_check_drawdown_trigger()` — Kein Portfolio → triggered=False
- `_check_drawdown_trigger()` — Kein Highwater Mark → triggered=False
- `_check_drawdown_trigger()` — Portfolio-Wert > Highwater → Highwater updated
- `_check_broker_cb_trigger()` — Alpaca CB open → triggered=True
- `_check_broker_cb_trigger()` — Alpaca CB closed → triggered=False
- `_check_verification_rate_trigger()` — Rate 60% < 70% → triggered=True
- `_check_verification_rate_trigger()` — Rate 80% > 70% → triggered=False
- `_check_verification_rate_trigger()` — Keine Analysen → triggered=False
- `evaluate_kill_switch_triggers()` — Drawdown Trigger → kill_switch aktiviert
- `evaluate_kill_switch_triggers()` — Kein Trigger → kill_switch bleibt inaktiv
- `evaluate_kill_switch_triggers()` — Kill-Switch schon aktiv → kein erneuter Aufruf

**Integration Tests:**
- Pre-Policy mit aktivem Kill-Switch → PolicyResult.passed=False, rule="kill_switch"
- Pre-Policy mit inaktivem Kill-Switch → PolicyResult.passed=True

**Mock-Pattern:** `@patch("src.services.kill_switch.get_supabase_admin")` für DB-Mocks. `_mock_admin_table()` Factory aus test_policy_engine.py wiederverwenden.

### `test_budget_manager.py` (~15 Tests)

**Unit Tests:**
- `get_monthly_spend()` — leere agent_cost_log → alle 0.0
- `get_monthly_spend()` — korrekte Summierung pro Tier
- `get_model_for_tier("standard")` — Budget verfügbar → Sonnet, degraded=False
- `get_model_for_tier("standard")` — Standard-Budget erschöpft → Haiku, degraded=True
- `get_model_for_tier("heavy")` — Heavy-Budget erschöpft → Sonnet, degraded=True
- `get_model_for_tier("heavy")` — Heavy+Standard erschöpft → Haiku, degraded=True
- `get_model_for_tier("light")` — Light-Budget erschöpft → BudgetExhaustedError
- `get_model_for_tier("standard")` — Total-Budget erschöpft → BudgetExhaustedError
- `get_budget_status()` — korrektes Dict mit remaining, warnings
- `get_budget_status()` — Soft Cap (80%) Warning enthalten
- `get_pricing("claude-sonnet-4-6")` — korrekte Preise
- `get_pricing("unknown-model")` — Fallback auf Sonnet-Preise

**Integration Tests:**
- `fundamental.py` mit degradiertem Model → cost_log.degraded=True
- `claim_extractor.py` mit degradiertem Light-Tier → korrekte Pricing

**Mock-Pattern:** `@patch("src.services.budget_manager.get_supabase_admin")` für Spend-Query.

### `test_system_route.py` (~10 Tests)

- `GET /api/system/kill-switch` — Returns status dict
- `POST /api/system/kill-switch/activate` — Aktiviert, returns active=True
- `POST /api/system/kill-switch/deactivate` — Deaktiviert, returns active=False
- `POST /api/system/kill-switch/evaluate` — Returns trigger checks
- `GET /api/system/budget` — Returns budget status
- Auth required: alle Endpoints ohne Token → 401
- Rate Limit: 10/min für activate/deactivate

**Mock-Pattern:** `auth_client` Fixture aus conftest.py + `@patch` auf Service-Funktionen.

### Bestehende Tests — Anpassungen

**`test_policy_engine.py`:**
- Bestehender Test `test_kill_switch_stub_does_not_block` → umbenennen und anpassen: Kill-Switch inaktiv → Pre-Policy passed
- Neuer Test: Kill-Switch aktiv → Pre-Policy blockt
- Drawdown-Check Tests anpassen: `_calculate_portfolio_drawdown(holdings, highwater)` nimmt Highwater als Parameter — bleibt pure, kein DB-Mock nötig. Bestehende Tests passen Funktionssignatur an (neuer `highwater` Parameter).

**`test_fundamental_agent.py`:**
- Neuer Test: `test_budget_degradation_uses_haiku` — Budget-Manager gibt Haiku zurück → messages.parse() mit Haiku-Model aufgerufen
- Neuer Test: `test_budget_exhausted_raises` — BudgetExhaustedError propagiert
- Bestehende Tests: `MODEL_ID` Referenzen anpassen (nicht mehr als Konstante)

**`test_claim_extractor.py`:**
- Neuer Test: Budget-Degradation für Light-Tier
- Bestehende Tests: Model-ID Assertions anpassen

**`test_fundamental_analysis.py`:**
- Neuer Test: `test_degraded_flag_in_cost_log` — degraded=True wird korrekt an agent_cost_log geschrieben
- Neuer Test: `test_budget_exhausted_returns_failed` — BudgetExhaustedError → AnalysisResult.status="failed"

**`test_trade_execution.py`:**
- Bestehender Test `test_successful_execution` → erweitern: `executed_price` in DB-Update vorhanden

**`test_trades_route.py`:**
- Neuer Test: `test_invalid_status_filter_returns_400` — `?status=invalid` → 400
- Neuer Test: `test_valid_status_filter_accepted` — `?status=executed` → 200

**`test_circuit_breaker.py`:**
- Neuer Test: `test_alpaca_cb_open_triggers_kill_switch` — Alpaca CB closed→open → activate_kill_switch aufgerufen
- Neuer Test: `test_finnhub_cb_open_does_not_trigger_kill_switch` — Finnhub CB open → kein Kill-Switch

---

## Architektur-Entscheidungen

### 1. Kill-Switch als separate Service-Datei (nicht in policy_engine.py)
Die Policy Engine ist deterministisch und liest nur DB-State. Der Kill-Switch hat eigene Business-Logik (Trigger-Evaluation, Highwater-Mark-Tracking, CB-Bridge). Separation of Concerns: Policy Engine fragt `is_kill_switch_active()`, Kill-Switch Service evaluiert und setzt den State.

### 2. system_state als Single-Row-Tabelle
Für MVP (single user) ist eine Tabelle mit genau einer Zeile die einfachste Lösung. Kein Key-Value-Store, kein JSON-Feld, kein Config-System. Jedes Feld hat einen klaren Typ. Spätere Erweiterung auf Multi-User: `user_id` Column hinzufügen.

### 3. Kill-Switch: fail-safe bei DB-Fehler
`is_kill_switch_active()` gibt `True` zurück wenn die DB nicht lesbar ist. Begründung: Im Zweifel blockieren (Conservative Safety). Ein fälschlich aktiver Kill-Switch blockiert nur neue Trades — bestehende Positionen bleiben unberührt. Das ist besser als ein fälschlich inaktiver Kill-Switch.

### 4. Budget-Manager als eigenständiger Service
Budget-Tracking und Model-Routing sind ein eigener Concern. `budget_manager.py` hat keine Abhängigkeit auf Agent-Code — Agents importieren den Budget-Manager, nicht umgekehrt. Leicht testbar: Mock die DB-Query, teste die Routing-Logik.

### 5. BudgetExhaustedError ist KEIN DataProviderError
Budget-Erschöpfung ist kein Provider-Fehler (die API funktioniert). Es ist ein Policy-Fehler — das System hat entschieden, keine weiteren Calls zu machen. Kein Retry sinnvoll. Propagiert zum Route-Handler → 503 "Budget exhausted".

### 6. CB-to-Kill-Switch Bridge nur für Alpaca
Finnhub/AV CB-Open degradiert Analyse-Qualität aber gefährdet keine Trades. Alpaca CB-Open bedeutet: Broker unreachbar → keine Trade-Execution möglich → Kill-Switch muss aktivieren. Konsistent mit execution-contract.md: "5 aufeinanderfolgende Broker-API-Fehler → Kill-Switch."

### 7. Model-Routing: Agents fragen Budget-Manager, nicht umgekehrt
Agents kennen ihren gewünschten Tier ("standard", "light"). Budget-Manager bestimmt das tatsächliche Modell. Return-Wert enthält `degraded` Flag für Cost-Logging. Pricing wird zentral im Budget-Manager definiert — keine duplizierten Pricing-Konstanten.

### 8. Drawdown: Highwater-Mark als Parameter statt DB-Read in Pure Helper
`_calculate_portfolio_drawdown(holdings, highwater)` bleibt eine pure Funktion (testbar ohne Mocks). Der DB-Read für den Highwater-Wert passiert im Caller (`run_full_policy()`). Alternativ: DB-Read in der Funktion — aber das bricht das bestehende Pattern "Pure helpers have NO DB access" aus dem Docstring.

### 9. Verification-Rate-Berechnung: Claims-basiert, nicht Analysis-basiert
Rate = `(verified + consistent) / total_claims`. Claims ohne verification_results Zeile sind implizit "unverified" und zählen zum Nenner. Das ist strenger als "verified / cross-checked" und konsistent mit den 70% Threshold aus execution-contract.md.

---

## Was NICHT implementiert wird (bewusst deferred)

| Feature | Warum deferred | Wann |
|---------|---------------|------|
| Cron-Job für Kill-Switch-Monitoring | Step 11 prüft on-demand (API-Endpoint). Periodische Prüfung braucht Scheduler-Infrastruktur. | Step 12 |
| Automatische Kill-Switch-Evaluation nach Trade-Execution | Highwater-Mark wird opportunistisch aktualisiert, Trigger-Evaluation aber nur on-demand. Für MVP (Paper Trading) akzeptabel. | Step 12 Cron |
| Push-Notification bei Kill-Switch | Kein Frontend-Push in Phase 3. Im MVP: Log-Eintrag + Dashboard-Query. | Phase 4 (Step 14 PWA) |
| Multi-User Kill-Switch (per-user) | MVP = single user | Phase 2+ |
| Opus Budget-Fallback | Kein Opus-Agent in MVP (Devil's Advocate + Synthesizer = Phase 2+) | Phase 2+ |
| Cache-Token Tracking im Budget | `cache_read_tokens` existiert in Schema, aber Budget-Manager zählt nur `cost_usd` | Phase 2+ (wenn Caching implementiert) |
| expire_stale_trades User-Scoping | MVP = single user, cross-user ist acceptable | Phase 2+ |
| Automatischer Kill-Switch bei Trade-Failure | Nur Broker-CB-Open triggert, nicht einzelne Trade-Fehler | Phase 2+ |
| Budget-Caps via ENV konfigurierbar | Code-Konstanten reichen für MVP | Phase 2+ |
| Highwater-Mark aus Broker Account (cash + positions) | MVP nutzt nur portfolio_holdings (kein cash) | Phase 2+ (IBKR Integration) |

---

## Wichtige Patterns zum Befolgen

- **Kein Circular Import:** `is_kill_switch_active()` darf NICHT `get_effective_policy()` importieren. Nur `evaluate_kill_switch_triggers()` tut das. Prüfe beim Implementieren ob Top-Level-Import oder Lazy-Import nötig ist.
- **Fail-Safe:** Kill-Switch `is_kill_switch_active()` → `True` bei DB-Fehler. Budget-Manager → `BudgetExhaustedError` bei DB-Fehler (konservativ: kein Geld ausgeben wenn unklar).
- **Pure Helpers:** `_calculate_portfolio_drawdown(holdings, highwater)` bekommt Highwater als Parameter. Kein DB-Read in Pure Helpers.
- **Error Logging:** Alle Kill-Switch-Events (`activated`, `deactivated`, Triggers) und Budget-Events (`budget_degraded`, `budget_exhausted`) über `log_error()` in `error_log` Tabelle.
- **Module-Level Imports vermeiden für kill_switch→policy_engine und umgekehrt:** Potentieller Zirkel. Lazy Import in Funktionen wenn nötig.
- **3-Tuple Return in Agents:** `call_fundamental_agent()` gibt `(analysis_dict, usage, routing)` zurück. Alle Caller anpassen.
- **`@patch` am Usage-Ort:** `patch("src.services.kill_switch.get_supabase_admin")` nicht `patch("src.services.supabase.get_supabase_admin")`
- **Mock-Table-Factory:** `_mock_admin_table()` Pattern aus test_policy_engine.py wiederverwenden
- **Bestehende Tests nicht brechen:** Alle 482 bestehenden Tests müssen weiterhin grün sein
- **Model-Pricing zentral:** Pricing-Konstanten in `budget_manager.py`, nicht in Agent-Dateien
- **Supabase Migration:** Migration in `supabase/migrations/` mit Timestamp-Prefix, auch via Supabase MCP anwenden
- **RLS:** `system_state` hat nur authenticated SELECT — kein User-Scoped Writing (service_role only)
- **Idempotenz:** `activate_kill_switch()` doppelt aufrufen → kein Fehler, loggt nur
- **Status-Allowlist:** `frozenset` für O(1) Lookup, sortiert in Error-Message

---

## Workflow

1. **Branch erstellen:** `feature/step-11-kill-switch-budget` von `main`
2. DB-Migration erstellen und anwenden (`system_state` Tabelle + `executed_price` Feld)
3. `backend/src/services/exceptions.py` editieren (`BudgetExhaustedError`)
4. `backend/src/services/kill_switch.py` erstellen (Kill-Switch Logik)
5. `backend/src/services/budget_manager.py` erstellen (Budget-Tracking + Model-Routing)
6. `backend/src/routes/system.py` erstellen (API-Endpoints)
7. `backend/src/main.py` editieren (system Router hinzufügen)
8. `backend/src/services/policy_engine.py` editieren (Kill-Switch-Stub ersetzen + Drawdown-Highwater)
9. `backend/src/services/circuit_breaker.py` editieren (CB→Kill-Switch Bridge)
10. `backend/src/agents/fundamental.py` editieren (Model-Routing)
11. `backend/src/agents/claim_extractor.py` editieren (Model-Routing)
12. `backend/src/services/fundamental_analysis.py` editieren (degraded Flag)
13. `backend/src/services/claim_extraction.py` editieren (degraded Flag)
14. `backend/src/services/trade_execution.py` editieren (executed_price)
15. `backend/src/routes/trades.py` editieren (Status-Allowlist)
16. Tests erstellen und bestehende anpassen
17. `cd backend && pytest` — alle Tests grün (~482 bestehend + ~50 neu = ~530 Tests)
18. Sprint-Roadmap Step 11 Checkboxen abhaken
19. Self-Audit (1-10 Skala)
20. Commit + Push

---

## Qualitätsanforderungen

- Halte dich immer strikt an die beschriebene Arbeitsweise aus deiner Claude.md File!!
- Halte dich strikt an deinen Plan!
- Arbeite immer im Sinne des **Best Practice**, **Development Standards** und **MVP-gerecht** (kein Over-Engineering)
- **KEINE Workarounds** — außer es muss sein, dann begründen warum
- Meine App sollte auch nach deiner Arbeit weiterhin **sicher, skalierbar und qualitativ** bleiben
- Wenn du fertig bist führe `cd backend && pytest` durch und bereinige deine Fehler!
- Nutze für die Arbeit den/die passenden **Agenten**! Nutze für deine Arbeit die richtigen **Claude Skills**!
- Am Ende: **Reviewe und bewerte** deine Arbeit mit einer **Skala von 1 bis 10** und begründe deine Bewertung
