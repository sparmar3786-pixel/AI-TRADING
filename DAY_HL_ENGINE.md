# DAY HL — PDH/PDL liquidity engine

The pure-Python engine is in `quant/day_hl_liquidity.py`. It detects:
- **PDH bearish sweep:** candle high crosses above previous-day high and closes back below it.
- **PDL bullish sweep:** candle low crosses below previous-day low and closes back above it.

It requires real, timestamped OHLC candles plus previous-session high/low from a trusted feed. It validates levels, timestamps, chronological order, and OHLC consistency; it does not fabricate prices.

## Tests

Run from the repository root:

```bash
python -m unittest discover -s tests -p 'test_day_hl_liquidity.py' -v
```

## Integration boundary

This repository's DAY HL React page currently reads the existing frontend market snapshot. The repo does not contain the live Python API implementation or its candle-history endpoint, so this module is **not yet wired into the deployed backend/API or the UI**. To complete live integration, the backend repository/service must expose authenticated previous-session levels and timestamped OHLC candles, call `detect_pdh_pdl_sweeps`, and return the results to DAY HL. Do not map current-session high/low to PDH/PDL.
