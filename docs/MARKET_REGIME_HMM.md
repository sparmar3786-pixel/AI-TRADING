# Backend-only Market Regime Detection (HMM)

The optional `quant.regime_detector.MarketRegimeDetector` fits a Gaussian HMM to recent completed candles using log returns, rolling return volatility and volume momentum. It is research/advisory only, not a trading strategy.

## Install

```bash
pip install -r requirements-quant.txt
```

## Example

```python
import pandas as pd
from quant.regime_detector import MarketRegimeDetector

# Provide completed candles from a trusted backend source.
candles: pd.DataFrame = load_completed_candles()
result = MarketRegimeDetector(n_states=3, lookback_window=500).train_and_predict(candles)
if result['status'] != 'success':
    print('REGIME UNAVAILABLE / WAIT:', result['message'])
else:
    print(result['regime_name'], result['strategy_multiplier'])
```

## Boundaries

- Backend-only: does not restore the removed Strategy page or Quant Engine UI and is not connected to an order-placement path.
- Does not fetch candles or prove that data is live/fresh. Callers must validate source, timestamps, gaps and closed-bar status independently.
- State IDs are arbitrary and may change between fits; interpret the current state using its returned per-fit analysis, never a fixed ID.
- Failed or insufficient fits return `status=unavailable` and multiplier `0.0`; a successful multiplier is advisory, not an execution signal.
- Volatility thresholds depend on timeframe/instrument and require out-of-sample calibration. No live trading or automatic order execution is included.
