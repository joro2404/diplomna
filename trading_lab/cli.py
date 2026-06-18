"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trading_lab.backtest.engine import run_analysis
from trading_lab.config.symbols import DEFAULT_UNIVERSE
from trading_lab.data.loader import fetch_and_cache
from trading_lab.strategies.registry import create_strategy, list_strategies


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="trading-lab",
        description="Run strategy backtests on Yahoo Finance symbols.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # fetch: download and cache data without backtesting
    fetch = sub.add_parser(
        "fetch",
        help="Download full OHLCV data and save raw + clean CSVs",
    )
    fetch.add_argument(
        "--symbols", "-y",
        nargs="+",
        default=list(DEFAULT_UNIVERSE),
        help="Yahoo Finance tickers (default: thesis universe)",
    )
    fetch.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    fetch.add_argument("--end", default=None, help="End date (YYYY-MM-DD), exclusive")
    fetch.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when local cache already exists",
    )

    # run: fetch (or reuse cache) and run a backtest
    run = sub.add_parser("run", help="Download OHLCV data and run a backtest")
    run.add_argument(
        "--strategy", "-s",
        required=True,
        choices=list_strategies(),
        help="Registered strategy name",
    )
    run.add_argument(
        "--symbols", "-y",
        nargs="+",
        default=list(DEFAULT_UNIVERSE),
        help="Yahoo Finance tickers (default: thesis universe)",
    )
    run.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    run.add_argument("--end", default=None, help="End date (YYYY-MM-DD), exclusive")
    run.add_argument("--capital", type=float, default=100_000.0, help="Initial capital")
    run.add_argument(
        "--commission", type=float, default=0.0005, help="Per-turnover commission rate"
    )

    # --- sma_crossover / ema_crossover shared params ---
    run.add_argument("--fast", type=int, default=None,
                     help="[sma_crossover] fast SMA window  "
                          "[ema_crossover] fast EMA window  "
                          "[macd_crossover] fast EMA period  "
                          "[triple_sma] fast SMA window")
    run.add_argument("--slow", type=int, default=None,
                     help="[sma_crossover] slow SMA window  "
                          "[ema_crossover] slow EMA window  "
                          "[macd_crossover] slow EMA period  "
                          "[triple_sma] slow SMA window")

    # --- rsi_mean_reversion ---
    run.add_argument("--rsi-period", type=int, default=14,
                     help="[rsi_mean_reversion] RSI period")
    run.add_argument("--oversold", type=float, default=30.0,
                     help="[rsi_mean_reversion] oversold level")
    run.add_argument("--overbought", type=float, default=70.0,
                     help="[rsi_mean_reversion] overbought level")

    # --- macd_crossover ---
    run.add_argument("--macd-signal", type=int, default=9,
                     help="[macd_crossover] signal-line EMA period")

    # --- bollinger_band_reversion ---
    run.add_argument("--bb-window", type=int, default=20,
                     help="[bollinger_band_reversion] rolling window")
    run.add_argument("--bb-std", type=float, default=2.0,
                     help="[bollinger_band_reversion] band width in std devs")

    # --- momentum ---
    run.add_argument("--mom-lookback", type=int, default=252,
                     help="[momentum] trailing return window (trading days)")

    # --- mean_reversion_zscore ---
    run.add_argument("--zscore-window", type=int, default=20,
                     help="[mean_reversion_zscore] rolling window")
    run.add_argument("--zscore-entry", type=float, default=1.5,
                     help="[mean_reversion_zscore] entry z-score threshold")
    run.add_argument("--zscore-exit", type=float, default=0.0,
                     help="[mean_reversion_zscore] exit z-score threshold")

    # --- donchian_breakout ---
    run.add_argument("--don-window", type=int, default=20,
                     help="[donchian_breakout] channel lookback window")

    # --- fibonacci_retracement ---
    run.add_argument("--fib-window", type=int, default=50,
                     help="[fibonacci_retracement] swing-point lookback window")
    run.add_argument("--fib-entry", type=float, default=0.618,
                     help="[fibonacci_retracement] entry retracement level (default 0.618 — golden ratio)")
    run.add_argument("--fib-exit", type=float, default=0.382,
                     help="[fibonacci_retracement] exit retracement level (default 0.382)")

    # --- triple_sma ---
    run.add_argument("--triple-mid", type=int, default=50,
                     help="[triple_sma] mid SMA window")

    # --- custom_triad_conviction (experimental hybrid) ---
    run.add_argument("--triad-bear-throttle", type=float, default=0.5,
                     help="[custom_triad_conviction] exposure multiplier in bear regimes (0..1)")
    run.add_argument("--triad-conviction-power", type=float, default=1.0,
                     help="[custom_triad_conviction] convexity of the conviction curve (>1 = demand more agreement)")
    run.add_argument("--triad-don-window", type=int, default=20,
                     help="[custom_triad_conviction] Donchian channel lookback window")
    run.add_argument("--triad-mom-lookback", type=int, default=252,
                     help="[custom_triad_conviction] momentum regime lookback (trading days)")

    run.add_argument(
        "--no-cache",
        action="store_true",
        help="Force a fresh download; overwrite any existing cached CSV files",
    )
    run.add_argument(
        "--export-json",
        type=Path,
        default=None,
        help="Write summary metrics to this JSON file",
    )

    sub.add_parser("list-strategies", help="Print registered strategy names")

    return p


def _build_strategy_params(args: argparse.Namespace) -> dict[str, float | int]:
    """Map CLI args to the param dict expected by create_strategy."""
    s = args.strategy

    if s == "sma_crossover":
        return {"fast": args.fast or 20, "slow": args.slow or 50}

    if s == "rsi_mean_reversion":
        return {
            "period": args.rsi_period,
            "oversold": args.oversold,
            "overbought": args.overbought,
        }

    if s == "macd_crossover":
        return {
            "fast": args.fast or 12,
            "slow": args.slow or 26,
            "signal": args.macd_signal,
        }

    if s == "bollinger_band_reversion":
        return {"window": args.bb_window, "num_std": args.bb_std}

    if s == "momentum":
        return {"lookback": args.mom_lookback}

    if s == "mean_reversion_zscore":
        return {
            "window": args.zscore_window,
            "entry_z": args.zscore_entry,
            "exit_z": args.zscore_exit,
        }

    if s == "ema_crossover":
        return {"fast": args.fast or 50, "slow": args.slow or 200}

    if s == "donchian_breakout":
        return {"window": args.don_window}

    if s == "fibonacci_retracement":
        return {
            "window": args.fib_window,
            "entry_fib": args.fib_entry,
            "exit_fib": args.fib_exit,
        }

    if s == "triple_sma":
        return {
            "fast": args.fast or 10,
            "mid": args.triple_mid,
            "slow": args.slow or 200,
        }

    if s == "custom_triad_conviction":
        return {
            "mom_lookback": args.triad_mom_lookback,
            "donchian_window": args.triad_don_window,
            "bear_throttle": args.triad_bear_throttle,
            "conviction_power": args.triad_conviction_power,
        }

    return {}


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "list-strategies":
        for name in list_strategies():
            print(name)
        return 0

    if args.command == "fetch":
        symbols: list[str] = list(args.symbols)
        print(f"Fetching {len(symbols)} symbol(s): {', '.join(symbols)}")
        frames = fetch_and_cache(
            symbols,
            start=args.start,
            end=args.end,
            force_refresh=args.force,
            verbose=True,
        )
        print()
        for sym, df in frames.items():
            print(
                f"  {sym:12s}  {len(df):>5d} rows  "
                f"{df.index.min().date()} … {df.index.max().date()}"
            )
        return 0

    if args.command == "run":
        strategy = create_strategy(args.strategy, **_build_strategy_params(args))

        ohlcv_frames = fetch_and_cache(
            list(args.symbols),
            start=args.start,
            end=args.end,
            force_refresh=args.no_cache,
            verbose=False,
        )

        results = run_analysis(
            ohlcv_frames,
            strategy,
            initial_capital=args.capital,
            commission_rate=args.commission,
        )

        summary: dict[str, dict[str, float]] = {}
        for sym, res in results.items():
            m = res.metrics
            summary[sym] = m
            print(f"\n=== {sym}  ({res.strategy_name}) ===")
            for k, v in m.items():
                print(f"  {k}: {v:.4f}")

        if args.export_json:
            args.export_json.parent.mkdir(parents=True, exist_ok=True)
            args.export_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(f"\nWrote {args.export_json}")

        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
