"""Named universes and symbol helpers for backtests."""

from __future__ import annotations

# Yahoo Finance tickers used in thesis experiments (adjust as needed).
DEFAULT_UNIVERSE: tuple[str, ...] = (
    "^GSPC",  # S&P 500 index
    "^IXIC",  # Nasdaq Composite
    "GLD",  # gold ETF
    "SLV",  # silver ETF
    "BTC-USD",  # Bitcoin / USD
)

# Optional: map a loose label to a concrete ticker for reporting.
_BENCHMARK_ALIASES: dict[str, str] = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "gold": "GLD",
    "silver": "SLV",
    "btc": "BTC-USD",
}


def benchmark_symbol_for(label: str) -> str:
    """Resolve a short name to a Yahoo ticker."""
    key = label.strip().lower()
    return _BENCHMARK_ALIASES.get(key, label)
