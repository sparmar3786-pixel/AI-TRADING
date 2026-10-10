# AI-TRADING — Strategy Research Workspace

This repository is a research workspace for systematic strategies and an eventual server-side broker/data integration. It contains original strategy/backtest/risk helpers and partial upstream imports. It is not a live trading service and does not guarantee returns.

## Start here

- [Integration guide](INTEGRATION_GUIDE.md) — modules, example, test command and safety boundaries.
- [Upstream repository inventory](UPSTREAM_REPOSITORIES.md) — trading-related GitHub sources collected for review.
- [Upstream audit](UPSTREAM_AUDIT.md) — what has been checked and imported.
- [Copy status](COPY_STATUS.md) — exact files and remaining work.

## Original research components

- `strategies/technical.py`: SMA, EMA, RSI, ATR, EMA crossover and RSI reversion.
- `strategies/advanced.py`: Bollinger bands/re-entry, MACD, Donchian breakout/channels and VWAP.
- `strategy_engine.py`: explainable confluence diagnostics.
- `backtesting/engine.py`: a simple delayed-signal close-to-close backtest.
- `risk/position_sizing.py` and `risk/controls.py`: sizing, ATR levels and fail-closed proposed-order checks.
- `vendor/`: partial imports of TradingAgents, FinGPT, FinRobot and Qlib with per-project import notes/licenses.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Security and integration boundaries

The Android app should call a backend over HTTPS. Angel One credentials, MPIN, TOTP seeds, JWT/feed tokens and AI keys must remain server-side and must never be embedded in an APK or committed to GitHub. No code in the strategy modules authenticates Angel One or submits live orders.

Not every upstream repository is copied; many are references pending detailed license, dependency and security review. Validate strategy results with realistic costs, spread, slippage, out-of-sample data and paper trading before considering live use.
