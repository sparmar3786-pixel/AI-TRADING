import numpy as np
import pandas as pd

from quant.regime_detector import MarketRegimeDetector


def candles(rows=260):
    rng = np.random.default_rng(7)
    returns = rng.normal(0.0002, 0.004, rows)
    close = 25000 * np.exp(np.cumsum(returns))
    return pd.DataFrame({
        "close": close,
        "volume": rng.integers(1000, 10000, rows).astype(float),
    })


def test_feature_builder_produces_finite_three_column_matrix():
    detector = MarketRegimeDetector(min_samples=100)
    features = detector._prepare_features(candles())
    assert features.ndim == 2
    assert features.shape[1] == 3
    assert len(features) >= 100
    assert np.isfinite(features).all()


def test_insufficient_candles_fail_closed():
    detector = MarketRegimeDetector(min_samples=100)
    result = detector.train_and_predict(candles(60))
    assert result["status"] == "unavailable"
    assert result["regime_id"] == -1
    assert result["size_multiplier"] == 0.0
    assert detector.get_strategy_multiplier(result) == 0.0


def test_missing_volume_fails_closed():
    frame = candles().drop(columns=["volume"])
    detector = MarketRegimeDetector(min_samples=100)
    result = detector.train_and_predict(frame)
    assert result["status"] == "unavailable"
    assert result["size_multiplier"] == 0.0


def test_non_success_result_never_permits_sizing():
    detector = MarketRegimeDetector()
    assert detector.get_strategy_multiplier({"status": "error", "size_multiplier": 1}) == 0.0
    assert detector.get_strategy_multiplier({"status": "success", "size_multiplier": float("nan")}) == 0.0
