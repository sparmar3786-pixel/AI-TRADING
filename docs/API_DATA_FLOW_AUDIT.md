# AI-TRADING API / Data Flow Audit — 13 Oct 2026

## Evidence
- Railway ai-trading-signals-api logs show /v1/signals requests lasting about 19–73 seconds.
- Multiple requests ended in HTTP 499 because the client closed the request before a response arrived.
- Latest six-hour metrics observed: 2,741 requests, 2,665 2xx, 37 4xx, 39 5xx; 5xx rate 1.42%.
- /health, /v1/angel/status, and /v1/system/diagnostics frequently returned 200; route reachability does not prove fresh market data.

## Confirmed code-path issues
1. flutter_app/lib/main.dart: refresh() sets signalsEndpointOnline=false on signal request errors; _appBarStatus then renders API UP • DATA ERROR.
2. flutter_app/lib/api.dart: normal GET timeout defaults to 30 seconds.
3. backend/app/main.py: _get_signals() checks the shared cache under _lock but releases the lock before building. Concurrent cache misses can run expensive six-index broker collection simultaneously. WebSocket /ws calls _get_signals(False) every five seconds.
4. _index_snapshot() performs spot quote, historical candles, option quote batch, Greeks and selected-option ATR work per index; six indices plus commodity snapshots create a heavy sequential refresh.
5. /ws sends sampled OHLC snapshots and aggregate top-five bid/ask depth only. It does not send the lv price-level map or step required by the uploaded HTML footprint chart.
6. Prior flutter_app/lib/order_flow_page.dart rendered simple OHLC candles and had no timeframe dropdown, POC/imbalance cells or HTML chart controls.
7. Backend AI diagnostics state that configured OpenAI/OpenRouter credentials do not mean a provider test succeeded; authenticated inference must be implemented and verified before ok=true.

## Page communication contract
Angel One REST/WebSocket → exchange-timestamped market snapshot → shared market[index] and option-chain cache → indicators/OI → five-layer quant engine → risk/strategy gates → provider evidence validation → notifications and screens.

- Dashboard / Market / Indicators: shared market snapshot, quote age, source timestamp and indicators.
- Option Chain / OI Lab: shared per-index option-chain cache with source timestamps.
- Signals / Risk / Trading Setup / Five Layer / Quant Engine Lab / Strategy Library: same signal object, validation verdict, guards and engine layers.
- Order Flow: fresh broker snapshot stream; footprint cells require actual price-level depth.
- Data Health: health, signal route status, Angel session, tick age, provider status and measured request/engine latency must remain separate.
- Notifications: timestamp, index, failing stage, latency, provider/model, validation verdict and safe error summary; never include API keys/tokens.

## Required fix order
1. Add single-flight protection for signal cache misses; re-check cache after acquiring the build lock so multiple clients share one refresh.
2. Instrument stage durations (market snapshot, option quotes, Greeks, ATR, commodities, total build) and expose them in diagnostics.
3. Reduce duplicate polling and have WebSocket consumers use the shared cached snapshot; verify no repeated 499s under concurrent app + WS clients.
4. Implement actual OpenAI and OpenRouter authenticated inference/test calls server-side; show output, model, latency and validation verdict only after a real response.
5. Add real price-level bid/ask depth to /ws from broker data before rendering Sell × Buy / POC / imbalance. If depth is absent, show an explicit unavailable state rather than fabricated cells.
6. Remove repository/reference cards from operational tabs; retain only app workflows and optionally a single dedicated reference library.
7. Verify Flutter analysis/tests, Python tests, CI APK artifact, and live Angel One timestamps separately.

## Footprint design requirements from supplied index(1).html
Preserve symbol selector; timeframes 1m, 3m, 5m, 15m, 30m, 1h; zoom; live control; manual; price axis; Sell × Buy ladder; green/red volume cells; POC outline; 3x imbalance; delta, volume, Buy ord and Sell ord; pan/drag and last-price line. Demo mode must not be used.

## Verification limits
This is an evidence-based audit, not a claim that all tabs are now end-to-end verified. A green /health, successful APK build, or configured AI key does not prove fresh Angel One ticks or successful AI inference. Live order placement remains disabled while validation is incomplete.
