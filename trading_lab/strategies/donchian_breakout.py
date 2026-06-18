"""Donchian Channel breakout strategy (long / flat)."""

from __future__ import annotations

import pandas as pd

from trading_lab.strategies.base import Strategy, StrategyMeta


class DonchianBreakoutStrategy(Strategy):
    """Long when Close breaks above the N-day high, exit below the N-day low."""

    meta = StrategyMeta(
        name="donchian_breakout",
        description=(
            "Long when Close breaks above the N-day High (Donchian upper); "
            "exit when Close breaks below the N-day Low."
        ),
    )

    def __init__(self, window: int = 20) -> None:
        if window <= 0:
            raise ValueError("window must be positive")
        self.window = window

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["Close"]
        high_src = ohlcv["High"] if "High" in ohlcv.columns else close
        low_src = ohlcv["Low"] if "Low" in ohlcv.columns else close

        # shift(1) so today's signal uses the channel up to yesterday
        upper = high_src.rolling(self.window, min_periods=self.window).max().shift(1)
        lower = low_src.rolling(self.window, min_periods=self.window).min().shift(1)

        pos = pd.Series(0.0, index=close.index, dtype="float64")
        state = 0.0
        for i in range(len(close)):
            if pd.isna(upper.iloc[i]):
                pos.iloc[i] = state
                continue
            c = close.iloc[i]
            if c >= upper.iloc[i]:
                state = 1.0
            elif c <= lower.iloc[i]:
                state = 0.0
            pos.iloc[i] = state
        return pos
