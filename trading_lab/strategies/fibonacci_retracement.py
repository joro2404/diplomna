"""Fibonacci retracement mean-reversion strategy (long / flat)."""

from __future__ import annotations

import pandas as pd

from trading_lab.strategies.base import Strategy, StrategyMeta

_FIB_LEVELS: tuple[float, ...] = (0.236, 0.382, 0.500, 0.618, 0.786)


class FibonacciRetracementStrategy(Strategy):
    """Buy a deep retracement into the swing range, exit on the bounce back.

    The retracement level is measured down from the rolling swing high:
        level = swing_high - ratio * (swing_high - swing_low)
    Enter at entry_fib, exit at exit_fib, and bail out below the swing low.
    """

    meta = StrategyMeta(
        name="fibonacci_retracement",
        description=(
            "Long when price retraces to the 61.8 % Fibonacci level "
            "(golden ratio support); exit at the 38.2 % level."
        ),
    )

    def __init__(
        self,
        window: int = 50,
        entry_fib: float = 0.618,
        exit_fib: float = 0.382,
    ) -> None:
        if window <= 1:
            raise ValueError("window must be > 1")
        if not (0 < exit_fib < entry_fib < 1):
            raise ValueError(
                "Fibonacci levels must satisfy 0 < exit_fib < entry_fib < 1"
            )
        self.window = window
        self.entry_fib = entry_fib
        self.exit_fib = exit_fib

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["Close"]
        high_src = ohlcv["High"] if "High" in ohlcv.columns else close
        low_src = ohlcv["Low"] if "Low" in ohlcv.columns else close

        swing_high = high_src.rolling(self.window, min_periods=self.window).max().shift(1)
        swing_low = low_src.rolling(self.window, min_periods=self.window).min().shift(1)

        price_range = swing_high - swing_low
        entry_level = swing_high - self.entry_fib * price_range
        exit_level = swing_high - self.exit_fib * price_range

        pos = pd.Series(0.0, index=close.index, dtype="float64")
        state = 0.0
        for i in range(len(close)):
            if pd.isna(entry_level.iloc[i]):
                pos.iloc[i] = state
                continue

            c = float(close.iloc[i])
            sl = float(swing_low.iloc[i])

            if c < sl:
                state = 0.0
            elif c <= entry_level.iloc[i]:
                state = 1.0
            elif state == 1.0 and c >= exit_level.iloc[i]:
                state = 0.0

            pos.iloc[i] = state
        return pos
