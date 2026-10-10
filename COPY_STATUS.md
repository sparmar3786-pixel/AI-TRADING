# Code integration status — AI-TRADING

Destination: https://github.com/sparmar3786-pixel/AI-TRADING
Last updated: 2026-10-10

## Original project modules

| Path | What it provides | Status |
|---|---|---|
| `strategies/technical.py` | SMA, EMA, RSI, ATR, EMA crossover and RSI reversion | Existing original implementation |
| `strategies/advanced.py` | Bollinger bands/re-entry, MACD, Donchian channels/breakout and VWAP | Added in this change; original code |
| `strategy_engine.py` | Explainable confluence diagnostics | Existing original implementation |
| `risk/position_sizing.py` | Equity-risk sizing and ATR stop/target helpers | Existing original implementation |
| `risk/controls.py` | Fail-closed proposed-order risk gate | Added in this change; no order execution |
| `backtesting/engine.py` | One-bar-delayed close-to-close backtest, fee/slippage estimates and drawdown metrics | Added in this change; starter simulator |
| `tests/test_research_strategies.py` | Existing indicator/sizing tests | Existing |
| `tests/test_advanced_strategies.py` | Tests for advanced strategy/backtest/risk modules | Added in this change |
| `.github/workflows/python-tests.yml` | Python unit-test CI | Added in this change |
| `INTEGRATION_GUIDE.md` | How to use modules and understand limitations | Added in this change |

## Partial upstream imports

- `vendor/TradingAgents/` — selected multi-agent research modules; not complete.
- `vendor/FinGPT/` — selected finance NLP/forecasting modules; not complete.
- `vendor/FinRobot/` — selected agent/data/analysis modules; not complete.
- `vendor/Qlib/` — selected backtest/strategy modules; not complete.

Each vendor directory includes import notes and applicable license/notice files. These packages are not automatically runnable as-is: dependencies, model/API keys, data sources and configuration must be installed and validated separately.

## Remaining upstream work

The repositories in `UPSTREAM_REPOSITORIES.md` are not all copied. Most remain reference-only/pending detailed file-level license, security and compatibility review. Huge frameworks, crypto-only engines, UI projects and broker gateways should not be flattened into one runtime without review. Angel One SmartAPI code remains reference-only until its redistribution permissions and broker terms are confirmed.

## Not done / not claimed

- No live Angel One authentication, market-data connection or live order execution is enabled by these strategy modules.
- No Railway variables or deployment were changed by this strategy pass.
- No profit, win-rate or production-readiness guarantee is made.
- The test workflow must finish successfully for the new branch before merge; paper/out-of-sample validation remains necessary.

Run tests with:

```bash
python -m unittest discover -s tests -v
```

Do not commit API keys, passwords, MPINs, TOTP seeds, JWTs, feed tokens or other account secrets.
