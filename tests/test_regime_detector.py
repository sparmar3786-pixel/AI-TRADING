import unittest
import numpy as np
import pandas as pd
from quant.regime_detector import MarketRegimeDetector


def candles(rows=260):
    rng = np.random.default_rng(7)
    returns = rng.normal(0.0002, 0.004, rows)
    close = 25000 * np.exp(np.cumsum(returns))
    return pd.DataFrame({'close': close, 'volume': rng.integers(1000, 10000, rows).astype(float)})


class RegimeDetectorTests(unittest.TestCase):
    def test_feature_builder_produces_finite_three_column_matrix(self):
        features = MarketRegimeDetector(min_samples=100)._prepare_features(candles())
        self.assertEqual(features.ndim, 2)
        self.assertEqual(features.shape[1], 3)
        self.assertGreaterEqual(len(features), 100)
        self.assertTrue(np.isfinite(features).all())

    def test_insufficient_candles_fail_closed(self):
        detector = MarketRegimeDetector(min_samples=100)
        result = detector.train_and_predict(candles(60))
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['regime_id'], -1)
        self.assertEqual(result['size_multiplier'], 0.0)
        self.assertEqual(detector.get_strategy_multiplier(result), 0.0)

    def test_missing_volume_fails_closed(self):
        result = MarketRegimeDetector(min_samples=100).train_and_predict(candles().drop(columns=['volume']))
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['size_multiplier'], 0.0)

    def test_invalid_result_never_permits_sizing(self):
        detector = MarketRegimeDetector()
        self.assertEqual(detector.get_strategy_multiplier({'status': 'error', 'size_multiplier': 1}), 0.0)
        self.assertEqual(detector.get_strategy_multiplier({'status': 'success', 'size_multiplier': float('nan')}), 0.0)


if __name__ == '__main__':
    unittest.main()
