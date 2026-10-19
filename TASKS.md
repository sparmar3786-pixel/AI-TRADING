# AI-TRADING — Task Board

Use checkboxes only after verifying the work in the current repository/branch. Do not mark a task complete from an earlier chat or an HTTP 200 alone.

## P0 — Signal correctness and safety
- [ ] Trace the canonical `/v1/signals` contract from backend route to every UI consumer.
- [ ] Verify live-tick freshness and broker-authentication checks independently from generic health status.
- [ ] Verify stale/cached/fallback data forces WAIT and clears strike, entry, stop-loss, target and expiry.
- [ ] Test the 600-second same-side-and-strike stability gate, including side/strike changes, failed validation and refresh gaps greater than 60 seconds.
- [ ] Confirm quant/risk validation cannot be bypassed by strategy consensus or AI responses.
- [ ] Audit client bundles/APK source for broker credentials and provider secrets.

## P1 — Strategy end-to-end integration
- [ ] OI Price Action: verify option-chain/OI snapshot input, pressure/bias calculation, engine output, normalized signal mapping, API response and Strategies UI.
- [ ] Hero Zero: verify expiry-day/time/near-OTM assumptions, risk limits, input validation and end-to-end UI/API path.
- [ ] PDH/PDL Liquidity: verify sweep/reclaim logic, market-session timezone handling and output mapping.
- [ ] EMA Crossover: locate implementation and verify tests; if absent, record as not implemented rather than showing a fake card.
- [ ] DPY/HL Liquidity Sweep: locate implementation and verify inputs, reset conditions and output mapping.
- [ ] ORB and VWAP: verify reported working status with actual tests and live integration evidence.
- [ ] Add per-strategy positive, negative, stale-data and missing-input tests.

## P1 — App scope and UX
- [ ] Confirm AI Chat and PDF Report are absent from navigation and reachable routes.
- [ ] Confirm repository/library links and local GGUF/Qwen/DeepSeek UI are fully absent.
- [ ] Confirm SMC chart, MCX/commodities and Order Flow/Footprint are absent from this APK.
- [ ] Add/verify a dedicated Strategies tab using real engine/API status, not hard-coded readiness.
- [ ] Ensure dashboard, signals, setup and risk screens display the same canonical signal.

## P2 — Provider reliability (backend only)
- [ ] Verify NVIDIA chat endpoint request/response schema and error handling.
- [ ] Verify Kumo Tabular endpoint/schema separately; do not use it for signal decisions until inference and target schema are validated.
- [ ] Verify OpenRouter server-side configuration and a real smoke test.
- [ ] Verify Exa/Tavily server-side configuration, response parsing and rate-limit handling.
- [ ] Remove unsupported provider claims and unused integrations without breaking core signal flow.

## P2 — Quality and release
- [ ] Run frontend typecheck and production build.
- [ ] Run backend unit/integration tests (do not silently skip them).
- [ ] Run strategy and signal-contract regression tests.
- [ ] Review CI results and fix failures before requesting merge.
- [ ] Build an APK only after the user explicitly requests it and the checks pass.
