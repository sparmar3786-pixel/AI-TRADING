# AI-TRADING — Product Requirements

## Product purpose
Build a reliable Android trading-signal terminal for Indian index/options markets. The app is **signal-only**: it must not place live broker orders. Users may execute separately through their own broker/demat workflow.

## Primary users and outcome
Users need a clear, timely, explainable CALL BUY / PUT BUY / WAIT signal, including instrument/strike, entry, stop-loss, target, expiry and risk context only when those fields are valid and supported by fresh data.

## Scope
- NSE index/options workflows, especially NIFTY and BANKNIFTY; support other indices only where backend/data coverage is verified.
- One canonical backend signal contract consumed consistently by dashboard, signal, strategy, setup and risk views.
- Strategy tab exposing engines that are actually wired end-to-end: OI Price Action, Hero Zero, PDH/PDL Liquidity, EMA Crossover, DPY/HL Liquidity Sweep, ORB and VWAP where present and verified.
- Option-chain/market context and risk views where supported by verified data.
- Live-data/backend diagnostics that distinguish API reachability from authenticated broker access and fresh market ticks.
- Paper/simulation functionality only where explicitly supported and tested.

## Out of scope
- Live order placement or automatic execution.
- Dedicated SMC chart, MCX/commodities screens, and Order Flow/Footprint chart in this APK; these are intended for a separate APK.
- AI Chat and PDF Report pages; do not reintroduce them into the app UI.
- Repository/library links, local GGUF/Qwen/DeepSeek model UI, or model-picker/testing screens.
- Any feature represented as live/working solely because an HTTP request returned 200.

## Signal safety and acceptance criteria
1. Default to WAIT whenever live data, validation, strategy output, strike, expiry, entry, stop-loss or target is missing, stale, malformed or contradictory.
2. Candidate must pass all required quant/risk/data-quality gates before it can become actionable.
3. Require the exact same option side and strike to remain valid for 600 continuous seconds before an actionable signal is shown.
4. Reset the 600-second timer if side/strike changes, validation fails, or refresh gap exceeds 60 seconds.
5. If feed disconnects or the backend is using cache/fallback rather than verified live data, immediately downgrade to display-only WAIT and zero live broker risk.
6. AI output is advisory only. It cannot independently create a signal, override deterministic quant validation, or set risk levels without validated rules/data.
7. Never expose broker credentials, provider API keys, or secrets in the APK/client.
8. Do not claim a strategy is operational until data input, engine invocation, signal contract, UI rendering and tests are verified end-to-end.

## Success metrics
- Correct fail-closed behavior for missing/stale data.
- Consistent signal values across all screens.
- 600-second stability gate and reset behavior covered by automated tests.
- Strategy-by-strategy integration and test evidence.
- Reproducible frontend/backend checks and a successful production build.
- No APK build/artifact unless explicitly requested.

## Open questions to resolve from code, not assumptions
- Current supported markets and exact live-data freshness threshold.
- Which strategy engines are truly connected end-to-end on main.
- Current backend routes and schema version.
- Whether ORB/VWAP tests cover live integration or only unit behavior.
