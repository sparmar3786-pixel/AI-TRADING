# AI-TRADING — Architecture

## Intended data flow
```text
Angel One SmartAPI / market feed
        |
        v
Backend broker session + live-feed freshness validation
        |
        v
Normalized market snapshots / option-chain data
        |
        v
Deterministic strategy engines
(OI Price Action, Hero Zero, PDH/PDL, EMA, DPY/HL, ORB, VWAP as verified)
        |
        v
Quant confluence + risk + spread/slippage safeguards
        |
        v
600-second side-and-strike stability gate
        |
        v
Canonical signal API (intended shared contract: /v1/signals)
        |
        v
Android UI: Dashboard / Signals / Strategies / Setup / Risk
```

This is the target architecture and must be checked against actual source before asserting every edge is implemented.

## Trust boundaries
- **Android client:** presentation and user interaction. No broker login secrets or provider API keys; no live order placement.
- **Backend:** owns broker authentication, feed ingestion, freshness checks, normalization, strategy orchestration, risk checks and provider credentials.
- **Quant/risk engine:** authoritative for signal eligibility and risk fields.
- **AI providers:** optional advisory/validation layer only. Current intended provider direction is NVIDIA + OpenRouter, with Exa/Tavily for research/search where implemented. Provider availability must never bypass deterministic gates. Do not claim a provider is working without a verified request/response and tests.
- **External broker:** separate user-controlled execution workflow; this app is not an execution bridge.

## Signal contract expectations
A signal response should explicitly identify:
- instrument/underlying and timestamp;
- data source and whether it is truly live versus cached/fallback;
- candidate side and strike, expiry, entry, stop-loss and target when valid;
- quant/risk validation status and reasons;
- stability-gate state and elapsed confirmation time;
- WAIT/block reason when not actionable.

Missing/invalid values must not be filled with plausible defaults. Stale signal fields must be cleared when the candidate is invalidated.

## Operational health
Keep these states distinct:
- API reachable;
- backend worker healthy;
- broker session authenticated;
- live feed connected;
- latest market tick fresh;
- strategy cycle completed;
- signal passed quant/risk validation.

HTTP 200 or a generic health endpoint proves none of the later states by itself.

## Resilience
- Fail closed to WAIT on disconnect, stale ticks, cache fallback, rate limits, malformed responses, incomplete option chain or failed validation.
- Do not silently reuse a stale strike/entry/SL/target/expiry.
- Rate-limit responses should be parsed as an explicit unavailable/stale state, not as valid market data.
- Use backend caching/aggregation where needed, but label cached data and prohibit actionable signals from it.

## Verification required
Inspect actual route definitions, data models, strategy registry, UI consumers, tests and deployment configuration before changing this document to claim implementation. The intended flow above is not proof of current end-to-end wiring.
