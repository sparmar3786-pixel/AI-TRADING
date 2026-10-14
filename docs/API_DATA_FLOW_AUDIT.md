# AI-TRADING API / Data Flow Audit — 13 Oct 2026

## Evidence
- Railway ai-trading-signals-api logs show /v1/signals requests lasting about 19–73 seconds.
- Multiple requests ended in HTTP 499 because the client closed the request before a response arrived.
- Latest six-hour metrics observed: 2,741 requests, 2,665 2xx, 37 4xx, 39 5xx; 5xx rate 1.42%.
- /health, /v1/angel/status, and /v1/system/diagnostics frequently returned 200; route reachability does not prove fresh market data.

## Confirmed code-path issues
- CI container smoke test exposed `ModuleNotFoundError: No module named 'backend'` because the service is launched as `app.main` inside the Docker image. The router import now supports both container and repository test module paths; confirm the next container smoke test passes.
1. flutter_app/lib/main.dart: refresh() sets signalsEndpointOnline=false on signal request errors; _appBarStatus then renders API UP • DATA ERROR.
2. flutter_app/lib/api.dart: normal GET timeout defaults to 30 seconds.
3. backend/app/main.py: _get_signals() uses a single background refresh guarded by _signal_build_metrics['in_flight'] and serves explicitly stale cached snapshots while refreshing. This should reduce duplicate broker fan-out; verify under concurrent app + WebSocket load because earlier logs showed HTTP 499s.
4. _index_snapshot() performs spot quote, historical candles, option quote batch, Greeks and selected-option ATR work per index; six indices plus commodity snapshots can still make refreshes slow. The SMC chart now includes real daily candles and hourly aggregates of real 5-minute candles in both normal and signal-fallback paths; live latency and broker history availability still require verification.
5. /ws now sends broker-derived best-five price-level buckets (`lv`) and the instrument tick step to the bundled footprint chart. These values are bid/ask depth, not exchange-classified trade prints; the UI must preserve that distinction.
6. `flutter_app/lib/order_flow_page.dart` loads the bundled original footprint HTML and records WebSocket telemetry. Real-device WebView rendering and live depth availability still need on-device verification.
7. Backend `/v1/ai/status` reports key/configuration state, while `_run_ai_validation_probe()` performs a real authenticated provider request for a validation probe. Production credentials, provider quota, response parsing and successful inference must still be verified from live logs.

## Page communication contract
Angel One REST/WebSocket → exchange-timestamped market snapshot → shared market[index] and option-chain cache → indicators/OI → five-layer quant engine → risk/strategy gates → provider evidence validation → notifications and screens.

- Dashboard / Market / Indicators: shared market snapshot, quote age, source timestamp and indicators.
- Option Chain / OI Lab: shared per-index option-chain cache with source timestamps.
- Signals / Risk / Trading Setup / Five Layer / Quant Engine Lab / Strategy Library: same signal object, validation verdict, guards and engine layers.
- Order Flow: fresh broker snapshot stream; footprint cells require actual price-level depth.
- Data Health: health, signal route status, Angel session, tick age, provider status and measured request/engine latency must remain separate.
- Notifications: timestamp, index, failing stage, latency, provider/model, validation verdict and safe error summary; never include API keys/tokens.

## Required fix order
1. Confirm the existing single-background-refresh guard prevents duplicate broker fan-out under concurrent clients; add a load test if 499s recur.
2. Instrument stage durations (market snapshot, option quotes, Greeks, ATR, commodities, total build) and expose them in diagnostics.
3. Reduce duplicate polling and have WebSocket consumers use the shared cached snapshot; verify no repeated 499s under concurrent app + WS clients.
4. Verify OpenAI and OpenRouter authenticated probes against production credentials; keep configured-but-untested separate from successful inference and preserve secret-free error messages.
5. Verify real broker best-five levels reach the footprint HTML and show explicit unavailable states when depth is absent; never label depth-derived buckets as classified trade prints.
6. Remove repository/reference cards from operational tabs; retain only app workflows and optionally a single dedicated reference library.
7. Verify Flutter analysis/tests, Python tests, CI APK artifact, and live Angel One timestamps separately. The Android build workflow's service manifest setting must match the plugin's exported=true declaration to avoid manifest-merger failure.

## Footprint design requirements from supplied index(1).html
Preserve symbol selector; timeframes 1m, 3m, 5m, 15m, 30m, 1h; zoom; live control; manual; price axis; Sell × Buy ladder; green/red volume cells; POC outline; 3x imbalance; delta, volume, Buy ord and Sell ord; pan/drag and last-price line. Demo mode must not be used.

## Verification limits
This is an evidence-based audit, not a claim that all tabs are now end-to-end verified. A green /health, successful APK build, or configured AI key does not prove fresh Angel One ticks or successful AI inference. Live order placement remains disabled while validation is incomplete.

## Fixes applied during the follow-up audit — 13 Oct 2026

- **Angel One environment bootstrap:** the signals backend now accepts either `ANGEL_CLIENT_CODE` or the already-configured Railway name `ANGEL_CLIENT_ID`. A regression test covers the alias. This removes a confirmed name mismatch; actual broker authentication still must be confirmed by a fresh device request and current SmartAPI response.
- **SMC API contract:** Guardeer and Inner Circle wrappers now accept the API's optional `liquidity_tolerance` argument. The SMC panel displays the server-reported ICT killzone window and New York local time.
- **SMC candle freshness:** live chart/analysis now requires a live backend marker plus a recent timestamped 15-minute candle. Empty, stale, or demo candles remain non-actionable.
- **Signal request timeout:** Flutter's `/v1/signals` request timeout is 80 seconds to avoid converting a delayed response into a misleading timeout error. This is a resilience guard, not a replacement for reducing backend latency.
- **Verification:** Python unit tests passed after the credential and SMC test fixes. Railway's `ai-trading-signals-api` deployment for the environment-variable fix completed successfully and its `/health` startup check returned HTTP 200. Flutter analysis and widget/API tests passed; APK workflow run `38443313114` completed successfully and published artifact `ai-trading-apk-274` (39,304,610 bytes; expires 27 Oct 2026).
- **Still requires runtime confirmation:** a new authenticated device request must confirm Angel One login, fresh exchange timestamps, option-chain quotes, WebSocket tick freshness, and real NVIDIA/OpenRouter inference. A successful health check alone does not prove those paths.

