# Upstream review log

Destination: https://github.com/sparmar3786-pixel/AI-TRADING
Review date: 2026-10-10

## Metadata/root access checks

The GitHub repository API confirmed that these public repositories exist and exposed their default branches. This is a repository access check, **not a complete file-by-file source audit**.

| Source | Default branch confirmed | Intended use / decision | Upstream code copied? |
|---|---|---|---|
| `TauricResearch/TradingAgents` | `main` | Multi-agent research design reference; dependencies and license notices need review before integration | No |
| `AI4Finance-Foundation/FinGPT` | `master` | Finance NLP/LLM reference; model weights and runtime are not suitable to blindly bundle into this small repo | No |
| `AI4Finance-Foundation/FinRobot` | `master` | Agent framework reference; large dependency surface | No |
| `HKUDS/AI-Trader` | `main` | Agent evaluation/research reference; inspect setup and data assumptions first | No |
| `schen9999/financial-agent` | `main` | Financial research agent reference; API/security and dependencies need review | No |
| `rahul-jajala/ai-financial-research-agent` | `main` | Research-agent example; assess quality and license before reuse | No |
| `Open-Finance-Lab/AgenticTrading` | `main` | Agentic research reference; dependencies and live-execution paths need review | No |
| `microsoft/qlib` | `main` | Quant research framework; use as a separately installed framework if needed | No |
| `polakowo/vectorbt` | `master` | Vectorized backtesting reference; package is much larger than this project | No |
| `mementum/backtrader` | `master` | Backtesting framework reference; not copied into a home-grown engine | No |
| `kernc/backtesting.py` | `master` | Backtesting framework reference; review current license and dependency model before vendoring | No |
| `QuantConnect/Lean` | `master` | Large .NET trading engine; not a direct Python/Flutter drop-in | No |
| `freqtrade/freqtrade` | `develop` | Crypto bot; unrelated exchange assumptions and large dependency surface | No |
| `hummingbot/hummingbot` | `master` | Market-making framework; crypto connector assumptions, not copied | No |
| `angel-one/smartapi-python` | `main` | Official broker client reference; do not vendor implementation until license/terms are confirmed | No |
| `marketcalls/openalgo` | `main` | Broker gateway/platform reference; large independent app, not merged wholesale | No |
| `AI4Finance-Foundation/FinRL` | `master` | RL research reference; needs environment, reproducibility and risk review | No |
| `dcajasn/Riskfolio-Lib` | `master` | Portfolio risk library reference; prefer dependency/package integration after review | No |
| `RuchiTanmay/nselib` | `main` | NSE data client reference; review data terms and current endpoints before wiring | No |
| `tradingview/lightweight-charts` | `master` | Frontend chart library reference; not relevant to this Python-only strategy module | No |

The repository list also includes discovery catalogs, crypto bots, UI prototypes, dashboards, Flutter chat projects and repositories whose exact URL/name should be confirmed. They are listed in `UPSTREAM_REPOSITORIES.md`; not all have undergone detailed license or source review.

## Code added to AI-TRADING in this pass

These are **original implementations** designed for this repo, not copied source files from the projects above:

- `strategies/advanced.py`: Bollinger bands/re-entry, MACD, Donchian channels/breakout and cumulative VWAP.
- `backtesting/engine.py`: close-to-close backtest with one-bar signal delay, fee/slippage estimates and drawdown metrics.
- `risk/controls.py`: fail-closed proposed-order validation for risk budget, notional, daily loss, position count, stale data and kill switch.
- `tests/test_advanced_strategies.py`: unit tests for the added modules.
- `.github/workflows/python-tests.yml`: CI unit-test workflow.
- `INTEGRATION_GUIDE.md`: usage, assumptions and safety boundaries.

## Limits of this audit

- We did not inspect every file in every upstream repository; several are very large.
- Root listing or repo metadata does not prove license permission to redistribute source.
- No complete upstream source tree has been copied into this destination.
- No Angel One live order path, broker login, market-data connection or Railway deployment was changed by these additions.
- The code needs CI/test confirmation before it should be considered verified; backtest results still need realistic costs and out-of-sample/paper validation.

Never commit API keys, broker passwords, MPINs, TOTP seeds, JWTs, feed tokens or account data.