# Vendored upstream code status

## TradingAgents
- Upstream: https://github.com/TauricResearch/TradingAgents
- License: Apache-2.0; the upstream LICENSE is retained at `vendor/TradingAgents/LICENSE`.
- Source snapshot branch: `main`; fetched 2026-10-10.
- Imported all 83 Python/package source files under upstream `tradingagents/` (verified against the upstream recursive Git tree), plus the upstream README, package metadata, requirements file, license, and logo asset.
- Upstream README is retained as both `README.md` (needed by package metadata) and `UPSTREAM_README.md`.
- Source files are preserved under `vendor/TradingAgents/tradingagents/`; they are vendored separately and have not been wired into the main app runtime.
- This is not a full clone of every upstream repository item: upstream CLI, tests, workflows, docs and other non-package assets have not all been imported.
- No claim that the vendored package currently runs end-to-end. Dependencies, API keys, market-data access, configuration and integration tests have not been validated here.

## Next
Other repositories from `UPSTREAM_REPOSITORIES.md` still need their own file-level import pass. Check license, security, dependencies and compatibility before each import. Do not copy broker secrets or enable live order execution merely by vendoring source.
