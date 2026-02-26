# Broker-Router — MyTrade

## Routing-Regeln

| Asset-Typ | Stufe 1 (Paper) | Stufe 2+ (Live) |
|-----------|----------------|-----------------|
| US-Einzelaktien (Satellite) | Alpaca Paper API | IBKR |
| US-ETFs (Paper-Simulation) | Alpaca Paper API | IBKR |
| UCITS-ETFs (Core) | Außerhalb System (Flatex) | Außerhalb System (Flatex) |
| EU-Aktien (ab Phase 2) | Manuelles Tracking | IBKR |

## Alpaca Paper API
- Nur US-listed Securities (NYSE, NASDAQ)
- Kommissionsfrei
- Paper Trading Mode: dedizierter API Key
- REST + WebSocket API
- UCITS-ETFs (CSPX, VWCE) sind NICHT verfügbar

## IBKR (Interactive Brokers)
- 150+ Börsen weltweit (inkl. Xetra, LSE)
- TWS API + REST API (komplex)
- Nicht steuer-einfach für Österreich
- Erst ab Stufe 2 relevant

## Broker-Adapter Architektur
```python
class BrokerAdapter(ABC):
    @abstractmethod
    async def submit_order(self, order: Order) -> OrderResult: ...
    @abstractmethod
    async def get_positions(self) -> list[Position]: ...
    @abstractmethod  
    async def get_account(self) -> AccountInfo: ...

class AlpacaPaperAdapter(BrokerAdapter): ...  # Stufe 1
class IBKRAdapter(BrokerAdapter): ...          # Stufe 2+
```
