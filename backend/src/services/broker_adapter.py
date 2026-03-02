"""Abstract broker adapter interface and shared dataclasses.

Defines the contract that all broker implementations must follow.
Stufe 1: AlpacaPaperAdapter (in alpaca_paper.py)
Stufe 2+: IBKRAdapter (not implemented)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Order:
    """Order request to broker."""

    ticker: str
    action: str  # "BUY" or "SELL"
    shares: float
    price: float
    order_type: str  # "LIMIT" or "MARKET"
    stop_loss: float | None = None


@dataclass
class OrderResult:
    """Result from broker after order submission."""

    success: bool
    broker_order_id: str | None = None
    executed_price: float | None = None
    executed_at: str | None = None  # ISO timestamp
    error_message: str | None = None


@dataclass
class Position:
    """A single portfolio position from broker."""

    ticker: str
    shares: float
    avg_price: float
    current_price: float
    market_value: float


@dataclass
class AccountInfo:
    """Broker account summary."""

    total_value: float
    cash: float
    buying_power: float


class BrokerAdapter(ABC):
    """Abstract base class for broker integrations.

    Stufe 1: AlpacaPaperAdapter
    Stufe 2+: IBKRAdapter (not implemented)
    """

    @abstractmethod
    def submit_order(self, order: Order) -> OrderResult:
        """Submit an order to the broker."""
        ...

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Get current positions from broker account."""
        ...

    @abstractmethod
    def get_account(self) -> AccountInfo:
        """Get account summary (total value, cash, buying power)."""
        ...
