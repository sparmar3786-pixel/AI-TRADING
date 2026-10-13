# API and tab communication audit

Audit date: 2026-10-13

## Confirmed failure evidence

- Railway logs previously showed repeated successful `/health` requests while `/v1/signals` sometimes took roughly 19–73 seconds.
- Several `/v1/signals` requests ended as HTTP 499 because the client closed the request before the response arrived.
- A green health endpoint proves that the service process is reachable; it does not prove that the Angel One quote is fresh, the signal calculation completed, or the AI provider ran.

## Changes in this branch

1. **Signal API single-flight:** serializes cache misses around the expensive broker collection so multiple WebSocket clients and periodic refreshes do not launch duplicate signal builds concurrently.
2. **API transfer telemetry:** records method, path, HTTP status, request-to-response latency, response-body byte count, and UTC receive timestamp for the latest completed request.
3. **Visible diagnostics:** changes the app status to distinguish signal timeout, signal error, waiting data, market closed, and live status; reports a changed signal error through an in-app snackbar. Long-press the status text for the last completed API request metrics.
4. **Footprint chart:** embeds the user-provided HTML chart as an asset, retains its six timeframe choices (1m/3m/5m/15m/30m/1h), symbol picker, zoom, drag, Live control, and manual. The chart connects to the configured backend `/ws`; it does not synthesize demo prices.
5. **Repository clutter:** removes the repository tabs and hides external repository link cards from the operational Trading Setup, Research Engines, Trade Engine, and Strategy Library views.

## Critical data limitation

The existing `/ws` contract sends timestamped OHLC-like spot snapshots and aggregate top-of-book quantities. It does **not** currently send the HTML chart's required per-price `lv` Sell × Buy ladder, POC, or order counts (`bo`/`so`). Therefore the embedded chart must show **LIVE SNAPSHOT · NO PRICE-LEVEL DEPTH** until the backend can source and validate real broker depth levels. It must not fill those cells with demo/synthetic values. Index spot itself does not have exchange-traded volume; a proper footprint needs an explicitly selected liquid futures contract or supported depth stream, plus timestamp and aggregation rules.

## Expected communication flow

Angel One session / stream
→ exchange-timestamped quote + actual depth
→ shared per-index snapshot/cache
→ indicators + option-chain/OI
→ deterministic five-layer quant engine
→ risk/strategy guards
→ optional AI evidence validation (OpenAI/OpenRouter only after authenticated inference succeeds)
→ shared signal contract
→ Dashboard, Market, Option Chain/OI Lab, Signals, Risk, Trading Setup, Research, Five-Layer, Quant Engine Lab, Order Flow and notifications.

All pages should use the same selected index, snapshot timestamp, source freshness and normalized signal contract. Missing/stale data must remain WAIT/NO TRADE.

## AI provider status

The currently inspected backend payload explicitly reports AI as not configured on the signal service. Provider keys being present elsewhere, or a health check returning 200, is not evidence that OpenAI or OpenRouter returned a validation. Each provider must execute a real authenticated inference and report provider/model, duration, result/verdict, and sanitized error before the UI may mark it working.

## Verification still required before merge/release

- Run backend unit tests, Flutter analyzer, widget/API tests, and Android APK build.
- In Railway, confirm repeated `/v1/signals` latency falls and 499s stop during multiple active WebSocket clients.
- With an authenticated Angel One session, confirm quote timestamps and actual depth levels are present. Until then, do not label the footprint ladder live.
- Run authenticated OpenAI and OpenRouter validation tests and confirm their real output events reach notifications.
- Verify all operational tabs display no repository link cards and consume the same selected-index snapshot.

A passing build is not proof of live Angel One data or AI-provider output.
