"""RSI mean-reversion (long / flat)."""

from __future__ import annotations

import pandas as pd

from trading_lab.strategies.base import Strategy, StrategyMeta


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


class RSIMeanReversionStrategy(Strategy):
    meta = StrategyMeta(
        name="rsi_mean_reversion",
        description="Long when RSI < oversold; flat when RSI > overbought.",
    )

    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0) -> None:
        if period <= 0:
            raise ValueError("RSI period must be positive")
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["Close"]
        rsi = _rsi(close, self.period)
        pos = pd.Series(0.0, index=close.index, dtype="float64")
        state = 0.0
        for i in range(len(close)):
            r = rsi.iloc[i]
            if pd.isna(r):
                pos.iloc[i] = state
                continue
            if r < self.oversold:
                state = 1.0
            elif r > self.overbought:
                state = 0.0
            pos.iloc[i] = state
        return pos
