"""Time-series price momentum strategy (long / flat)."""

from __future__ import annotations

import pandas as pd

from trading_lab.strategies.base import Strategy, StrategyMeta


class MomentumStrategy(Strategy):
    """Long when the trailing lookback-day return is positive, flat otherwise."""

    meta = StrategyMeta(
        name="momentum",
        description=(
            "Long when the trailing lookback-day return is positive; "
            "flat otherwise."
        ),
    )

    def __init__(self, lookback: int = 252) -> None:
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        self.lookback = lookback

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["Close"]
        trailing_return = close.pct_change(self.lookback)
        return (trailing_return > 0).astype("float64")
