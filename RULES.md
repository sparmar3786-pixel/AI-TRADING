# AI-TRADING — Engineering Rules

## Safety first
1. Signal-only app: never implement live broker order placement without a separately approved product change.
2. Fail closed. Missing, stale, contradictory, cached-only or malformed inputs produce WAIT/BLOCK, never PASS.
3. Never invent fallback prices, strikes, expiries, validation layers, timestamps or broker-live status.
4. AI is non-authoritative. It cannot override deterministic quant/risk checks or generate unsupported trade levels.
5. Do not put Angel One credentials, NVIDIA/OpenRouter/Exa/Tavily secrets, or other API keys in source-controlled client code or APK assets.
6. Do not log secrets, auth tokens, TOTP/MPIN values or sensitive account details.
7. Do not add removed UI: AI Chat, PDF Report, repository/library links, local GGUF/Qwen/DeepSeek controls, SMC chart, MCX/commodities screens or Order Flow/Footprint chart.

## Signal and data rules
- Use a canonical signal response; avoid separate screens computing conflicting signal truth.
- Treat HTTP success as transport success only. Validate payload, source, timestamp, freshness and broker/feed state independently.
- Invalidate old trade fields immediately when a signal becomes WAIT/BLOCK.
- Keep the 600-second same-side-and-strike confirmation gate; reset on side/strike change, failed validation, or a refresh gap greater than 60 seconds.
- Never treat cache/fallback as verified live data.
- Strategy existence in a folder is not evidence of live integration. Verify the complete path from market input through engine, risk gate, API and UI.
- Handle provider rate limits, timeouts, schema errors and empty results explicitly.
- Keep all risk calculations deterministic and testable.

## Code quality
- Inspect existing conventions and tests before editing.
- Prefer small, reviewable changes; do not rewrite unrelated modules.
- Add regression tests for every bug fix and negative-path/fail-closed behavior.
- Avoid hard-coded PASS statuses, fake health flags, silent defaults and success-shaped mock data in production paths.
- Keep API schemas typed and validate external payloads at boundaries.
- Preserve unrelated user changes. Never force-push or merge a PR without explicit instruction.
- No APK build/artifact unless the user explicitly asks for one.

## Completion reporting
Report what changed, exact branch/commit/PR, tests actually run and their results. Separate verified facts from assumptions and remaining work. Never claim deployment, live-feed health or provider success without evidence.
