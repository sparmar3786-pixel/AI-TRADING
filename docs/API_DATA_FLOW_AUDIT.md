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



## Full system / data-flow audit — 14 Oct 2026

### Production evidence captured during audit
- Railway production project `humble-optimism`: `ai-trading-signals-api` is deployed from `sparmar3786-pixel/AI-TRADING`, branch `main`; deployment for merge `7e9f2d491b3cf4c33f2922706d74d7faf98046e9` reported `SUCCESS`.
- Last six hours at audit time: 2,148 HTTP requests, 2,144 2xx, 3 4xx, 1 5xx. The error-rate tool reported one 5xx and 3 client errors; interpret the returned percentage alongside bucket/window boundaries.
- Response-time distribution showed p50 8 ms, p90 31 ms, p95 5,296 ms, p99 16,516 ms. Recent /v1/option-chain calls took about 5.4–7.3 seconds; cached /v1/signals requests commonly returned in 8–26 ms.
- Recent logs contain repeated 200 responses for /health, /v1/signals, /v1/system/diagnostics, /v1/angel/status and /v1/ai/status. Client-closed WebSocket requests (499) also occur. HTTP 200 confirms route response, not fresh Angel One quotes or successful AI inference.
- Railway uses `KUMO_NVIDIA_API_KEY` and `KUMO_NIM_BASE_URL` for structured Kumo predictions. NVIDIA chat uses a separate `NVIDIA_API_KEY`; OpenRouter is the configured fallback. Keep these credentials separate and never mark the provider working until a real inference succeeds.

### Confirmed structure / integration gaps
1. Resolved 14 Oct 2026: Flutter cloud chat, AI status and provider checks now use `SIGNAL_BACKEND_URL` and `/v1/ai/nvidia-chat`; the previous split between backend URLs is removed.
2. Exa/Tavily status/test and Kumo endpoints existed in Python but the Flutter API route allowlist did not consistently route them to AI-TRADING. Kumo had no Flutter client methods or AI Access status display.
3. `/v1/ai/kumo/status` checks hosted `/models`: reachability/auth only, not successful prediction. `/v1/ai/kumo/predict` requires the full Universal TFM envelope (`model`, `task`, `schema`, `context`, `predict`, `output`) and target-labeled context rows. The repo does not yet define a validated historical target/features pipeline to safely feed Kumo into live quant signals. Do not guess target labels or promote its output to a trade.
4. Chat and signal review use NVIDIA hosted chat completions with OpenRouter fallback. Kumo Tabular is a separate structured-prediction model, not a general chat replacement. The configured NVIDIA key must be entitled for the selected chat model; a Kumo-only key may work for Kumo but fail chat inference.
5. Periodic refresh and Flow Monitor can create concurrent reads. Cached signal reads are usually fast in the captured window, but option-chain reads remain multi-second and WebSocket clients sometimes close early. Stage timings and load checks are needed before claiming end-to-end low latency.
6. Strategy suite traces explicitly report `ai_consumed=false`, `research_engine_received=false`, and `trading_setup_received=false`. AI chat may receive a strategy summary in prompt context, but that does not prove semantic use or downstream propagation.
7. AI provider status reused cached probe results whenever the key remained merely configured. Rotating one non-empty key to another could leave a stale green result. The audit branch now fingerprints key/model/endpoint configuration without exposing secrets and invalidates cached results when those values change.

### Changes in branch `audit/ai-dataflow-kumo-wiring`
- Route AI chat/status/provider-test/search-test/Kumo endpoints through the AI-TRADING signal backend.
- Add Flutter API methods for Kumo status and prediction; the prediction method accepts a caller-provided schema-complete envelope and does not fabricate training labels.
- Add Kumo reachability visibility to AI Access and label it as reachability-only, not inference-ready.
- Add API URI regression tests for unified AI/search/Kumo routing.
- Invalidate cached NVIDIA/OpenRouter probe status after key/model/endpoint changes and cover key rotation with a backend regression test.

### Verification gates before declaring fully working
- CI: Python tests, Flutter analyze, widget/API URI tests, release and ARM64 APK jobs all green on the audit branch.
- Runtime: authenticated device request to `/v1/ai/kumo/status`; one representative Kumo prediction using validated target/schema; real NVIDIA chat probe and OpenRouter fallback test.
- Market data: Angel One authenticated session, fresh exchange timestamps, option quotes/Greeks, WebSocket tick age and option-chain freshness during NSE sessions.
- Flow: measure /v1/signals and /v1/option-chain p50/p95/p99, WebSocket reconnects, client 499 frequency and concurrency behavior after route changes.
- Safety: deterministic WAIT remains authoritative unless required data/quant/risk checks pass; AI/Kumo must never promote blocked signals or submit broker orders.


## Follow-up: Strategy Engine is now a mandatory live Quant gate

The live /v1/signals path now passes each index's completed 5-minute Angel One candle strategy-suite consensus into a backend confluence filter before returning the shared response to the Flutter pages.

- A Quant candidate of CALL BUY requires strategy-suite LONG with at least three LONG votes and more LONG than SHORT votes.
- A Quant candidate of PUT BUY requires strategy-suite SHORT with at least three SHORT votes and more SHORT than LONG votes.
- Missing, weak, or conflicting strategy consensus forces the final decision to WAIT; the actionable strike, expiry, entry, stop-loss and target are cleared. The original proposal is retained separately as candidate_setup with BLOCKED_NOT_ACTIONABLE status for diagnostics only.
- The shared response exposes strategy_filter; the strategy execution trace now records that Research/Trading Setup consumed the strategy result. The independent /v1/strategies/evaluate endpoint remains research-only.
- Added regression tests for matching, conflicting, weak-consensus and no-Quant-candidate cases.

This does not claim NVIDIA chat or Kumo Tabular prediction is a verified live-signal input. Kumo still needs a validated feature/target schema and successful prediction evidence before it can be made a mandatory model gate. Deterministic data-quality, Quant, strategy-confluence and risk checks remain authoritative; no broker orders are placed.


## Additional fail-closed corrections

- Strategy votes are computed only from 5-minute bars whose timestamp plus five minutes is no later than the current UTC time; the in-progress bar is excluded from indicators/strategy votes.
- A strategy consensus cannot mark the gate PASS unless the original Five-Layer Quant decision and live-validation verdict are both still PASS for the same candidate.
- When Quant/live-data validation blocks a candidate, the response records BLOCKED_BY_QUANT_VALIDATION rather than reporting a misleading strategy mismatch/pass.
- WAIT and stale-refresh responses clear actionable strike, expiry, entry, exit, stop-loss, target and option-side fields, and set the shared trade plan grade to WAIT. The stale snapshot remains detached from the cache.
- Regression tests cover stale snapshot clearing, incomplete-candle exclusion, conflicting/weak strategy votes, and prevention of Quant-validation bypass.
