"""Performance and risk statistics."""

from __future__ import annotations

import numpy as np
import pandas as pd


def max_drawdown(equity: pd.Series) -> float:
    """Maximum peak-to-trough drawdown (negative fraction, e.g. -0.25)."""
    if equity.empty:
        return float("nan")
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def sharpe_ratio(returns: pd.Series, freq: str = "daily", risk_free: float = 0.0) -> float:
    """Annualized Sharpe (daily returns, sample std, ddof=1)."""
    if freq != "daily":
        raise ValueError("Only daily Sharpe is implemented")
    r = returns.dropna()
    if len(r) < 2:
        return float("nan")
    excess = r - risk_free / 252.0
    std = excess.std(ddof=1)
    if std == 0 or np.isnan(std):
        return float("nan")
    return float(np.sqrt(252.0) * excess.mean() / std)


def summarize_returns(returns: pd.Series, equity: pd.Series, freq: str = "daily") -> dict[str, float]:
    """Core metrics for backtest reporting."""
    r = returns.dropna()
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0) if len(equity) > 1 else 0.0
    vol = float(r.std(ddof=1) * np.sqrt(252.0)) if freq == "daily" and len(r) > 1 else float("nan")
    return {
        "total_return": total_return,
        "cagr": _cagr(equity),
        "volatility_ann": vol,
        "sharpe": sharpe_ratio(r, freq=freq),
        "max_drawdown": max_drawdown(equity),
    }


def _cagr(equity: pd.Series) -> float:
    if len(equity) < 2:
        return float("nan")
    start = equity.index[0]
    end = equity.index[-1]
    years = (end - start).days / 365.25
    if years <= 0:
        return float("nan")
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0)
