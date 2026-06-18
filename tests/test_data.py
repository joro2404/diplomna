"""Unit tests for the data storage, cleaning, and loading layers.

All tests are offline — no network calls, no real disk writes.
The Yahoo Finance download and the CSV persistence layer are patched
with in-memory fakes so the suite runs fast and deterministically.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from trading_lab.data.cleaner import clean_ohlcv, cleaning_report
from trading_lab.data.storage import (
    _safe_filename,
    clean_path,
    raw_path,
)


def _make_ohlcv(
    n: int = 30,
    start: str = "2023-01-02",
    base_price: float = 100.0,
    *,
    tz: str | None = None,
    add_nan_rows: bool = False,
    add_duplicates: bool = False,
    add_future: bool = False,
    add_zero_close: bool = False,
    add_extreme_return: bool = False,
    negative_volume: bool = False,
) -> pd.DataFrame:
    """Build a synthetic OHLCV DataFrame for testing."""
    dates = pd.date_range(start, periods=n, freq="B")  # business days
    if tz:
        dates = dates.tz_localize(tz)
    rng = np.random.default_rng(42)
    # Geometric (log-normal) walk: always positive, daily returns ~0.5 %
    log_returns = rng.normal(0.0005, 0.005, n)
    close = base_price * np.exp(np.cumsum(log_returns))
    df = pd.DataFrame(
        {
            "Open": close * 0.99,
            "High": close * 1.02,
            "Low": close * 0.97,
            "Close": close,
            "Volume": rng.integers(1_000_000, 5_000_000, n),
            "Dividends": 0.0,
            "Stock Splits": 0.0,
        },
        index=dates,
    )
    df.index.name = "Date"

    if add_nan_rows:
        df.loc[df.index[5], ["Open", "High", "Low", "Close"]] = np.nan
        df.loc[df.index[6], ["Open", "High", "Low", "Close"]] = np.nan

    if add_duplicates:
        dup = df.iloc[[10]].copy()
        dup["Close"] = dup["Close"] * 1.01
        df = pd.concat([df, dup]).sort_index()

    if add_future:
        future_date = pd.Timestamp.today().normalize() + pd.Timedelta(days=10)
        future_row = df.iloc[[-1]].copy()
        future_row.index = pd.DatetimeIndex([future_date])
        df = pd.concat([df, future_row])

    if add_zero_close:
        df.loc[df.index[15], "Close"] = 0.0

    if add_extreme_return:
        df.loc[df.index[20], "Close"] = df.loc[df.index[19], "Close"] * 10.0

    if negative_volume:
        df.loc[df.index[3], "Volume"] = -500

    return df


# storage helpers

class TestSafeFilename(unittest.TestCase):
    def test_caret_replaced(self):
        self.assertEqual(_safe_filename("^GSPC"), "_GSPC.csv")

    def test_slash_replaced(self):
        self.assertEqual(_safe_filename("BRK/B"), "BRK-B.csv")

    def test_plain_ticker(self):
        self.assertEqual(_safe_filename("AAPL"), "AAPL.csv")

    def test_crypto(self):
        self.assertEqual(_safe_filename("BTC-USD"), "BTC-USD.csv")


class TestPathHelpers(unittest.TestCase):
    def test_raw_path_ends_with_csv(self):
        self.assertTrue(str(raw_path("AAPL")).endswith(".csv"))

    def test_clean_path_different_dir(self):
        self.assertNotEqual(str(raw_path("AAPL")), str(clean_path("AAPL")))
        self.assertIn("raw", str(raw_path("AAPL")))
        self.assertIn("clean", str(clean_path("AAPL")))


# cleaner

class TestCleanerIndexHygiene(unittest.TestCase):
    def test_tz_aware_index_stripped(self):
        df = _make_ohlcv(10, tz="UTC")
        result = clean_ohlcv(df)
        self.assertIsNone(result.index.tz)

    def test_index_sorted_ascending(self):
        df = _make_ohlcv(20)
        df = df.iloc[::-1]  # reverse order
        result = clean_ohlcv(df)
        self.assertTrue(result.index.is_monotonic_increasing)

    def test_index_named_date(self):
        df = _make_ohlcv(5)
        result = clean_ohlcv(df)
        self.assertEqual(result.index.name, "Date")


class TestCleanerDuplicates(unittest.TestCase):
    def test_duplicate_dates_removed(self):
        df = _make_ohlcv(20, add_duplicates=True)
        original_dupes = df.index.duplicated().sum()
        self.assertGreater(original_dupes, 0)

        result = clean_ohlcv(df)
        self.assertEqual(result.index.duplicated().sum(), 0)

    def test_last_value_kept_on_duplicate(self):
        """When a date appears twice the later (updated) value is kept."""
        dates = pd.date_range("2023-01-02", periods=3, freq="B")
        df = pd.DataFrame(
            {"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": [10.0, 20.0, 20.0], "Volume": 100},
            index=[dates[0], dates[1], dates[1]],
        )
        result = clean_ohlcv(df)
        self.assertEqual(len(result), 2)
        self.assertEqual(result.loc[dates[1], "Close"], 20.0)


class TestCleanerFutureDates(unittest.TestCase):
    def test_future_rows_dropped(self):
        df = _make_ohlcv(20, add_future=True)
        today = pd.Timestamp.today().normalize()
        self.assertTrue((df.index > today).any())

        result = clean_ohlcv(df)
        self.assertTrue((result.index <= today).all())


class TestCleanerZeroClose(unittest.TestCase):
    def test_zero_close_dropped(self):
        df = _make_ohlcv(20, add_zero_close=True)
        result = clean_ohlcv(df)
        self.assertTrue((result["Close"] > 0).all())


class TestCleanerNaN(unittest.TestCase):
    def test_single_nan_forward_filled(self):
        df = _make_ohlcv(20)
        df.loc[df.index[5], "Close"] = np.nan
        result = clean_ohlcv(df)
        # Row should survive because ffill covers a 1-day gap
        self.assertEqual(result["Close"].isna().sum(), 0)

    def test_long_nan_run_dropped(self):
        """A gap longer than the fill limit must be dropped."""
        df = _make_ohlcv(30)
        # Blank out 10 consecutive rows — well above the 5-day fill limit
        for i in range(5, 15):
            df.loc[df.index[i], "Close"] = np.nan
        result = clean_ohlcv(df)
        self.assertEqual(result["Close"].isna().sum(), 0)
        # Some rows should have been dropped
        self.assertLess(len(result), len(df))

    def test_two_consecutive_nans_forward_filled(self):
        df = _make_ohlcv(20)
        df.loc[df.index[7], "Close"] = np.nan
        df.loc[df.index[8], "Close"] = np.nan
        result = clean_ohlcv(df)
        self.assertEqual(result["Close"].isna().sum(), 0)


class TestCleanerVolume(unittest.TestCase):
    def test_negative_volume_clipped_to_zero(self):
        df = _make_ohlcv(10, negative_volume=True)
        result = clean_ohlcv(df)
        self.assertTrue((result["Volume"] >= 0).all())

    def test_volume_dtype_integer(self):
        df = _make_ohlcv(10)
        result = clean_ohlcv(df)
        self.assertTrue(pd.api.types.is_integer_dtype(result["Volume"]))


class TestCleanerExtremeReturns(unittest.TestCase):
    def test_single_extreme_return_removed(self):
        """One extreme row in a long equity-like series should be removed.

        Uses 200 rows so the spike fraction (1/200 = 0.5 %) is well below
        the 1 % threshold that activates equity-mode removal.
        """
        df = _make_ohlcv(200, add_extreme_return=True)
        spike_date = df.index[20]
        result = clean_ohlcv(df, symbol="TEST")
        self.assertNotIn(spike_date, result.index)

    def test_crypto_like_extremes_kept(self):
        """When > 1 % of days have large moves the cleaner must not touch them."""
        df = _make_ohlcv(50)
        # Inject large moves in > 1 % of rows (more than 0.5 out of 50 rows)
        for i in range(1, 50, 8):
            df.loc[df.index[i], "Close"] = df.loc[df.index[i - 1], "Close"] * 2.0
        result = clean_ohlcv(df, symbol="BTC-USD")
        # All rows except possibly zero-close/future rows should survive
        self.assertGreater(len(result), 40)


class TestCleanerColumnsPreserved(unittest.TestCase):
    def test_all_source_columns_present(self):
        df = _make_ohlcv(10)
        result = clean_ohlcv(df)
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            self.assertIn(col, result.columns)

    def test_original_df_not_mutated(self):
        df = _make_ohlcv(10, add_nan_rows=True)
        original_nan_count = df["Close"].isna().sum()
        clean_ohlcv(df)
        self.assertEqual(df["Close"].isna().sum(), original_nan_count)


# cleaning_report

class TestCleaningReport(unittest.TestCase):
    def test_report_keys_present(self):
        raw = _make_ohlcv(20, add_nan_rows=True)
        cleaned = clean_ohlcv(raw, symbol="AAPL")
        report = cleaning_report(raw, cleaned, symbol="AAPL")
        for key in [
            "symbol", "raw_rows", "clean_rows", "rows_removed",
            "date_range_raw", "date_range_clean",
            "nan_counts_raw", "nan_counts_clean",
        ]:
            self.assertIn(key, report)

    def test_rows_removed_non_negative(self):
        raw = _make_ohlcv(20, add_nan_rows=True)
        cleaned = clean_ohlcv(raw)
        report = cleaning_report(raw, cleaned)
        self.assertGreaterEqual(report["rows_removed"], 0)

    def test_clean_nan_counts_are_zero_for_close(self):
        raw = _make_ohlcv(20, add_nan_rows=True)
        cleaned = clean_ohlcv(raw)
        report = cleaning_report(raw, cleaned)
        self.assertEqual(report["nan_counts_clean"].get("Close", 0), 0)


# storage layer (disk writes patched with a temp dir)

class TestStorageRoundTrip(unittest.TestCase):
    """save_raw / save_clean / load_raw / load_clean round-trip test."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patch = patch(
            "trading_lab.data.storage._DATA_ROOT",
            Path(self._tmpdir.name),
        )
        # Also patch the derived dirs so they resolve inside the tmpdir
        self._patch.start()
        import trading_lab.data.storage as s
        s._RAW_DIR = Path(self._tmpdir.name) / "raw"
        s._CLEAN_DIR = Path(self._tmpdir.name) / "clean"

    def tearDown(self):
        self._patch.stop()
        self._tmpdir.cleanup()
        # Restore module-level dirs
        import trading_lab.data.storage as s
        from pathlib import Path as _P
        root = _P(__file__).parent.parent / "market_data"
        s._DATA_ROOT = root
        s._RAW_DIR = root / "raw"
        s._CLEAN_DIR = root / "clean"

    def test_save_and_load_raw(self):
        from trading_lab.data.storage import load_raw, save_raw
        df = _make_ohlcv(10)
        save_raw("AAPL", df)
        loaded = load_raw("AAPL")
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded), len(df))
        self.assertAlmostEqual(
            float(loaded["Close"].iloc[0]), float(df["Close"].iloc[0]), places=4
        )

    def test_save_and_load_clean(self):
        from trading_lab.data.storage import load_clean, save_clean
        df = _make_ohlcv(10)
        save_clean("MSFT", df)
        loaded = load_clean("MSFT")
        self.assertIsNotNone(loaded)
        pd.testing.assert_index_equal(
            loaded.index.normalize(), df.index.normalize()
        )

    def test_load_missing_returns_none(self):
        from trading_lab.data.storage import load_clean, load_raw
        self.assertIsNone(load_raw("NONEXISTENT"))
        self.assertIsNone(load_clean("NONEXISTENT"))

    def test_cache_covers_after_save(self):
        from trading_lab.data.storage import cache_covers, save_clean
        df = _make_ohlcv(60, start="2023-01-02")
        save_clean("GLD", df)
        start = pd.Timestamp("2023-01-05")
        end = pd.Timestamp("2023-02-01")
        self.assertTrue(cache_covers("GLD", start, end))

    def test_cache_covers_outside_range_returns_false(self):
        from trading_lab.data.storage import cache_covers, save_clean
        df = _make_ohlcv(10, start="2023-06-01")
        save_clean("SLV", df)
        # Request a period entirely before the cached data
        start = pd.Timestamp("2020-01-01")
        end = pd.Timestamp("2020-12-31")
        self.assertFalse(cache_covers("SLV", start, end))


# loader (network + disk patched)

class TestLoader(unittest.TestCase):
    """Tests for fetch_and_cache and load_adj_close with mocked yfinance."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._raw_dir = Path(self._tmpdir.name) / "raw"
        self._clean_dir = Path(self._tmpdir.name) / "clean"

        import trading_lab.data.storage as s
        s._RAW_DIR = self._raw_dir
        s._CLEAN_DIR = self._clean_dir
        s._DATA_ROOT = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()
        import trading_lab.data.storage as s
        from pathlib import Path as _P
        root = _P(__file__).parent.parent / "market_data"
        s._DATA_ROOT = root
        s._RAW_DIR = root / "raw"
        s._CLEAN_DIR = root / "clean"

    def _patch_download(self, df: pd.DataFrame):
        """Return a context manager that stubs _download in loader.py."""
        return patch("trading_lab.data.loader._download", return_value=df)

    def test_fetch_and_cache_saves_csv_files(self):
        from trading_lab.data.loader import fetch_and_cache
        df = _make_ohlcv(30, start="2023-01-02")
        with self._patch_download(df):
            fetch_and_cache(["AAPL"], start="2023-01-02", end="2023-02-15")
        self.assertTrue(self._raw_dir.joinpath("AAPL.csv").exists())
        self.assertTrue(self._clean_dir.joinpath("AAPL.csv").exists())

    def test_fetch_and_cache_returns_close_column(self):
        from trading_lab.data.loader import fetch_and_cache
        df = _make_ohlcv(30, start="2023-01-02")
        with self._patch_download(df):
            frames = fetch_and_cache(["AAPL"], start="2023-01-02", end="2023-02-15")
        self.assertIn("AAPL", frames)
        self.assertIn("Close", frames["AAPL"].columns)

    def test_second_call_uses_cache_not_network(self):
        from trading_lab.data.loader import fetch_and_cache
        df = _make_ohlcv(60, start="2023-01-02")
        mock_dl = MagicMock(return_value=df)
        with patch("trading_lab.data.loader._download", mock_dl):
            fetch_and_cache(["AAPL"], start="2023-01-05", end="2023-02-01")
            fetch_and_cache(["AAPL"], start="2023-01-05", end="2023-02-01")
        # _download should be called exactly once
        self.assertEqual(mock_dl.call_count, 1)

    def test_force_refresh_re_downloads(self):
        from trading_lab.data.loader import fetch_and_cache
        df = _make_ohlcv(60, start="2023-01-02")
        mock_dl = MagicMock(return_value=df)
        with patch("trading_lab.data.loader._download", mock_dl):
            fetch_and_cache(["MSFT"], start="2023-01-05", end="2023-02-01")
            fetch_and_cache(
                ["MSFT"], start="2023-01-05", end="2023-02-01", force_refresh=True
            )
        self.assertEqual(mock_dl.call_count, 2)

    def test_load_adj_close_returns_dataframe(self):
        from trading_lab.data.loader import load_adj_close
        df = _make_ohlcv(30, start="2023-01-02")
        with self._patch_download(df):
            adj = load_adj_close(["AAPL"], start="2023-01-02", end="2023-02-15")
        self.assertIsInstance(adj, pd.DataFrame)
        self.assertIn("AAPL", adj.columns)
        self.assertFalse(adj["AAPL"].isna().any())

    def test_load_adj_close_multiple_symbols(self):
        from trading_lab.data.loader import load_adj_close
        df = _make_ohlcv(30, start="2023-01-02")
        with self._patch_download(df):
            adj = load_adj_close(
                ["AAPL", "MSFT"], start="2023-01-02", end="2023-02-15"
            )
        self.assertIn("AAPL", adj.columns)
        self.assertIn("MSFT", adj.columns)

    def test_load_adj_close_index_is_timezone_naive(self):
        from trading_lab.data.loader import load_adj_close
        df = _make_ohlcv(30, start="2023-01-02")
        with self._patch_download(df):
            adj = load_adj_close(["AAPL"], start="2023-01-02", end="2023-02-15")
        self.assertIsNone(adj.index.tz)

    def test_load_adj_close_index_sorted(self):
        from trading_lab.data.loader import load_adj_close
        df = _make_ohlcv(30, start="2023-01-02")
        with self._patch_download(df):
            adj = load_adj_close(["AAPL"], start="2023-01-02", end="2023-02-15")
        self.assertTrue(adj.index.is_monotonic_increasing)

    def test_empty_symbols_raises(self):
        from trading_lab.data.loader import load_adj_close
        with self.assertRaises(ValueError):
            load_adj_close([], start="2023-01-01")


if __name__ == "__main__":
    unittest.main()
