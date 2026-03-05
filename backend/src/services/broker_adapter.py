"""Abstract broker adapter interface and shared dataclasses.

Defines the contract that all broker implementations must follow.
Stufe 1: AlpacaPaperAdapter (in alpaca_paper.py)
Stufe 2+: IBKRAdapter (not implemented)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Order:
    """Order request to broker.

    Financial fields (shares, price, stop_loss) use Decimal for precision.
    __post_init__ coerces float/int/str inputs to Decimal automatically.
    """

    ticker: str
    action: str  # "BUY" or "SELL"
    shares: Decimal
    price: Decimal
    order_type: str  # "LIMIT" or "MARKET"
    stop_loss: Decimal | None = None

    def __post_init__(self):
        """Coerce numeric inputs to Decimal for type safety."""
        if not isinstance(self.shares, Decimal):
            self.shares = Decimal(str(self.shares))
        if not isinstance(self.price, Decimal):
            self.price = Decimal(str(self.price))
        if self.stop_loss is not None and not isinstance(self.stop_loss, Decimal):
            self.stop_loss = Decimal(str(self.stop_loss))


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
