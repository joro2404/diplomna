"""Backtesting engine."""

from __future__ import annotations

import pandas as pd

from trading_lab.backtest.results import BacktestResult
from trading_lab.metrics.performance import summarize_returns
from trading_lab.strategies.base import Strategy


def run_backtest(
    ohlcv: pd.DataFrame,
    strategy: Strategy,
    *,
    symbol: str,
    initial_capital: float = 100_000.0,
    commission_rate: float = 0.0005,
) -> BacktestResult:
    """Vectorised backtest for one symbol with next-bar execution.

    Signals from close at t are applied to returns from t to t+1 via
    positions.shift(1) so there is no same-bar lookahead. Commission is a
    linear cost on turnover (|Δposition| * commission_rate) per period.
    """
    ohlcv = ohlcv.sort_index()
    prices = ohlcv["Close"].astype("float64")

    signals = (
        strategy.generate_signals(ohlcv)
        .reindex(prices.index)
        .fillna(0.0)
        .astype("float64")
    )
    signals = signals.clip(-1.0, 1.0)

    positions = signals.shift(1).fillna(0.0)
    market_returns = prices.pct_change().fillna(0.0)
    gross = positions * market_returns

    turnover = positions.diff().abs()
    if len(turnover):
        turnover.iloc[0] = abs(float(positions.iloc[0]))
    costs = turnover.fillna(0.0) * commission_rate
    net_returns = gross - costs

    equity = (1.0 + net_returns).cumprod() * initial_capital
    metrics = summarize_returns(net_returns, equity, freq="daily")

    return BacktestResult(
        symbol=symbol,
        strategy_name=strategy.meta.name,
        prices=prices,
        signals=signals,
        positions=positions,
        returns=net_returns,
        equity=equity,
        metrics=metrics,
    )


def run_analysis(
    ohlcv_frames: dict[str, pd.DataFrame],
    strategy: Strategy,
    *,
    initial_capital: float = 100_000.0,
    commission_rate: float = 0.0005,
) -> dict[str, BacktestResult]:
    """Run the same strategy independently on each symbol."""
    results: dict[str, BacktestResult] = {}
    for sym, ohlcv in ohlcv_frames.items():
        if ohlcv is None or ohlcv.empty or "Close" not in ohlcv.columns:
            continue
        df = ohlcv.dropna(subset=["Close"])
        if df.empty:
            continue
        results[sym] = run_backtest(
            df,
            strategy,
            symbol=sym,
            initial_capital=initial_capital,
            commission_rate=commission_rate,
        )
    return results
