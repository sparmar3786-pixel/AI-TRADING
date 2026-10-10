# Upstream Import Progress

Last verified: 2026-10-11

This file distinguishes source files actually committed from projects that are only inventoried. Vendored code is not automatically integrated into the main application.

## Current verified vendor file counts
- `vendor/TradingAgents/`: 210 files
- `vendor/backtesting.py/`: 46 files
- `vendor/FinGPT/`: 56 files
- `vendor/qlib/`: 19 files
- `vendor/financial-agent/`: 15 files

These are destination file counts, not proof that every upstream file was imported.

## Imports

### TauricResearch/TradingAgents
- Upstream license: Apache-2.0.
- Upstream branch: main.
- Source package, CLI/runtime files, project metadata and test files were imported into `vendor/TradingAgents/`.
- A previous tree comparison found the 208 files under the upstream tree covered; destination currently has 210 files. This import has not been installed or tested as part of the host application.

### kernc/backtesting.py
- Upstream license: AGPL-3.0.
- Upstream branch: master.
- 46 files imported into `vendor/backtesting.py/`.
- Includes the main backtesting engine, library helpers, tests, sample CSVs, Python examples, setup metadata, and license.
- Some upstream docs/notebooks/assets are not copied. AGPL-3.0 creates significant distribution/compliance obligations; review before distributing or integrating it into the main application.

### AI4Finance-Foundation/FinGPT
- Upstream license: MIT.
- 56 destination files imported into `vendor/FinGPT/`, covering selected benchmark and Forex-intelligence modules/configuration.
- This is a partial import, not the entire FinGPT repository. Notebooks, data/model artifacts and other source files remain.
- Some files could not be imported through the available GitHub tool; credential-bearing examples and secrets must not be copied.

### microsoft/qlib
- Upstream license: MIT.
- 19 destination files imported into `vendor/qlib/`, including selected backtest, config, dataset, evaluation and model modules.
- This is a partial import; Qlib's full package tree, dependencies and data are not imported or wired into the application.

### schen9999/financial-agent
- 15 destination files imported into `vendor/financial-agent/`, including the license, README, agent core/graph/grounding modules, tools, tracing and API entry point.
- This is a partial import; the complete upstream repository and dependency setup have not been imported or tested.

## Still incomplete
- Other repositories in `UPSTREAM_REPOSITORIES.md` still need individual access, default-branch and license checks and source imports.
- FinRobot, other listed trading/backtesting/broker/risk/UI/deployment projects have not been fully imported.
- Angel One API, Railway backend, NSE MCP, live market data, and the app's frontend are not confirmed integrated by these vendor imports.
- Python tests and integration tests have not been run as part of this import work.

## Important
Upstream source is retained in separate vendor folders to avoid overwriting the project's own code. Dependencies, environment variables, license obligations, security, API routes, data providers and execution behavior must be reviewed before enabling copied code. No claim is made that the application is production-ready or connected to live brokerage APIs.
