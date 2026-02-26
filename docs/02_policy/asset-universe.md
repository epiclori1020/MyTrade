# Asset Universe Policy — MyTrade v1

## Grundregel
Das System analysiert und handelt NUR Instrumente die in diesem Dokument definiert sind.
Alles andere wird von der Policy Engine deterministisch blockiert.

---

## Core (70%) — AUSSERHALB des Systems

**Broker:** Flatex.at (steuer-einfach, manueller Sparplan)
**Managed by System:** NEIN — das System hat keinen Zugriff auf den Core.

| ETF | ISIN | Börse | Target | TER | Typ |
|-----|------|-------|--------|-----|-----|
| VWCE (Vanguard FTSE All-World UCITS) | IE00BK5BQT80 | Xetra | 40% | 0.22% | Thesaurierend |
| CSPX (iShares Core S&P 500 UCITS) | IE00B5BMR087 | LSE | 30% | 0.07% | Thesaurierend |

**Warum thesaurierend:** Für österreichische Investoren steuerlich optimal.
Keine manuelle Wiederanlage nötig. KESt wird auf ausschüttungsgleiche Erträge automatisch berechnet.

---

## Satellite (30%) — System-managed

### Erlaubtes Universum

**Phase 1 (MVP — Stufe 1):**
- **US Large Cap:** S&P 500 Komponenten (Einzelaktien)
- **US ETFs:** Sektor-ETFs, Themen-ETFs (nur US-listed für Alpaca Paper)
- **EM ETFs:** z.B. iShares EM UCITS (nur via ETF, keine Einzelaktien)

**Phase 2 (nach Stufe 2 mit IBKR):**
- **EU Large Cap:** Euro Stoxx 50 Komponenten (Einzelaktien via IBKR)
- **UCITS ETFs:** Auf Xetra/LSE handelbar

### Regionen-Regeln

| Region | Einzelaktien erlaubt? | ETFs erlaubt? | Max % Satellite | Begründung |
|--------|----------------------|--------------|----------------|------------|
| USA | ✅ Ja | ✅ Ja | Unbegrenzt | Tier A Verification via SEC EDGAR |
| EU | ✅ Ja (ab Phase 2) | ✅ Ja | 50% | Tier A eingeschränkt (kein EDGAR), aber IR-Seiten verfügbar |
| Emerging Markets | ❌ Nein | ✅ Nur ETF | 15% | Keine Tier A Verification für Einzeltitel möglich |
| China | ❌ Nein | ✅ Nur ETF | Teil der 15% EM | VIE-Strukturen, Transparenzlücken |
| India | ❌ Nein | ✅ Nur ETF | Teil der 15% EM | Begrenzte API-Abdeckung |

### Explizit verbotene Instrumente

Die Policy Engine blockiert folgende Typen deterministisch (kein LLM kann das überschreiben):

- ❌ Optionen & Futures
- ❌ Kryptowährungen
- ❌ Leveraged / Inverse ETFs
- ❌ Penny Stocks (Kurs < $5)
- ❌ SPACs (Special Purpose Acquisition Companies)
- ❌ OTC (Over-the-Counter) Wertpapiere
- ❌ Bonds / Anleihen (nicht im Scope des Systems)

### Positionslimits

- Max. Einzelposition: **5% des Satellite-Anteils**
- Max. Sektor-Konzentration: **30% des Satellite-Anteils**
- Cash-Reserve: **Min. 5% des Satellite** immer verfügbar
- Max. Trades pro Monat: **10**
- Max. gleichzeitige Positionen: **10-15** (empfohlen, kein Hard Limit)

### MVP Startuniversum (hardcoded für Phase 1)

Für den Vertical Slice MVP wird ein festes Universum verwendet:

```python
MVP_UNIVERSE = [
    # US Large Cap Einzelaktien
    "AAPL",   # Apple — Tech
    "MSFT",   # Microsoft — Tech
    "JNJ",    # Johnson & Johnson — Healthcare
    "JPM",    # JPMorgan — Financials
    "PG",     # Procter & Gamble — Consumer Staples
    # ETFs
    "VOO",    # Vanguard S&P 500 (US-listed, für Alpaca Paper)
    "VWO",    # Vanguard EM (US-listed, für Alpaca Paper)
]
```

**Hinweis:** VOO/VWO sind US-listed ETFs für Alpaca Paper Trading. Im Live-Betrieb (Stufe 2+)
werden diese durch UCITS-Äquivalente (CSPX, EIMI) auf IBKR ersetzt.
