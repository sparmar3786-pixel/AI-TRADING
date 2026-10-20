"""Tests for backend-only HMM regime detection."""
import unittest
import numpy as np
import pandas as pd
from quant.regime_detector import MarketRegimeDetector


class MarketRegimeDetectorTests(unittest.TestCase):
    def test_missing_columns_fail_closed(self):
        result = MarketRegimeDetector().train_and_predict(pd.DataFrame({"close": [100] * 200}))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["current_regime"], -1)
        self.assertEqual(result["strategy_multiplier"], 0.0)

    def test_insufficient_data_fail_closed(self):
        candles = pd.DataFrame({"close": np.arange(100, 150), "volume": np.arange(50)})
        result = MarketRegimeDetector().train_and_predict(candles)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["strategy_multiplier"], 0.0)

    def test_features_finite_and_three_columns(self):
        candles = pd.DataFrame({"close": np.linspace(100, 120, 600),
                                "volume": np.linspace(1000, 2000, 600)})
        features = MarketRegimeDetector()._prepare_features(candles)
        self.assertEqual(features.ndim, 2)
        self.assertEqual(features.shape[1], 3)
        self.assertTrue(np.isfinite(features).all())

    def test_unknown_state_has_zero_multiplier(self):
        self.assertEqual(MarketRegimeDetector().get_strategy_multiplier(-1, {}), 0.0)

    def test_state_labels_are_analysis_based(self):
        detector = MarketRegimeDetector()
        stats = {2: {"mean_return": 0.002, "mean_volatility": 0.001, "frequency": 0.4}}
        self.assertEqual(detector._get_regime_name(2, stats), "Bullish Trend")
        self.assertEqual(detector._get_regime_name(1, stats), "Unknown")


if __name__ == "__main__":
    unittest.main()
