# Upstream import continuation — 2026-10-12

This directory is a **curated source snapshot** of TradingGoose/TradingGoose.github.io, copied under `vendor/TradingGoose/` to avoid overwriting AI-TRADING's active application code.

## Included in this batch
- Upstream `LICENSE`, `README.md`, `package.json`, TypeScript/Vite configuration and app shell
- Trading/portfolio UI components, history and performance views
- Alpaca client/connection helper and market/ticker/time helpers
- Agent functions for bull/bear/market/fundamentals/news/macro/research/risk/trader roles
- Shared market-data, indicator, order, portfolio, status and validation helpers
- Rebalance and schedule-rebalance UI/workflow files

## Safety and compatibility notes
- These are vendored reference files only; they are **not wired into the active AI-TRADING runtime**.
- The upstream project is primarily a TypeScript/React + Supabase application and targets Alpaca-oriented workflows; it is not a drop-in Angel One/NSE integration.
- Do not copy or commit secrets. Upstream `.env.example` and deployment credentials are intentionally not included.
- Some upstream paths were skipped after the GitHub write API returned conflicts/validation errors or safety blocks; this is not a complete clone of that upstream repository.
- No tests or Railway deployment verification were run for this source snapshot.
- Check upstream license and dependencies before reusing any file in production.
