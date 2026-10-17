# Live Signal Integration Acceptance Contract

Date: 2026-10-17
Repository: AI-TRADING

## Safety invariant
A strategy module returning a candidate is not an actionable signal. Until the active Railway service proves fresh source data, complete Quant evidence, option-contract mapping, risk geometry, and a server-owned 600-second stability gate, the canonical decision must remain WAIT/BLOCK. Missing, stale, future-dated, conflicting, malformed, or fallback evidence must never be promoted to PASS.

## Strategy-by-strategy acceptance

| Strategy | Required input evidence | Reject / WAIT conditions |
|---|---|---|
| OI Price Action | Timestamped option-chain OI/PCR, underlying LTP, completed candles, source timestamps | Missing/stale OI or LTP; incomplete candles; no valid option contract |
| Hero Zero | Verified expiry date/session, underlying spot, near-OTM contract identity, fresh bid/ask/premium, liquidity | Not expiry session; expiry unresolved; stale quote; invalid/illiquid strike; invalid stop/target |
| PDH/PDL / Failed-Move | Previous completed session high/low, timestamped price sequence, sweep and reclaim/failure evidence | Missing prior-session levels; unconfirmed reclaim; stale/out-of-session data |
| EMA Crossover | Completed candles, fast/slow EMA values and crossover timestamps, ATR | Still-forming/duplicate/out-of-order candles; no crossover; missing ATR |
| DAY-HL Liquidity Sweep | Prior-day high/low and timestamped sweep/rejection evidence | Levels unavailable; sweep not confirmed. Detector-only until a separate planner maps entry/risk |
| ORB baseline | IST opening-range candles, completed-candle breakout, volume confirmation where required, ATR | Range incomplete; stale/incomplete candles; invalid risk geometry |
| VWAP baseline | Session-reset cumulative VWAP, completed-candle cross, volume and ATR evidence | Invalid session reset; missing/stale volume or candles; invalid risk geometry |

## Canonical /v1/signals response contract
- Final decision must be explicitly WAIT, BLOCK, or a validated actionable decision. Candidate fields must never overwrite the final decision.
- Data freshness must include per-source timestamp, age, provider and server-computed freshness. Reject future timestamps and stale thresholds.
- Quant must expose exactly five named layers, each with explicit status/verdict, reason/blockers, input timestamps and evidence provenance. Missing, malformed or unknown layers block; they never default to PASS.
- Strategy candidates must include strategy ID, candidate decision, reason, source timestamps and candidate key. A candidate is not an approved trade.
- Option contract must include exchange, symbol/token, expiry, strike, CALL/PUT, bid, ask, premium, quote timestamp and liquidity/spread checks. No valid contract means WAIT.
- Risk must use option-premium entry/SL/target with validated positive geometry. Never label underlying spot levels as option premium.
- Stability evidence must be server-owned and include candidate key, first/last seen, elapsed seconds, required 600 seconds, refresh-gap status and reset reason.

## Stability gate rules
1. Start/restart only after the complete candidate key (strategy + instrument + strike + side) and prerequisite validation pass.
2. Require 600 continuous seconds of the same candidate.
3. Reset if candidate/strike/side changes, any validation fails, timestamp is stale/future, or refresh gap exceeds 60 seconds.
4. Persist state on the server; browser localStorage or APK memory is not authoritative.
5. Missing gate payload, elapsed time without server evidence, or state lost on restart remains WAIT/BLOCK.

## Regression tests required before release
- Every strategy: valid input produces candidate only; missing/stale/future input yields WAIT.
- Quant: each layer independently missing, stale, malformed or conflicting blocks final decision.
- Option mapping: missing contract, wrong expiry, invalid strike/side, stale bid/ask, crossed spread, zero liquidity and bad risk geometry block.
- Stability: 599 seconds blocks; 600 seconds can pass only with continuous valid evidence; candidate change resets; validation failure resets; refresh gap over 60 seconds resets; server restart persistence is tested.
- Dashboard, Signals, Risk, Strategies and Quant Engine show the same canonical decision and blocker reasons; no screen upgrades a candidate locally.
- 5xx, timeout, invalid JSON, empty payload and fallback/cache data cannot appear live/confirmed.

## Evidence required to mark production-ready
- CI results for the active backend repository and Flutter/API regression suite.
- Exact deployed commit SHA and successful Railway deployment for the actual signal service.
- Sanitized live /v1/signals payload demonstrating source ages, all five layer results, option mapping, risk and server-owned gate.
- Market-open end-to-end observations covering refresh continuity and resets.
- APK build only after these gates pass and the user requests a release.

## Current status
This file is a verification/acceptance specification, not evidence that live integration is complete. Repository source presence, a green /health, HTTP 200 or a successful build alone does not certify live signal correctness. Do not claim BUY/SELL-ready or profitability without the evidence above.
