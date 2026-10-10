# Code integration status — AI-TRADING

Destination: https://github.com/sparmar3786-pixel/AI-TRADING
Last updated: 2026-10-10

## Added on branch `integrate-trading-research-20261010`

| Path | What it provides | Origin/status |
|---|---|---|
| `strategies/technical.py` | SMA, EMA, RSI, ATR, EMA crossover and RSI reversion | Existing original implementation |
| `strategies/advanced.py` | Bollinger bands/re-entry, MACD, Donchian breakout/channels and VWAP | New original implementation, not verbatim copied |
| `strategy_engine.py` | Explainable indicator/option evidence confluence | Existing original implementation |
| `risk/position_sizing.py` | Equity-risk position sizing and ATR stop/target helpers | Existing original implementation |
| `risk/controls.py` | Fail-closed risk gate for proposed orders | New original implementation; no order execution |
| `backtesting/engine.py` | Starter close-to-close backtest, one-bar signal delay, fee/slippage estimate and drawdown | New original implementation |
| `tests/test_research_strategies.py` | Indicator and sizing tests | Existing original tests |
| `tests/test_advanced_strategies.py` | Advanced strategy/backtest/risk tests | New original tests |
| `.github/workflows/python-tests.yml` | Run unittest suite on pushes and PRs | New CI workflow |
| `INTEGRATION_GUIDE.md` | How to run/use modules and limitations | New docs |
| `UPSTREAM_REPOSITORIES.md` | Full source-reference inventory from chat | References only; not copied source |
| `UPSTREAM_AUDIT.md` | Repository access checks and exact integration scope | Audit notes |

## Upstream source status

**No complete third-party repository tree has been imported.** The upstream list includes projects that are huge, written in different languages, aimed at crypto exchanges, frontend UI libraries, research frameworks or broker gateways. Copying every file into one project without reviewing license terms, dependency compatibility and execution behavior would be unsafe and could break the project. The code added here is original functionality implementing useful research patterns rather than a claim that upstream files were copied.

Selected upstream repository metadata/default branches were checked. Detailed file/license/security review remains pending for most sources. See `UPSTREAM_AUDIT.md`.

## Not done / not claimed

- No broker authentication or live order execution was implemented by this strategy pass.
- No live Angel One data was pulled into the tests.
- No Railway variables or deployment were changed.
- No claim of profitability, win rate or production readiness is made.
- Tests have not yet been confirmed passing by a completed CI run; the workflow was added to run them.

## Test

```bash
python -m unittest discover -s tests -v
```

Do not commit API keys, passwords, MPINs, TOTP seeds, JWTs, feed tokens or other account secrets.