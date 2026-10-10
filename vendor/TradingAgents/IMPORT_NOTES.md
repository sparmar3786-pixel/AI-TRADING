# Vendored upstream code status

## TradingAgents
- Upstream: https://github.com/TauricResearch/TradingAgents
- License: Apache-2.0; the upstream LICENSE is retained at `vendor/TradingAgents/LICENSE`.
- Source snapshot branch: `main`; fetched 2026-10-10.
- All 208 upstream tracked files from the recursive Git tree have been imported under `vendor/TradingAgents/` and checked against the upstream tree, including 83 package files under `tradingagents/`, CLI source, tests, workflow/configuration templates, documentation, packaging metadata and image assets.
- The upstream README is retained as `README.md` (needed by package metadata) and `UPSTREAM_README.md`.
- The vendored project remains isolated under `vendor/TradingAgents/`; it has not been wired into the main app runtime.
- Import completeness does not mean the package is runnable or production-ready. Dependencies, API keys, market-data access, configuration, and tests have not been validated in this environment.

## Next
Other repositories from `UPSTREAM_REPOSITORIES.md` still need their own file-level import pass. Check license, security, dependencies and compatibility before each import. Do not copy broker secrets or enable live order execution merely by vendoring source.
