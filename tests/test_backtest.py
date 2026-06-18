import unittest

import numpy as np
import pandas as pd

from trading_lab.backtest.engine import run_analysis, run_backtest
from trading_lab.strategies.bollinger_band_reversion import BollingerBandReversionStrategy
from trading_lab.strategies.fibonacci_retracement import FibonacciRetracementStrategy
from trading_lab.strategies.buy_and_hold import BuyAndHoldStrategy
from trading_lab.strategies.donchian_breakout import DonchianBreakoutStrategy
from trading_lab.strategies.ema_crossover import EMACrossoverStrategy
from trading_lab.strategies.macd_crossover import MACDCrossoverStrategy
from trading_lab.strategies.mean_reversion_zscore import MeanReversionZScoreStrategy
from trading_lab.strategies.momentum import MomentumStrategy
from trading_lab.strategies.rsi_mean_reversion import RSIMeanReversionStrategy
from trading_lab.strategies.sma_crossover import SMACrossoverStrategy
from trading_lab.strategies.triple_sma import TripleSMAStrategy


def _make_ohlcv(n: int = 300, start: str = "2020-01-01") -> pd.DataFrame:
    """Synthetic OHLCV DataFrame for unit tests."""
    idx = pd.date_range(start, periods=n, freq="B")
    rng = np.random.default_rng(0)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))
    high = close * (1 + rng.uniform(0.0, 0.02, n))
    low = close * (1 - rng.uniform(0.0, 0.02, n))
    open_ = close * (1 + rng.normal(0.0, 0.005, n))
    volume = rng.integers(1_000_000, 10_000_000, n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


class TestBacktestEngine(unittest.TestCase):
    def _check_result(self, res, strategy_name: str) -> None:
        self.assertTrue((res.equity > 0).all(), f"{strategy_name}: equity went non-positive")
        self.assertIn("sharpe", res.metrics)
        self.assertEqual(len(res.signals), len(res.prices))

    def test_buy_and_hold_positive_equity(self) -> None:
        ohlcv = _make_ohlcv()
        res = run_backtest(ohlcv, BuyAndHoldStrategy(), symbol="TEST")
        self._check_result(res, "buy_and_hold")

    def test_sma_crossover(self) -> None:
        ohlcv = _make_ohlcv()
        res = run_backtest(ohlcv, SMACrossoverStrategy(fast=10, slow=30), symbol="TEST")
        self._check_result(res, "sma_crossover")

    def test_rsi_mean_reversion(self) -> None:
        ohlcv = _make_ohlcv()
        res = run_backtest(ohlcv, RSIMeanReversionStrategy(), symbol="TEST")
        self._check_result(res, "rsi_mean_reversion")

    def test_macd_crossover(self) -> None:
        ohlcv = _make_ohlcv()
        res = run_backtest(ohlcv, MACDCrossoverStrategy(), symbol="TEST")
        self._check_result(res, "macd_crossover")

    def test_bollinger_band_reversion(self) -> None:
        ohlcv = _make_ohlcv()
        res = run_backtest(ohlcv, BollingerBandReversionStrategy(), symbol="TEST")
        self._check_result(res, "bollinger_band_reversion")

    def test_momentum(self) -> None:
        ohlcv = _make_ohlcv(n=500)
        res = run_backtest(ohlcv, MomentumStrategy(lookback=252), symbol="TEST")
        self._check_result(res, "momentum")

    def test_mean_reversion_zscore(self) -> None:
        ohlcv = _make_ohlcv()
        res = run_backtest(ohlcv, MeanReversionZScoreStrategy(), symbol="TEST")
        self._check_result(res, "mean_reversion_zscore")

    def test_ema_crossover(self) -> None:
        ohlcv = _make_ohlcv(n=500)
        res = run_backtest(ohlcv, EMACrossoverStrategy(fast=20, slow=50), symbol="TEST")
        self._check_result(res, "ema_crossover")

    def test_donchian_breakout(self) -> None:
        ohlcv = _make_ohlcv()
        res = run_backtest(ohlcv, DonchianBreakoutStrategy(), symbol="TEST")
        self._check_result(res, "donchian_breakout")

    def test_triple_sma(self) -> None:
        ohlcv = _make_ohlcv(n=500)
        res = run_backtest(ohlcv, TripleSMAStrategy(fast=10, mid=30, slow=100), symbol="TEST")
        self._check_result(res, "triple_sma")

    def test_fibonacci_retracement(self) -> None:
        ohlcv = _make_ohlcv()
        res = run_backtest(ohlcv, FibonacciRetracementStrategy(window=20), symbol="TEST")
        self._check_result(res, "fibonacci_retracement")

    def test_run_analysis(self) -> None:
        ohlcv = _make_ohlcv()
        frames = {"SYM1": ohlcv, "SYM2": ohlcv.copy()}
        results = run_analysis(frames, BuyAndHoldStrategy())
        self.assertEqual(set(results.keys()), {"SYM1", "SYM2"})
        for res in results.values():
            self.assertTrue((res.equity > 0).all())


if __name__ == "__main__":
    unittest.main()
