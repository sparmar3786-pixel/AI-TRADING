# AI-TRADING — Angel One Strategy Research

This repository is a strategy/research workspace for an eventual server-side market-data and broker integration. Strategy and backtest helpers are not a broker, not a live trading service, and do not guarantee returns.

## Start here

- [Integration guide](INTEGRATION_GUIDE.md) — modules, example, tests and safety boundaries.
- [Upstream inventory](UPSTREAM_REPOSITORIES.md) — trading-related GitHub repositories supplied for review.
- [Upstream audit](UPSTREAM_AUDIT.md) — what was checked and what has/has not been imported.
- [Copy/integration status](COPY_STATUS.md) — committed files and remaining work.

## Included research components

- `strategies/technical.py`: SMA, EMA, RSI, ATR, EMA crossover and RSI reversion.
- `strategies/advanced.py`: Bollinger bands/re-entry, MACD, Donchian breakout/channels and VWAP.
- `strategy_engine.py`: explainable confluence diagnostics.
- `backtesting/engine.py`: a simple delayed-signal close-to-close backtest.
- `risk/position_sizing.py` and `risk/controls.py`: sizing, ATR levels and pre-trade validation.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Broker/AI security

The Android APK should call a backend over HTTPS. Angel One API credentials, MPIN, TOTP seeds, JWT/feed tokens and AI keys must remain server-side and must never be embedded in the APK or committed to GitHub. No code in this repo currently authenticates Angel One or submits live orders.

The upstream projects are tracked as references; they have not all been copied. Import only compatible files after reviewing license/NOTICE requirements, dependencies and security. Validate with realistic fees, spread, slippage, out-of-sample data and paper trading before considering live use.
