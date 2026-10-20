"""Optional ML research filter and walk-forward evaluation; never authorizes live orders."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd

FEATURES = ("ret1", "ret3", "vol10", "ema_gap", "range_pct")

@dataclass
class MLTrainingReport:
    status: str
    train_rows: int = 0
    test_rows: int = 0
    test_accuracy: Optional[float] = None
    test_auc: Optional[float] = None
    reason: Optional[str] = None

class MLFilter:
    def __init__(self, probability_threshold: float = 0.58, model_path: Optional[str] = None):
        if not 0.5 < probability_threshold < 1: raise ValueError("probability threshold must be between 0.5 and 1")
        self.threshold, self.model_path, self.model = probability_threshold, model_path, None
        self.feature_columns = list(FEATURES)

    @staticmethod
    def features(candles: pd.DataFrame) -> pd.DataFrame:
        if "close" not in candles: raise ValueError("close column required")
        close = pd.to_numeric(candles.close, errors="coerce")
        out = pd.DataFrame(index=candles.index)
        out["ret1"] = close.pct_change(1); out["ret3"] = close.pct_change(3)
        returns = close.pct_change()
        out["vol10"] = returns.rolling(10, min_periods=10).std()
        out["ema_gap"] = (close.ewm(span=8, adjust=False).mean() - close.ewm(span=21, adjust=False).mean()) / close
        if {"high", "low"}.issubset(candles.columns): out["range_pct"] = (candles.high - candles.low) / close
        else: out["range_pct"] = 0.0
        return out.replace([float("inf"), float("-inf")], float("nan"))

    def train(self, candles: pd.DataFrame, horizon_bars: int = 3, label_threshold_pct: float = 0.08) -> MLTrainingReport:
        try:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.metrics import accuracy_score, roc_auc_score
            import joblib
        except ImportError: return MLTrainingReport("unavailable", reason="install scikit-learn and joblib to enable optional ML")
        if horizon_bars < 1 or label_threshold_pct <= 0: return MLTrainingReport("invalid_config", reason="invalid horizon/label threshold")
        frame = self.features(candles)
        future_return = pd.to_numeric(candles.close, errors="coerce").shift(-horizon_bars) / pd.to_numeric(candles.close, errors="coerce") - 1
        frame["label"] = (future_return > label_threshold_pct / 100).astype(int)
        frame.loc[future_return.isna(), "label"] = float("nan")
        frame = frame.dropna(subset=list(FEATURES) + ["label"])
        if len(frame) < 500 or frame.label.nunique() < 2: return MLTrainingReport("insufficient_data", reason="need >=500 clean rows and both classes")
        split = int(len(frame) * 0.8); train, test = frame.iloc[:split], frame.iloc[split:]
        if train.label.nunique() < 2 or test.label.nunique() < 2: return MLTrainingReport("invalid_split", reason="chronological split needs both classes")
        model = RandomForestClassifier(n_estimators=200, max_depth=5, min_samples_leaf=20, random_state=42, n_jobs=-1, class_weight="balanced_subsample")
        model.fit(train[list(FEATURES)], train.label.astype(int)); probabilities = model.predict_proba(test[list(FEATURES)])[:, list(model.classes_).index(1)]
        preds = (probabilities >= self.threshold).astype(int)
        try: auc = float(roc_auc_score(test.label.astype(int), probabilities))
        except ValueError: auc = None
        self.model = model
        if self.model_path: joblib.dump({"model": model, "features": list(FEATURES), "threshold": self.threshold}, self.model_path)
        return MLTrainingReport("trained", len(train), len(test), float(accuracy_score(test.label.astype(int), preds)), auc)

    def allow_trade(self, candles: pd.DataFrame, direction: int) -> bool:
        """Fail closed: untrained, stale, or malformed model inputs never approve a trade."""
        if direction not in (-1, 1) or self.model is None: return False
        frame = self.features(candles).dropna(subset=list(FEATURES))
        if frame.empty: return False
        try:
            probs = self.model.predict_proba(frame[list(FEATURES)].iloc[-1:])[0]
            classes = list(self.model.classes_); p_up = float(probs[classes.index(1)])
            return p_up >= self.threshold if direction == 1 else p_up <= 1 - self.threshold
        except Exception: return False
