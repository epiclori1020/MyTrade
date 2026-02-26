# Policy Engine — MyTrade

## Zweck
Die Policy Engine ist **deterministischer Python-Code** (kein LLM).
Sie validiert jeden Trade-Vorschlag gegen das IPS BEVOR er an den User oder Broker geht.

## Ablauf
```
                    ┌─────────────────────┐
                    │ user_policy (DB)     │
                    │ mode + preset +      │
                    │ overrides            │
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
                    │ get_effective_policy │ ← siehe settings-spec.md
                    │ (resolves preset +  │
                    │  overrides +        │
                    │  hard constraints)  │
                    └──────────┬──────────┘
                               ▼
User Request → Pre-Policy ──→ Agent ──→ Claims ──→ Verification ──→ Full-Policy ──→ Trade Plan ──→ Execute
                  ↓                                    ↓                 ↓
            REJECT wenn                          Flag/Dispute      REJECT wenn
            Typ/Region/                          wenn Quellen      Sizing/Exposure
            Instrument                           abweichen         verletzt
            verboten
```

### Pipeline-Reihenfolge (verbindlich)
1. **Pre-Policy** (vor Agent Call): Blockt sofort wenn Instrument/Typ/Region verboten → spart Opus-Tokens
2. **Agent** analysiert und extrahiert Claims
3. **Verification** prüft Claims gegen 2. Quelle → setzt Tier + Status
4. **Full-Policy** prüft Sizing/Exposure auf Basis **verifizierter** Zahlen → blockt wenn IPS verletzt
5. **Trade Plan** wird generiert (nur wenn Full-Policy passed)
6. **Execute** (Paper Order / Human-Confirm)

### Warum diese Reihenfolge?
- Pre-Policy VOR Agent: Warum Opus bezahlen für eine verbotene Penny Stock?
- Verification VOR Full-Policy: Sizing-Entscheidungen basieren auf verifizierten Zahlen, nicht auf potenziell falschen Daten.

### Policy-Quellen (Priorität)
1. `user_policy` Tabelle (DB) — primäre Quelle
2. `ips-template.yaml` — Fallback wenn DB nicht erreichbar
3. Hard Constraints — immer erzwungen, nicht überschreibbar (verbotene Instrumente, EM nur ETF)

## Validierungsregeln (aus ips-template.yaml)

```python
def validate_trade(trade: TradeProposal, ips: IPS, portfolio: Portfolio) -> ValidationResult:
    errors = []
    
    # 1. Erlaubter Typ?
    if trade.instrument_type in ips.satellite.forbidden_types:
        errors.append(f"BLOCKED: {trade.instrument_type} ist verboten")
    
    # 2. Max Single Position?
    new_position_pct = calculate_position_pct(trade, portfolio)
    if new_position_pct > ips.satellite.max_single_position_pct:
        errors.append(f"BLOCKED: Position {new_position_pct}% > Max {ips.satellite.max_single_position_pct}%")
    
    # 3. Max Sektor-Konzentration?
    sector_pct = calculate_sector_pct(trade, portfolio)
    if sector_pct > ips.satellite.max_sector_concentration_pct:
        errors.append(f"BLOCKED: Sektor {sector_pct}% > Max {ips.satellite.max_sector_concentration_pct}%")
    
    # 4. Max Trades/Monat?
    monthly_trades = count_trades_this_month(portfolio)
    if monthly_trades >= ips.satellite.max_trades_per_month:
        errors.append(f"BLOCKED: {monthly_trades} Trades diesen Monat >= Max {ips.satellite.max_trades_per_month}")
    
    # 5. Cash Reserve?
    remaining_cash_pct = calculate_remaining_cash(trade, portfolio)
    if remaining_cash_pct < ips.satellite.cash_reserve_pct:
        errors.append(f"BLOCKED: Cash {remaining_cash_pct}% < Min {ips.satellite.cash_reserve_pct}%")
    
    # 6. Drawdown Kill-Switch?
    if portfolio.current_drawdown_pct >= ips.risk.max_portfolio_drawdown_pct:
        errors.append(f"KILL SWITCH: Drawdown {portfolio.current_drawdown_pct}% >= {ips.risk.max_portfolio_drawdown_pct}%")
    
    # 7. Region erlaubt?
    region_rule = find_region_rule(trade.region, ips)
    if not region_rule:
        errors.append(f"BLOCKED: Region {trade.region} nicht erlaubt")
    elif trade.instrument_type not in region_rule.instruments:
        errors.append(f"BLOCKED: {trade.instrument_type} nicht erlaubt in {trade.region}")
    
    # 8. Maturity Stage erlaubt?
    if ips.execution.maturity_stage < 2 and trade.is_live_order:
        errors.append("BLOCKED: Live Orders nicht erlaubt in Stufe < 2")
    
    if errors:
        return ValidationResult(status="rejected", errors=errors)
    return ValidationResult(status="passed", errors=[])
```

## Wichtig
- Die Policy Engine liest ips-template.yaml — NICHT den LLM-Output
- Kein LLM kann die Policy Engine überschreiben
- JEDER Trade-Vorschlag durchläuft die Engine, auch in Paper Trading
- Rejected Trades werden geloggt (Audit Trail)
