# AI-TRADING research integration guide

The repository contains original strategy/backtest/risk helpers and selected, partially vendored upstream projects under `vendor/`. The vendor folders have their own `IMPORT_NOTES.md` and license/notice files; check those before using them. They are not complete copies of all upstream repositories.

## Included modules

- `strategies/technical.py`: SMA, EMA, RSI, ATR, EMA crossover and RSI reversion.
- `strategies/advanced.py`: Bollinger bands/re-entry, MACD, Donchian channels/breakout and cumulative VWAP.
- `strategy_engine.py`: explainable confluence diagnostics for a proposed CALL BUY / PUT BUY / WAIT candidate.
- `quant_engine.py`: five-layer fail-closed signal research gate for data freshness, multi-timeframe trend/session sentiment, bid/ask order flow, liquid option selection, ATR-based risk levels and continuous 10-minute candidate confirmation.
- `backtesting/engine.py`: close-to-close backtest with one-bar signal delay, estimated fee/slippage, equity curve and drawdown metrics.
- `risk/position_sizing.py`: equity-risk position sizing and ATR stop/target helpers.
- `risk/controls.py`: fail-closed proposed-order checks for stale data, daily loss, max positions, per-trade risk, notional and kill switch.
- `vendor/TradingAgents`, `vendor/FinGPT`, `vendor/FinRobot`, `vendor/Qlib`: partial upstream imports; not all dependencies, files or runtime integration are included.

## Run tests

```bash
python -m unittest discover -s tests -v
```

The current test suite is designed to run without installing the heavyweight vendor frameworks. The GitHub Actions workflow runs the unit tests on pushes and pull requests.

## Example (research only)

```python
from strategies.advanced import donchian_breakout
from backtesting.engine import run_backtest

closes = [100, 101, 102, 101, 105, 107]
highs  = [101, 102, 103, 102, 106, 108]
lows   = [99, 100, 101, 100, 104, 106]
signals = donchian_breakout(closes, highs, lows, period=3)
report = run_backtest(closes, signals, fee_rate=0.0005, slippage_rate=0.0005)
print(report["total_return"], report["max_drawdown"])
```

The included engine is a starter for research, not a realistic broker simulator. It omits spread, taxes, market impact, margin, options expiry/lot rules, liquidity and gaps. Validate out-of-sample/walk-forward and paper trading before any real-money use.

## Security and licensing

- No code here sends live orders or authenticates a broker session.
- The Angel One SmartAPI repository is a reference only; do not vendor it without confirming its license and applicable broker terms.
- Do not commit API keys, passwords, MPINs, TOTP seeds, JWTs, feed tokens or account data.
- Third-party code stays under `vendor/` with import notes and notices; review each project's license before redistribution.
- Strategy scores are not probabilities of profit. Missing/stale inputs should produce WAIT/NO TRADE.


## Five-layer engine status

`quant_engine.py` is a tested, broker-neutral evaluator for normalized snapshots. `backend/app/main.py` currently calls it from `_index_snapshot()` and exposes its layer results as both `quant_engine` and `five_layer_engine`. The evaluator itself does not log in to Angel One or submit orders; the caller supplies exchange-timestamped quotes, historical candles, option data, indicators and sentiment. This code path still requires live Railway verification with valid broker credentials and fresh source timestamps. If evidence is missing or stale, the app should show `WAIT` / `DATA REQUIRED`, not a passing layer. MPIN, TOTP seed, client ID and broker/session tokens must remain in server-side secret storage, never in APK source or app preferences.
