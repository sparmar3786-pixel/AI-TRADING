# Upstream import continuation — 2026-10-12

Destination: https://github.com/sparmar3786-pixel/AI-TRADING
Working branch: `continue-upstream-import-20261012`

## Non-overlap rule

Before adding any upstream source, compare its path and purpose with the existing original modules and `vendor/` imports. Do not overwrite `strategies/technical.py`, `strategies/advanced.py`, `strategy_engine.py`, `risk/position_sizing.py`, `risk/controls.py`, `backtesting/engine.py`, or existing tests. Prefer a small adapter or a uniquely namespaced `vendor/<project>/` path. Keep the upstream LICENSE/NOTICE and attribution where redistribution is allowed. Never copy secrets, API keys, model weights, generated caches, virtual environments, or build artifacts.

## Previously present — do not duplicate

- Original technical indicators and ATR position sizing: `strategies/technical.py`, `risk/position_sizing.py`.
- Advanced indicator implementations: `strategies/advanced.py`.
- Original backtest and risk-gate helpers: `backtesting/engine.py`, `risk/controls.py`.
- Tests and CI: `tests/test_research_strategies.py`, `tests/test_advanced_strategies.py`, `.github/workflows/python-tests.yml`.
- `vendor/TradingAgents/`: existing import is documented as 208 tracked upstream files, including its Apache-2.0 license; it is not yet runtime-integrated or end-to-end tested.
- `vendor/FinGPT/`, `vendor/FinRobot/`, `vendor/Qlib/`: partial imports already exist; do not copy them a second time.
- Angel One readonly adapter and MCP work was previously recorded in PR #3; check that branch/PR before adding duplicate integration files.

## Requested upstreams — deduplicated inventory

The same `fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis` URL was supplied three times; it is listed once below.

| Upstream | Repository | Initial inspection result | Import decision |
|---|---|---|---|
| Awesome Systematic Trading | https://github.com/wangzhe3224/awesome-systematic-trading | README fetch returned 404 for this exact owner/repo path | Blocked pending valid repo URL |
| Awesome Systematic Trading | https://github.com/paperswithbacktest/awesome-systematic-trading | README reachable; curated resource catalog, not an application codebase | Reference/catalog only; do not bulk-copy linked projects |
| Awesome AI in Finance | https://github.com/georgezouq/awesome-ai-in-finance | README reachable; curated links covering agents, MCP, strategies and data | Reference/catalog only; do not bulk-copy linked projects |
| HFTBacktest | https://github.com/nkaz001/hftbacktest | README fetch returned 404 for this exact owner/repo path | Blocked pending valid repo URL |
| QTPyLib | https://github.com/ranaroussi/qtpylib | README fetch returned 404 for this exact owner/repo path | Blocked pending valid repo URL |
| Intelligent Trading Bot | https://github.com/asavinov/intelligent-trading-bot | README reachable; ML crypto-trading project | Review license, dependencies and exchange assumptions before source import |
| Earnings Intelligence / Trading Bot | https://github.com/Sebacaraballo/Trading-Bot | README describes SEC filings + LLM signal extraction; MIT badge in README | Candidate for isolated research adapter; verify LICENSE file before redistribution |
| LLM Trader | https://github.com/qrak/LLM_trader | README reachable; Python 3.13 and MIT license stated in README | Candidate for isolated research import; check actual LICENSE and dependency/runtime fit |
| Agentic AI Trading Bot | https://github.com/fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis | README reachable; news/social/PDF ingestion, LLM orchestration, backtesting and optional execution | Review actual license, secrets handling and execution paths before source import |
| TradeSignalFlux | https://github.com/ItsKillionaire/TradeSignalFlux | README reachable; news sentiment + DeepSeek + Telegram | Research reference; provider-specific API and notification code needs adaptation |
| Next Gen Algo Trading Bot | https://github.com/studiogangster/next-gen-algo-trading-bot | README reachable; Vue/Python, Zerodha, Redis and live/historical charting | Not a direct drop-in; isolate compatible data-sync patterns only after license review |
| LLM-TradeBot | https://github.com/FalconTrading06/llm-tradebot | README reachable; MIT license stated; multi-agent futures framework | Review license file, exchange assumptions and all live-execution paths before import |
| SNIPR-X Trading Bot | https://github.com/DevGohil411/Trading-bot | README reachable; MetaTrader 5/Next.js/FastAPI; MIT badge | Not a direct Angel One/NSE drop-in; review actual license and dependencies |
| TradingBot | https://github.com/Gifted87/TradingBot | README reachable; Gemini + SMC/Wyckoff, Forex/crypto focus | Review license and data/exchange assumptions before import |
| TradingGoose site | https://github.com/TradingGoose/TradingGoose.github.io | README reachable; current README points to TradingGoose Studio as the primary project | Documentation/reference only until actual app repo/license is reviewed |
| Quantitative Finance topic | https://github.com/topics/quantitative-finance | Topic page, not a source repository | Discovery only |
| Trade Analysis topic | https://github.com/topics/trade-analysis | Topic page, not a source repository | Discovery only |
| Trading Bot 2026 topic | https://github.com/topics/tradingbot2026 | Topic page, not a source repository | Discovery only |
| FinLLM trading-agent demo | https://github.com/Open-Finance-Lab/FinLLM-Leaderboard/blob/main/docs/source/demos_of_finagents/trading_agent.rst | Single documentation/demo file, not a repository root | Review attribution/license and dependencies before adapting |

## Integration constraints

- This is an Indian-market/Angel One-oriented Python research repository, not a universal host for entire unrelated apps.
- Keep all third-party code namespaced. Do not merge alternate frontends, their lockfiles, environment files, or their deployment configuration over the existing project.
- Use public, fresh market data with explicit timestamps and stale-data rejection. A model-generated recommendation is not a verified market fact.
- Keep all AI outputs advisory until deterministic validation, risk controls and paper-trading tests pass. Do not enable live order execution as part of a bulk import.
- Do not include API keys, TOTP seeds, JWTs, feed tokens, personal account data, caches, compiled binaries, APKs, or model weights.
- This file records initial README access checks, not a completed full license/security audit. A source is not cleared for redistribution merely because its README is public.
