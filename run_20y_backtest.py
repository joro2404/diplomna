"""Run every strategy on every asset over ~20 years and write the results.

Outputs a metrics CSV, a markdown report and a handful of charts under
results/. Run with: python run_20y_backtest.py
"""

from __future__ import annotations

import math
import os
import textwrap
from datetime import date
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from trading_lab.config.symbols import DEFAULT_UNIVERSE
from trading_lab.data.loader import fetch_and_cache
from trading_lab.backtest.engine import run_backtest
from trading_lab.backtest.results import BacktestResult
from trading_lab.strategies.registry import list_strategies, create_strategy

START_DATE     = "2006-05-20"
END_DATE: str | None = None
INITIAL_CAPITAL  = 100_000.0
COMMISSION_RATE  = 0.0005
# True re-downloads everything; False reuses the cached CSVs when they cover the range
FORCE_REFRESH  = False

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
CHARTS_DIR  = os.path.join(RESULTS_DIR, "charts")
METRICS_CSV = os.path.join(RESULTS_DIR, "backtest_20y_metrics.csv")
REPORT_MD   = os.path.join(RESULTS_DIR, "backtest_20y_report.md")

SYMBOLS = list(DEFAULT_UNIVERSE)

ASSET_LABELS = {
    "^GSPC":   "S&P 500",
    "^IXIC":   "Nasdaq",
    "GLD":     "Gold ETF",
    "SLV":     "Silver ETF",
    "BTC-USD": "Bitcoin",
}

STRATEGY_DESCRIPTIONS = {
    "buy_and_hold":             "Long from day 1, never exits (baseline).",
    "sma_crossover":            "Long when fast SMA (20d) > slow SMA (50d).",
    "ema_crossover":            "Golden Cross: long when EMA-50 > EMA-200.",
    "triple_sma":               "Long only when SMA-10 > SMA-50 > SMA-200.",
    "macd_crossover":           "Long when MACD line > signal line (12/26/9).",
    "rsi_mean_reversion":       "Long when RSI-14 < 30; exit when RSI > 70.",
    "bollinger_band_reversion": "Long below lower Bollinger Band (20d, 2σ).",
    "mean_reversion_zscore":    "Long when z-score < -1.5; exit when z > 0.",
    "momentum":                 "Long when 252-day trailing return is positive.",
    "donchian_breakout":        "Long above 20-day high; exit on 20-day low.",
    "fibonacci_retracement":    "Long at 61.8 % Fib level; exit at 38.2 %.",
    "custom_triad_conviction":  "Experimental hybrid of the top 3: MACD + momentum + Donchian vote; goes fully long when a majority (>=2 of 3) agree & throttled in bear regimes.",
}

CHART_STYLE    = "seaborn-v0_8-whitegrid"
BNH_COLOR      = "#E74C3C"
STRATEGY_ALPHA = 0.75

# our custom strategy gets highlighted on every chart
HIGHLIGHT_STRAT = "custom_triad_conviction"
HIGHLIGHT_COLOR = "#8E44AD"
HIGHLIGHT_EDGE  = "#F1C40F"
HIGHLIGHT_EDGE_LW = 2.6

# (column, label, higher_is_better, scale, fmt)
METRICS: list[tuple[str, str, bool, float, str]] = [
    ("total_return",   "Total Return",    True,  100.0, "+.1f%"),
    ("cagr",           "CAGR",            True,  100.0, "+.2f%"),
    ("volatility_ann", "Volatility",      False, 100.0, ".1f%"),
    ("sharpe",         "Sharpe Ratio",    True,  1.0,   "+.3f"),
    ("max_drawdown",   "Max Drawdown",    True,  100.0, ".1f%"),
]


def _fmt(v: float, spec: str) -> str:
    if math.isnan(v):
        return "n/a"
    return format(v, spec)

def _delta_str(delta: float, scale: float = 1.0, unit: str = "") -> str:
    if math.isnan(delta):
        return "n/a"
    arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "–")
    return f"{arrow}{abs(delta * scale):.2f}{unit}"

def _hr(char: str = "-", width: int = 90) -> str:
    return char * width

def _style() -> None:
    try:
        plt.style.use(CHART_STYLE)
    except Exception:
        pass

def _mark_tick(ax: Any, target: str, axis: str = "y",
               color: str = HIGHLIGHT_COLOR) -> None:
    """Bold + recolor one tick label so the custom strategy stands out."""
    labels = ax.get_yticklabels() if axis == "y" else ax.get_xticklabels()
    for lab in labels:
        if lab.get_text() == target:
            lab.set_color(color)
            lab.set_fontweight("bold")
            lab.set_fontsize(lab.get_fontsize() + 1)


def run_all() -> tuple[pd.DataFrame, dict[tuple[str, str], BacktestResult]]:
    from trading_lab.data.storage import load_clean, raw_path, clean_path
    from trading_lab.data.cleaner import cleaning_report

    print("=" * 70)
    print("  20-Year Backtest  |  All strategies × All assets")
    print(f"  Period : {START_DATE}  →  {date.today()}")
    print(f"  Capital: ${INITIAL_CAPITAL:,.0f}  |  Commission: {COMMISSION_RATE*10000:.0f} bps/side")
    print(f"  Force refresh: {FORCE_REFRESH}")
    print("=" * 70)

    # download everything first; we reload from the clean CSVs below
    print(f"\n[1/4] Downloading raw data → market_data/raw/")
    print(f"      (skipped per symbol if cache already covers {START_DATE} → today and FORCE_REFRESH=False)")

    fetch_and_cache(
        SYMBOLS,
        start=START_DATE,
        end=END_DATE,
        force_refresh=FORCE_REFRESH,
        verbose=True,
    )

    print()
    print(f"  {'Asset':<18} {'Symbol':<10} {'Raw file':<28} {'Clean file'}")
    print(f"  {'-'*18} {'-'*10} {'-'*28} {'-'*28}")
    for sym in SYMBOLS:
        label = ASSET_LABELS.get(sym, sym)
        rp    = raw_path(sym)
        cp    = clean_path(sym)
        raw_info   = f"{rp.stat().st_size/1024:6.0f} KB  {rp.name}" if rp.exists() else "MISSING"
        clean_info = f"{cp.stat().st_size/1024:6.0f} KB  {cp.name}" if cp.exists() else "MISSING"
        print(f"  {label:<18} {sym:<10} {raw_info:<28} {clean_info}")

    print(f"\n[2/4] Loading from market_data/clean/ and filtering to {START_DATE} → today …")
    start_ts = pd.Timestamp(START_DATE)
    end_ts   = (pd.Timestamp(END_DATE) if END_DATE
                else pd.Timestamp.today().normalize() + pd.Timedelta(days=1))

    ohlcv_frames: dict[str, pd.DataFrame] = {}
    for sym in SYMBOLS:
        label    = ASSET_LABELS.get(sym, sym)
        df_clean = load_clean(sym)
        if df_clean is None or df_clean.empty:
            print(f"  ✗ {label} ({sym}): no clean data in market_data/clean/ — skipping")
            continue
        filtered = df_clean[(df_clean.index >= start_ts) & (df_clean.index < end_ts)].copy()
        if filtered.empty:
            print(f"  ✗ {label} ({sym}): no data in requested date range — skipping")
            continue
        ohlcv_frames[sym] = filtered
        s   = filtered.index[0].date()
        e   = filtered.index[-1].date()
        yrs = len(filtered) / 252
        print(f"  ✓ {label:<18} {sym:<10} {s} → {e}  ({len(filtered):4d} days ≈ {yrs:.1f} yr)")

    strategies = list_strategies()
    total = len(strategies) * len(ohlcv_frames)
    print(f"\n[3/4] Running {len(strategies)} strategies × {len(ohlcv_frames)} assets = {total} backtests …\n")

    rows: list[dict] = []
    results: dict[tuple[str, str], BacktestResult] = {}
    done = 0

    for strat_name in strategies:
        strategy = create_strategy(strat_name)
        for sym in SYMBOLS:
            ohlcv = ohlcv_frames.get(sym)
            if ohlcv is None or ohlcv.empty:
                done += 1
                continue
            result = run_backtest(
                ohlcv, strategy, symbol=sym,
                initial_capital=INITIAL_CAPITAL,
                commission_rate=COMMISSION_RATE,
            )
            results[(strat_name, sym)] = result
            m = result.metrics
            rows.append({
                "strategy":       strat_name,
                "symbol":         sym,
                "asset":          ASSET_LABELS.get(sym, sym),
                "start_date":     str(result.prices.index[0].date()),
                "end_date":       str(result.prices.index[-1].date()),
                "trading_days":   len(result.prices),
                "years":          round(len(result.prices) / 252, 1),
                "total_return":   m["total_return"],
                "cagr":           m["cagr"],
                "volatility_ann": m["volatility_ann"],
                "sharpe":         m["sharpe"],
                "max_drawdown":   m["max_drawdown"],
                "final_equity":   result.equity.iloc[-1],
            })
            done += 1
            print(
                f"  [{done:3d}/{total}]  {strat_name:<30} {sym:<10} "
                f"Ret={m['total_return']*100:+7.1f}%  CAGR={m['cagr']*100:+5.2f}%  "
                f"Vol={m['volatility_ann']*100:4.1f}%  Sharpe={m['sharpe']:+.2f}  "
                f"MaxDD={m['max_drawdown']*100:6.1f}%"
            )

    df = pd.DataFrame(rows)

    # attach buy-and-hold reference columns and per-metric deltas
    bnh_ref: dict[str, dict] = {}
    for _, row in df[df["strategy"] == "buy_and_hold"].iterrows():
        bnh_ref[row["symbol"]] = {
            "bnh_total_return":   row["total_return"],
            "bnh_cagr":           row["cagr"],
            "bnh_volatility_ann": row["volatility_ann"],
            "bnh_sharpe":         row["sharpe"],
            "bnh_max_drawdown":   row["max_drawdown"],
        }

    extra_rows = []
    for _, row in df.iterrows():
        bnh = bnh_ref.get(row["symbol"], {})
        nan = float("nan")
        extra_rows.append({
            "bnh_total_return":    bnh.get("bnh_total_return",   nan),
            "bnh_cagr":            bnh.get("bnh_cagr",           nan),
            "bnh_volatility_ann":  bnh.get("bnh_volatility_ann", nan),
            "bnh_sharpe":          bnh.get("bnh_sharpe",         nan),
            "bnh_max_drawdown":    bnh.get("bnh_max_drawdown",   nan),
            # deltas: positive always means the strategy beats B&H
            "delta_total_return":  row["total_return"]   - bnh.get("bnh_total_return",   nan),
            "delta_cagr":          row["cagr"]           - bnh.get("bnh_cagr",           nan),
            "delta_volatility":    bnh.get("bnh_volatility_ann", nan) - row["volatility_ann"],
            "delta_sharpe":        row["sharpe"]         - bnh.get("bnh_sharpe",         nan),
            "delta_max_drawdown":  row["max_drawdown"]   - bnh.get("bnh_max_drawdown",   nan),
            "beats_total_return":  row["total_return"]   > bnh.get("bnh_total_return",   nan),
            "beats_cagr":          row["cagr"]           > bnh.get("bnh_cagr",           nan),
            "beats_volatility":    row["volatility_ann"] < bnh.get("bnh_volatility_ann", nan),
            "beats_sharpe":        row["sharpe"]         > bnh.get("bnh_sharpe",         nan),
            "beats_max_drawdown":  row["max_drawdown"]   > bnh.get("bnh_max_drawdown",   nan),
        })

    df = pd.concat([df.reset_index(drop=True), pd.DataFrame(extra_rows)], axis=1)

    # composite rank per asset, then averaged
    rank_blocks = []
    for sym in SYMBOLS:
        sub = df[df["symbol"] == sym].copy()
        for col in ["total_return", "cagr", "sharpe", "max_drawdown"]:
            sub[f"_rank_{col}"] = sub[col].rank(ascending=True)
        # lower vol is better, so rank it the other way round
        sub["_rank_volatility_ann"] = sub["volatility_ann"].rank(ascending=False)
        rank_blocks.append(sub)

    ranked = pd.concat(rank_blocks, ignore_index=True)
    rank_cols = [c for c in ranked.columns if c.startswith("_rank_")]
    ranked["composite_score"] = ranked[rank_cols].mean(axis=1)

    df = df.merge(
        ranked[["strategy", "symbol", "composite_score"]],
        on=["strategy", "symbol"], how="left"
    )

    return df, results


def save_csv(df: pd.DataFrame) -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = df.copy()

    pct_raw = [
        "total_return", "cagr", "volatility_ann", "max_drawdown",
        "bnh_total_return", "bnh_cagr", "bnh_volatility_ann", "bnh_max_drawdown",
    ]
    for col in pct_raw:
        if col in out.columns:
            out[col] = (out[col] * 100).round(2)

    delta_pct = ["delta_total_return", "delta_cagr", "delta_volatility", "delta_max_drawdown"]
    for col in delta_pct:
        if col in out.columns:
            out[col] = (out[col] * 100).round(2)

    for col in ["sharpe", "bnh_sharpe", "delta_sharpe"]:
        if col in out.columns:
            out[col] = out[col].round(3)

    out["final_equity"]     = out["final_equity"].round(2)
    out["composite_score"]  = out["composite_score"].round(2)

    out = out[[c for c in out.columns if not c.startswith("_rank_")]]

    out.to_csv(METRICS_CSV, index=False)
    print(f"  ✓ Metrics CSV → {METRICS_CSV}")


def save_charts(
    df: pd.DataFrame,
    results: dict[tuple[str, str], BacktestResult],
) -> list[str]:
    os.makedirs(CHARTS_DIR, exist_ok=True)
    generated: list[str] = []

    active_strats = [s for s in list_strategies() if s != "buy_and_hold"]
    asset_labels  = [ASSET_LABELS.get(s, s) for s in SYMBOLS]

    # Chart 1: Sharpe heatmap
    strat_order = (
        df[df["strategy"] != "buy_and_hold"]
        .groupby("strategy")["sharpe"].mean()
        .sort_values(ascending=True).index.tolist()
    )
    row_labels = ["buy_and_hold"] + strat_order

    matrix = np.full((len(row_labels), len(SYMBOLS)), np.nan)
    for r, strat in enumerate(row_labels):
        for c, sym in enumerate(SYMBOLS):
            vals = df.loc[(df["strategy"] == strat) & (df["symbol"] == sym), "sharpe"]
            if not vals.empty:
                matrix[r, c] = vals.values[0]

    _style()
    fig, ax = plt.subplots(figsize=(10, 7))
    im = ax.imshow(matrix, cmap="RdYlGn", aspect="auto", vmin=-0.1, vmax=1.2)
    ax.set_xticks(range(len(SYMBOLS)))
    ax.set_xticklabels(asset_labels, fontsize=11)
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels, fontsize=10)
    ax.xaxis.tick_top()
    ax.xaxis.set_label_position("top")
    for r in range(len(row_labels)):
        for c in range(len(SYMBOLS)):
            v = matrix[r, c]
            if not np.isnan(v):
                tc = "white" if v < 0.15 or v > 1.0 else "black"
                ax.text(c, r, f"{v:.2f}", ha="center", va="center",
                        fontsize=9, color=tc, fontweight="bold")
    ax.add_patch(plt.Rectangle((-0.5, -0.5), len(SYMBOLS), 1,
                                fill=False, edgecolor=BNH_COLOR, linewidth=2.5, zorder=3))
    if HIGHLIGHT_STRAT in row_labels:
        hr = row_labels.index(HIGHLIGHT_STRAT)
        ax.add_patch(plt.Rectangle((-0.5, hr - 0.5), len(SYMBOLS), 1,
                                    fill=False, edgecolor=HIGHLIGHT_COLOR,
                                    linewidth=HIGHLIGHT_EDGE_LW + 0.6, zorder=4))
        _mark_tick(ax, HIGHLIGHT_STRAT, axis="y")
    fig.colorbar(im, ax=ax, label="Sharpe Ratio", shrink=0.7)
    ax.set_title("Sharpe Ratio Heatmap — Strategies × Assets\n"
                 "(red border = Buy-and-Hold baseline · purple border = custom hybrid)",
                 pad=18, fontsize=12)
    fig.tight_layout()
    path = os.path.join(CHARTS_DIR, "sharpe_heatmap.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    generated.append("charts/sharpe_heatmap.png")
    print(f"  ✓ Chart → {path}")

    # Chart 2: 5-panel metric comparison
    agg = df.groupby("strategy").agg(
        avg_total_return=  ("total_return",   "mean"),
        avg_cagr=          ("cagr",           "mean"),
        avg_volatility=    ("volatility_ann", "mean"),
        avg_sharpe=        ("sharpe",         "mean"),
        avg_max_drawdown=  ("max_drawdown",   "mean"),
    ).reset_index()

    panel_defs = [
        ("avg_total_return", "Avg Total Return (%)", True,  100.0),
        ("avg_cagr",         "Avg CAGR (%)",         True,  100.0),
        ("avg_volatility",   "Avg Volatility (%)\nlower = safer", False, 100.0),
        ("avg_sharpe",       "Avg Sharpe Ratio",     True,  1.0),
        ("avg_max_drawdown", "Avg Max Drawdown (%)\nless negative = better", True, 100.0),
    ]

    _style()
    fig, axes = plt.subplots(1, 5, figsize=(22, 7))
    for ax, (col, label, higher_better, scale) in zip(axes, panel_defs):
        sub = agg[["strategy", col]].copy()
        sub["val"] = sub[col] * scale
        sub = sub.sort_values("val", ascending=True)
        colors = [
            BNH_COLOR if s == "buy_and_hold"
            else HIGHLIGHT_COLOR if s == HIGHLIGHT_STRAT
            else "#3498DB"
            for s in sub["strategy"]
        ]
        edges = [HIGHLIGHT_EDGE if s == HIGHLIGHT_STRAT else "white" for s in sub["strategy"]]
        lws   = [HIGHLIGHT_EDGE_LW if s == HIGHLIGHT_STRAT else 0.6 for s in sub["strategy"]]
        bars = ax.barh(sub["strategy"], sub["val"], color=colors,
                       edgecolor=edges, linewidth=lws, height=0.6)

        bnh_val = sub.loc[sub["strategy"] == "buy_and_hold", "val"]
        if not bnh_val.empty and not np.isnan(bnh_val.values[0]):
            ax.axvline(bnh_val.values[0], color=BNH_COLOR, linewidth=1.5, linestyle="--")

        for bar, (s, v) in zip(bars, zip(sub["strategy"], sub["val"])):
            sign = "+" if v > 0 else ""
            ax.text(v + (abs(sub["val"].max()) * 0.01),
                    bar.get_y() + bar.get_height() / 2,
                    f"{sign}{v:.1f}", va="center", fontsize=7.5,
                    fontweight="bold" if s == HIGHLIGHT_STRAT else "normal")

        ax.set_title(label, fontsize=9, fontweight="bold")
        ax.tick_params(axis="y", labelsize=8)
        ax.tick_params(axis="x", labelsize=7.5)
        _mark_tick(ax, HIGHLIGHT_STRAT, axis="y")
        arrow = "↑ better" if higher_better else "↓ better"
        ax.set_xlabel(arrow, fontsize=7.5, color="grey")

    fig.suptitle(
        "All Strategies — Average Performance Across All Assets\n"
        "(red = Buy-and-Hold baseline · purple = custom hybrid)",
        fontsize=13, y=1.01,
    )
    fig.tight_layout()
    path = os.path.join(CHARTS_DIR, "metric_comparison.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    generated.append("charts/metric_comparison.png")
    print(f"  ✓ Chart → {path}")

    # Chart 3: Composite ranking
    comp = (
        df.groupby("strategy")["composite_score"]
        .mean()
        .sort_values(ascending=True)
    )
    bnh_comp = comp.get("buy_and_hold", np.nan)
    colors = [
        BNH_COLOR if s == "buy_and_hold"
        else HIGHLIGHT_COLOR if s == HIGHLIGHT_STRAT
        else "#2ECC71"
        for s in comp.index
    ]
    edges = [HIGHLIGHT_EDGE if s == HIGHLIGHT_STRAT else "white" for s in comp.index]
    lws   = [HIGHLIGHT_EDGE_LW if s == HIGHLIGHT_STRAT else 0.6 for s in comp.index]

    _style()
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(comp.index, comp.values, color=colors,
                   edgecolor=edges, linewidth=lws, height=0.6)
    for bar, (s, v) in zip(bars, zip(comp.index, comp.values)):
        ax.text(v + 0.05, bar.get_y() + bar.get_height() / 2,
                f"{v:.2f}", va="center", fontsize=9,
                fontweight="bold" if s == HIGHLIGHT_STRAT else "normal")
    legend_handles = []
    if not np.isnan(bnh_comp):
        ax.axvline(bnh_comp, color=BNH_COLOR, linewidth=1.8, linestyle="--")
        legend_handles.append(Line2D([0], [0], color=BNH_COLOR, lw=1.8, ls="--",
                                     label=f"Buy-and-Hold ({bnh_comp:.2f})"))
    if HIGHLIGHT_STRAT in comp.index:
        legend_handles.append(Patch(facecolor=HIGHLIGHT_COLOR, edgecolor=HIGHLIGHT_EDGE,
                                    linewidth=HIGHLIGHT_EDGE_LW,
                                    label=f"custom hybrid ({comp[HIGHLIGHT_STRAT]:.2f})"))
        _mark_tick(ax, HIGHLIGHT_STRAT, axis="y")
    if legend_handles:
        ax.legend(handles=legend_handles, fontsize=9, loc="lower right")
    ax.set_xlabel("Composite Score (avg rank across all 5 metrics — higher = better)", fontsize=10)
    ax.set_title(
        "Composite Strategy Ranking — All 5 Metrics Combined\n"
        "(Total Return, CAGR, Volatility, Sharpe, Max Drawdown)",
        fontsize=12,
    )
    fig.tight_layout()
    path = os.path.join(CHARTS_DIR, "composite_ranking.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    generated.append("charts/composite_ranking.png")
    print(f"  ✓ Chart → {path}")

    # Chart 4: Overall ranking (avg Sharpe across all assets)
    sharpe_rank = (
        df.groupby("strategy")["sharpe"].mean().sort_values(ascending=True)
    )
    bnh_sharpe = sharpe_rank.get("buy_and_hold", np.nan)
    s_colors = [
        BNH_COLOR if s == "buy_and_hold"
        else HIGHLIGHT_COLOR if s == HIGHLIGHT_STRAT
        else "#3498DB"
        for s in sharpe_rank.index
    ]
    s_edges = [HIGHLIGHT_EDGE if s == HIGHLIGHT_STRAT else "white" for s in sharpe_rank.index]
    s_lws   = [HIGHLIGHT_EDGE_LW if s == HIGHLIGHT_STRAT else 0.6 for s in sharpe_rank.index]

    _style()
    fig, ax = plt.subplots(figsize=(10, 6.5))
    bars = ax.barh(sharpe_rank.index, sharpe_rank.values, color=s_colors,
                   edgecolor=s_edges, linewidth=s_lws, height=0.62)
    for bar, (s, v) in zip(bars, zip(sharpe_rank.index, sharpe_rank.values)):
        ax.text(v + 0.005, bar.get_y() + bar.get_height() / 2,
                f"{v:+.3f}", va="center", fontsize=8.5,
                fontweight="bold" if s == HIGHLIGHT_STRAT else "normal")
    legend_handles = []
    if not np.isnan(bnh_sharpe):
        ax.axvline(bnh_sharpe, color=BNH_COLOR, linewidth=1.8, linestyle="--")
        legend_handles.append(Line2D([0], [0], color=BNH_COLOR, lw=1.8, ls="--",
                                     label=f"Buy-and-Hold ({bnh_sharpe:+.3f})"))
    if HIGHLIGHT_STRAT in sharpe_rank.index:
        legend_handles.append(Patch(facecolor=HIGHLIGHT_COLOR, edgecolor=HIGHLIGHT_EDGE,
                                    linewidth=HIGHLIGHT_EDGE_LW,
                                    label=f"custom hybrid ({sharpe_rank[HIGHLIGHT_STRAT]:+.3f})"))
        _mark_tick(ax, HIGHLIGHT_STRAT, axis="y")
    if legend_handles:
        ax.legend(handles=legend_handles, fontsize=9, loc="lower right")
    ax.set_xlabel("Average Sharpe Ratio (all assets)", fontsize=10)
    ax.set_title(
        "Overall Strategy Ranking — Average Sharpe Across All Assets\n"
        "(red = Buy-and-Hold baseline · purple = custom hybrid)",
        fontsize=12,
    )
    fig.tight_layout()
    path = os.path.join(CHARTS_DIR, "overall_ranking.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    generated.append("charts/overall_ranking.png")
    print(f"  ✓ Chart → {path}")

    # Charts 5-9: Equity curves per asset
    cmap = plt.get_cmap("tab10")
    strat_colors = {s: cmap(i % 10) for i, s in enumerate(active_strats)}
    strat_colors["buy_and_hold"] = BNH_COLOR
    strat_colors[HIGHLIGHT_STRAT] = HIGHLIGHT_COLOR

    for sym in SYMBOLS:
        label = ASSET_LABELS.get(sym, sym)
        safe  = sym.replace("^", "").replace("-", "_")

        _style()
        fig, ax = plt.subplots(figsize=(13, 6))

        bnh_res = results.get(("buy_and_hold", sym))
        if bnh_res is not None:
            eq = bnh_res.equity / INITIAL_CAPITAL * 100
            ax.plot(eq.index, eq.values, color=BNH_COLOR, linewidth=2.5,
                    linestyle="--", label="buy_and_hold (baseline)", zorder=10)

        for strat_name in active_strats:
            if strat_name == HIGHLIGHT_STRAT:
                continue  # drawn last, on top
            res = results.get((strat_name, sym))
            if res is None:
                continue
            eq = res.equity / INITIAL_CAPITAL * 100
            ax.plot(eq.index, eq.values, color=strat_colors[strat_name],
                    linewidth=1.2, alpha=STRATEGY_ALPHA, label=strat_name)

        # Custom hybrid drawn last: thick, full-opacity, on top of everything.
        hl_res = results.get((HIGHLIGHT_STRAT, sym))
        if hl_res is not None:
            eq = hl_res.equity / INITIAL_CAPITAL * 100
            ax.plot(eq.index, eq.values, color=HIGHLIGHT_COLOR, linewidth=3.0,
                    alpha=1.0, zorder=11, label=f"{HIGHLIGHT_STRAT} (CUSTOM)")

        ax.axhline(100, color="grey", linewidth=0.8, linestyle=":")
        ax.set_ylabel("Portfolio Value (start = 100)", fontsize=11)
        ax.set_title(
            f"Equity Curves — {label} ({sym})\n"
            "Custom hybrid (thick purple line) vs Buy-and-Hold (red dashed)",
            fontsize=12,
        )
        ax.yaxis.set_major_formatter(mtick.FormatStrFormatter("%.0f"))
        ax.legend(fontsize=7.5, ncol=2, loc="upper left")
        fig.tight_layout()
        path = os.path.join(CHARTS_DIR, f"equity_{safe}.png")
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        generated.append(f"charts/equity_{safe}.png")
        print(f"  ✓ Chart → {path}")

    return generated


def build_report(df: pd.DataFrame, chart_paths: list[str]) -> str:
    today = date.today()
    lines: list[str] = []

    def h1(t: str) -> None:
        lines.extend([f"# {t}", ""])

    def h2(t: str) -> None:
        lines.extend([f"## {t}", ""])

    def h3(t: str) -> None:
        lines.extend([f"### {t}", ""])

    def p(t: str = "") -> None:
        lines.append(t)

    def img(path: str, caption: str) -> None:
        lines.extend([f"![{caption}]({path})", ""])

    # title
    h1("20-Year Multi-Strategy Backtest Report")
    p(f"**Generated:** {today}  ")
    p(f"**Period:** {START_DATE} → {today} (target: 20 years)  ")
    p(f"**Universe:** {', '.join(SYMBOLS)}  ")
    p(f"**Initial capital:** ${INITIAL_CAPITAL:,.0f} per strategy/asset pair  ")
    p(f"**Commission:** {COMMISSION_RATE*10000:.0f} bps per trade side (next-bar execution)  ")
    p(f"**Metrics tracked:** Total Return, CAGR, Volatility, Sharpe Ratio, Max Drawdown  ")
    p(f"**Baseline:** every active strategy is compared against **buy-and-hold** on the same asset.  ")
    p()

    # data coverage
    h2("Data Coverage")
    coverage = (df[["symbol", "asset", "start_date", "end_date", "trading_days", "years"]]
                .drop_duplicates("symbol").sort_values("symbol"))
    p("| Asset | Symbol | Start | End | Trading Days | Years |")
    p("|-------|--------|-------|-----|--------------|-------|")
    for _, row in coverage.iterrows():
        p(f"| {row['asset']} | `{row['symbol']}` | {row['start_date']} | {row['end_date']} "
          f"| {int(row['trading_days']):,} | {row['years']:.1f} |")
    p()
    p("> **Note:** BTC-USD available from September 2014 (~12 years), not the full 20.")
    p()

    # strategy catalogue
    h2("Strategy Catalogue")
    p("| # | Strategy | Description |")
    p("|---|----------|-------------|")
    for i, (name, desc) in enumerate(sorted(STRATEGY_DESCRIPTIONS.items()), 1):
        marker = " *(baseline)*" if name == "buy_and_hold" else ""
        p(f"| {i} | `{name}`{marker} | {desc} |")
    p()

    # aggregate stats
    agg = df.groupby("strategy").agg(
        avg_total_return=  ("total_return",   "mean"),
        avg_cagr=          ("cagr",           "mean"),
        avg_volatility=    ("volatility_ann", "mean"),
        avg_sharpe=        ("sharpe",         "mean"),
        avg_max_drawdown=  ("max_drawdown",   "mean"),
        avg_composite=     ("composite_score","mean"),
        min_sharpe=        ("sharpe",         "min"),
        max_sharpe=        ("sharpe",         "max"),
        min_cagr=          ("cagr",           "min"),
        max_cagr=          ("cagr",           "max"),
    ).reset_index()

    bnh_agg = agg[agg["strategy"] == "buy_and_hold"]
    bnh = {col: bnh_agg[col].values[0] if not bnh_agg.empty else float("nan")
           for col in agg.columns if col != "strategy"}

    # multi-metric comparison chart
    h2("Multi-Metric Performance Overview")
    p("Each panel shows all strategies ranked on one metric. "
      "**Red bar & dashed line = buy-and-hold baseline.**")
    p()
    if "charts/metric_comparison.png" in chart_paths:
        img("charts/metric_comparison.png", "Multi-Metric Comparison")

    # composite ranking chart
    h2("Composite Ranking (All 5 Metrics Combined)")
    p("The composite score averages a strategy's **rank** across all five metrics "
      "(Total Return, CAGR, Volatility, Sharpe, Max Drawdown) and all five assets. "
      "A higher score means consistently good performance across every dimension — "
      "it cannot be won by excelling on one metric alone.")
    p()
    if "charts/composite_ranking.png" in chart_paths:
        img("charts/composite_ranking.png", "Composite Ranking")

    # overall ranking (avg Sharpe) chart
    h2("Overall Ranking (Average Sharpe Across All Assets)")
    p("A simpler single-metric view: strategies ranked purely by their average "
      "Sharpe ratio across all five assets. "
      "**Red = buy-and-hold baseline · purple = the custom hybrid.**")
    p()
    if "charts/overall_ranking.png" in chart_paths:
        img("charts/overall_ranking.png", "Overall Ranking — Average Sharpe")

    comp_ranked = agg.sort_values("avg_composite", ascending=False).reset_index(drop=True)
    bnh_comp    = bnh.get("avg_composite", float("nan"))

    p("| Rank | Strategy | Composite Score | vs B&H | Avg Return% | Avg CAGR% | Avg Vol% | Avg Sharpe | Avg DD% |")
    p("|------|----------|----------------|--------|------------|---------|--------|-----------|--------|")
    for i, row in comp_ranked.iterrows():
        rank  = i + 1
        medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else f" {rank}."))
        delta = row["avg_composite"] - bnh_comp
        vs    = "*(baseline)*" if row["strategy"] == "buy_and_hold" else _delta_str(delta, 1.0, "")
        p(
            f"| {medal} | `{row['strategy']}` "
            f"| {row['avg_composite']:.2f} "
            f"| {vs} "
            f"| {row['avg_total_return']*100:+.1f} "
            f"| {row['avg_cagr']*100:+.2f} "
            f"| {row['avg_volatility']*100:.1f} "
            f"| {row['avg_sharpe']:+.3f} "
            f"| {row['avg_max_drawdown']*100:.1f} |"
        )
    p()

    # per-metric leaderboards
    h2("Per-Metric Leaderboards")
    p("Each table ranks strategies on **one metric only**, averaged across all assets. "
      "B&H reference shown for every entry.")
    p()

    metric_defs = [
        ("avg_total_return",  "Total Return (%)",       True,  100.0, "+.1f"),
        ("avg_cagr",          "CAGR (%)",               True,  100.0, "+.2f"),
        ("avg_volatility",    "Volatility (%, lower=better)", False, 100.0, ".1f"),
        ("avg_sharpe",        "Sharpe Ratio",           True,  1.0,   "+.3f"),
        ("avg_max_drawdown",  "Max Drawdown (%, less negative=better)", True, 100.0, ".1f"),
    ]

    for col, label, higher_better, scale, fmt in metric_defs:
        h3(label)
        sorted_agg = agg.sort_values(col, ascending=not higher_better).reset_index(drop=True)
        bnh_val    = bnh.get(col, float("nan"))
        direction  = "↑ higher is better" if higher_better else "↓ lower is better"
        p(f"*{direction}. B&H value: {format(bnh_val * scale, fmt)}.*")
        p()
        p(f"| Rank | Strategy | Avg {label} | vs B&H |")
        p(f"|------|----------|------------|--------|")
        for i, row in sorted_agg.iterrows():
            rank  = i + 1
            medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else f" {rank}."))
            v     = row[col] * scale
            delta = (row[col] - bnh_val) * scale
            if higher_better:
                delta_s = _delta_str(delta, 1.0, "")
            else:
                delta_s = _delta_str(-delta, 1.0, "")   # flip: lower vol is good → positive arrow
            vs = "*(baseline)*" if row["strategy"] == "buy_and_hold" else delta_s
            p(f"| {medal} | `{row['strategy']}` | {format(v, fmt)} | {vs} |")
        p()

    # sharpe heatmap
    h2("Sharpe Ratio Heatmap")
    p("Green = high Sharpe (good), red = low. B&H row outlined in red.")
    p()
    if "charts/sharpe_heatmap.png" in chart_paths:
        img("charts/sharpe_heatmap.png", "Sharpe Heatmap")

    # active strategies vs B&H per asset
    h2("Active Strategies vs Buy-and-Hold — Per Asset")
    p("All five metrics are shown with their delta vs B&H on the same asset. "
      "`Δ` values: positive always means **the strategy is better than B&H** on that metric.")
    p()

    for sym in SYMBOLS:
        label = ASSET_LABELS.get(sym, sym)
        h3(f"{label} (`{sym}`)")

        asset_df  = df[df["symbol"] == sym].copy()
        bnh_row   = asset_df[asset_df["strategy"] == "buy_and_hold"]
        if bnh_row.empty:
            continue
        bnh_r = bnh_row.iloc[0]

        p(f"**Buy-and-Hold baseline:**")
        p(f"- Total Return: **{bnh_r['total_return']*100:+.1f}%**  ")
        p(f"- CAGR: **{bnh_r['cagr']*100:+.2f}%**  ")
        p(f"- Volatility: **{bnh_r['volatility_ann']*100:.1f}%** (annualised)  ")
        p(f"- Sharpe: **{bnh_r['sharpe']:+.2f}**  ")
        p(f"- Max Drawdown: **{bnh_r['max_drawdown']*100:.1f}%**  ")
        p()

        active = asset_df[asset_df["strategy"] != "buy_and_hold"].copy()
        # Sort by composite_score for this asset (already per-asset)
        active = active.sort_values("composite_score", ascending=False).reset_index(drop=True)

        p("*Sorted by composite score. Δ = strategy minus B&H (positive = better than B&H).*")
        p()
        p("| Rank | Strategy | Ret% | Δ Ret | CAGR% | Δ CAGR | Vol% | Δ Vol | Sharpe | Δ Sharpe | MaxDD% | Δ MaxDD | Score |")
        p("|------|----------|------|-------|-------|--------|------|-------|--------|----------|--------|---------|-------|")
        for j, row in active.iterrows():
            rank  = j + 1
            medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else f" {rank}."))
            # delta_volatility is already flipped (positive = lower vol = better)
            p(
                f"| {medal} | `{row['strategy']}` "
                f"| {row['total_return']*100:+.1f} "
                f"| {_delta_str(row['delta_total_return'], 100.0, 'pp')} "
                f"| {row['cagr']*100:+.2f} "
                f"| {_delta_str(row['delta_cagr'], 100.0, 'pp')} "
                f"| {row['volatility_ann']*100:.1f} "
                f"| {_delta_str(row['delta_volatility'], 100.0, 'pp')} "
                f"| {row['sharpe']:+.2f} "
                f"| {_delta_str(row['delta_sharpe'], 1.0, '')} "
                f"| {row['max_drawdown']*100:.1f} "
                f"| {_delta_str(row['delta_max_drawdown'], 100.0, 'pp')} "
                f"| {row['composite_score']:.2f} |"
            )
        p()

    # equity curves
    h2("Equity Curves")
    p("Normalised to start = 100. **Red dashed line = buy-and-hold.**")
    p()
    for sym in SYMBOLS:
        label = ASSET_LABELS.get(sym, sym)
        safe  = sym.replace("^", "").replace("-", "_")
        path  = f"charts/equity_{safe}.png"
        if path in chart_paths:
            p(f"**{label} (`{sym}`)**")
            p()
            img(path, f"Equity – {label}")

    # beats-B&H scorecard
    h2("Beats-B&H Scorecard (Active Strategies Only)")
    p("How many of the 5 assets does each strategy beat buy-and-hold on, per metric?")
    p()

    beat_cols = {
        "Total Return":  "beats_total_return",
        "CAGR":          "beats_cagr",
        "Volatility":    "beats_volatility",
        "Sharpe":        "beats_sharpe",
        "Max Drawdown":  "beats_max_drawdown",
    }

    active_df = df[df["strategy"] != "buy_and_hold"]
    beats_agg = (
        active_df.groupby("strategy")[list(beat_cols.values())]
        .sum().astype(int)
    )
    beats_agg["total_wins"] = beats_agg.sum(axis=1)
    beats_agg = beats_agg.sort_values("total_wins", ascending=False)

    header_metrics = " | ".join(beat_cols.keys())
    sep_metrics    = " | ".join(["-----"] * len(beat_cols))
    p(f"| Strategy | {header_metrics} | Total wins |")
    p(f"|----------|{sep_metrics}|------------|")
    for strat, row in beats_agg.iterrows():
        cells = " | ".join(
            f"{int(row[col])}/5 {'■'*int(row[col])}{'□'*(len(SYMBOLS)-int(row[col]))}"
            for col in beat_cols.values()
        )
        p(f"| `{strat}` | {cells} | **{row['total_wins']}/25** |")
    p()

    # analysis & key findings
    h2("Analysis & Key Findings")

    comp_winner = comp_ranked.iloc[0]
    comp_loser  = comp_ranked.iloc[-1]

    trend_strats  = ["sma_crossover", "ema_crossover", "triple_sma",
                     "macd_crossover", "momentum", "donchian_breakout",
                     "custom_triad_conviction"]
    revert_strats = ["rsi_mean_reversion", "bollinger_band_reversion",
                     "mean_reversion_zscore", "fibonacci_retracement"]

    h3("1. Composite winner — best across all metrics")
    p(
        f"**`{comp_winner['strategy']}`** earns the highest composite score of "
        f"**{comp_winner['avg_composite']:.2f}** by ranking consistently well across "
        f"every metric and every asset.  "
    )
    p(
        f"Its averages: Total Return {comp_winner['avg_total_return']*100:+.1f}%, "
        f"CAGR {comp_winner['avg_cagr']*100:+.2f}%, "
        f"Volatility {comp_winner['avg_volatility']*100:.1f}%, "
        f"Sharpe {comp_winner['avg_sharpe']:+.3f}, "
        f"Max Drawdown {comp_winner['avg_max_drawdown']*100:.1f}%."
    )
    p()
    p(
        f"The weakest overall performer is **`{comp_loser['strategy']}`** "
        f"(composite score {comp_loser['avg_composite']:.2f})."
    )
    p()

    h3("2. Total Return & CAGR — who grows money fastest?")
    ret_winner = agg.sort_values("avg_total_return", ascending=False).iloc[0]
    cagr_winner = agg.sort_values("avg_cagr", ascending=False).iloc[0]
    p(
        f"- **Highest average total return:** `{ret_winner['strategy']}` at "
        f"**{ret_winner['avg_total_return']*100:+.1f}%**"
    )
    p(
        f"- **Highest average CAGR:** `{cagr_winner['strategy']}` at "
        f"**{cagr_winner['avg_cagr']*100:+.2f}% per year**"
    )
    p()
    bnh_ret  = bnh.get("avg_total_return", float("nan"))
    bnh_cagr = bnh.get("avg_cagr", float("nan"))
    beat_ret  = agg[(agg["strategy"] != "buy_and_hold") & (agg["avg_total_return"] > bnh_ret)]
    beat_cagr = agg[(agg["strategy"] != "buy_and_hold") & (agg["avg_cagr"] > bnh_cagr)]
    p(
        f"Buy-and-hold averages **{bnh_ret*100:+.1f}% total return** and "
        f"**{bnh_cagr*100:+.2f}% CAGR**.  "
        f"{len(beat_ret)} active strategies beat it on total return; "
        f"{len(beat_cagr)} beat it on CAGR.  "
        f"The primary drag on active returns is time spent in cash — strategies miss "
        f"portions of the market's upward drift."
    )
    p()

    h3("3. Volatility — who provides the smoothest ride?")
    vol_winner = agg.sort_values("avg_volatility", ascending=True).iloc[0]
    bnh_vol    = bnh.get("avg_volatility", float("nan"))
    beat_vol   = agg[(agg["strategy"] != "buy_and_hold") & (agg["avg_volatility"] < bnh_vol)]
    p(
        f"- **Lowest average volatility:** `{vol_winner['strategy']}` at "
        f"**{vol_winner['avg_volatility']*100:.1f}%** annualised"
    )
    p(
        f"- Buy-and-hold volatility: **{bnh_vol*100:.1f}%**  "
        f"→ {len(beat_vol)} active strategies are calmer than buy-and-hold."
    )
    p()
    p(
        "Lower volatility active strategies achieve this by moving to cash — "
        "they avoid market crashes but they also miss rallies. "
        "A smoother equity curve is psychologically easier to hold through."
    )
    p()

    h3("4. Sharpe Ratio — best risk-adjusted return?")
    sharpe_winner = agg.sort_values("avg_sharpe", ascending=False).iloc[0]
    bnh_sharpe    = bnh.get("avg_sharpe", float("nan"))
    beat_sharpe   = agg[(agg["strategy"] != "buy_and_hold") & (agg["avg_sharpe"] > bnh_sharpe)]
    p(
        f"- **Best average Sharpe:** `{sharpe_winner['strategy']}` at **{sharpe_winner['avg_sharpe']:+.3f}**"
    )
    p(
        f"- Buy-and-hold Sharpe: **{bnh_sharpe:+.3f}** → "
        f"{len(beat_sharpe)} active strategies beat it on risk-adjusted return."
    )
    p()
    if beat_sharpe.empty:
        p(
            "No active strategy beats buy-and-hold's Sharpe on average across all assets. "
            "This is a classic result: passive investing's low turnover and full market "
            "exposure is hard to outperform on a risk-adjusted basis."
        )
    else:
        for _, row in beat_sharpe.iterrows():
            p(f"- `{row['strategy']}`: Sharpe {row['avg_sharpe']:+.3f} "
              f"(Δ {row['avg_sharpe'] - bnh_sharpe:+.3f} vs B&H)")
    p()

    h3("5. Max Drawdown — who protects capital in crashes?")
    dd_winner  = agg.sort_values("avg_max_drawdown", ascending=False).iloc[0]  # least negative
    bnh_dd     = bnh.get("avg_max_drawdown", float("nan"))
    beat_dd    = agg[(agg["strategy"] != "buy_and_hold") & (agg["avg_max_drawdown"] > bnh_dd)]
    p(
        f"- **Best (least severe) average drawdown:** `{dd_winner['strategy']}` at "
        f"**{dd_winner['avg_max_drawdown']*100:.1f}%**"
    )
    p(
        f"- Buy-and-hold average drawdown: **{bnh_dd*100:.1f}%** → "
        f"{len(beat_dd)} active strategies have smaller drawdowns."
    )
    p()
    p(
        "Drawdown is where active strategies often add real value: moving to cash during "
        "crashes dramatically limits the peak-to-trough loss a real investor would have to "
        "endure. Even if CAGR is lower, a smaller drawdown means less panic-selling risk and "
        "a shorter recovery time."
    )
    p()
    p("| Asset | B&H MaxDD% | Best Active DD% | Strategy | Improvement |")
    p("|-------|-----------|----------------|----------|-------------|")
    for sym in SYMBOLS:
        sym_label = ASSET_LABELS.get(sym, sym)
        bnh_dd_a  = df[(df["symbol"] == sym) & (df["strategy"] == "buy_and_hold")]["max_drawdown"].values
        if not len(bnh_dd_a):
            continue
        act_sub   = df[(df["symbol"] == sym) & (df["strategy"] != "buy_and_hold")]
        best_dd_i = act_sub["max_drawdown"].idxmax()
        best_dd_row = act_sub.loc[best_dd_i]
        improvement = best_dd_row["max_drawdown"] - bnh_dd_a[0]
        p(
            f"| {sym_label} | {bnh_dd_a[0]*100:.1f}% "
            f"| {best_dd_row['max_drawdown']*100:.1f}% "
            f"| `{best_dd_row['strategy']}` "
            f"| {_delta_str(improvement, 100.0, 'pp')} |"
        )
    p()

    h3("6. Trend-following vs mean-reversion")
    def _group_avg(strats: list[str], col: str) -> float:
        return agg[agg["strategy"].isin(strats)][col].mean()

    tf_ret   = _group_avg(trend_strats,  "avg_total_return")
    mr_ret   = _group_avg(revert_strats, "avg_total_return")
    tf_vol   = _group_avg(trend_strats,  "avg_volatility")
    mr_vol   = _group_avg(revert_strats, "avg_volatility")
    tf_sh    = _group_avg(trend_strats,  "avg_sharpe")
    mr_sh    = _group_avg(revert_strats, "avg_sharpe")
    tf_dd    = _group_avg(trend_strats,  "avg_max_drawdown")
    mr_dd    = _group_avg(revert_strats, "avg_max_drawdown")
    tf_comp  = _group_avg(trend_strats,  "avg_composite")
    mr_comp  = _group_avg(revert_strats, "avg_composite")

    p("| Metric | Trend-Following | Mean-Reversion | Winner |")
    p("|--------|----------------|---------------|--------|")
    p(f"| Avg Total Return% | {tf_ret*100:+.1f}% | {mr_ret*100:+.1f}% | {'Trend' if tf_ret>mr_ret else 'Mean-Rev'} |")
    p(f"| Avg Volatility%   | {tf_vol*100:.1f}% | {mr_vol*100:.1f}% | {'Mean-Rev' if tf_vol<mr_vol else 'Trend'} ← lower better |")
    p(f"| Avg Sharpe        | {tf_sh:+.3f} | {mr_sh:+.3f} | {'Trend' if tf_sh>mr_sh else 'Mean-Rev'} |")
    p(f"| Avg Max Drawdown% | {tf_dd*100:.1f}% | {mr_dd*100:.1f}% | {'Trend' if tf_dd>mr_dd else 'Mean-Rev'} ← less negative better |")
    p(f"| Composite Score   | {tf_comp:.2f} | {mr_comp:.2f} | {'**Trend**' if tf_comp>mr_comp else '**Mean-Rev**'} |")
    p()
    p(
        "The 2006–2026 period favoured trend-following because it contained prolonged "
        "directional moves: the 2008 crash, the decade-long equity bull run, COVID-19, and "
        "multiple Bitcoin cycles. Mean-reversion strategies consistently buy dips that keep "
        "falling, hurting both return and drawdown."
    )
    p()

    h3("7. Methodology notes")
    p(textwrap.dedent("""
    - **Next-bar execution**: signals from close at *t* applied to *t+1* returns — no look-ahead.
    - **Commission**: 5 bps per trade side penalises high-turnover strategies.
    - **Long-only, no leverage**: positions in [0, 1]; no short selling.
    - **No slippage model**: bid-ask spread and market impact not modelled.
    - **Composite score**: each strategy is ranked 1–N on each metric per asset (higher=better
      after inversion for volatility), then ranks are averaged across metrics and assets.
    - **Default parameters**: all strategies use their defaults — results may differ with tuning.
    """).strip())
    p()

    h2("Output Files")
    p("| File | Description |")
    p("|------|-------------|")
    p(f"| `results/backtest_20y_metrics.csv` | {len(df)} rows with all metrics, B&H deltas, composite score |")
    p(f"| `results/backtest_20y_report.md` | This report |")
    for cp in chart_paths:
        p(f"| `results/{cp}` | Chart |")
    p()

    return "\n".join(lines)


def main() -> None:
    df, results = run_all()

    print(f"\n[4/4] Generating charts & saving results …")
    chart_paths = save_charts(df, results)
    print()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    save_csv(df)
    report = build_report(df, chart_paths)
    with open(REPORT_MD, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"  ✓ Report → {REPORT_MD}")

    # terminal summary
    print()
    print(_hr("="))
    print("  COMPOSITE RANKING  (avg rank across all 5 metrics & all assets)")
    print(_hr("="))
    comp = df.groupby("strategy")["composite_score"].mean().sort_values(ascending=False)
    bnh_c = comp.get("buy_and_hold", float("nan"))
    for i, (name, val) in enumerate(comp.items(), 1):
        delta  = val - bnh_c
        marker = " ← baseline" if name == "buy_and_hold" else f"  Δ{delta:+.2f} vs B&H"
        bar    = "█" * max(0, int(val))
        print(f"  {i:2d}. {name:<30} {val:.2f}{marker}")
    print()
    print(f"  All outputs → {RESULTS_DIR}/")
    print(_hr("="))


if __name__ == "__main__":
    main()
