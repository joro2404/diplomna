"""MACD crossover strategy (long / flat)."""

from __future__ import annotations

import pandas as pd

from trading_lab.strategies.base import Strategy, StrategyMeta


class MACDCrossoverStrategy(Strategy):
    """Long when the MACD line is above the signal line; flat otherwise."""

    meta = StrategyMeta(
        name="macd_crossover",
        description=(
            "Long when the MACD line (EMA fast − EMA slow) "
            "is above the signal line; flat otherwise."
        ),
    )

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        if fast <= 0 or slow <= 0 or signal <= 0:
            raise ValueError("MACD periods must be positive")
        if fast >= slow:
            raise ValueError("fast period must be smaller than slow period")
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["Close"]
        ema_fast = close.ewm(span=self.fast, min_periods=self.fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow, min_periods=self.slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(
            span=self.signal, min_periods=self.signal, adjust=False
        ).mean()
        return (macd_line > signal_line).astype("float64")
