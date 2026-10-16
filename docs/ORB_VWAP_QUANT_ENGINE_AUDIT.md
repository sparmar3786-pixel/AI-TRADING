# ORB, VWAP and Five-Layer Quant Engine Audit

Audit date: 2026-10-16  
Repository: AI-TRADING  
Active Railway branch reviewed: `fix/signal-backend-health-status` (commit `47ab9a7f0faad48e7244a0d4c16a9271fcc7fb` at audit start).  
Scope: source, backend signal pipeline and UI wiring. Live Angel One session and production response bodies were not available for this code review.

## ORB and VWAP

- The active backend branch's `backend/app/parmar_api.py` explicitly listed ORB and VWAP as `ENGINE_NOT_IMPLEMENTED`; no standalone first-party engine modules were present on that branch.
- Added `quant/orb_engine.py`: IST opening range, completed-candle breakout, volume confirmation, ATR-bounded underlying stop/target, and stale/future candle rejection.
- Added `quant/vwap_strategy.py`: session-reset VWAP, completed-candle cross, volume confirmation, ATR-based underlying stop/target, and stale/future candle rejection.
- Wired both engines into `backend/app/main.py::_index_snapshot()` using the same completed Angel One 5-minute candles consumed by the canonical signal pipeline. Their results are exposed under `strategy_candidates.orb` and `strategy_candidates.vwap`.
- Added a Strategy Library panel to display each candidate, underlying entry/SL/target, reasons and blockers. A candidate always has `decision=WAIT` and `actionable=false`; the values are underlying spot levels, not option-premium prices.
- Registered the modules in the Parmar strategy inventory. The diagnostic `/v1/parmar/evaluate` endpoint remains fail-closed for caller-supplied snapshots; live candidates come from the trusted `/v1/signals` pipeline instead.

## Five-layer Quant Engine audit

### Findings fixed in this change
- `quant_engine.py` previously stored the independent 600-second confirmation gate inside the same `layers` dictionary as the five validation layers. The API therefore reported six total layers, and the UI could mislabel candidate generation/final validation as quant layers.
- The evaluator now returns exactly five validation layers: data quality, trend/sentiment, order flow, option selection and risk levels. The 600-second confirmation result is a separate `confirmation` object.
- The canonical signal API now emits a normalized `five_layer_engine` / `quant_engine` contract with exactly five named layers, explicit PASS/FAIL status, per-layer evidence text, a source timestamp and a freshness flag. The pass count is out of five and is not a win probability.
- The Trade Engine UI now labels candidate generation and the final validation gate separately from the five quant layers; the stability gate is shown separately and is not counted as layer six.
- The Strategy Library counts only the five normalized validation layers, and shows ORB/VWAP backend candidate status from the shared signal response.

### Remaining risks / production verification
- The 600-second confirmation state is held in process memory (`_confirmation_states`). Restarting the service resets the gate to WAIT, which is fail-closed; multiple Railway replicas would not share confirmation state. For multi-replica production, use a shared Redis/Postgres state with atomic updates.
- The web React page's `getQuantLayers()` is still a hard-coded `UNAVAILABLE` stub. The active Flutter backend path is the one wired to `/v1/signals`; do not treat the separate web stub as a live quant calculation.
- ORB/VWAP candidates are not final trade signals. Their underlying levels still require fresh option-contract resolution, premium-based entry/SL/target calculation, agreement with the five quant layers, all risk checks, and an uninterrupted server-side 600-second same-candidate gate.
- An HTTP 200, a fresh spot quote, or a strategy candidate does not prove that all layers passed. Check response bodies, timestamp provenance, option bid/ask/OI/volume, selected contract, and server confirmation state in live Railway diagnostics.
- No accuracy, win-rate, profitability, APK build, or live broker execution is claimed.

## Tests
- `tests/test_orb_vwap_engines.py`: candidate generation, stop/target ordering, missing-volume rejection, and out-of-window rejection.
- `tests/test_quant_engine.py`: stale data, timestamp normalization, trend/flow/option/risk blockers, 10-minute confirmation and reset behavior, and the separation between five validation layers and the confirmation gate.
