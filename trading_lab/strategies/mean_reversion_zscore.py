"""Z-score mean-reversion strategy (long / flat)."""

from __future__ import annotations

import pandas as pd

from trading_lab.strategies.base import Strategy, StrategyMeta


class MeanReversionZScoreStrategy(Strategy):
    """Go long when the rolling z-score drops below -entry_z, exit above exit_z."""

    meta = StrategyMeta(
        name="mean_reversion_zscore",
        description=(
            "Long when rolling z-score of price falls below -entry_z; "
            "exit when z-score rises above exit_z."
        ),
    )

    def __init__(
        self,
        window: int = 20,
        entry_z: float = 1.5,
        exit_z: float = 0.0,
    ) -> None:
        if window <= 1:
            raise ValueError("window must be > 1")
        self.window = window
        self.entry_z = entry_z
        self.exit_z = exit_z

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["Close"]
        roll_mean = close.rolling(self.window, min_periods=self.window).mean()
        roll_std = close.rolling(self.window, min_periods=self.window).std(ddof=1)
        z = (close - roll_mean) / roll_std.replace(0.0, float("nan"))

        pos = pd.Series(0.0, index=close.index, dtype="float64")
        state = 0.0
        for i in range(len(close)):
            zi = z.iloc[i]
            if pd.isna(zi):
                pos.iloc[i] = state
                continue
            if zi < -self.entry_z:
                state = 1.0
            elif zi > self.exit_z:
                state = 0.0
            pos.iloc[i] = state
        return pos
