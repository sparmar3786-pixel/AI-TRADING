# Indian Market MCP deployment notes

## Upstream evaluated

- Project: https://github.com/afthabvp/indian-market-mcp
- Package: `indian-market-mcp`
- Declared license: MIT; retain its copyright/license notice when redistributing source.
- This repository's app integration is limited to supported NSE/BSE index and F&O research flows. Do not expose commodity/MCX tools through AI-TRADING UI; upstream package capabilities are not a guarantee of availability.
- Upstream README describes cache TTLs of 60 seconds for quotes, 120 seconds for option chains/gainers/losers, 300 seconds for indices/ETFs/FII-DII and longer for historical/fund data. These are cache settings, not proof that upstream data itself is current.
- Public NSE endpoints may rate-limit or change; data may be delayed, missing, or unavailable. The client must show source and fetch time and must not treat cached public data as an execution-grade feed.

## Recommended Railway separation

Deploy this MCP as a separate Railway service from the AI-TRADING API, using the upstream GitHub repository as the service source. Set `MCP_TRANSPORT=http`, `MCP_HOST=0.0.0.0`, and let Railway provide `PORT` if the service supports it; verify the actual listening port and `/mcp` health after deploy.

**Do not set Angel One credentials on this combined MCP service by default.** Upstream broker mode advertises live order placement and cancellation tools when Angel credentials are configured. Keep the combined MCP for market research, and use the repository's `integrations.angelone_readonly.AngelOneReadOnly` adapter for a separate, read-only SmartAPI path until broker permissions and an explicit order-approval workflow are implemented.

## Angel One server-side variables

Configure only on the trusted backend/Railway service that runs the read-only adapter:

- `ANGEL_API_KEY`
- `ANGEL_CLIENT_CODE`
- `ANGEL_PIN`
- `ANGEL_TOTP_SECRET`

Never put these values in APK assets, frontend environment variables, logs, GitHub commits, or public MCP configuration. The adapter needs `smartapi-python` and `pyotp` installed in that backend environment.

## Compatibility and validation checklist

1. Check upstream `pyproject.toml`, Python requirement (currently declared `>=3.10`), dependency extras and license before each upgrade.
2. Pin a tested release/commit before production deployment; avoid floating dependencies for a live service.
3. Validate actual option-chain schema, symbol/token mapping, exchange timestamp availability and API throttling against the chosen source.
4. Add an explicit maximum-age policy in the consuming API; if timestamps are absent or too old, return `UNKNOWN` / `WAIT`, not a trade signal.
5. Run unit tests and a non-trading read-only smoke test. Do not test order placement as part of deployment verification.
6. Verify Railway deployment, public URL, logs, health and environment variables separately; a GitHub commit does not prove a Railway deployment succeeded.

## Current scope

This repository adds a read-only SmartAPI wrapper and integration notes only. It does not install the upstream MCP package into the app runtime, does not expose a public API route by itself, does not submit orders, and does not change Railway services or secrets.
