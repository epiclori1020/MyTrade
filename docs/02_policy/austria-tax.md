# Österreichische Steuerregeln — MyTrade

## KESt (Kapitalertragsteuer)
- **Satz:** 27.5% auf Kapitalerträge (Dividenden, Kursgewinne, ausschüttungsgleiche Erträge)
- **Gilt für:** Alle Investments (Core + Satellite)

## Steuer-einfach vs. Selbstmelden
| Broker | Steuer-einfach? | Details |
|--------|----------------|---------|
| Flatex.at (Core) | ✅ Ja | KESt wird automatisch abgeführt |
| Alpaca (Paper) | ❌ Nein | Kein echtes Geld in Stufe 1, irrelevant |
| IBKR (Stufe 2+) | ❌ Nein | Selbst melden über Einkommensteuererklärung |

## W-8BEN
- Formular zur Reduktion der US-Quellensteuer auf Dividenden (30% → 15%)
- Differenz zu 27.5% KESt wird in Österreich angerechnet
- Bei Flatex: automatisch, bei IBKR: online ausfüllen

## Thesaurierende vs. Ausschüttende ETFs
- **Thesaurierend empfohlen** für AT-Investoren
- Ausschüttungsgleiche Erträge werden jährlich mit KESt besteuert (auch ohne Verkauf)
- Kein manuelles Reinvestieren nötig

## OeKB-Meldefonds
- UCITS-ETFs die in Österreich als Meldefonds registriert sind
- VWCE und CSPX sind Meldefonds → steuerlich korrekt behandelt auf Flatex
- Prüfung: https://my.oekb.at/kapitalmarkt-services

## Verlustausgleich
- Verluste aus Aktien/ETFs können mit Gewinnen im selben Jahr verrechnet werden
- Kein Verlustvortrag in Folgejahre (für natürliche Personen)
- Flatex macht das automatisch, IBKR muss manuell in Steuererklärung

## System-Implikation
- Alle Performance-Berechnungen müssen KESt 27.5% berücksichtigen
- Trade-Pläne sollten steuerliche Auswirkungen berücksichtigen (z.B. Haltedauer)
- Kein Tax-Loss-Harvesting automatisieren (Verlustausgleich nur innerhalb des Jahres)
