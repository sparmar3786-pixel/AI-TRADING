# ORB, VWAP and Five-Layer Quant Engine Audit

Audit date: 2026-10-16  
Repository: AI-TRADING  
Scope: repository source and UI wiring only; no broker secrets, Railway credentials, APK runtime, or live order execution were available to this audit.

## Findings

### ORB and VWAP
- The Flutter Strategy Library explicitly marked ORB and VWAP as NOT IMPLEMENTED.
- The existing VWAP references in the repository are indicator/vendor examples; they do not prove a first-party entry/exit strategy is routed into the active signal API.
- Added deterministic, fail-closed research candidate engines:
  - `quant/orb_engine.py`: IST session opening range, completed-candle breakout, optional volume confirmation, ATR-bounded risk levels.
  - `quant/vwap_strategy.py`: session-reset cumulative VWAP, completed-candle cross, volume confirmation and ATR-based risk levels.
- Both emit candidates with `live_validation=PENDING`; they do not authorize trades. The strategy library must continue to say live API wiring is unverified until the external Railway signal service imports/calls these modules and end-to-end tests prove it.

### Five-layer Quant Engine — critical integration gap
- The current main branch tree does not contain the backend evaluator described in the old integration guide (the guide refers to `quant_engine.py` and `backend/app/main.py`, which are absent from the current tracked tree).
- `src/services/api.ts` implements `getQuantLayers()` as five hard-coded `UNAVAILABLE` records. The web Quant Engine page calls this stub, not a backend calculation. This is safe from false PASS but is not a functioning live engine.
- The Flutter Quant Engine page reads `quant_engine` / `five_layer_engine` fields from a signal response, but this repository does not contain the backend implementation that guarantees those fields are computed and supplied. Therefore the UI alone cannot establish that any layer executed.
- The TypeScript 10-minute gate stores confirmation state in browser `localStorage`. That is not server-owned and can be reset by clearing storage/reinstalling. It must not be the authoritative production stability gate.
- A passing HTTP status, non-empty response, or a market row marked live is not evidence that all five quant layers passed. Each layer needs timestamped input provenance, explicit result/reason, and fail-closed semantics.

## Required production integration before any BUY/SELL
1. Add/import the actual five-layer evaluator in the active Railway backend repository.
2. Run it in the same canonical signal pipeline used by dashboard, strategy, risk and signal pages.
3. Require all five layer outputs to be present, schema-valid and fresh; no missing layer may default to PASS.
4. Keep the 600-second candidate+strike+side stability state server-side; reset on candidate change, failed validation, stale/future timestamps or a gap over 60 seconds.
5. Map underlying entry/SL/target to a real, fresh, liquid option contract and its premium. Never label spot prices as option premium prices.
6. Add backend regression tests for stale/future/missing data, cross-layer conflicts, invalid spreads, missing ATR, invalid option liquidity, expiry/strike mapping and stability resets.
7. Verify live Angel One session/stream and fresh option-chain data from Railway logs and response bodies, not HTTP 200 alone.

## Verification status
- Added unit tests cover ORB/VWAP candidate, missing-volume and out-of-window behavior.
- These engines are research candidates only; the active Railway endpoint is not wired by this repository change.
- No APK was built and no live API, Angel One, Railway deployment, profitability or win-rate claim is made.
