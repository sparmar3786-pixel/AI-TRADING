# AI-TRADING — Design System

## Visual direction
- Dark navy base with restrained teal accents, clear contrast and compact trading-terminal information density.
- Prioritize readability on Android phones; use consistent spacing, alignment and accessible touch targets.
- Keep screens focused on signal status, data freshness, risk and strategy state rather than decorative AI branding.

## Information hierarchy
1. Current data/feed status and last verified tick.
2. Signal state: WAIT / BLOCK / candidate / actionable only after every gate passes.
3. Instrument, side, strike and expiry.
4. Entry, stop-loss, target and risk/reward only when validated.
5. Quant/strategy evidence, validation failures and plain-language reasons.
6. Diagnostics and secondary market context.

## State presentation
- WAIT/BLOCK must be visually clear and must never resemble a valid BUY signal.
- Show why a signal is unavailable (stale tick, disconnected broker, cached data, validation failure, stability timer).
- Distinguish API reachable, broker authenticated, feed connected and fresh ticks; never collapse them into one green status.
- Display timestamps and data freshness near market-derived values.
- Do not leave stale trade values visible after invalidation.

## Navigation and scope
- A dedicated Strategies tab should list only strategies actually available in the app, with explicit status such as Ready, Waiting for data, Disabled or Not verified.
- Keep AI Chat, PDF Report, repository/library links and local-model setup/testing UI out of the APK.
- Keep SMC chart, MCX/commodities and Order Flow/Footprint out of this APK; they belong in a separate app.
- Avoid duplicate strategy controls and inconsistent signal panels.

## UI acceptance checks
- Test narrow Android screens, loading, empty, offline, stale, rate-limited and error states.
- Check text contrast and touch targets.
- Verify the displayed state against the actual API payload, not mocked defaults.
