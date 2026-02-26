# Execution Decision Contract — MyTrade v1

## Zweck
Dieses Dokument definiert **exakt** was das System in jeder Stufe vorschlagen und ausführen darf.
Es ist die rechtliche und operationale Grundlage. Die Policy Engine erzwingt diese Regeln deterministisch.

---

## Grundsatz
**Das System bietet Decision Support, keine Anlageberatung.**
Alle Investmententscheidungen liegen beim User.
Kein Haftungsanspruch gegen das System.

---

## Stufe 0 — Advisory Only

| Aktion | Erlaubt? | Details |
|--------|---------|---------|
| Analyse-Memos generieren | ✅ | Vollständige Analyse mit Claims und Verification |
| Trade-Pläne als Dokument | ✅ | "Empfehlung: Kaufe AAPL bei $180" als Text |
| Broker-API aufrufen | ❌ | Keine Verbindung zum Broker |
| Orders erstellen | ❌ | Weder Paper noch Live |
| Portfolio-Daten lesen | ❌ | Nur manuelle Eingabe durch User |

**User-Aktion:** Handelt komplett manuell im Broker-UI.

---

## Stufe 1 — Paper Trading (AKTUELLER MVP)

| Aktion | Erlaubt? | Details |
|--------|---------|---------|
| Analyse-Memos generieren | ✅ | Vollständig |
| Trade-Pläne generieren | ✅ | JSON mit Ticker, Richtung, Size, Begründung |
| Alpaca Paper API aufrufen | ✅ | NUR Paper-Modus, kein echtes Geld |
| Paper-Orders erstellen | ✅ | Simulierte Ausführung über Alpaca Paper |
| Paper-Portfolio lesen | ✅ | Aktueller Stand der simulierten Positionen |
| Echte Orders erstellen | ❌ | **VERBOTEN** — kein Live-Broker-Zugang |
| Echtes Portfolio lesen | ❌ | Kein Zugang zu Flatex oder IBKR Live |
| Geld transferieren | ❌ | **VERBOTEN** |

**User-Aktion:** Reviewed Paper-Trading-Ergebnisse. Kein echtes Geld involviert.

**Technische Absicherung:**
- Alpaca Paper API Key (nicht Live Key) in Environment
- Backend-Code prüft `ALPACA_PAPER_MODE=true` vor jedem API-Call
- Kein IBKR-Zugang konfiguriert

---

## Stufe 2 — Human Confirms

| Aktion | Erlaubt? | Details |
|--------|---------|---------|
| Analyse-Memos generieren | ✅ | Vollständig |
| Trade-Pläne generieren | ✅ | Inkl. exakte Order-Details |
| Order-Vorschläge erstellen | ✅ | Ticker, Richtung, Size, Limit-Preis, Stop-Loss |
| Order an Broker senden | ⚠️ | **NUR nach explizitem User-Approve** |
| Portfolio lesen | ✅ | Live-Portfolio von IBKR |
| Automatisch Orders ausführen | ❌ | **VERBOTEN** — jeder Trade braucht Klick |
| Geld transferieren | ❌ | **VERBOTEN** |

**User-Aktion:** Sieht Order-Vorschlag → klickt "Approve" oder "Reject" → System führt aus oder verwirft.

**Technische Absicherung:**
- `trade_log.status` muss von `proposed` auf `approved` gesetzt werden (User-JWT, nicht service_role)
- Timeout: Unbestätigte Orders verfallen nach **24 Stunden**
- Max. Order-Größe: 5% des Satellite (= 1.5% Gesamtportfolio)
- Policy Engine validiert VOR Order-Erstellung

---

## Stufe 3 — Auto-Execute (Zukunft, nicht implementiert)

| Aktion | Erlaubt? | Details |
|--------|---------|---------|
| Automatisch Rebalancing ausführen | ⚠️ | NUR innerhalb strenger IPS-Limits |
| Neue Positionen eröffnen | ❌ | **Braucht weiterhin Human-Confirm** |
| Kill-Switch | ✅ | Jederzeit verfügbar, stoppt alle Auto-Executions sofort |
| Max. Order-Größe | 2% | Pro automatischem Trade max. 2% des Portfolios |

**Hinweis:** Stufe 3 ist für einen risikoarmen Langfrist-Investor NICHT notwendig.
Stufe 2 (Human Confirms) ist der empfohlene Dauerzustand.

---

## Kill-Switch Regeln (gelten für ALLE Stufen)

Der Kill-Switch aktiviert sich automatisch wenn:
1. Portfolio Drawdown ≥ **20%** vom Höchststand
2. **5 aufeinanderfolgende** Broker-API-Fehler (Circuit Breaker)
3. Verification-Rate fällt unter **70%** (zu viele ungeprüfte Claims)
4. User aktiviert Kill-Switch manuell

**Was der Kill-Switch tut:**
- Stoppt alle neuen Order-Vorschläge
- Stoppt alle Auto-Executions (Stufe 3)
- Bestehende Positionen bleiben unverändert (kein Panik-Verkauf)
- System wechselt in Advisory-Only-Modus (Stufe 0)
- User wird sofort benachrichtigt
- Manuelle Reaktivierung erforderlich

---

## Gate-Kriterien für Stufenwechsel

### Stufe 0 → Stufe 1 (Paper Trading)
- [ ] IPS vollständig definiert und von User freigegeben
- [ ] Mindestens 1 erfolgreicher End-to-End-Analyselauf
- [ ] Policy Engine validiert korrekt gegen IPS
- [ ] Alpaca Paper API verbunden und getestet

### Stufe 1 → Stufe 2 (Human Confirms)
- [ ] Min. **3 Monate** Paper Trading abgeschlossen
- [ ] Pipeline-Fehlerrate < **5%**
- [ ] Verification-Rate > **85%**
- [ ] IPS-Compliance: **100%** (kein Regelverstoß durchgerutscht)
- [ ] User versteht und kann Outputs interpretieren
- [ ] Security Audit bestanden
- [ ] IBKR Account eröffnet und API konfiguriert
- [ ] **NICHT:** "Profitables Paper Trading" (marktabhängig, kein Qualitätskriterium)

### Stufe 2 → Stufe 3 (Auto-Execute)
- [ ] Min. **6 Monate** Stufe 2 stabil betrieben
- [ ] Alle Gate-Kriterien von Stufe 1→2 weiterhin erfüllt
- [ ] Kill-Switch getestet (manuell + automatisch)
- [ ] Max. Auto-Trade-Size ≤ 2% implementiert und getestet
- [ ] **Empfehlung: Stufe 3 ist für dieses Profil NICHT nötig**
