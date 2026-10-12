# Trading-related upstream repository inventory

Destination: https://github.com/sparmar3786-pixel/AI-TRADING

**Important:** these are the upstream sources supplied or identified for review. This inventory does not mean their source trees have been copied. The repository now contains original compatible strategy, backtest and risk helpers; complete upstream trees are not imported. Large projects have different runtimes, dependencies, licenses, data assumptions and execution models, so relevant files and licenses must be reviewed before vendoring.

## Curated lists and discovery
- https://github.com/AI4Finance-Foundation/Awesome_AI4Finance
- https://github.com/tradevectorsrobots/awesome-algo-trading-india
- https://github.com/PlaceNL2026/best-of-algorithmic-trading
- https://github.com/bettyguo/awesome-llm-trading-agents
- https://github.com/Tom-roujiang/Awesome-LLM-Quantitative-Trading-Papers
- https://github.com/shakeebshaan/awesome-crypto-trading-agents
- https://github.com/LLMQuant
- https://github.com/LLMQuant/awesome-trading-agents
- https://github.com/topics/algo-trade
- https://github.com/topics/backtesting
- https://github.com/topics/trade
- https://github.com/topics/strategies
- https://github.com/topics/india-stock-market
- https://github.com/orgs/Indian-Algorithmic-Trading-Community/repositories

## AI agents, signals and financial research
- https://github.com/TauricResearch/TradingAgents
- https://github.com/AI4Finance-Foundation/FinGPT
- https://github.com/AI4Finance-Foundation/FinRobot
- https://github.com/HKUDS/AI-Trader
- https://github.com/schen9999/financial-agent
- https://github.com/rahul-jajala/ai-financial-research-agent
- https://github.com/Hasan8123/Trading-Agents-Team
- https://github.com/Open-Finance-Lab/AgenticTrading
- https://github.com/virattt/ai-hedge-fund
- https://github.com/asavinov/intelligent-trading-bot
- https://github.com/Sebacaraballo/Trading-Bot
- https://github.com/keerthivasanrk/AI-Trading-Signal-Engine-FOREX-
- https://github.com/karimcodes/systematic-trading
- https://github.com/JasonTeixeira/trade-engine
- https://github.com/hyuwowo/opentrading
- https://github.com/kr8tiv-ai/Jarvis

## Quant, backtesting and portfolio/risk
- https://github.com/microsoft/qlib
- https://github.com/polakowo/vectorbt
- https://github.com/mementum/backtrader
- https://github.com/kernc/backtesting.py
- https://github.com/QuantConnect/Lean
- https://github.com/quantopian/zipline
- https://github.com/gbeced/pyalgotrade
- https://github.com/AI4Finance-Foundation/FinRL
- https://github.com/ai4finance-foundation/finrl-trading
- https://github.com/dcajasn/Riskfolio-Lib
- https://github.com/0xemmkty/QuantMuse
- https://github.com/tanmaykaper/Paper-Trading-Bot
- https://github.com/buzzsubash/algo_trading_strategies_india

## Trading bots, brokers and data feeds
- https://github.com/freqtrade/freqtrade
- https://github.com/hummingbot/hummingbot
- https://github.com/jesse-ai/jesse
- https://github.com/Drakkar-Software/OctoBot
- https://github.com/marketcalls/openalgo
- https://github.com/StockSharp/StockSharp
- https://github.com/zerodha/pykiteconnect
- https://github.com/angel-one/smartapi-python
- https://github.com/RuchiTanmay/nselib
- https://github.com/nsepy/nsepy
- https://github.com/ranaroussi/yfinance
- https://github.com/ccxt/ccxt
- https://github.com/StreamAlpha/py5paisa

## India market dashboards and UI
- https://github.com/vikram-2101/Stock-Market-Dashboard
- https://github.com/SujaySingh-0403/stock-dashboard
- https://github.com/tradingview/lightweight-charts
- https://github.com/rudra-sah00/trading-chart
- https://github.com/galafis/trading-dashboard-react
- https://github.com/dngr2/fastapi-trading-dashboard
- https://github.com/Ritik5Prasad/GrowwClone_Public

## Backend, deployment, chat and mobile/UI references
- https://github.com/lNamelessl/fastapi-fullstack-railway
- https://github.com/flutter/ai
- https://github.com/tariqjamel/Flutter-Chat-Bot
- https://github.com/msnandanwar/AI-Chatbot
- https://github.com/iampawan/ChatGPT-Flutter-AIChatBot
- https://github.com/PocketLLM/PocketLLM
- https://github.com/flyerhq/flutter_chat_ui
- https://github.com/hkuczynski/firebase-messaging
- https://github.com/Conferbot/conferbot-flutter
- https://github.com/GetStream/stream-chat-flutter
- https://github.com/otida/flutter_ai_toolkit
- https://github.com/codegeoss/flutter_ai_toolkit
- https://github.com/uxduck/push

## Status definitions
- **Adapted/original code committed:** equivalent useful behavior implemented as new code in this repository; not a verbatim upstream copy.
- **Reference only:** source URL is recorded; upstream code is not vendored.
- **Pending review:** inspect all relevant files, default branch, license/NOTICE, dependencies, security, data requirements and compatibility.
- **Blocked:** source is inaccessible or redistribution permissions are unclear for the intended use.

## Current status
The original research toolkit is documented in `INTEGRATION_GUIDE.md`. Most upstream sources remain reference-only/pending review. See `UPSTREAM_AUDIT.md` and `COPY_STATUS.md`. This inventory intentionally does not claim that every repository has been copied.

 
## Continuation import status (updated 2026-10-12)

The separate branch `continue-upstream-import-20261012` and [PR #4](https://github.com/sparmar3786-pixel/AI-TRADING/pull/4) now contain selected vendor snapshots from the upstream sources below. This is **not** a statement that all listed sources—or 500 repositories—have been completely cloned.

- MIT: `qrak/LLM_trader`, `asavinov/intelligent-trading-bot`, `Sebacaraballo/Trading-Bot`, `FalconTrading06/llm-tradebot`, `karimcodes/systematic-trading`, `Jaydot33/automated-trading-system`, `Open-Finance-Lab/FinLLM-Leaderboard`, `AI4Finance-Foundation/FinRL`, `virattt/ai-hedge-fund`, `schen9999/financial-agent`, `zerodha/pykiteconnect`.
- Apache-2.0: `tripolskypetr/backtest-kit` is MIT (TypeScript); `QuantConnect/Lean` and `RuchiTanmay/nselib` are Apache-2.0.
- CC0-1.0 catalog: `georgezouq/awesome-ai-in-finance`.
- `TradingAgents`, `FinGPT`, `FinRobot`, and `Qlib` had prior partial vendor trees documented before this continuation.

The branch currently represents **15 distinct upstream projects across 149 vendored files** (licenses, documentation, configuration/dependency metadata, examples, tests and source combined). Most projects are partial subsets; `vendor/nselib/` and `vendor/pykiteconnect/` contain their tracked textual Python source/examples/tests/config as inspected in the fetched repository tree, with IDE-only metadata excluded. All code remains isolated under `vendor/`; no third-party strategy or broker client was wired into production execution. Tests, dependency installs, security checks and Railway deployment are pending.
