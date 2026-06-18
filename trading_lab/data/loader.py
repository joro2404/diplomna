"""Historical price loading with a local CSV cache.

If a clean CSV already covers the requested range we read it from disk,
otherwise we download the full history from Yahoo Finance, save the raw and
cleaned CSVs, and return the cleaned frame.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import yfinance as yf

from trading_lab.data.cleaner import clean_ohlcv, cleaning_report
from trading_lab.data.storage import (
    cache_covers,
    load_clean,
    save_clean,
    save_raw,
)

logger = logging.getLogger(__name__)


def _download(symbol: str, start: str | date, end: str | date | None) -> pd.DataFrame:
    """Fetch the full OHLCV history from Yahoo Finance for one symbol."""
    ticker = yf.Ticker(symbol)
    hist = ticker.history(start=start, end=end, auto_adjust=True)
    if hist.empty:
        raise ValueError(
            f"No data returned for {symbol!r} between {start!r} and {end!r}. "
            "Check the ticker and date range."
        )
    hist.index = pd.to_datetime(hist.index).tz_localize(None)
    hist.index.name = "Date"
    return hist


def _filter_range(
    df: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    return df[(df.index >= start) & (df.index < end)]


def fetch_and_cache(
    symbols: list[str],
    start: str | date,
    end: str | date | None = None,
    *,
    force_refresh: bool = False,
    verbose: bool = False,
) -> dict[str, pd.DataFrame]:
    """Download (or load from cache) cleaned OHLCV data for each symbol.

    Returns a mapping of symbol -> cleaned OHLCV DataFrame filtered to
    [start, end). end=None means today; force_refresh ignores the cache.
    """
    if not symbols:
        raise ValueError("symbols must be non-empty")

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) if end else pd.Timestamp.today().normalize() + pd.Timedelta(days=1)

    result: dict[str, pd.DataFrame] = {}

    for sym in symbols:
        use_cached = (
            not force_refresh
            and cache_covers(sym, start_ts, end_ts)
        )

        if use_cached:
            logger.info("[%s] Loading from local clean cache.", sym)
            cached = load_clean(sym)
            if cached is not None and not cached.empty:
                result[sym] = _filter_range(cached, start_ts, end_ts)
                continue

        logger.info("[%s] Downloading from Yahoo Finance …", sym)
        raw = _download(sym, start, end)
        raw_path = save_raw(sym, raw)
        logger.info("[%s] Raw data saved → %s (%d rows)", sym, raw_path, len(raw))

        cleaned = clean_ohlcv(raw, symbol=sym)
        clean_path_saved = save_clean(sym, cleaned)
        logger.info(
            "[%s] Clean data saved → %s (%d rows)", sym, clean_path_saved, len(cleaned)
        )

        if verbose:
            report = cleaning_report(raw, cleaned, symbol=sym)
            _print_cleaning_report(report)

        result[sym] = _filter_range(cleaned, start_ts, end_ts)

    return result


def load_adj_close(
    symbols: list[str],
    start: str | date,
    end: str | date | None = None,
    *,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Return a DataFrame of close prices, one column per symbol.

    Index is a timezone-naive ascending DatetimeIndex; rows where every
    symbol is NaN are dropped. use_cache=False forces a fresh download.
    """
    if not symbols:
        raise ValueError("symbols must be non-empty")

    frames = fetch_and_cache(symbols, start, end, force_refresh=not use_cache)

    columns: list[pd.Series] = []
    for sym in symbols:
        df = frames.get(sym)
        if df is None or df.empty or "Close" not in df.columns:
            raise ValueError(
                f"No usable Close data for {sym!r} in range {start!r} … {end!r}."
            )
        columns.append(df["Close"].rename(sym))

    adj = pd.concat(columns, axis=1)
    adj.index = pd.to_datetime(adj.index).tz_localize(None)
    adj = adj.sort_index()
    adj = adj.dropna(how="all")
    return adj


def _print_cleaning_report(report: dict[str, object]) -> None:
    sym = report["symbol"]
    print(f"\n  Cleaning report — {sym}")
    print(f"    Rows  : {report['raw_rows']} raw → {report['clean_rows']} clean "
          f"(removed {report['rows_removed']})")
    raw_start, raw_end = report["date_range_raw"]
    cln_start, cln_end = report["date_range_clean"]
    print(f"    Range : {raw_start} … {raw_end}  →  {cln_start} … {cln_end}")
    nan_raw: dict = report["nan_counts_raw"]  # type: ignore[assignment]
    total_nan = sum(nan_raw.values())
    if total_nan:
        print(f"    NaNs  : {nan_raw}")
