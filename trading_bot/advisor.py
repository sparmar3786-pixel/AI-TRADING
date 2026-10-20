from __future__ import annotations
import numpy as np
import pandas as pd
from quant.regime_detector import MarketRegimeDetector

class MultiLevelAdvisor:
    """Signal-only multi-factor advisor. It never sends or routes broker orders."""
    def __init__(self, params: dict | None = None):
        self.p = {'ema_fast': 9, 'ema_slow': 21, 'rsi_period': 14, 'atr_period': 14,
                  'breakout_window': 20, 'entry_score_threshold': 3, 'sl_atr': 1.2,
                  'rsi_buy_min': 52, 'rsi_buy_max': 75, 'rsi_sell_min': 25,
                  'rsi_sell_max': 48, 'min_atr_pct': 0.05, 'max_atr_pct': 3.0}
        self.p.update(params or {})
        self.regime = MarketRegimeDetector(n_states=3, lookback_window=500, min_samples=100)

    def evaluate(self, candles: list[dict], spot: float | None = None, risk_can_open: bool = True) -> dict:
        df = pd.DataFrame(candles)
        required = {'high', 'low', 'close', 'volume'}
        if not required.issubset(df.columns) or len(df) < 60:
            return {'decision': 'WAIT', 'status': 'unavailable', 'reason': 'insufficient_or_invalid_candles', 'entry': None, 'stop_loss': None, 'target': None, 'strike': None}
        for col in required:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=list(required)).reset_index(drop=True)
        if len(df) < 60 or (df['close'] <= 0).any():
            return {'decision': 'WAIT', 'status': 'unavailable', 'reason': 'invalid_candle_values', 'entry': None, 'stop_loss': None, 'target': None, 'strike': None}
        close = df['close']; high = df['high']; low = df['low']
        p = self.p
        fast = close.ewm(span=int(p['ema_fast']), adjust=False).mean()
        slow = close.ewm(span=int(p['ema_slow']), adjust=False).mean()
        delta = close.diff(); gain = delta.clip(lower=0).ewm(alpha=1/int(p['rsi_period']), adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/int(p['rsi_period']), adjust=False).mean()
        rsi = 100 - 100/(1 + gain/loss.replace(0, np.nan))
        prev = close.shift(1)
        tr = pd.concat([(high-low).abs(), (high-prev).abs(), (low-prev).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1/int(p['atr_period']), adjust=False).mean()
        macd_hist = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        macd_hist = macd_hist - macd_hist.ewm(span=9, adjust=False).mean()
        upper = high.rolling(int(p['breakout_window'])).max().shift(1)
        lower = low.rolling(int(p['breakout_window'])).min().shift(1)
        typical = (high + low + close) / 3
        volume = df['volume'].clip(lower=0)
        vwap = (typical * volume).cumsum() / volume.cumsum().replace(0, np.nan)
        i = len(df) - 1
        vals = [fast.iloc[i], slow.iloc[i], rsi.iloc[i], atr.iloc[i], macd_hist.iloc[i], upper.iloc[i], lower.iloc[i]]
        if not all(pd.notna(v) and np.isfinite(float(v)) for v in vals):
            return {'decision': 'WAIT', 'status': 'unavailable', 'reason': 'indicator_warmup_incomplete', 'entry': None, 'stop_loss': None, 'target': None, 'strike': None}
        score = 0; reasons = []
        if fast.iloc[i] > slow.iloc[i] and close.iloc[i] > slow.iloc[i]: score += 1; reasons.append('trend_up')
        elif fast.iloc[i] < slow.iloc[i] and close.iloc[i] < slow.iloc[i]: score -= 1; reasons.append('trend_down')
        rv = float(rsi.iloc[i])
        if p['rsi_buy_min'] <= rv <= p['rsi_buy_max']: score += 1; reasons.append('rsi_bull')
        elif p['rsi_sell_min'] <= rv <= p['rsi_sell_max']: score -= 1; reasons.append('rsi_bear')
        if macd_hist.iloc[i] > 0: score += 1; reasons.append('macd_bull')
        elif macd_hist.iloc[i] < 0: score -= 1; reasons.append('macd_bear')
        if close.iloc[i] > upper.iloc[i]: score += 1; reasons.append('breakout_up')
        elif close.iloc[i] < lower.iloc[i]: score -= 1; reasons.append('breakout_down')
        if pd.notna(vwap.iloc[i]):
            if close.iloc[i] > vwap.iloc[i]: score += 1; reasons.append('vwap_bull')
            elif close.iloc[i] < vwap.iloc[i]: score -= 1; reasons.append('vwap_bear')
        atr_pct = float(atr.iloc[i] / close.iloc[i] * 100)
        if not float(p['min_atr_pct']) <= atr_pct <= float(p['max_atr_pct']):
            return {'decision': 'WAIT', 'status': 'blocked', 'reason': 'atr_filter_failed', 'score': score, 'entry': None, 'stop_loss': None, 'target': None, 'strike': None}
        regime = self.regime.train_and_predict(df)
        multiplier = float(regime.get('strategy_multiplier', 0.0))
        if regime.get('status') != 'success' or multiplier <= 0:
            return {'decision': 'WAIT', 'status': 'blocked', 'reason': 'regime_unavailable_or_high_volatility', 'regime': regime, 'score': score, 'entry': None, 'stop_loss': None, 'target': None, 'strike': None}
        direction = 1 if score >= int(p['entry_score_threshold']) else (-1 if score <= -int(p['entry_score_threshold']) else 0)
        if direction == 0 or not risk_can_open:
            return {'decision': 'WAIT', 'status': 'blocked' if not risk_can_open else 'no_signal', 'reason': 'risk_gate_blocked' if not risk_can_open else 'score_below_threshold', 'score': score, 'reasons': reasons, 'regime': regime, 'entry': None, 'stop_loss': None, 'target': None, 'strike': None}
        entry = float(spot) if spot is not None and np.isfinite(spot) and spot > 0 else float(close.iloc[i])
        distance = float(atr.iloc[i]) * float(p['sl_atr'])
        sl = entry - direction * distance
        target = entry + direction * distance * 1.5
        step = int(p.get('strike_step', 50)); strike = round(entry / step) * step if step > 0 else None
        return {'decision': 'CALL BUY' if direction > 0 else 'PUT BUY', 'status': 'advisory_only', 'score': score, 'reasons': reasons, 'regime': regime, 'regime_multiplier': multiplier, 'entry': entry, 'stop_loss': sl, 'target': target, 'strike': strike, 'risk_reward': 1.5, 'orders_sent': False}
