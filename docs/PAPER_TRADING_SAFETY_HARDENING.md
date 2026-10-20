# Paper-trading skeleton hardening — integration notes

The Python multi-level bot skeleton discussed in chat is **not currently present** as `trading_bot/bot.py`, `trading_bot/broker_angel.py`, `risk.py`, or `api.py` on the repository's `main` branch. Therefore these changes add reusable, tested safety primitives instead of pretending to patch or deploy nonexistent files.

## Added

- `quant/paper_trading_safety.py`: normalizes common SmartAPI candle payload shapes and rejects malformed OHLCV, calculates P&L from the traded instrument's entry/mark/side/quantity, checks timestamp freshness, and rounds exits down to lot-aligned quantities.
- `tests/test_paper_trading_safety.py`: regression tests using simulated payloads only; no broker credentials or live orders.

## Mandatory integration requirements

Before connecting these helpers to a bot:
1. Confirm the installed SmartAPI SDK's exact method signatures and response shape from a sanitized response sample.
2. Resolve the selected option using the actual contract master (expiry, CE/PE, strike, exchange, trading symbol and token). Never send an order for a fixed symbol while displaying a different selected strike.
3. Mark a target complete only after a confirmed successful fill; handle rejected/partial/unknown order states and reconcile broker positions.
4. Persist daily realized P&L, daily lock state, trade count, and open-position state across process restarts. Never reset daily risk limits merely because the process starts.
5. Protect control endpoints with authentication and prevent concurrent bot starts.
6. Keep stop-loss protection and exit monitoring fail-closed; a local polling loop alone is not a guaranteed stop-loss.
7. Keep live execution disabled until paper tests and deployment smoke tests pass.

## Scope and verification

These helpers are not yet wired into a broker order path and do not claim to fix the live `API UP / DATA ERROR` on their own. They do not place orders. Live Angel One connectivity, persistent risk-state recovery, broker-side protection, and APK/backend end-to-end behavior must be tested separately. The repository's existing signal engines remain candidate-only and must continue to require downstream freshness/risk/stability validation.