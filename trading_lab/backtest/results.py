"""Backtest output types."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    """Outcome of a single-symbol backtest."""

    symbol: str
    strategy_name: str
    prices: pd.Series
    signals: pd.Series
    positions: pd.Series
    returns: pd.Series
    equity: pd.Series
    metrics: dict[str, float] = field(default_factory=dict)
