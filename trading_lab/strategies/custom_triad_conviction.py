"""Custom hybrid of the three best strategies from the backtest.

It combines MACD, 12-month momentum and Donchian breakout. Each one casts a
long/flat vote; we go fully long when at least 2 of the 3 agree, and stay flat
otherwise. Momentum does double duty: when the long-term trend is negative we
halve the exposure (bear_throttle) so we don't fight the trend on the two fast
signals alone.

Note: conviction_power is kept for backward compatibility but no longer does
anything with the current majority gate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_lab.strategies.base import Strategy, StrategyMeta


class CustomTriadConvictionStrategy(Strategy):
    """Fractional-exposure ensemble of MACD, momentum, and Donchian breakout."""

    meta = StrategyMeta(
        name="custom_triad_conviction",
        description=(
            "Experimental hybrid: MACD + 12-month momentum + Donchian breakout "
            "vote for long exposure; goes fully long when a majority (>=2 of 3) "
            "agree and is throttled in bear regimes."
        ),
    )

    def __init__(
        self,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        mom_lookback: int = 252,
        donchian_window: int = 20,
        bear_throttle: float = 0.5,
        conviction_power: float = 1.0,
    ) -> None:
        if macd_fast <= 0 or macd_slow <= 0 or macd_signal <= 0:
            raise ValueError("MACD periods must be positive")
        if macd_fast >= macd_slow:
            raise ValueError("macd_fast must be smaller than macd_slow")
        if mom_lookback <= 0:
            raise ValueError("mom_lookback must be positive")
        if donchian_window <= 0:
            raise ValueError("donchian_window must be positive")
        if not 0.0 <= bear_throttle <= 1.0:
            raise ValueError("bear_throttle must be in [0, 1]")
        if conviction_power <= 0:
            raise ValueError("conviction_power must be positive")

        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.mom_lookback = mom_lookback
        self.donchian_window = donchian_window
        self.bear_throttle = bear_throttle
        self.conviction_power = conviction_power

    def _macd_vote(self, close: pd.Series) -> pd.Series:
        ema_fast = close.ewm(span=self.macd_fast, min_periods=self.macd_fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.macd_slow, min_periods=self.macd_slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(
            span=self.macd_signal, min_periods=self.macd_signal, adjust=False
        ).mean()
        return (macd_line > signal_line).astype("float64")

    def _momentum_regime(self, close: pd.Series) -> pd.Series:
        trailing_return = close.pct_change(self.mom_lookback)
        return (trailing_return > 0).astype("float64")

    def _donchian_vote(self, ohlcv: pd.DataFrame, close: pd.Series) -> pd.Series:
        high_src = ohlcv["High"] if "High" in ohlcv.columns else close
        low_src = ohlcv["Low"] if "Low" in ohlcv.columns else close
        upper = high_src.rolling(self.donchian_window, min_periods=self.donchian_window).max().shift(1)
        lower = low_src.rolling(self.donchian_window, min_periods=self.donchian_window).min().shift(1)

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

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["Close"]

        macd_vote = self._macd_vote(close)
        mom_regime = self._momentum_regime(close)
        donchian_vote = self._donchian_vote(ohlcv, close)

        conviction = (macd_vote + mom_regime + donchian_vote) / 3.0
        full_in = (conviction > 0.5).astype("float64")

        # throttle exposure when the long-term trend is down
        throttle = np.where(mom_regime > 0.0, 1.0, self.bear_throttle)

        position = (full_in * throttle).clip(0.0, 1.0)
        return position.astype("float64")
