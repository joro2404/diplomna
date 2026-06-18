"""Strategy interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class StrategyMeta:
    name: str
    description: str


class Strategy(ABC):
    """Turns a price history into a target position series in [-1, 1]."""

    meta: StrategyMeta

    @abstractmethod
    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        """Return positions aligned with ohlcv.index (same length)."""
