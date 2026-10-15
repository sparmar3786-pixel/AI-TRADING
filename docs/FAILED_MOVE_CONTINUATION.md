# Failed-Move Continuation Engine

Isolated strategy module: `quant/failed_move_fade.py`.

Despite the historical name “fade”, this strategy is **continuation/acceptance**, not a reversal:
- CALL candidate only after the latest configured completed closes remain above previous-day high (PDH).
- PUT candidate only after the latest configured completed closes remain below previous-day low (PDL).
- Uses previous-session levels only, IST-normalized timestamps, completed bars, optional mandatory volume confirmation, ATR-based stop buffer, and a maximum ATR risk cap.
- Invalid/stale inputs fail closed. The API mapper emits `decision="WAIT"` and keeps the BUY side in `candidate_decision` for the downstream 10-minute stability and live validation gates.

## Import

```python
from quant.failed_move_fade import (
    FailedMoveFadeEngine,
    FailedMoveSignal,
    failed_move_to_signal_data,
)
```

## Use

```python
engine = FailedMoveFadeEngine(
    hold_bars=3,
    atr_sl_buffer_mult=0.25,
    max_risk_atr_mult=2.0,
    risk_reward=2.0,
    use_volume_filter=True,
)
signal = engine.generate(
    daily_df=daily_ohlc,
    intraday_df=intraday_5min,
    current_spot=current_spot,
    current_time=current_time,
    strike_step=50,
)
payload = failed_move_to_signal_data(
    signal, index="NIFTY", timestamp=current_time.isoformat(), data_fresh=True
)
```

This module uses its own `FailedMoveSignal` and `failed_move_to_signal_data` names. It does not modify the EMA engine, DAY HL engine, shared `QuantSignal`, workflow, frontend, broker integration, or Railway deployment. The returned candidate is not an order instruction and still requires the existing live-risk and 10-minute confirmation gates.
