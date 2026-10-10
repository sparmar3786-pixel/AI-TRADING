# Upstream Import Progress

Last verified: 2026-10-11 (continued imports to main branch)

This file distinguishes source files actually committed from projects that are only inventoried. Vendored code is not automatically integrated into the main application.

## Current verified vendor file counts
- `vendor/TradingAgents/`: 210 files
- `vendor/backtesting.py/`: 46 files
- `vendor/FinGPT/`: 56 files
- `vendor/qlib/`: 19 files
- `vendor/financial-agent/`: 15 files

These are destination file counts, not proof that every upstream file was imported.

## Imports

### TauricResearch/TradingAgents
- Upstream license: Apache-2.0.
- Upstream branch: main.
- Source package, CLI/runtime files, project metadata and test files were imported into `vendor/TradingAgents/`.
- A previous tree comparison found the 208 files under the upstream tree covered; destination currently has 210 files. This import has not been installed or tested as part of the host application.

### kernc/backtesting.py
- Upstream license: AGPL-3.0.
- Upstream branch: master.
- 46 files imported into `vendor/backtesting.py/`.
- Includes the main backtesting engine, library helpers, tests, sample CSVs, Python examples, setup metadata, and license.
- Some upstream docs/notebooks/assets are not copied. AGPL-3.0 creates significant distribution/compliance obligations; review before distributing or integrating it into the main application.

### AI4Finance-Foundation/FinGPT
- Upstream license: MIT.
- 56 destination files imported into `vendor/FinGPT/`, covering selected benchmark and Forex-intelligence modules/configuration.
- This is a partial import, not the entire FinGPT repository. Notebooks, data/model artifacts and other source files remain.
- Some files could not be imported through the available GitHub tool; credential-bearing examples and secrets must not be copied.

### microsoft/qlib
- Upstream license: MIT.
- 19 destination files imported into `vendor/qlib/`, including selected backtest, config, dataset, evaluation and model modules.
- This is a partial import; Qlib's full package tree, dependencies and data are not imported or wired into the application.

### schen9999/financial-agent
- 15 destination files imported into `vendor/financial-agent/`, including the license, README, agent core/graph/grounding modules, tools, tracing and API entry point.
- This is a partial import; the complete upstream repository and dependency setup have not been imported or tested.

### Additional requested repositories — files actually imported in this pass

#### asavinov/intelligent-trading-bot
- Upstream branch: master; license: MIT.
- Text/source files were imported under `vendor/intelligent-trading-bot/`: ML classifiers, feature and label generation, signals, backtesting helpers, data collectors, notifier/trader adapters, scripts, service files, tests, configs, README and LICENSE.
- Non-text image assets were not copied. This is a source import, not a host-app integration or test result.

#### Sebacaraballo/Trading-Bot
- Upstream branch: main; license: MIT.
- Files imported under `vendor/Sebacaraballo-Trading-Bot/`: LLM analysis/prompt pipeline, backtest engine/store, API, data fetcher/market client/SEC client, main entry point, dependency manifest, dashboard UI components and snapshot JSON data.
- This import is partial. Dashboard assets and remaining upstream files still need comparison. Local credential-bearing settings and secret files were intentionally excluded.

#### qrak/LLM_trader
- Upstream branch: master; license: MIT.
- Files imported under `vendor/LLM_trader/`: license/readme/notices, dependency files, example configuration, analyzer/data fetcher, prompt and market formatters, risk/reward and trend validation, technical/market metrics, sentiment analysis, pattern scoring, selected indicator modules and selected tests.
- Partial import only; this large repository has many remaining modules and tests. No AI provider keys or real credentials were added.

#### wangzhe3224/awesome-systematic-trading
- Upstream branch: master; license: MIT.
- Text/code files imported under `vendor/awesome-systematic-trading/`, including the license, reading lists, and sample Go/Python/Rust implementations. Verify any downstream data/library terms before use.

#### georgezouq/awesome-ai-in-finance
- Upstream branch: main; license: CC0-1.0.
- Reading-list/docs files imported under `vendor/awesome-ai-in-finance/`. This is primarily an index of resources, not a trading engine.

#### nkaz001/hftbacktest
- Upstream branch: master; license: MIT.
- License, README, selected exchange examples, core package initializer, data validation, order/recorder and performance-metrics files imported under `vendor/hftbacktest/`.
- Partial import. This high-frequency backtesting framework requires additional package/build components and market-by-order data; it is not yet runnable in this project.

#### ranaroussi/qtpylib
- Upstream branch: main; license: Apache-2.0; upstream repository is archived.
- License, README, indicators, algo module and strategy example imported under `vendor/qtpylib/`.
- Partial import only; archived code/dependencies and broker assumptions need review.


#### FalconTrading06/llm-tradebot
- Upstream branch: main; license: MIT.
- Selected entry points, backtesting/strategy-comparison, research workflow, and signal-analysis files imported under `vendor/llm-tradebot/`.
- Partial import only; remaining repository files and dependencies are not all copied or tested.

#### Open-Finance-Lab/FinLLM-Leaderboard
- Upstream branch: main; license: MIT.
- Requested `docs/source/demos_of_finagents/trading_agent.rst` and LICENSE imported under `vendor/FinLLM-Leaderboard/`.
- This is the requested demo document, not the entire leaderboard repository.

## Still incomplete
- Other repositories in `UPSTREAM_REPOSITORIES.md` still need individual access, default-branch and license checks and source imports.
- FinRobot, other listed trading/backtesting/broker/risk/UI/deployment projects have not been fully imported.
- Angel One API, Railway backend, NSE MCP, live market data, and the app's frontend are not confirmed integrated by these vendor imports.
- Python tests and integration tests have not been run as part of this import work.


### Remaining items from the user's latest list (not yet fully imported)
- `qrak/LLM_trader`: MIT partial import is underway; many upstream source modules, website files, and tests remain.
- `FalconTrading06/llm-tradebot`: MIT partial import; many research/scripts and support files remain.
- `nkaz001/hftbacktest`: MIT partial import; full package/build tree and examples remain.
- `ranaroussi/qtpylib`: Apache-2.0 partial import; repository is archived and remaining dependencies/broker assumptions need review.
- `paperswithbacktest/awesome-systematic-trading`: license metadata was not confirmed in the audit; do not bulk-copy its strategy files until their reuse terms are confirmed.
- `fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis`, `ItsKillionaire/TradeSignalFlux`, `studiogangster/next-gen-algo-trading-bot`, `DevGohil411/Trading-bot`, and `Gifted87/TradingBot`: license permission was not confirmed in the audit. Source redistribution is on hold rather than silently copying code with unclear terms. The agentic repo tree also contains a checked-in `venv/`; do not import vendored third-party runtime packages wholesale.
- `TradingGoose/TradingGoose.github.io`: AGPL-3.0, but it is a website project rather than a clearly isolated strategy engine; evaluate its relevance and AGPL obligations before importing more than notices/docs.
- GitHub topic URLs such as `topics/quantitative-finance`, `topics/trade-analysis`, and `topics/tradingbot2026` are discovery pages, not single repositories or source trees to copy.

### Safety and execution boundary
- The new vendor folders are source archives only. No APK bundle, frontend navigation, backend API route, Railway deployment, Angel One session, NSE MCP, or live execution was changed/verified by these commits.
- No tests were executed during these source-copy commits. Run the host project's CI/tests and validate each vendor project in an isolated environment before integration.

## Important
Upstream source is retained in separate vendor folders to avoid overwriting the project's own code. Dependencies, environment variables, license obligations, security, API routes, data providers and execution behavior must be reviewed before enabling copied code. No claim is made that the application is production-ready or connected to live brokerage APIs.
