"""Triple SMA trend-filter strategy (long / flat)."""

from __future__ import annotations

import pandas as pd

from trading_lab.strategies.base import Strategy, StrategyMeta


class TripleSMAStrategy(Strategy):
    """Long only when fast SMA > mid SMA > slow SMA (all three aligned)."""

    meta = StrategyMeta(
        name="triple_sma",
        description=(
            "Long only when fast SMA > mid SMA > slow SMA "
            "(all three in bullish alignment)."
        ),
    )

    def __init__(self, fast: int = 10, mid: int = 50, slow: int = 200) -> None:
        if fast <= 0 or mid <= 0 or slow <= 0:
            raise ValueError("SMA windows must be positive")
        if not (fast < mid < slow):
            raise ValueError("Windows must satisfy: fast < mid < slow")
        self.fast = fast
        self.mid = mid
        self.slow = slow

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["Close"]
        sma_fast = close.rolling(self.fast, min_periods=self.fast).mean()
        sma_mid = close.rolling(self.mid, min_periods=self.mid).mean()
        sma_slow = close.rolling(self.slow, min_periods=self.slow).mean()
        aligned = (sma_fast > sma_mid) & (sma_mid > sma_slow)
        return aligned.astype("float64")
