"""Strategy factory and discovery."""

from __future__ import annotations

from typing import Callable

from trading_lab.strategies.base import Strategy
from trading_lab.strategies.bollinger_band_reversion import BollingerBandReversionStrategy
from trading_lab.strategies.buy_and_hold import BuyAndHoldStrategy
from trading_lab.strategies.fibonacci_retracement import FibonacciRetracementStrategy
from trading_lab.strategies.donchian_breakout import DonchianBreakoutStrategy
from trading_lab.strategies.ema_crossover import EMACrossoverStrategy
from trading_lab.strategies.macd_crossover import MACDCrossoverStrategy
from trading_lab.strategies.mean_reversion_zscore import MeanReversionZScoreStrategy
from trading_lab.strategies.momentum import MomentumStrategy
from trading_lab.strategies.rsi_mean_reversion import RSIMeanReversionStrategy
from trading_lab.strategies.custom_triad_conviction import CustomTriadConvictionStrategy
from trading_lab.strategies.sma_crossover import SMACrossoverStrategy
from trading_lab.strategies.triple_sma import TripleSMAStrategy

StrategyFactory = Callable[[], Strategy]

_REGISTRY: dict[str, StrategyFactory] = {
    "bollinger_band_reversion": lambda: BollingerBandReversionStrategy(),
    "buy_and_hold": lambda: BuyAndHoldStrategy(),
    "fibonacci_retracement": lambda: FibonacciRetracementStrategy(),
    "donchian_breakout": lambda: DonchianBreakoutStrategy(),
    "ema_crossover": lambda: EMACrossoverStrategy(),
    "macd_crossover": lambda: MACDCrossoverStrategy(),
    "mean_reversion_zscore": lambda: MeanReversionZScoreStrategy(),
    "momentum": lambda: MomentumStrategy(),
    "rsi_mean_reversion": lambda: RSIMeanReversionStrategy(),
    "custom_triad_conviction": lambda: CustomTriadConvictionStrategy(),
    "sma_crossover": lambda: SMACrossoverStrategy(),
    "triple_sma": lambda: TripleSMAStrategy(),
}


def list_strategies() -> list[str]:
    return sorted(_REGISTRY.keys())


def create_strategy(name: str, **params: float | int) -> Strategy:
    """Instantiate a registered strategy, forwarding any recognised params."""
    key = name.strip().lower()
    if key not in _REGISTRY:
        raise KeyError(f"Unknown strategy {name!r}. Available: {list_strategies()}")

    if key == "sma_crossover":
        return SMACrossoverStrategy(
            fast=int(params.get("fast", 20)),
            slow=int(params.get("slow", 50)),
        )
    if key == "rsi_mean_reversion":
        return RSIMeanReversionStrategy(
            period=int(params.get("period", 14)),
            oversold=float(params.get("oversold", 30.0)),
            overbought=float(params.get("overbought", 70.0)),
        )
    if key == "macd_crossover":
        return MACDCrossoverStrategy(
            fast=int(params.get("fast", 12)),
            slow=int(params.get("slow", 26)),
            signal=int(params.get("signal", 9)),
        )
    if key == "bollinger_band_reversion":
        return BollingerBandReversionStrategy(
            window=int(params.get("window", 20)),
            num_std=float(params.get("num_std", 2.0)),
        )
    if key == "fibonacci_retracement":
        return FibonacciRetracementStrategy(
            window=int(params.get("window", 50)),
            entry_fib=float(params.get("entry_fib", 0.618)),
            exit_fib=float(params.get("exit_fib", 0.382)),
        )
    if key == "momentum":
        return MomentumStrategy(
            lookback=int(params.get("lookback", 252)),
        )
    if key == "mean_reversion_zscore":
        return MeanReversionZScoreStrategy(
            window=int(params.get("window", 20)),
            entry_z=float(params.get("entry_z", 1.5)),
            exit_z=float(params.get("exit_z", 0.0)),
        )
    if key == "ema_crossover":
        return EMACrossoverStrategy(
            fast=int(params.get("fast", 50)),
            slow=int(params.get("slow", 200)),
        )
    if key == "donchian_breakout":
        return DonchianBreakoutStrategy(
            window=int(params.get("window", 20)),
        )
    if key == "triple_sma":
        return TripleSMAStrategy(
            fast=int(params.get("fast", 10)),
            mid=int(params.get("mid", 50)),
            slow=int(params.get("slow", 200)),
        )
    if key == "custom_triad_conviction":
        return CustomTriadConvictionStrategy(
            macd_fast=int(params.get("macd_fast", 12)),
            macd_slow=int(params.get("macd_slow", 26)),
            macd_signal=int(params.get("macd_signal", 9)),
            mom_lookback=int(params.get("mom_lookback", 252)),
            donchian_window=int(params.get("donchian_window", 20)),
            bear_throttle=float(params.get("bear_throttle", 0.5)),
            conviction_power=float(params.get("conviction_power", 1.0)),
        )

    if params:
        raise TypeError(f"Strategy {name!r} does not accept parameters {params!r}")
    return _REGISTRY[key]()
