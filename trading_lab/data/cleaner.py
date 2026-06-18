"""OHLCV data-cleaning pipeline.

Keeps all original columns; Close is guaranteed non-NaN in every surviving row.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# fill gaps up to this many days (long weekends, short halts)
_MAX_FFILL_DAYS: int = 5

# single-day returns above this are treated as bad ticks for equities/ETFs,
# but skipped when too many days breach it (crypto)
_EXTREME_RETURN_THRESHOLD: float = 0.50

_MIN_PRICE: float = 1e-6


def clean_ohlcv(df: pd.DataFrame, symbol: str = "") -> pd.DataFrame:
    """Clean a raw OHLCV frame returned by yfinance.

    Strips the timezone, drops duplicate/future dates and bad-price rows,
    forward-fills short gaps, fixes Volume, and removes obvious return
    outliers for non-crypto instruments. The input frame is not modified.
    """
    tag = f"[{symbol}] " if symbol else ""
    original_len = len(df)
    df = df.copy()

    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "Date"
    df = df.sort_index()

    # duplicate dates: keep the last (most recently updated) bar
    n_dupes = df.index.duplicated(keep="last").sum()
    if n_dupes:
        logger.debug("%sDropping %d duplicate date(s)", tag, n_dupes)
    df = df[~df.index.duplicated(keep="last")]

    today = pd.Timestamp.today().normalize()
    n_future = (df.index > today).sum()
    if n_future:
        logger.debug("%sDropping %d future-dated row(s)", tag, n_future)
    df = df[df.index <= today]

    if "Close" in df.columns:
        bad_price = df["Close"] <= _MIN_PRICE
        if bad_price.any():
            logger.debug("%sDropping %d row(s) with Close ≤ %g", tag, bad_price.sum(), _MIN_PRICE)
        df = df[~bad_price | df["Close"].isna()]

    price_cols = [c for c in ["Open", "High", "Low", "Close"] if c in df.columns]
    if price_cols:
        n_nan_before = df[price_cols].isna().sum().sum()
        df[price_cols] = df[price_cols].ffill(limit=_MAX_FFILL_DAYS)
        n_filled = n_nan_before - df[price_cols].isna().sum().sum()
        if n_filled:
            logger.debug("%sForward-filled %d NaN price cell(s)", tag, n_filled)

    if "Close" in df.columns:
        n_no_close = df["Close"].isna().sum()
        if n_no_close:
            logger.debug("%sDropping %d row(s) with no Close price", tag, n_no_close)
        df = df.dropna(subset=["Close"])

    if "Volume" in df.columns:
        df["Volume"] = df["Volume"].clip(lower=0).fillna(0).astype("int64")

    if "Close" in df.columns and len(df) > 1:
        daily_ret = df["Close"].pct_change().abs()
        extreme = daily_ret > _EXTREME_RETURN_THRESHOLD
        n_extreme = int(extreme.sum())
        if n_extreme:
            frac = n_extreme / len(df)
            if frac <= 0.01:
                logger.warning(
                    "%sRemoving %d row(s) with |daily return| > %.0f%% "
                    "(likely data errors)",
                    tag,
                    n_extreme,
                    _EXTREME_RETURN_THRESHOLD * 100,
                )
                df = df[~extreme]
            else:
                logger.debug(
                    "%sRetaining %d row(s) with |daily return| > %.0f%% "
                    "(crypto-like instrument — outlier removal skipped)",
                    tag,
                    n_extreme,
                    _EXTREME_RETURN_THRESHOLD * 100,
                )

    df = df.sort_index()
    logger.info(
        "%sCleaning complete: %d → %d rows (removed %d)",
        tag,
        original_len,
        len(df),
        original_len - len(df),
    )
    return df


def cleaning_report(raw: pd.DataFrame, clean: pd.DataFrame, symbol: str = "") -> dict[str, object]:
    """Summarise what the cleaner changed, for the CLI or logs."""
    tag = symbol or "symbol"
    report: dict[str, object] = {
        "symbol": tag,
        "raw_rows": len(raw),
        "clean_rows": len(clean),
        "rows_removed": len(raw) - len(clean),
        "date_range_raw": (
            str(raw.index.min().date()) if not raw.empty else "n/a",
            str(raw.index.max().date()) if not raw.empty else "n/a",
        ),
        "date_range_clean": (
            str(clean.index.min().date()) if not clean.empty else "n/a",
            str(clean.index.max().date()) if not clean.empty else "n/a",
        ),
        "nan_counts_raw": raw.isna().sum().to_dict(),
        "nan_counts_clean": clean.isna().sum().to_dict(),
    }
    return report
