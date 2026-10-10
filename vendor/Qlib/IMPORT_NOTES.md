# Microsoft Qlib vendor import notes

- Upstream: https://github.com/microsoft/qlib
- Branch: `main`
- License: MIT; upstream license retained at `vendor/Qlib/LICENSE`.
- Source fetched on 2026-10-10/11.
- Imported selected backtesting account/decision/exchange/executor/report/signal modules, base/rule/signal strategies, order generation and cost control, portfolio evaluation, and risk/return/IC report modules.
- This is a partial import, not the complete Qlib platform. The files depend on many Qlib modules and external packages that are not all included here.
- No tests or live data validation have been run for this vendored subset.
