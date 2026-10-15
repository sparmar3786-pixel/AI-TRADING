# EMA Quant Strategy

`quant/ema_quant_engine.py` adds the supplied EMA crossover concept as a deterministic, fail-closed research engine. It uses Wilder-smoothed ATR, RSI filtering, half-up ATM strike rounding, forming-bar exclusion, opening-window skip, volume confirmation, and ATR-capped stop risk.

## Safety / integration notes
- Requires a timezone-aware or otherwise valid `DatetimeIndex` and OHLC columns. The newest row is treated as forming and dropped.
- When volume filtering is enabled, missing/insufficient volume data returns WAIT instead of silently passing.
- A signal is only a **candidate**. `to_signal_data` keeps `decision=WAIT`; the existing downstream freshness/risk/10-minute confirmation gate must explicitly promote it.
- This is source integration only. It is not wired into a live API or active UI signal route in this PR, and has not been deployed to Railway. Do not use this module alone for live orders.
## Tests
The GitHub Actions Python workflow installs pandas/numpy and discovers regression tests in `.github/scripts`. Run locally with:
`python -m unittest .github.scripts.test_ema_quant_engine -v` (or copy the test into that directory and use discovery).
