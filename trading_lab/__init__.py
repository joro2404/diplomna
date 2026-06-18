"""Multi-symbol strategy backtesting toolkit."""

from trading_lab.backtest.engine import run_analysis, run_backtest
from trading_lab.backtest.results import BacktestResult
from trading_lab.data.cleaner import clean_ohlcv, cleaning_report
from trading_lab.data.loader import fetch_and_cache, load_adj_close
from trading_lab.data.storage import (
    cache_covers,
    clean_path,
    load_clean,
    load_raw,
    raw_path,
    save_clean,
    save_raw,
)
from trading_lab.strategies.bollinger_band_reversion import BollingerBandReversionStrategy
from trading_lab.strategies.buy_and_hold import BuyAndHoldStrategy
from trading_lab.strategies.fibonacci_retracement import FibonacciRetracementStrategy
from trading_lab.strategies.donchian_breakout import DonchianBreakoutStrategy
from trading_lab.strategies.ema_crossover import EMACrossoverStrategy
from trading_lab.strategies.macd_crossover import MACDCrossoverStrategy
from trading_lab.strategies.mean_reversion_zscore import MeanReversionZScoreStrategy
from trading_lab.strategies.momentum import MomentumStrategy
from trading_lab.strategies.registry import create_strategy, list_strategies
from trading_lab.strategies.rsi_mean_reversion import RSIMeanReversionStrategy
from trading_lab.strategies.custom_triad_conviction import CustomTriadConvictionStrategy
from trading_lab.strategies.sma_crossover import SMACrossoverStrategy
from trading_lab.strategies.triple_sma import TripleSMAStrategy

__version__ = "0.1.0"

__all__ = [
    "BacktestResult",
    "BollingerBandReversionStrategy",
    "BuyAndHoldStrategy",
    "DonchianBreakoutStrategy",
    "EMACrossoverStrategy",
    "FibonacciRetracementStrategy",
    "MACDCrossoverStrategy",
    "MeanReversionZScoreStrategy",
    "MomentumStrategy",
    "RSIMeanReversionStrategy",
    "CustomTriadConvictionStrategy",
    "SMACrossoverStrategy",
    "TripleSMAStrategy",
    "cache_covers",
    "clean_ohlcv",
    "clean_path",
    "cleaning_report",
    "create_strategy",
    "fetch_and_cache",
    "list_strategies",
    "load_adj_close",
    "load_clean",
    "load_raw",
    "raw_path",
    "run_analysis",
    "run_backtest",
    "save_clean",
    "save_raw",
]
