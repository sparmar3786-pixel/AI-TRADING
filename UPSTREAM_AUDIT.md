# Upstream review log

Destination: https://github.com/sparmar3786-pixel/AI-TRADING
Review date: 2026-10-10

## Current partial imports already present on `main`

The latest repository tree contains partial upstream code under `vendor/`:

| Upstream | Current destination | Status |
|---|---|---|
| `TauricResearch/TradingAgents` | `vendor/TradingAgents/` | Partial; includes upstream license, README copy, dependency files and selected analyst/research/graph modules. Not a complete upstream tree. |
| `AI4Finance-Foundation/FinGPT` | `vendor/FinGPT/` | Partial; selected forecaster and Forex intelligence files plus license/import notes. Not a complete upstream tree. |
| `AI4Finance-Foundation/FinRobot` | `vendor/FinRobot/` | Partial; selected agents, data-source and functional modules plus LICENSE/NOTICE/import notes. Not a complete upstream tree. |
| `microsoft/qlib` | `vendor/Qlib/` | Partial; selected backtest/strategy files plus license/import notes. Not a complete upstream tree. |

These are useful starting points, not fully integrated runnable packages. Their own dependencies and data sources are not automatically installed or configured by this repo.

## Metadata/default-branch checks

GitHub API access and default branch metadata were confirmed for these public projects:

- `TauricResearch/TradingAgents` (`main`)
- `AI4Finance-Foundation/FinGPT` (`master`)
- `AI4Finance-Foundation/FinRobot` (`master`)
- `HKUDS/AI-Trader` (`main`)
- `schen9999/financial-agent` (`main`)
- `rahul-jajala/ai-financial-research-agent` (`main`)
- `Open-Finance-Lab/AgenticTrading` (`main`)
- `microsoft/qlib` (`main`)
- `polakowo/vectorbt` (`master`)
- `mementum/backtrader` (`master`)
- `kernc/backtesting.py` (`master`)
- `QuantConnect/Lean` (`master`)
- `freqtrade/freqtrade` (`develop`)
- `hummingbot/hummingbot` (`master`)
- `angel-one/smartapi-python` (`main`)
- `marketcalls/openalgo` (`main`)
- `AI4Finance-Foundation/FinRL` (`master`)
- `dcajasn/Riskfolio-Lib` (`master`)
- `RuchiTanmay/nselib` (`main`)
- `tradingview/lightweight-charts` (`master`)

A metadata or root-directory check is **not** a full source-file, security or license audit. Most repositories in `UPSTREAM_REPOSITORIES.md` still need per-file review.

## New original code in this change

- `strategies/advanced.py`: Bollinger bands/re-entry, MACD, Donchian channels/breakout and VWAP.
- `backtesting/engine.py`: one-bar-delayed close-to-close backtest with estimated fees/slippage and drawdown metrics.
- `risk/controls.py`: fail-closed risk validation for proposed paper orders.
- `tests/test_advanced_strategies.py`: regression tests for the new modules.
- `.github/workflows/python-tests.yml`: CI workflow for the unittest suite.
- `INTEGRATION_GUIDE.md`: usage and limitations.

These modules are original code; they are not represented as verbatim copies of upstream implementations.

## Important limits

- No full copy of every repository in the inventory has been made. Many sources are very large, use unrelated languages/runtimes or have separate license/dependency requirements.
- `angel-one/smartapi-python` remains reference-only pending confirmation of license/redistribution permissions and review of broker terms.
- No live Angel One authentication, market-data connection, order route or Railway deployment was changed by this strategy integration.
- Backtesting is a starter engine, not an exchange-accurate simulator. Costs, spread, slippage, taxes, gaps, margin, options contract rules and liquidity need explicit modeling.
- Do not treat model confidence or confluence score as probability of profit.

Never commit API keys, broker passwords, MPINs, TOTP seeds, JWTs, feed tokens or account data.
