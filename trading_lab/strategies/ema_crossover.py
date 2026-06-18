"""EMA crossover strategy — Golden Cross / Death Cross (long / flat)."""

from __future__ import annotations

import pandas as pd

from trading_lab.strategies.base import Strategy, StrategyMeta


class EMACrossoverStrategy(Strategy):
    """Long when the fast EMA is above the slow EMA, flat otherwise."""

    meta = StrategyMeta(
        name="ema_crossover",
        description=(
            "Long when fast EMA > slow EMA (Golden Cross); "
            "flat on Death Cross."
        ),
    )

    def __init__(self, fast: int = 50, slow: int = 200) -> None:
        if fast <= 0 or slow <= 0:
            raise ValueError("EMA windows must be positive")
        if fast >= slow:
            raise ValueError("fast window must be smaller than slow window")
        self.fast = fast
        self.slow = slow

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["Close"]
        ema_fast = close.ewm(span=self.fast, min_periods=self.fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow, min_periods=self.slow, adjust=False).mean()
        return (ema_fast > ema_slow).astype("float64")
