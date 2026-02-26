# IPS Settings System — MyTrade v1

## Übersicht
Das IPS (Investment Policy Statement) ist über drei Bedienebenen konfigurierbar.
Alle Ebenen schreiben in dieselbe `user_policy` Tabelle. Die Policy Engine liest
immer nur die **effective policy** — egal ob sie von einem Preset oder Custom-Werten kommt.

---

## 3 Bedienebenen

### Ebene 1: Einsteiger (Default)
- Aktiv bei neuem User
- User sieht: "Profil: Einsteiger" + kurze Erklärung
- Keine editierbaren Regler
- Policy = Einsteiger-Preset (fest)

### Ebene 2: Vordefinierte Profile (Presets)
- 3 Presets als Buttons/Cards
- Beim Wechsel: Info-Panel "Was ändert sich?" + "Risiko steigt/sinkt"
- Policy = gewählter Preset (fest, nicht editierbar)

### Ebene 3: Advanced (Einzelsettings)
- Toggle "Advanced Einstellungen" mit Danger-Zone-UI
- Bestätigungs-Checkbox: "Ich verstehe, dass höhere Aktivität/mehr Satellite Risiko erhöht"
- 15 Regler mit Microcopy-Tooltips
- Änderungen nur innerhalb definierter Constraints
- Policy = aktueller Preset + Overrides

---

## Presets

| Setting | Einsteiger | Balanced | Aktiv |
|---------|-----------|----------|-------|
| Core/Satellite | 80/20 | 70/30 | 60/40 |
| Max Drawdown (Kill-Switch) | 15% | 20% | 25% |
| Max Single Position | 5% | 5% | 8% |
| Max Sektor-Konzentration | 25% | 30% | 35% |
| Max Trades/Monat | 4 | 8 | 10 |
| Stop-Loss Soft-Flag | 10% | 15% | 20% |
| EM Cap | 10% | 15% | 20% |
| Cash-Reserve | 10% | 5% | 3% |
| Rebalancing-Trigger | 3% | 5% | 8% |

**Alle Presets teilen diese fixen Werte (nicht änderbar, auch nicht in Advanced):**
- Verbotene Instrumente: Optionen, Futures, Crypto, Leveraged ETFs, Penny Stocks, SPACs
- EM: nur via ETF (keine Einzelaktien)
- Core-ETFs: VWCE + CSPX (thesaurierend, Flatex)
- Core-Broker: Flatex.at (außerhalb des Systems)
- Paper-Broker: Alpaca Paper API
- Live-Broker: IBKR (ab Stufe 2)
- Review-Frequenz: Vierteljährlich
- Execution: Human-Confirm (Stufe 1-2)

---

## Datenmodell

### Tabelle: `user_policy`
```sql
CREATE TABLE user_policy (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) NOT NULL,
  policy_mode TEXT NOT NULL DEFAULT 'BEGINNER'
    CHECK (policy_mode IN ('BEGINNER', 'PRESET', 'ADVANCED')),
  preset_id TEXT DEFAULT 'beginner'
    CHECK (preset_id IN ('beginner', 'balanced', 'active')),
  policy_overrides JSONB DEFAULT '{}'::jsonb,
  cooldown_until TIMESTAMPTZ DEFAULT NULL,
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id)
);

-- RLS
ALTER TABLE user_policy ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can read own policy"
  ON user_policy FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can update own policy"
  ON user_policy FOR UPDATE USING (auth.uid() = user_id);
```

### Tabelle: `policy_change_log`
```sql
CREATE TABLE policy_change_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) NOT NULL,
  changed_at TIMESTAMPTZ DEFAULT now(),
  old_mode TEXT,
  new_mode TEXT,
  old_preset TEXT,
  new_preset TEXT,
  old_overrides JSONB,
  new_overrides JSONB,
  change_reason TEXT DEFAULT NULL
);

-- RLS
ALTER TABLE policy_change_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can read own log"
  ON policy_change_log FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own log"
  ON policy_change_log FOR INSERT WITH CHECK (auth.uid() = user_id);
```

---

## Effective Policy Resolution

```python
def get_effective_policy(user_policy: UserPolicy) -> EffectivePolicy:
    """
    Resolves the active policy from mode + preset + overrides.
    This is what the Policy Engine reads.
    """
    # 1. Start with preset values
    base = PRESETS[user_policy.preset_id]

    # 2. If ADVANCED, apply overrides (validated against constraints)
    if user_policy.policy_mode == 'ADVANCED':
        for key, value in user_policy.policy_overrides.items():
            if is_within_constraints(key, value, user_policy.preset_id):
                base[key] = value

    # 3. Always enforce hard constraints (non-overridable)
    base['forbidden_types'] = ALWAYS_FORBIDDEN
    base['em_instruments'] = ['etf']  # never single stocks
    base['execution_stage'] = current_stage  # from execution contract

    return EffectivePolicy(**base)
```

---

## Constraints (Advanced Mode)

Advanced-Overrides sind nur innerhalb dieser Grenzen erlaubt:

| Setting | Min | Max | Begründung |
|---------|-----|-----|-----------|
| satellite_pct | 10 | 40 | <10% lohnt sich nicht, >40% zu riskant |
| max_drawdown_pct | 10 | 30 | <10% triggert ständig, >30% zu gefährlich |
| max_single_position_pct | 3 | 10 | <3% braucht zu viele Positionen, >10% Klumpenrisiko |
| max_sector_pct | 20 | 40 | <20% zu restriktiv, >40% Pseudo-Sektorfonds |
| max_trades_month | 2 | 12 | <2% zu passiv für System, >12 Overtrading |
| stop_loss_flag_pct | 5 | 25 | <5% triggert bei Tageschwankung, >25% zu spät |
| em_cap_pct | 0 | 25 | 0 = kein EM, >25% zu viel EM-Risiko |
| cash_reserve_pct | 0 | 15 | 0 = kein Puffer, >15% bremst Performance |
| rebalance_trigger_pct | 2 | 10 | <2% ständiges Rebalancing, >10% zu viel Drift |

---

## Cooldown-Regel

- **Mode-Wechsel** (z.B. Balanced → Aktiv): wird sofort gespeichert, aber **erst nach 24h aktiv**
- Während Cooldown: UI zeigt "Wechsel zu {neuer Mode} aktiv ab {Zeitpunkt}"
- Policy Engine nutzt bis dahin den alten Mode
- **Regler-Änderungen in Advanced**: sofort aktiv (kein Cooldown pro Regler)
- **Preset-Wechsel löscht alle Overrides** (sauberer Zustand)

---

## Microcopy (Tooltip-Texte für UI)

| Regler | Microcopy |
|--------|-----------|
| Core/Satellite | Mehr Satellite = mehr Schwankung & mehr Systemeinfluss auf dein Portfolio. |
| Max Drawdown | Stoppt alle neuen Trades wenn dein Satellite um diesen Wert fällt. Schützt vor Crash-Verlusten. |
| Max Single Position | Begrenzt wie viel eine einzelne Aktie deines Satellite ausmachen darf. |
| Max Sektor | Verhindert dass dein Satellite zum Tech-only-Portfolio wird. |
| Trades/Monat | Mehr Trades = höhere Kosten & Overtrading-Risiko. Weniger = weniger Chancen. |
| Stop-Loss Flag | Das System warnt dich ab diesem Verlust und prüft ob die Investment-These noch stimmt. Kein Auto-Verkauf. |
| EM Cap | Emerging Markets sind volatiler. Cap begrenzt dein Klumpenrisiko in politisch instabilen Märkten. |
| Cash-Reserve | Trockenpulver für Kaufgelegenheiten. 0% = du musst immer erst verkaufen um zu kaufen. |
| Rebalancing-Trigger | Ab dieser Abweichung vom Target schlägt das System Rebalancing vor. Zu eng = zu viele Trades. |

---

## Integration mit bestehender Architektur

### Policy Engine
- Liest `get_effective_policy()` statt `ips-template.yaml` direkt
- `ips-template.yaml` bleibt als **Fallback** falls DB nicht erreichbar
- Pre-Policy und Full-Policy Logik bleibt unverändert
- Validierung gegen Constraints passiert beim Speichern (nicht beim Lesen)

### Agents
- Agents erhalten die effective policy als Kontext
- Keine Agent-Logik ändert sich — sie sehen nur andere Zahlen

### Frontend
- Settings-Page: 3 Tabs oder Accordion (Einsteiger / Presets / Advanced)
- Presets als Cards mit Vergleichstabelle
- Advanced: Slider pro Setting mit Microcopy darunter
- Validation inline (grün/rot Feedback sofort beim Schieben)
- "Änderungen speichern" Button → API Call → policy_change_log Eintrag

### Verification Layer
- Unverändert. Verification ist datengetrieben, nicht policy-getrieben.
