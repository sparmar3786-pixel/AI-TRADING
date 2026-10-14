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
- Optional: set `NVIDIA_CHAT_MODEL=nvidia/llama-3.3-nemotron-super-49b-v1.5` and `NVIDIA_CHAT_BASE_URL=https://integrate.api.nvidia.com/v1/chat/completions`.
- Optional fallback: configure `OPENROUTER_API_KEY`; default fallback model is `meta-llama/llama-3.3-70b-instruct`.
- Run **Test AI Providers** in the app after deployment. A key being present only means configured; green status requires a real authenticated inference response.
- NVIDIA chat handles natural-language Q&A and signal review. Kumo Tabular remains a separate structured-prediction service. Neither AI provider can override deterministic WAIT/risk gates, and the service does not place orders.
- Keep all API keys in Railway variables or a local untracked environment file. Never commit secrets or put them in Flutter build arguments.
