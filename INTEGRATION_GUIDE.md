# AI-TRADING research integration guide

This repository now contains an original, dependency-free research toolkit alongside the upstream-repository inventory. The upstream projects are referenced for study; their entire source trees have **not** been copied into this project.

## Included modules

- `strategies/technical.py`: SMA, EMA, RSI, ATR, EMA crossover and RSI reversion.
- `strategies/advanced.py`: Bollinger bands/re-entry, MACD, Donchian channels/breakout and cumulative VWAP.
- `strategy_engine.py`: explainable confluence diagnostics for a proposed CALL BUY / PUT BUY / WAIT candidate.
- `backtesting/engine.py`: simple close-to-close backtest with one-bar signal delay, estimated fee/slippage, equity curve and drawdown metrics.
- `risk/position_sizing.py`: equity-risk sizing and ATR stop/target helpers.
- `risk/controls.py`: fail-closed proposed-order checks for stale data, daily loss, max positions, per-trade risk, notional and kill switch.

## Run tests

```bash
python -m unittest discover -s tests -v
```

No third-party packages are required for the current unit tests. The GitHub Actions workflow runs the same command on pushes and pull requests.

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

Backtest values are highly dependent on instrument, timeframe, data quality, fees, spread, slippage, taxes, liquidity, corporate actions, derivatives expiry/lot rules and market regime. The included engine is a starter for research, not a realistic broker simulator. Validate with out-of-sample/walk-forward tests and paper trading before any real-money use.

## Important safety boundaries

- Nothing in this repository sends live orders or authenticates a broker session.
- The Angel One SmartAPI repository is a reference only; do not copy its implementation without confirming its license and applicable broker terms.
- Do not place API keys, passwords, MPINs, TOTP seeds, JWTs, feed tokens or account data in GitHub. Use Railway/GitHub secrets and server-side secret storage.
- Strategy scores are not probabilities of profit. No win rate or future return is guaranteed.
- Options require contract-aware sizing and checks for expiry, lot size, liquidity, spread, margin and risk; the generic stock/price backtester does not model those mechanics.

## Upstream policy

See `UPSTREAM_REPOSITORIES.md` for the full source list and `UPSTREAM_AUDIT.md` / `COPY_STATUS.md` for what was actually reviewed or integrated. A link in the inventory does not mean its files have been imported. For large frameworks, use their official install/package interface or a pinned submodule/fork instead of flattening every file into one Python app.
