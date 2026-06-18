# Trading lab

Python backtesting for multi-symbol strategy research.

## Setup

```bash
cd diplomna
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run an analysis

```bash
trading-lab run --strategy sma_crossover --symbols SPY GLD BTC-USD --start 2018-01-01
```

Or:

```bash
python -m trading_lab run --strategy buy_and_hold --symbols ^GSPC --start 2015-01-01 --end 2024-12-31
```

From Python (e.g. a notebook):

```python
from trading_lab import fetch_and_cache, run_analysis, create_strategy

frames = fetch_and_cache(["^GSPC", "GLD", "BTC-USD"], start="2018-01-01")
strategy = create_strategy("sma_crossover", fast=20, slow=50)
results = run_analysis(frames, strategy)
print(results["GLD"].metrics)
```

## Project layout

- `trading_lab/config` — default universes and date ranges
- `trading_lab/data` — historical price loading (Yahoo Finance)
- `trading_lab/strategies` — one module per strategy; register in `registry.py`
- `trading_lab/backtest` — engine and result types
- `trading_lab/metrics` — performance statistics
