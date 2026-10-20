"""Backend-only HMM market-regime research module.

Advisory only: this module neither places orders nor restores removed app pages.
Callers must supply completed, fresh OHLCV candles and validate data freshness.
"""
from __future__ import annotations
from typing import Any, Dict
import numpy as np
import pandas as pd

try:
    from hmmlearn.hmm import GaussianHMM
except ImportError:
    GaussianHMM = None


class MarketRegimeDetector:
    """Fit a Gaussian HMM to log-return, volatility and volume-momentum features.

    State IDs are arbitrary between fits; interpret them with returned analysis.
    """
    REQUIRED_COLUMNS = ("close", "volume")

    def __init__(self, n_states: int = 3, lookback_window: int = 500,
                 min_samples: int = 100, volatility_window: int = 20,
                 random_state: int = 42, high_volatility_threshold: float = 0.015,
                 trend_return_threshold: float = 0.001) -> None:
        if n_states < 2:
            raise ValueError("n_states must be at least 2")
        if min_samples < 30 or lookback_window < min_samples:
            raise ValueError("lookback_window must be >= min_samples >= 30")
        if volatility_window < 2:
            raise ValueError("volatility_window must be at least 2")
        self.n_states = n_states
        self.lookback_window = lookback_window
        self.min_samples = min_samples
        self.volatility_window = volatility_window
        self.random_state = random_state
        self.high_volatility_threshold = high_volatility_threshold
        self.trend_return_threshold = trend_return_threshold
        self.model: Any = None

    def _prepare_features(self, candles: pd.DataFrame) -> np.ndarray:
        if not isinstance(candles, pd.DataFrame):
            return np.empty((0, 3), dtype=float)
        if any(c not in candles.columns for c in self.REQUIRED_COLUMNS):
            return np.empty((0, 3), dtype=float)
        frame = candles.loc[:, list(self.REQUIRED_COLUMNS)].tail(self.lookback_window).copy()
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
        frame.loc[frame["close"] <= 0, "close"] = np.nan
        frame.loc[frame["volume"] < 0, "volume"] = np.nan
        frame["log_ret"] = np.log(frame["close"] / frame["close"].shift(1))
        frame["volatility"] = frame["log_ret"].rolling(
            window=self.volatility_window, min_periods=self.volatility_window
        ).std()
        frame["vol_mom"] = frame["volume"].pct_change().replace([np.inf, -np.inf], np.nan)
        values = frame[["log_ret", "volatility", "vol_mom"]].replace(
            [np.inf, -np.inf], np.nan
        ).dropna().to_numpy(dtype=float)
        if values.ndim != 2 or values.shape[1] != 3 or not np.isfinite(values).all():
            return np.empty((0, 3), dtype=float)
        return values

    @staticmethod
    def _standardize(features: np.ndarray) -> np.ndarray:
        mean = features.mean(axis=0)
        scale = features.std(axis=0)
        scale = np.where(scale < 1e-8, 1.0, scale)
        return (features - mean) / scale

    def train_and_predict(self, candles: pd.DataFrame) -> Dict[str, Any]:
        """Fit on supplied completed candles; unavailable results fail closed."""
        unavailable = {
            "status": "unavailable", "current_regime": -1, "regime": -1,
            "regime_name": "Unknown", "analysis": {}, "strategy_multiplier": 0.0,
            "message": "",
        }
        if GaussianHMM is None:
            unavailable["message"] = "hmmlearn missing; install requirements-quant.txt"
            return unavailable
        features = self._prepare_features(candles)
        if len(features) < self.min_samples:
            unavailable["message"] = (
                f"Insufficient valid candle features: {len(features)}; need {self.min_samples}"
            )
            return unavailable
        try:
            standardized = self._standardize(features)
            self.model = GaussianHMM(
                n_components=self.n_states, covariance_type="diag", n_iter=200,
                tol=1e-3, min_covar=1e-4, random_state=self.random_state,
            )
            self.model.fit(standardized)
            states = self.model.predict(standardized)
            regime = int(states[-1])
            analysis = self._analyze_regimes(features, states)
            name = self._get_regime_name(regime, analysis)
            multiplier = self.get_strategy_multiplier(regime, analysis)
            if not np.isfinite(multiplier):
                raise ValueError("non-finite multiplier")
            return {
                "status": "success", "current_regime": regime, "regime": regime,
                "regime_name": name, "analysis": analysis,
                "strategy_multiplier": multiplier, "samples_used": int(len(features)),
                "message": "",
            }
        except Exception as exc:
            unavailable["message"] = f"HMM fit/prediction failed: {type(exc).__name__}"
            return unavailable

    def _analyze_regimes(self, features: np.ndarray, states: np.ndarray) -> Dict[int, Dict[str, float]]:
        analysis: Dict[int, Dict[str, float]] = {}
        for state_id in range(self.n_states):
            group = features[states == state_id]
            if len(group):
                analysis[state_id] = {
                    "mean_return": float(np.mean(group[:, 0])),
                    "mean_volatility": float(np.mean(group[:, 1])),
                    "frequency": float(len(group) / len(states)),
                }
        return analysis

    def _get_regime_name(self, regime_id: int, analysis: Dict[int, Dict[str, float]]) -> str:
        stats = analysis.get(regime_id)
        if not stats:
            return "Unknown"
        ret, vol = stats["mean_return"], stats["mean_volatility"]
        if vol >= self.high_volatility_threshold:
            return "High Volatility / Crash Risk"
        if ret >= self.trend_return_threshold:
            return "Bullish Trend"
        if ret <= -self.trend_return_threshold:
            return "Bearish Trend"
        return "Choppy / Sideways"

    def get_strategy_multiplier(self, regime_id: int, analysis: Dict[int, Dict[str, float]]) -> float:
        """Advisory sizing multiplier; unknown/high-volatility states block by default."""
        name = self._get_regime_name(regime_id, analysis)
        if name == "Unknown" or "High Volatility" in name or "Crash Risk" in name:
            return 0.0
        if name == "Choppy / Sideways":
            return 0.5
        return 1.0
