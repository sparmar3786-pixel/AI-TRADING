# Upstream Import Progress

Last updated: 2026-10-11

This file distinguishes source files actually committed from projects that are only inventoried. A vendored project is not automatically integrated into the main application.

## Completed source imports

### TauricResearch/TradingAgents
- Upstream license: Apache-2.0.
- Upstream branch: main.
- Verification: all 208 upstream blob paths were found in `vendor/TradingAgents/` at the time of the last tree comparison.
- Includes its package source, CLI/runtime files, project metadata and test files.
- Not yet installed, integrated with this app, or tested in this repository.

### kernc/backtesting.py
- Upstream license: AGPL-3.0.
- Upstream branch: master.
- 46 of 53 upstream files copied to `vendor/backtesting.py/`.
- Includes the main backtesting engine, library helpers, tests, sample CSVs, Python examples, setup metadata, and `LICENSE.md`.
- Not copied: `README.md` (import tool blocked it), five Jupyter notebooks (their equivalent Python example files were copied), and `doc/logo.png` (binary asset).
- AGPL-3.0 is a significant distribution/compliance consideration; do not merge or distribute the overall application without reviewing obligations.

## Partial source imports

### AI4Finance-Foundation/FinGPT
- Upstream license: MIT.
- Copied selected benchmark, forecasting and Forex-intelligence files into `vendor/FinGPT/`.
- This is a partial import, not the entire FinGPT repository. The upstream repository has hundreds of files and notebook/data/model artifacts; sensitive-looking token examples and credentials must not be copied.
- Some notebook/data download files were intentionally not imported; one data-download file was blocked by the import tool.

### microsoft/qlib
- Upstream license: MIT.
- Copied selected backtest, config, dataset, evaluation and model modules into `vendor/qlib/`.
- This is a partial import; Qlib's full package tree, dependency graph and data are not imported or wired into the application.

## Not yet completed
- Other repositories from `UPSTREAM_REPOSITORIES.md` still need to be reviewed and imported one at a time.
- `financial-agent`, `FinRobot`, and the remaining listed trading, broker, risk, UI and deployment projects have not been fully imported.
- No claim is made that the overall app is production-ready or connected to live brokerage APIs.
- Python tests and integration tests have not been run as part of this import progress.

## Important
Upstream source is retained in separate vendor folders to avoid overwriting the project's own code. Dependencies, environment variables, license obligations, security, API routes, data providers and execution behavior must be reviewed before enabling any copied code.


### schen9999/financial-agent
- Upstream license: MIT.
- Partial source import committed under `vendor/financial-agent/`: core agent/graph/grounding/numeric checks, LLM ledger, news/SEC/stock tools, tracing, API entrypoint, README and LICENSE.
- This is a curated subset of a much larger upstream repository, not a complete import. The upstream `agent/tools/__init__.py` file was blocked by the import tool; remaining tools/dependencies and tests are not imported.
