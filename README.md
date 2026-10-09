# AI-TRADING — Angel One Strategy Research

This repository is being used as a clean research/strategy workspace for the Fresh-Apk Android client and its Angel One backend.

## Requested upstream research repositories

These projects are kept as upstream references rather than blindly vendored wholesale:

- https://github.com/wangzhe3224/awesome-systematic-trading — MIT-licensed curated systematic-trading resource list.
- https://github.com/paperswithbacktest/awesome-systematic-trading — curated research/resource list; check its current license and each linked strategy's license before copying implementation code.
- https://github.com/georgezouq/awesome-ai-in-finance — CC0-1.0 resource list.
- https://github.com/nkaz001/hftbacktest — MIT; high-fidelity tick/order-book backtesting and latency/queue modeling. Its examples target crypto venues (not Angel One).
- https://github.com/ranaroussi/qtpylib — Apache-2.0; archived and designed around Interactive Brokers, not Angel One.

## Integration policy

The resource lists are catalogs, not installable trading engines. Importing every listed project would introduce unrelated broker integrations, heavy dependencies, incompatible licenses, and unnecessary APK size. This repo therefore starts with an original, broker-neutral confluence module. It is intended to run in the server-side Python backend, not inside the Android APK itself.

The APK should call the hosted backend over HTTPS. Angel One credentials and AI keys must remain server-side and must not be packaged in the APK.

## Strategy flow

1. Require fresh, timestamped Angel One index and option-chain data.
2. Evaluate deterministic trend/momentum and multi-timeframe confluence.
3. Check option quote spread/liquidity and OI context.
4. Ask configured AI to audit the strategy plan, never to fabricate missing prices or override risk guards.
5. Require a separate live validation gate before exposing BUY/SELL as validated.
6. Return WAIT/NO TRADE if inputs are stale, missing, contradictory, or risk checks fail.
7. Validate with out-of-sample walk-forward backtests including fees, slippage, spread and latency assumptions before any live use.

## Signal terminology

- `CALL BUY`: bullish option-side setup; validated market direction is `BUY`.
- `PUT BUY`: bearish option-side setup; validated market direction is `SELL` (this means buying a put, not selling an uncovered option).
- Missing/failed validation: `WAIT`.

No strategy guarantees profit. Do not turn a backtest score or AI confidence into a claimed win probability.
