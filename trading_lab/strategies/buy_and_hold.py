"""Buy-and-hold baseline."""

from __future__ import annotations

import pandas as pd

from trading_lab.strategies.base import Strategy, StrategyMeta


class BuyAndHoldStrategy(Strategy):
    meta = StrategyMeta(
        name="buy_and_hold",
        description="Enter long on the first bar and hold.",
    )

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=ohlcv.index, dtype="float64")
