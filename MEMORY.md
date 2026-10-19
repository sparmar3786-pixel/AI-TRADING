# AI-TRADING — Project Memory

Last updated: 2026-10-19

## Repository and target
- Repository: https://github.com/sparmar3786-pixel/AI-TRADING
- Base branch used for this documentation change: `main`
- This branch documents the product and verification plan; it does not itself modify app behavior or prove tests pass.

## Current product direction
- Signal-only Android app; no live order placement.
- User wants reliable live signal data and explicit WAIT when data/validation is incomplete.
- Canonical shared signal flow is intended to power dashboard, signal, strategy, setup and risk views.
- 600-second stable same-side-and-strike gate; reset on candidate change, validation failure or refresh gap greater than 60 seconds.
- Dedicated Strategies tab requested for OI Price Action, Hero Zero, PDH/PDL, EMA Crossover, DPY/HL Liquidity Sweep, plus ORB and VWAP where genuinely available.
- User has reported ORB and VWAP as working; independently verify before relying on that status.
- User has emphasized that strategy code being present is not the same as complete end-to-end APK integration.

## Explicit exclusions for this APK
- AI Chat and PDF Report pages.
- Repository/library/reference links.
- Local GGUF/Qwen/DeepSeek model UI and model-picker/testing screens.
- SMC chart, MCX/commodities screens and Order Flow/Footprint chart; these are intended for a separate APK.
- No APK build or artifact unless explicitly requested.

## AI/provider direction
- Current intended backend-only providers: NVIDIA and OpenRouter, with Exa/Tavily for research/search where implemented.
- Do not restore Gemini as a provider without an explicit product decision.
- NVIDIA/Kumo readiness and provider success must be proven with validated request/response tests; a 200 response alone is insufficient.
- Provider output is advisory and must never override deterministic quant/risk gates.

## Known concerns from prior user reports — recheck against current code
- Angel One authentication/feed freshness has previously displayed unauthenticated or waiting-for-data states.
- OI Lab has previously returned access-rate-limit errors.
- Some CI/build attempts have failed; do not claim current green status without checking the actual run.
- Backend test coverage/status has previously been unclear or skipped.
- UI removals were previously reported as incomplete, so verify actual navigation/routes/screens rather than trusting a commit title.

## Working protocol
1. Inspect source before making implementation claims.
2. Make small changes with regression tests.
3. Keep secrets server-side and fail closed.
4. Report exact evidence and unresolved work.
5. Do not trigger APK artifacts unless explicitly asked.
