# Code integration status — AI-TRADING

Destination: https://github.com/sparmar3786-pixel/AI-TRADING
Last updated: 2026-10-10

## Committed project code in this pass

| Path | What it provides | Origin |
|---|---|---|
| `strategies/technical.py` | SMA, EMA, RSI, ATR, EMA crossover and RSI reversion signals | New original implementation; not copied verbatim from an upstream repository |
| `risk/position_sizing.py` | Equity-risk position sizing and ATR stop/target calculations | New original implementation |
| `tests/test_research_strategies.py` | Unit tests for the new indicators and risk helpers | New original implementation |

## Upstream source status

The repositories supplied in chat are tracked in `UPSTREAM_REPOSITORIES.md`. A repository URL or readable root listing is not evidence that its source code has been copied. TradingAgents has now been partially vendored under `vendor/TradingAgents/` (see `vendor/TradingAgents/IMPORT_NOTES.md`). This is not a complete import of that upstream repository.

Initial public root listings were readable for:
- `TauricResearch/TradingAgents`
- `schen9999/financial-agent`
- `microsoft/qlib`
- `kernc/backtesting.py`
- `angel-one/smartapi-python`

License note: MIT license text was found for `schen9999/financial-agent` and `microsoft/qlib`; Apache-2.0 license text was found for `TauricResearch/TradingAgents`. The Angel One Python repository's root listing did not show a LICENSE file, so permission must be confirmed before copying its implementation. The backtesting.py license file exists, but its terms need review before vendoring.

The first attempt to read `AI4Finance-Foundation/FinGPT` and `AI4Finance-Foundation/FinRobot` using the branch name `main` returned 404 ("No commit found for the ref main"). This is not enough to conclude the repositories are inaccessible; their default branches need separate discovery.

## Not yet done

- TradingAgents import is partial; remaining upstream modules and package dependencies are not yet all present.
- No Angel One live order path has been enabled by these commits.
- No backend/API wiring or Railway deployment changes were made in this pass.
- The unit tests have been committed but have not been executed in a Python environment during this GitHub-only operation.

## Safe next steps

1. Discover each upstream repository's actual default branch and license.
2. Import permitted code into clearly separated vendor folders with license/notice files, or use a submodule/fork where importing whole projects is unsuitable.
3. Integrate only the needed modules with this project's Python environment and API contracts.
4. Run tests and paper-trading validation before connecting any strategy to live orders.

Do not commit API keys, broker passwords, TOTP seeds, access tokens, or account secrets.
