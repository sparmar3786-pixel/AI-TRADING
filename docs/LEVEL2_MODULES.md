# Level-2 Trading Modules — Integration and Safety Notes

This branch adds a **research/paper-trading module layer** under `quant/level2/`. It does not activate live order placement and does not replace the existing APK signal API.

## Modules included

- `websocket_angel.py`: bounded reconnect supervisor, thread-safe latest-tick cache and freshness checks. It requires an injected Angel SmartAPI SDK connector and an SDK-version-specific binary tick parser. It deliberately does not guess authentication headers or interpret arbitrary WebSocket messages as prices.
- `option_chain.py`: symbol-master cache, normalized CE/PE contract lookup, nearest non-expired expiry and ATM strike helper. It returns no contract when an exact contract cannot be resolved.
- `backtest.py`: chronological callback-based OHLC replay, next-bar-open entries, slippage/fee parameters, risk-fraction sizing, conservative stop-first handling when stop and target are both touched, trade list and metrics.
- `alerts.py`: optional Telegram notifications using `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` environment variables; no credentials are committed.
- `dashboard.py`: FastAPI read-only status/dashboard factory. Requires an explicit bearer token; it intentionally exposes no start/stop or order-placement controls.
- `ml_optimizer.py`: optional scikit-learn training with chronological train/test split. An untrained/missing model returns `False` from `allow_trade`; model approval is never execution authorization.
- `tests/test_level2_modules.py`: deterministic tests with fixtures; no broker, Telegram, or live order calls.

## Important limits

1. The existing repository did not contain the chat-described `trading_bot/bot.py` and `broker_angel.py` package. These modules therefore remain separate, reusable research components rather than a claim of end-to-end bot integration.
2. WebSocket connection and binary tick decoding must be wired against the exact installed Angel SmartAPI SDK version and verified using sanitized sample packets. Do not put API key, JWT, TOTP seed, feed token or Telegram token in source control or the APK.
3. The symbol-master contract resolver is not a complete option-chain liquidity selector. Before any use, validate expiry/strike/token/lot-size against the current broker master and quote the *resolved contract*, not the underlying index.
4. Backtest metrics are research estimates, not proof of profitability. The engine is not a full options-premium simulator and does not model exchange margin, order-book fills, circuit limits, taxes or all broker charges.
5. ML model results require out-of-sample evaluation and walk-forward review. Do not auto-promote model/strategy parameters to production based on training accuracy.
6. The dashboard is a factory that must be mounted by the backend with a secret held in server environment configuration. The browser page requires an authorized request; no control endpoints are added.
7. These changes do **not** claim to fix the live `API UP / DATA ERROR`, confirm Render/Railway deployment, build an APK, or enable live trading. Existing signal freshness, risk, validation and stability gates must remain authoritative.

## Local validation

Install the repository's quant requirements and run:

```bash
python -m pip install -r requirements-quant.txt
python -m unittest tests.test_level2_modules -v
```

The CI workflow also discovers `tests/test*.py`. Optional ML training requires `scikit-learn` and `joblib`; FastAPI dashboard mounting requires `fastapi`.
