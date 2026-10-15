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


## Continuation update — 2026-10-11

Additional file-level imports were committed to the **AI-TRADING** repository (not Fresh-Apk):

- `vendor/hftbacktest/` — added 8 additional Python data utilities in commits `0c68ad67a73a5144cd94135a448493fb1754a9f8` and `4850e80f670ad13029f82ca0d592d6c8c0cde22a`. This vendor tree remains partial (30 files currently present versus a much larger upstream project); MIT license applies.
- `vendor/qtpylib/` — added SMS, TA-Lib indicators, indicator tests and workflow modules in commit `d094be7f359fcbe07f31b76d2be3d89120b7627f`. This vendor tree remains partial; upstream is archived and Apache-2.0 licensed.
- `vendor/LLM_trader/` — added app/config and dashboard/router modules in commits `ed5e563decf732696b67d1f573f03fa0c8787ab2`, `39346768b9f9eabe940f24e11339a5e1fc28036c` and `ba3842d185e542c4b49369153c9802ff07d86ae7`. This tree remains partial (75 files currently present versus 316 upstream files); MIT license retained.
- `vendor/intelligent-trading-bot/` currently contains 64 text/source files; upstream has 66 tracked files, with binary/document assets not all imported.
- `vendor/Sebacaraballo-Trading-Bot/` currently contains 66 files; upstream has 73 tracked files. This is not a claim that every upstream file was imported.
- `vendor/awesome-systematic-trading/` and `vendor/awesome-ai-in-finance/` retain their licensed reference/source files.
- `vendor/llm-tradebot/` and `vendor/FinLLM-Leaderboard/` were already present in part; neither is confirmed as a complete upstream import.

### Explicitly pending / licensing safeguards

- `fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis`, `ItsKillionaire/TradeSignalFlux`, `studiogangster/next-gen-algo-trading-bot`, `DevGohil411/Trading-bot`, `Gifted87/TradingBot`, `TradingGoose/TradingGoose.github.io`, and `paperswithbacktest/awesome-systematic-trading`: do not treat these as imported. Repository-level license metadata was absent for several of them, so their code must not be redistributed until a license/permission is verified. The TradingGoose repository is AGPL-3.0 and needs separate compatibility review before app integration.
- GitHub topic pages such as `quantitative-finance`, `trade-analysis` and `tradingbot2026` are discovery pages, not repositories to copy wholesale.
- These vendor imports are **source archives only**. They have not been wired into the APK UI or the active strategy engine, dependencies have not been resolved, and no Python tests, broker API, live-data or Railway deployment checks are claimed by this continuation.


### Further continuation commits

- `vendor/LLM_trader/`: additional MIT-licensed app/config, dashboard, sentiment and statistical-indicator files added in commits `b89b80527765f70c0e0e24fc8e69ed6d85e02b62` and `53eab0c4d1668f74f5101d83193fe8f8dbd7bc72`. The directory now has additional source beyond the earlier 75-file count; still partial and not wired into the app.
- The above imports are kept isolated under `vendor/` to avoid accidentally overriding the active AI-TRADING backend or APK frontend. Do not assume these vendored modules are called by the live app.


## Continuation — five-layer signal research and APK UI

- `quant_engine.py`: original five-layer fail-closed evaluator for freshness, trend/sentiment, order flow, option selection and risk/10-minute stability. Requires normalized upstream data and a server-owned confirmation state; it is not a live Angel One connector.
- `tests/test_quant_engine.py`: covers stale data, multi-timeframe conflicts, spread rejection, missing ATR, invalid order flow, continuous 10-minute confirmation and refresh-gap reset. Latest Python CI run passed on 2026-10-12.
- `flutter_app/lib/trade_engine_page.dart`: now presents five distinct validation layers and separates the read-only broker monitor. If the deployed backend does not return quant-layer fields, the UI shows data required instead of claiming the layer passed.
- Still pending before a production signal APK: wire `quant_engine.py` into the active Railway signal endpoint; verify Angel One WebSocket/session renewal, fresh option-chain bid/ask/OI/volume, NSE/BSE index data, whole-session news sentiment provenance, and on-device behavior. No profitability claim is made.
