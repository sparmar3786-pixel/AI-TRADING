# Signal-only multi-level bot scaffold

This is an optional standalone FastAPI service under `trading_bot/`. It is deliberately **advisory/paper-only**: no order placement, no broker order routes, no actual execution, and no promise of 15% daily profit.

## Install and run

```bash
python -m pip install -r requirements-trading-bot.txt
uvicorn trading_bot.api:app --host 127.0.0.1 --port 8000
```

Keep it on localhost during development. Before exposing it remotely, add authenticated access, TLS, rate limits, and deployment secret management.

## Angel One read-only data (backend environment only)

Set these environment variables in the backend's secret manager, never in the APK or source code:

- `ANGEL_API_KEY`
- `ANGEL_CLIENT_CODE`
- `ANGEL_PIN`
- `ANGEL_TOTP_SECRET`
- `ANGEL_SYMBOL_TOKEN` (numeric token for the underlying/index instrument)
- Optional: `ANGEL_EXCHANGE` (defaults to `NSE`), `ANGEL_INTERVAL` (defaults to `FIVE_MINUTE`), `ANGEL_LOOKBACK_DAYS` (defaults to `5`), `ANGEL_TRADING_SYMBOL` (if configured, used for an LTP request)

`GET /angel/evaluate` fetches candles and computes an advisory result. Angel One SDK/API changes, login failures, invalid symbol tokens, empty/stale data, insufficient history, and HMM failures return an error/WAIT instead of reusing a cached BUY/SELL signal. Confirm the correct exchange, symbol, token, and interval from the current Angel One instrument master before use.

## API endpoints

- `GET /health` and `GET /status`
- `POST /evaluate` with JSON `{ "candles": [{"ts":"...", "open":1, "high":2, "low":1, "close":1.5, "volume":100}], "spot": 1.5 }`
- `GET /angel/evaluate` (read-only Angel One historical candles)
- `GET /risk`, `GET /trades`, `GET /daily`
- `POST /risk/paper-update` to record simulated PnL deltas/open PnL and optionally count a simulated trade
- `POST /risk/reset-paper-day` (resets only the in-memory paper/advisory risk state)

## Safety and integration boundary

- Daily profit lock (15%), daily max loss (5%), and trade-count caps are simulated risk gates; they do not close a real broker position.
- The SQLite log stores evaluations, not a broker tradebook. `trading_bot/position_manager.py` simulates partial exits/trailing stops; `trading_bot/optimizer.py` creates bounded candidates only and does not auto-promote them.
- `/risk/paper-update` and `/risk/reset-paper-day` mutate in-memory simulation state. Keep the service bound to localhost unless authenticated, TLS-protected access is implemented.
- The supplied partial-exit/trailing-stop/live-order code was not copied verbatim because it assumes fills and broker responses that have not been verified and could send unintended live orders. This service has no order placement method.
- This new service is not yet deployed or connected to the app's existing `/v1/signals` backend. The HMM output is not currently controlling live app signals.
- The Flutter APK and web app have the Strategy and Quant Engine pages removed. These backend research files do not restore those screens.
