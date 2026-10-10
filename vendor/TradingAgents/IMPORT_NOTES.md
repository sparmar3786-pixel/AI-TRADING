# Vendored upstream code status

## TradingAgents
- Upstream: https://github.com/TauricResearch/TradingAgents
- License: Apache-2.0; the upstream LICENSE is retained at `vendor/TradingAgents/LICENSE`.
- Source snapshot branch: `main` (files fetched on 2026-10-10).
- Imported files include the upstream package initializers, agent state/schemas/tools/context, analyst agents, researcher agents, portfolio/research managers, trader, risk debaters, graph orchestration, Yahoo market/ohlcv dataflow files, config and packaging metadata.
- Upstream README is preserved as `vendor/TradingAgents/UPSTREAM_README.md`.
- This is a **partial vendor import**, not a complete clone of the upstream repository. Some imported modules depend on upstream files not yet imported and third-party packages listed in `vendor/TradingAgents/requirements.txt`.
- No claim that the vendored package currently runs end-to-end. Tests have not been run.

## Still pending
Other repositories from `UPSTREAM_REPOSITORIES.md` have not yet had their source trees imported. Each project must be checked for its license, branch, dependencies and compatibility before copying.