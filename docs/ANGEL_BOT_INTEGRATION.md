Reviewed Angel Bot integration status

This repository includes trading_bot/reviewed_engine.py, a deterministic paper-only position/risk engine based on the corrective review package.

Included: sticky 15% daily profit and 5% daily loss locks; simulated full exit when a lock is reached; entries blocked after halt; cumulative partial targets at 30%, 70%, and 100% of initial quantity; lot-multiple validation; stale-quote rejection; SQLite state persistence; manual kill latch. No broker order placement function exists and events explicitly report orders_sent=false.

Important boundary: this module is not yet wired to the Angel One polling loop or the existing /v1/signals backend. It validates paper-position behavior only. Existing trading_bot/api.py remains the read-only/advisory API. Do not describe this as a live auto-trading bot. Live execution needs broker order-state reconciliation, actual fills, protective-stop recovery, idempotency and account-level exposure checks before it can be considered.