# Code integration status — AI-TRADING

Destination: https://github.com/sparmar3786-pixel/AI-TRADING
Last updated: 2026-10-11

## Original project modules

| Path | What it provides | Status |
|---|---|---|
| `strategies/technical.py` | SMA, EMA, RSI, ATR, EMA crossover and RSI reversion | Original implementation |
| `strategies/advanced.py` | Bollinger bands/re-entry, MACD, Donchian channels/breakout and VWAP | Original implementation |
| `strategy_engine.py` | Explainable confluence diagnostics | Original implementation |
| `risk/position_sizing.py` | Equity-risk sizing and ATR stop/target helpers | Original implementation |
| `risk/controls.py` | Fail-closed proposed-order risk gate | Original code; no order execution |
| `backtesting/engine.py` | One-bar-delayed close-to-close backtest, fee/slippage estimates and drawdown metrics | Starter simulator |
| `tests/` | Indicator, sizing, strategy, backtest and risk checks | Test source files present; execution not confirmed in this pass |
| `.github/workflows/python-tests.yml` | Python unit-test CI | Workflow file present |
| `INTEGRATION_GUIDE.md` | How to use modules and understand limitations | Guide present |

## Upstream import status

- `vendor/TradingAgents/` — all 208 tracked files from the upstream recursive Git tree imported and checked, including all 83 package source files, CLI, tests, metadata, docs, templates and image assets. Apache-2.0 license retained. Not runtime-integrated or end-to-end tested.
- `vendor/FinGPT/` — selected ForexIntelligence and Forecaster files imported, including application entry point, market data pipeline, sentiment/symbol configuration, training and Docker files. Partial import; MIT license retained.
- `vendor/FinRobot/` — selected agent/data/analysis modules and upstream README retained; partial import under Apache-2.0.
- `vendor/Qlib/` — selected backtesting, strategy/order generation, cost-control, portfolio evaluation and risk/reporting modules imported. Partial import under MIT.

Each vendor directory should retain applicable license/notice files and import notes. Dependencies, model/API keys, data sources and configuration must be installed and validated separately.

## Remaining upstream work

The repositories in `UPSTREAM_REPOSITORIES.md` are not all copied. Most remain reference-only/pending detailed file-level license, security and compatibility review. Large frameworks, crypto-only engines, UI projects and broker gateways should not be flattened into one runtime without review. Angel One SmartAPI code remains reference-only until its redistribution permissions and broker terms are confirmed.

## Not done / not claimed

- No live Angel One authentication, market-data connection or live order execution is enabled by these source imports.
- No Railway variables or deployment were changed by this source-import pass.
- No profit, win-rate or production-readiness guarantee is made.
- Tests have not been run as part of this import pass. Paper/out-of-sample validation remains necessary.

Run project tests from the repository root with:

```bash
python -m unittest discover -s tests -v
```

Do not commit API keys, passwords, MPINs, TOTP seeds, JWTs, feed tokens or other account secrets.
