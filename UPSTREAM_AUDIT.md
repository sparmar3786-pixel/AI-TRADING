# Upstream review log

Destination: https://github.com/sparmar3786-pixel/AI-TRADING

## Review performed on 2026-10-10

| Repository | Read/access check | Notes | Source files copied into this repo |
|---|---|---|---|
| `TauricResearch/TradingAgents` | Public root listing readable | Apache-2.0 LICENSE present; Python project; needs dependency and integration review | No |
| `schen9999/financial-agent` | Public root listing readable | LICENSE present; includes API, agent, Docker and test code; needs dependency/security review | No |
| `microsoft/qlib` | Public root listing readable | LICENSE present; large quant research framework; not a drop-in module | No |
| `kernc/backtesting.py` | Public root listing readable | License file present; large library; needs license text review before copying | No |
| `angel-one/smartapi-python` | Public root listing readable | No root LICENSE file appeared in the directory listing checked; do not vendor code until its license/permission is confirmed | No |
| `AI4Finance-Foundation/FinGPT` | Initial `main` ref request returned 404 | This only means that ref name was not found; repository access and default branch must be checked separately | No |
| `AI4Finance-Foundation/FinRobot` | Initial `main` ref request returned 404 | This only means that ref name was not found; repository access and default branch must be checked separately | No |

## Current result

The inventory file was committed in commit `dcdede471e36522f2d8524247d52d7f8a617ef46`. This commit records source URLs only; it does **not** contain copied upstream application code.

I will only mark a repository as copied after its actual source files and required license notices have been committed. Private/inaccessible sources, repositories with unclear permissions, and code that cannot be safely integrated will be listed as blocked rather than represented as copied.
