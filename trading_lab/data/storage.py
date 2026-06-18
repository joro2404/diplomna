"""CSV persistence for raw and cleaned market data.

Files live under market_data/raw/ and market_data/clean/.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_DATA_ROOT = Path(__file__).parent.parent.parent / "market_data"
_RAW_DIR = _DATA_ROOT / "raw"
_CLEAN_DIR = _DATA_ROOT / "clean"


def _safe_filename(symbol: str) -> str:
    """Map a ticker to a valid filename, e.g. ^GSPC -> _GSPC.csv."""
    return symbol.replace("^", "_").replace("/", "-") + ".csv"


def raw_path(symbol: str) -> Path:
    return _RAW_DIR / _safe_filename(symbol)


def clean_path(symbol: str) -> Path:
    return _CLEAN_DIR / _safe_filename(symbol)


def save_raw(symbol: str, df: pd.DataFrame) -> Path:
    """Persist the raw OHLCV frame as downloaded; return the file path."""
    _RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = raw_path(symbol)
    df.to_csv(path)
    return path


def save_clean(symbol: str, df: pd.DataFrame) -> Path:
    """Persist the cleaned OHLCV frame; return the file path."""
    _CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    path = clean_path(symbol)
    df.to_csv(path)
    return path


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.sort_index()
    return df


def load_raw(symbol: str) -> pd.DataFrame | None:
    """Load the raw CSV for symbol, or None if it does not exist."""
    path = raw_path(symbol)
    if not path.exists():
        return None
    return _read_csv(path)


def load_clean(symbol: str) -> pd.DataFrame | None:
    """Load the cleaned CSV for symbol, or None if it does not exist."""
    path = clean_path(symbol)
    if not path.exists():
        return None
    return _read_csv(path)


def cache_covers(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> bool:
    """True when the clean cache fully covers [start, end)."""
    path = clean_path(symbol)
    if not path.exists():
        return False
    df = _read_csv(path)
    if df.empty:
        return False
    # allow a few days of slack at both ends for weekends/holidays
    slack = pd.Timedelta(days=5)
    return df.index.min() <= start + slack and df.index.max() >= end - slack
