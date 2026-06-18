"""Bollinger Band mean-reversion strategy (long / flat)."""

from __future__ import annotations

import pandas as pd

from trading_lab.strategies.base import Strategy, StrategyMeta


class BollingerBandReversionStrategy(Strategy):
    """Long when price closes below the lower band, exit above the middle band."""

    meta = StrategyMeta(
        name="bollinger_band_reversion",
        description=(
            "Long when close breaks below the lower Bollinger Band; "
            "exit when close recovers above the middle band (SMA)."
        ),
    )

    def __init__(self, window: int = 20, num_std: float = 2.0) -> None:
        if window <= 1:
            raise ValueError("window must be > 1")
        if num_std <= 0:
            raise ValueError("num_std must be positive")
        self.window = window
        self.num_std = num_std

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["Close"]
        mid = close.rolling(self.window, min_periods=self.window).mean()
        std = close.rolling(self.window, min_periods=self.window).std(ddof=1)
        lower = mid - self.num_std * std

        pos = pd.Series(0.0, index=close.index, dtype="float64")
        state = 0.0
        for i in range(len(close)):
            if pd.isna(mid.iloc[i]):
                pos.iloc[i] = state
                continue
            c = close.iloc[i]
            if c < lower.iloc[i]:
                state = 1.0
            elif c > mid.iloc[i]:
                state = 0.0
            pos.iloc[i] = state
        return pos
