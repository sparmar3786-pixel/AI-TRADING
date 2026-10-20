from __future__ import annotations
import copy
import random

PARAM_BOUNDS = {
    'ema_fast': (5, 20), 'ema_slow': (15, 50), 'rsi_period': (7, 21),
    'atr_period': (7, 30), 'sl_atr': (0.8, 2.5), 'entry_score_threshold': (3, 5),
    'breakout_window': (10, 60),
}
INTEGER_PARAMS = {'ema_fast', 'ema_slow', 'rsi_period', 'atr_period', 'entry_score_threshold', 'breakout_window'}

class ConservativeOptimizer:
    """Creates research candidates only; never promotes parameters automatically."""
    def candidate(self, current: dict, seed: int | None = None) -> dict:
        rng = random.Random(seed)
        result = copy.deepcopy(current)
        for key, value in list(result.items()):
            if key not in PARAM_BOUNDS or not isinstance(value, (int, float)):
                continue
            low, high = PARAM_BOUNDS[key]
            value = max(low, min(high, float(value) * rng.uniform(0.95, 1.05)))
            result[key] = int(round(value)) if key in INTEGER_PARAMS else round(value, 4)
        if result.get('ema_fast', 0) >= result.get('ema_slow', 1):
            result['ema_fast'] = max(PARAM_BOUNDS['ema_fast'][0], result['ema_slow'] - 5)
        return result

    @staticmethod
    def score(metrics: dict) -> float:
        # Conservative utility penalizes drawdown more heavily than win rate rewards.
        net = float(metrics.get('net_pnl', 0))
        drawdown = max(0.0, float(metrics.get('max_drawdown', 0)))
        win_rate = max(0.0, min(100.0, float(metrics.get('win_rate', 0))))
        return net - 0.75 * drawdown + 0.05 * win_rate
