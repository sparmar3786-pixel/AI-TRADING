# Upstream AI Trading Research and Integration Plan

Target repository: `sparmar3786-pixel/AI-TRADING`
Research branch: `upstream-ai-integration`

## Scope and safety

The supplied list contains 11 unique Git repositories plus two GitHub topic pages and one FinLLM demo document. The Agentic-AI repository URL was repeated three times; it is one source, not three separate systems.

Do not copy entire repositories or blindly combine their agents. Several projects target crypto, Forex, US equities, SEC filings, Alpaca, Binance, or MetaTrader 5. Those broker/data/execution assumptions do not directly fit an Angel One Indian F&O signal backend. Prefer small, independently testable concepts, implement compatible behavior in this project's own modules, and preserve attribution/license obligations for any copied code. Verify each source repository's LICENSE and dependencies before vendoring implementation code.

## Initial README-level review

| Source | Useful concept to evaluate | Fit / caveat |
|---|---|---|
| [asavinov/intelligent-trading-bot](https://github.com/asavinov/intelligent-trading-bot) | Consistent offline/online feature engineering, configurable timeframes, ML training and backtesting | Good architecture pattern; its example market is crypto/Binance, so replace data adapters |
| [Sebacaraballo/Trading-Bot](https://github.com/Sebacaraballo/Trading-Bot) | LLM extraction into structured sentiment, bull/bear cases, risk flags; benchmark and drawdown reporting | SEC earnings/US ticker workflow is not an Indian index-options data source; its README reports negative sample backtest results, a reminder to validate empirically |
| [qrak/LLM_trader](https://github.com/qrak/LLM_trader) | Persistent semantic trade memory, post-trade reflection, claim validation against computed indicators, news RAG, explicit risk veto | Potentially useful after resource and latency review; README says execution is a separate project/in testing |
| [fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis](https://github.com/fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis) | Multi-source sentiment ingestion, tool-based agents, hybrid rules + ML + LLM, circuit breakers | Validate source availability, licensing, and provider costs; do not let LLM bypass deterministic safety gates |
| [ItsKillionaire/TradeSignalFlux](https://github.com/ItsKillionaire/TradeSignalFlux) | Candidate for further code-level review | Very small repository; inspect files and license before adopting |
| [studiogangster/next-gen-algo-trading-bot](https://github.com/studiogangster/next-gen-algo-trading-bot) | Multi-agent analysis, multi-timeframe parsing, decision core, risk audit, optional reflection | Large codebase; inspect exact license, dependencies and broker assumptions before porting |
| [FalconTrading06/llm-tradebot](https://github.com/FalconTrading06/llm-tradebot) | Candidate for further code-level review of LLM/agent and risk design | Large codebase; inspect exact modules, license and runtime requirements before adopting |
| [DevGohil411/Trading-bot](https://github.com/DevGohil411/Trading-bot) | Candidate for further review of layered ML, sentiment, risk and exits | README describes MT5/Forex-style execution; not a drop-in Angel One adapter |
| [Open-Finance-Lab/FinLLM-Leaderboard trading_agent demo](https://github.com/Open-Finance-Lab/FinLLM-Leaderboard/blob/main/docs/source/demos_of_finagents/trading_agent.rst) | Benchmark/research ideas for evaluating financial agents | A demo/leaderboard reference, not automatically a production engine |
| [Gifted87/TradingBot](https://github.com/Gifted87/TradingBot) | SMC/Wyckoff analysis and entry/SL/target explanation | Forex/crypto-oriented and uses historical data; verify freshness and reproducibility |
| [TradingGoose/TradingGoose.github.io](https://github.com/TradingGoose/TradingGoose.github.io) | Multi-agent analyst roles, portfolio/risk manager veto, event-driven analysis | This is a project/documentation site; its README points to the separate TradingGoose Studio implementation. Review that implementation and its license separately if needed |
| [quantitative-finance topic](https://github.com/topics/quantitative-finance) | Discover backtesting, portfolio and quant research tools | Topic index only; each linked repo needs individual review |
| [trade-analysis topic](https://github.com/topics/trade-analysis) | Discover analysis and risk tools | Topic index only; not a single engine |
| [tradingbot2026 topic](https://github.com/topics/tradingbot2026) | Discover newer bot projects | Topic index only; inspect each candidate individually |

## Proposed compatible architecture

1. **Data contract and freshness gate** — normalize Angel One REST/WebSocket snapshots, timestamps, exchange/session state, missing fields, stale ticks and reconnect state. Every UI page must distinguish live, cached, stale and unavailable data.
2. **Deterministic quant layer** — EMA 8/13 and higher-timeframe trend, RSI, MACD, VWAP, ATR, Bollinger, price structure, volume, support/resistance and volatility regime.
3. **F&O/OI layer** — call/put OI changes, premium/OI classification (long buildup, short buildup, short covering, long unwinding), PCR, OI walls, strike distance, option Greeks/IV when genuinely supplied, bid/ask spread, depth/liquidity and expiry checks.
4. **Independent sentiment/research layer** — query Exa, Tavily and Brave through server-side adapters; deduplicate and timestamp sources; report source agreement and uncertainty. News sentiment is context, not a substitute for live price/OI evidence.
5. **Specialist AI agents** — market regime, technical setup, options/OI, news/sentiment and adversarial risk reviewer. Require structured outputs with evidence references and explicit UNKNOWN values.
6. **Decision core and hard vetoes** — combine validated evidence; allow only CALL BUY, PUT BUY, WAIT or NO TRADE. Contradictory, stale or insufficient inputs force WAIT/NO TRADE. AI cannot fabricate prices, strike data, probabilities, or override risk rules.
7. **Trade-plan calculator** — derive entry from a fresh executable quote, SL and targets from a declared strategy/volatility rule, risk/reward, spread and charges. Never show an actionable plan if lot size, quote or required inputs are missing.
8. **Memory and reflection** — store signal snapshots, rationale, rejected trades and outcomes; update rules only through evidence-weighted evaluation with decay, contradiction checks and out-of-sample validation. Do not silently self-modify live strategy parameters.
9. **Backtest and paper-trade validation** — walk-forward/out-of-sample tests, realistic spread/slippage/fees, latency, missing-data and expiry handling, drawdown, expectancy, profit factor and benchmark comparison. No performance claim without reproducible results.
10. **Observability** — per-stage status, last successful fetch, data age, error category, provider health, trace/correlation ID and UI/API contract tests. This is essential before adding more AI agents.

## Acceptance gates before merging

- Unit tests for each deterministic feature and every fail-closed path.
- Contract tests proving dashboard, OI, signal, and status endpoints share the same normalized snapshot and show stale/missing-data states honestly.
- Mocked Angel One/WebSocket reconnect, token expiry, throttling and malformed-payload tests.
- AI JSON schema validation, timeout/retry limits, source citations, prompt-injection resistance and deterministic risk veto tests.
- Walk-forward backtest with costs and no look-ahead leakage.
- Paper trading only until live data quality and out-of-sample performance are verified.
- No broker credentials, TOTP, AI keys, or search API keys in Android assets, logs, commits, or client-side storage.

## Current repository baseline

The existing `strategy_engine.py` is a small original confluence helper. Its alignment score is explicitly not a win probability. This plan is a research map, not evidence that upstream code has been imported or that a live Angel One connection has been validated. Continue by reviewing source files and licenses individually, then port one isolated capability at a time with tests.
