# AI-TRADING Read-only Live Signals API

This service connects the Flutter signal-only app to the official Angel One SmartAPI SDK and the repository's five-layer quant engine. It has **no order placement, modification, or cancellation endpoint**.

## What is implemented

- /health, /v1/metadata, /v1/system/diagnostics
- /v1/angel/connect, /v1/angel/status for API key + Client ID + MPIN + current TOTP authentication
- /v1/instruments/sync to refresh Angel One's public instrument master
- /v1/option-chain?index=NIFTY for timestamped, near-ATM option quotes and available Greeks
- /v1/market/sentiment?index=NIFTY for price-structure/order-book sentiment (not news sentiment)
- /v1/signals for NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX and BANKEX plus active MCX futures status
- /v1/market/ticks, /v1/live/status, /v1/stream/start
- /v1/backtest/historical for a deliberately basic long-only EMA 8/21 historical-candle baseline

Signals fail closed to WAIT when credentials, fresh exchange timestamps, depth, candle history, option quotes/Greeks, ATR or multi-timeframe alignment are missing. The five-layer engine requires the same candidate to remain valid for 600 seconds. Its score is not a probability of profit.

## Security and credential lifecycle

**Never commit credentials or put them in the APK.** The mobile app submits credentials over HTTPS to /v1/angel/connect. API key, Client ID and MPIN may be stored only as AES-GCM ciphertext when remember_credentials=true. TOTP is never persisted. Generated JWT/feed/refresh tokens remain in process memory and are never returned by API routes.

For production Railway deployment:

1. Attach a persistent volume mounted at /data.
2. Set CREDENTIALS_ENCRYPTION_KEY to a fresh 32-byte random key encoded as base64 (or 64 hex characters). Generate locally with this command: python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())". Do not commit the result.
3. Optionally set ANGEL_CREDENTIALS_FILE=/data/angel_credentials.enc.
4. Deploy this repository's root Dockerfile; Railway uses /health as the health check.
5. Open the app's API & Railway page and connect with API key, Client ID, MPIN and the current TOTP. Leave Remember credentials enabled only after the volume and encryption key are configured.
6. If the process restarts, the encrypted API key/Client ID/MPIN can be recovered, but a fresh TOTP is required to establish a new broker session. No TOTP seed is stored.

Environment-variable-only setup is also supported with ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PIN, and ANGEL_TOTP_SECRET. Keep all four in Railway variables, not GitHub or Flutter build args.

## Honest limitations

- SmartWebSocketV2 is started after successful Angel One login and subscribes to index/active MCX tokens; nearby option tokens are subscribed as they are discovered. REST FULL-depth quotes are the fallback when a fresh WebSocket tick or required bid/ask depth is missing. Diagnostics distinguish WebSocket-open from actual fresh ticks.
- The signal service uses market-structure sentiment from price and depth. News sentiment / Exa / Tavily are not wired into this service yet.
- Angel One SmartAPI's returned fields can differ by SDK and instrument; if a source timestamp or required field is absent, the affected signal stays WAIT.
- Index option selection uses the current nearest unexpired expiry and nearby strikes. Validate exchange symbol-master values, expiry conventions and live option depth against the account before relying on it.
- Commodity futures are shown with live quote freshness, but commodity-specific option-chain signals are not generated.
- Historical backtest is a research baseline, not exchange-accurate options backtesting; it excludes fees, taxes, spread, margin and slippage.
- A green CI build cannot verify broker credentials or live-market availability. Perform physical-device testing and paper trading during market hours.

## Run locally

    python -m pip install -r backend/requirements.txt
    uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8080

In a local shell, configure the four ANGEL_* environment variables before attempting broker login. Never paste them into a public issue or commit.
## Cloud AI provider (NVIDIA primary)

- Set `NVIDIA_API_KEY` in Railway for NVIDIA hosted chat inference. For an existing NVIDIA key used by Kumo, `KUMO_NVIDIA_API_KEY` is accepted as a fallback, provided that key has access to the selected chat model.
- Primary model defaults to `NVIDIA_CHAT_MODEL=z-ai/glm-5.3`; the default secondary model is `NVIDIA_CHAT_FALLBACK_MODEL=qwen/qwen2.5-coder-32b-instruct`. The backend tries GLM first and tries Qwen only if the primary inference fails. Both models must be enabled for the same NVIDIA API key. Override either variable if needed.
- `NVIDIA_CHAT_BASE_URL` defaults to `https://integrate.api.nvidia.com/v1/chat/completions`.
- Optional fallback: configure `OPENROUTER_API_KEY`; default fallback model is `meta-llama/llama-3.3-70b-instruct`.
- Run **Test AI Providers** in the app after deployment. A key being present only means configured; green status requires a real authenticated inference response.
- NVIDIA chat handles natural-language Q&A and signal review. Kumo Tabular remains a separate structured-prediction service. Neither AI provider can override deterministic WAIT/risk gates, and the service does not place orders.
- Keep all API keys in Railway variables or a local untracked environment file. Never commit secrets or put them in Flutter build arguments.


## Realtime chart performance rollout

The optional realtime chart router is mounted at:
- `GET /snapshot?symbol=BANKNIFTY&tf=1m&limit=1000` — initial candle snapshot with `seq` and `ts_server`.
- `WS /ws/chart?symbol=BANKNIFTY&tf=1m&lastSeq=0` — current-candle deltas and sequence-gap notifications.
- `POST /internal/chart/tick` — internal normalized candle/tick ingest; requires `Authorization: Bearer <MARKET_INGEST_TOKEN>`.

Set `REDIS_URL` to a Railway Redis connection string and set a strong random `MARKET_INGEST_TOKEN` before enabling the ingest route. Without Redis, endpoints use a process-local memory cache for development only; it is not durable and does not synchronize replicas. Redis keys use `candles:{SYMBOL}:{TF}`, `cur:{SYMBOL}:{TF}`, and `seq:{SYMBOL}:{TF}`. WebSocket topics use `chart.{SYMBOL}.{TF}`.

**Current integration status:** the existing SmartWebSocketV2 callback now passes normalized ticks to a bounded background queue, so Redis work does not block the broker callback. The worker builds OHLCV candles for supported timeframes and publishes Redis deltas. Set `CHART_TOKEN_SYMBOL_MAP` to a JSON object mapping exact Angel One instrument tokens to canonical app symbols (for example, `{"99926000":"NIFTY"}`); unmapped tokens are ignored. Configure `REDIS_URL` or the bridge deliberately does not publish chart data. The legacy `/internal/chart/tick` route remains token-protected for external/internal adapters.

**Flutter client:** the Pro Chart now requests `/snapshot`, connects to `/ws/chart`, retains the last sequence, reconnects with exponential backoff, and re-fetches the snapshot on sequence gaps/app resume. It caps retained bars and isolates chart painting with `RepaintBoundary`. This is source-code integration; a successful Android build and on-device test are still required before declaring it production-ready.

**Candle-close persistence and engine handoff:** the tick bridge writes closed candles to Redis Stream `chart:candle_closed`. Run a separate Railway service from the same image with start command `python -m app.engine_worker` and configure `REDIS_URL` plus `DATABASE_URL` (or `POSTGRES_URL`). The worker creates `market_candles` with a symbol/timeframe/epoch primary key and upserts candle closes idempotently, then emits `engine:candle_events` with a stable `event_id`. Any engine consumer must deduplicate on `event_id`; the stream is an event handoff, not a claim that all signal strategies are already running in this worker.

**Order safety:** this backend remains read-only and has no broker order-placement route. Do not add order placement to the chart or candle worker. Any future order service must be separate, validate freshness and deterministic risk gates again at submission, require explicit user authorization, and use a durable idempotency key before calling the broker.

**Still required before production cutover:** verify token mapping against the current Angel One instrument master; configure Railway Redis/Postgres and separate worker service; run Flutter analysis, Android build and physical-device reconnect/gap tests; add Android background decode/visible-candle rendering only if profiling shows it is needed; and compare measured tick-to-screen latency against a baseline. Do not route live orders through the chart service.
