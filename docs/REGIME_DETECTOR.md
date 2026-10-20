# Backend-only HMM market-regime detector

quant/regime_detector.py implements an optional Gaussian HMM over log returns, 20-candle return volatility, and volume momentum. State IDs are not hard-coded to Bull/Bear/Choppy; state labels are derived from observed state statistics.

## Safety contract

- The module is research/advisory only. It does not place orders and is not wired into the APK's signal approval path.
- Missing hmmlearn, too few valid rows, non-finite features, or fit/prediction errors return UNAVAILABLE and a zero sizing multiplier. The caller must keep new entries at WAIT.
- A successful HMM fit is not evidence of profitability or a validated regime prediction. Use out-of-sample tests before any future integration.
- The APK's Strategy and Quant Engine pages are intentionally removed. Adding this backend research module does not restore those screens.
- Do not copy broker credentials into Flutter, source control, or a client-visible config file.

## Install and test

```bash
pip install -r requirements-quant.txt
python -m unittest discover -s tests -p 'test_regime_detector.py' -v
```

## Integration status

This repository contains Flutter client code and standalone quant research modules, not the complete deployed Python signal-service implementation. Therefore this change deliberately does not claim that the HMM is affecting live /v1/signals decisions. To connect it later, the actual backend service must call the detector on fresh, validated candles and reject candidates whenever the detector returns UNAVAILABLE.
