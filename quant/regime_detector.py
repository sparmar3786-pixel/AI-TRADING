"""Fail-closed HMM market-regime detector.

This is backend-only research/advisory code. It does not place orders and must
not be treated as proof that any regime has predictive value.
"""
from __future__ import annotations

from typing import Any
import warnings

import numpy as np
import pandas as pd

try:
    from hmmlearn.hmm import GaussianHMM
except ImportError:  # optional dependency; absence must never create a trade
    GaussianHMM = None  # type: ignore[assignment,misc]


class MarketRegimeDetector:
    """Fit a small Gaussian HMM to recent candle features.

    State IDs are arbitrary HMM labels; interpretation is derived from fitted
    state statistics instead of assuming state 0/1/2 always means a fixed mood.
    """

    def __init__(self, n_states: int = 3, lookback_window: int = 500,
                 min_samples: int = 100, random_state: int = 42) -> None:
        if n_states < 2:
            raise ValueError("n_states must be at least 2")
        self.n_states = int(n_states)
        self.lookback_window = max(int(lookback_window), min_samples)
        self.min_samples = max(int(min_samples), 30)
        self.random_state = int(random_state)
        self.model: Any = None

    def _prepare_features(self, candles: pd.DataFrame) -> np.ndarray:
        required = {"close", "volume"}
        if candles is None or not required.issubset(candles.columns):
            return np.empty((0, 3), dtype=float)
        frame = candles.tail(self.lookback_window).copy()
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
        frame.loc[frame["close"] <= 0, "close"] = np.nan
        frame["log_ret"] = np.log(frame["close"] / frame["close"].shift(1))
        frame["volatility"] = frame["log_ret"].rolling(20, min_periods=20).std()
        # pct_change can be infinite around zero-volume rows; clean it below.
        frame["vol_mom"] = frame["volume"].pct_change(fill_method=None)
        features = frame[["log_ret", "volatility", "vol_mom"]].replace(
            [np.inf, -np.inf], np.nan
        ).dropna()
        values = features.to_numpy(dtype=float)
        if not np.isfinite(values).all():
            return np.empty((0, 3), dtype=float)
        return values

    def train_and_predict(self, candles: pd.DataFrame) -> dict[str, Any]:
        if GaussianHMM is None:
            return {"status": "unavailable", "regime_id": -1,
                    "regime_name": "UNAVAILABLE", "size_multiplier": 0.0,
                    "message": "hmmlearn is not installed; new entries must WAIT"}
        features = self._prepare_features(candles)
        if len(features) < self.min_samples:
            return {"status": "unavailable", "regime_id": -1,
                    "regime_name": "UNAVAILABLE", "size_multiplier": 0.0,
                    "sample_count": int(len(features)),
                    "message": f"Need at least {self.min_samples} valid feature rows"}

        # Standardize features because returns/volatility and volume changes
        # have different scales. Constant columns are guarded against divide-by-zero.
        mean = features.mean(axis=0)
        scale = features.std(axis=0)
        scale[scale < 1e-12] = 1.0
        normalized = (features - mean) / scale
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self.model = GaussianHMM(
                    n_components=self.n_states,
                    covariance_type="diag",
                    n_iter=200,
                    random_state=self.random_state,
                    min_covar=1e-4,
                )
                self.model.fit(normalized)
                states = self.model.predict(normalized)
            if not np.isfinite(self.model.score(normalized)):
                raise ValueError("HMM produced a non-finite model score")
            analysis: dict[int, dict[str, float]] = {}
            for state_id in range(self.n_states):
                rows = features[states == state_id]
                if len(rows) == 0:
                    continue
                analysis[state_id] = {
                    "mean_return": float(np.mean(rows[:, 0])),
                    "mean_volatility": float(np.mean(rows[:, 1])),
                    "frequency": float(len(rows) / len(features)),
                    "samples": int(len(rows)),
                }
            current = int(states[-1])
            current_stats = analysis.get(current)
            if not current_stats or current_stats["samples"] < 5:
                raise ValueError("current regime has insufficient observations")
            name, multiplier = self._classify(current_stats, analysis)
            return {
                "status": "success",
                "regime_id": current,
                "regime_name": name,
                "size_multiplier": multiplier,
                "analysis": analysis,
                "sample_count": int(len(features)),
                "model_score": float(self.model.score(normalized)),
                "message": "Research classification only; validate with out-of-sample tests",
            }
        except Exception as exc:
            self.model = None
            return {"status": "unavailable", "regime_id": -1,
                    "regime_name": "UNAVAILABLE", "size_multiplier": 0.0,
                    "sample_count": int(len(features)),
                    "message": f"HMM failed closed: {type(exc).__name__}: {exc}"}

    @staticmethod
    def _classify(stats: dict[str, float],
                  analysis: dict[int, dict[str, float]]) -> tuple[str, float]:
        vols = [v["mean_volatility"] for v in analysis.values()]
        vol_cutoff = float(np.quantile(vols, 0.75)) if vols else float("inf")
        ret = stats["mean_return"]
        vol = stats["mean_volatility"]
        # Relative volatility is more portable than a hard-coded 1.5% cutoff.
        if vol >= vol_cutoff and vol_cutoff > 0:
            return "HIGH_VOLATILITY", 0.0
        if ret > 0:
            return "BULLISH_TREND", 1.0
        if ret < 0:
            return "BEARISH_TREND", 1.0
        return "CHOPPY_OR_UNCERTAIN", 0.5

    def get_strategy_multiplier(self, result: dict[str, Any]) -> float:
        """Only validated results can permit sizing; failures return zero."""
        if result.get("status") != "success":
            return 0.0
        try:
            value = float(result["size_multiplier"])
        except (KeyError, TypeError, ValueError):
            return 0.0
        if not np.isfinite(value):
            return 0.0
        return max(0.0, min(1.0, value))
