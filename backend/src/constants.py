"""Project-wide constants for MyTrade backend."""

# MVP Asset Universe — hardcoded per docs/02_policy/asset-universe.md
MVP_UNIVERSE: list[str] = [
    "AAPL",  # Apple — Tech
    "MSFT",  # Microsoft — Tech
    "JNJ",   # Johnson & Johnson — Healthcare
    "JPM",   # JPMorgan — Financials
    "PG",    # Procter & Gamble — Consumer Staples
    "VOO",   # Vanguard S&P 500 ETF
    "VWO",   # Vanguard EM ETF
]


def is_valid_ticker(ticker: str) -> bool:
    """Check if a ticker is in the MVP universe (case-insensitive)."""
    return ticker.upper() in MVP_UNIVERSE
