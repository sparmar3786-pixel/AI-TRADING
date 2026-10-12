"""
0DTE Trading System - Machine Learning Probability Scorer
=========================================================
Uses ML models to score trade setups by historical success probability.

Models:
  - Random Forest: Ensemble for feature importance
  - Gradient Boosting: High accuracy predictions
  - LSTM (optional): Sequential pattern recognition

Features:
  - Zone characteristics (strength, freshness, touch count)
  - Candlestick pattern strength
  - VIX regime and divergence
  - Dealer positioning signals
  - Time-of-day effects
  - Recent price action momentum

Output:
  - Win probability (0-100%)
  - Expected R:R ratio
  - Confidence interval
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import pickle
import os

# ML imports
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import warnings
warnings.filterwarnings('ignore')


@dataclass
class MLPrediction:
    """ML model prediction for a trade setup."""
    win_probability: float  # 0-100%
    expected_rr: float      # Expected reward/risk ratio
    confidence: float       # Model confidence (0-100%)

    # Feature importance for this prediction
    top_features: List[Tuple[str, float]]

    # Model metadata
    model_type: str
    training_samples: int
    feature_count: int

    @property
    def should_trade(self) -> bool:
        """Whether the setup meets ML threshold."""
        return self.win_probability >= 55 and self.confidence >= 60

    @property
    def edge(self) -> float:
        """Expected edge = (win% * avg_win) - (loss% * avg_loss)."""
        # Assuming 1:1 base R:R
        return (self.win_probability / 100 * self.expected_rr) - ((100 - self.win_probability) / 100)

    def to_dict(self) -> dict:
        return {
            'win_probability': self.win_probability,
            'expected_rr': self.expected_rr,
            'confidence': self.confidence,
            'should_trade': self.should_trade,
            'edge': self.edge,
            'top_features': self.top_features,
            'model_type': self.model_type,
        }


@dataclass
class TradeFeatures:
    """
    Feature vector for ML model input.

    All features normalized to 0-1 or standardized.
    """
    # Zone features
    zone_confidence: float
    zone_strength: int  # 1-4
    zone_freshness: int  # 0=fresh, 1+=touched
    zone_height_atr: float  # Zone height as multiple of ATR

    # Candlestick features
    candle_strength: float
    candle_volume_confirmed: int  # 0 or 1
    candle_body_ratio: float
    candle_wick_ratio: float

    # VIX features
    vix_level: float
    vix_regime: int  # 0-4 (low to extreme)
    vix_percentile: float
    vix_divergence: int  # -1, 0, 1

    # Dealer features
    put_call_ratio: float
    distance_to_max_pain: float  # As % of price
    is_pinned: int  # 0 or 1

    # Time features
    hour_of_day: int  # 0-23
    day_of_week: int  # 0-4 (Mon-Fri)
    minutes_to_close: int  # Minutes until market close

    # Momentum features
    price_change_5bar: float  # % change over last 5 bars
    price_change_20bar: float  # % change over last 20 bars
    rsi_14: float  # RSI value (0-100)
    atr_percentile: float  # Current ATR vs 20-day ATR

    # Trade direction
    is_long: int  # 1 for long, 0 for short

    def to_array(self) -> np.ndarray:
        """Convert to numpy array for model input."""
        return np.array([
            self.zone_confidence / 100,
            self.zone_strength / 4,
            min(self.zone_freshness, 5) / 5,
            min(self.zone_height_atr, 3) / 3,
            self.candle_strength / 100,
            self.candle_volume_confirmed,
            self.candle_body_ratio,
            self.candle_wick_ratio,
            self.vix_level / 50,  # Normalize assuming max ~50
            self.vix_regime / 4,
            self.vix_percentile / 100,
            (self.vix_divergence + 1) / 2,  # Map -1,0,1 to 0,0.5,1
            min(self.put_call_ratio, 2) / 2,
            min(abs(self.distance_to_max_pain), 5) / 5,
            self.is_pinned,
            self.hour_of_day / 23,
            self.day_of_week / 4,
            min(self.minutes_to_close, 390) / 390,
            (self.price_change_5bar + 5) / 10,  # Normalize ±5% to 0-1
            (self.price_change_20bar + 10) / 20,  # Normalize ±10% to 0-1
            self.rsi_14 / 100,
            self.atr_percentile / 100,
            self.is_long,
        ])

    @staticmethod
    def feature_names() -> List[str]:
        """Get feature names for interpretation."""
        return [
            'zone_confidence', 'zone_strength', 'zone_freshness', 'zone_height_atr',
            'candle_strength', 'candle_volume_confirmed', 'candle_body_ratio', 'candle_wick_ratio',
            'vix_level', 'vix_regime', 'vix_percentile', 'vix_divergence',
            'put_call_ratio', 'distance_to_max_pain', 'is_pinned',
            'hour_of_day', 'day_of_week', 'minutes_to_close',
            'price_change_5bar', 'price_change_20bar', 'rsi_14', 'atr_percentile',
            'is_long',
        ]


class MLScorer:
    """
    Machine Learning model for scoring trade setups.

    Supports:
    - Training on historical trade data
    - Real-time prediction for new setups
    - Feature importance analysis
    - Model persistence
    """

    def __init__(
        self,
        model_type: str = 'gradient_boosting',  # 'random_forest' or 'gradient_boosting'
        model_path: Optional[str] = None,
    ):
        self.model_type = model_type
        self.model_path = model_path
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.training_metrics: Dict[str, float] = {}

        # Try to load trained model first
        trained_model_path = model_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'trained_models', 'latest.pkl'
        )

        if os.path.exists(trained_model_path):
            try:
                self.load_model(trained_model_path)
                print(f"Loaded trained ML model from {trained_model_path}")
                return
            except Exception as e:
                print(f"Could not load trained model: {e}")

        # Initialize untrained model as fallback
        if model_type == 'random_forest':
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1,
            )
        else:
            self.model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42,
            )

        print("ML Scorer: No trained model found - using heuristic fallback")

    def train(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        test_size: float = 0.2,
    ) -> Dict[str, float]:
        """
        Train the ML model on historical trade data.

        Args:
            features: Feature matrix (n_samples, n_features)
            labels: Binary labels (1=win, 0=loss)
            test_size: Fraction of data for testing

        Returns:
            Dict of training metrics
        """
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            features, labels, test_size=test_size, random_state=42, stratify=labels
        )

        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # Train model
        self.model.fit(X_train_scaled, y_train)
        self.is_trained = True

        # Evaluate
        y_pred = self.model.predict(X_test_scaled)
        y_prob = self.model.predict_proba(X_test_scaled)[:, 1]

        # Calculate metrics
        self.training_metrics = {
            'accuracy': accuracy_score(y_test, y_pred),
            'precision': precision_score(y_test, y_pred, zero_division=0),
            'recall': recall_score(y_test, y_pred, zero_division=0),
            'f1': f1_score(y_test, y_pred, zero_division=0),
            'training_samples': len(X_train),
            'test_samples': len(X_test),
        }

        # Cross-validation score
        cv_scores = cross_val_score(self.model, X_train_scaled, y_train, cv=5)
        self.training_metrics['cv_mean'] = cv_scores.mean()
        self.training_metrics['cv_std'] = cv_scores.std()

        return self.training_metrics

    def predict(self, features: TradeFeatures) -> MLPrediction:
        """
        Predict win probability for a trade setup.

        Args:
            features: TradeFeatures object

        Returns:
            MLPrediction object
        """
        if not self.is_trained:
            # Return default prediction if model not trained
            return self._default_prediction(features)

        # Convert to array and scale
        X = features.to_array().reshape(1, -1)
        X_scaled = self.scaler.transform(X)

        # Get prediction
        win_prob = self.model.predict_proba(X_scaled)[0, 1] * 100

        # Calculate confidence based on probability distance from 50%
        confidence = abs(win_prob - 50) * 2  # 50% -> 0 confidence, 100%/0% -> 100 confidence

        # Get feature importance
        if hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
            feature_names = TradeFeatures.feature_names()
            top_features = sorted(
                zip(feature_names, importances),
                key=lambda x: x[1],
                reverse=True
            )[:5]
        else:
            top_features = []

        # Estimate expected R:R based on win probability
        # Higher win prob -> can accept lower R:R
        if win_prob >= 70:
            expected_rr = 1.0
        elif win_prob >= 60:
            expected_rr = 1.2
        elif win_prob >= 55:
            expected_rr = 1.5
        else:
            expected_rr = 2.0

        return MLPrediction(
            win_probability=win_prob,
            expected_rr=expected_rr,
            confidence=confidence,
            top_features=top_features,
            model_type=self.model_type,
            training_samples=self.training_metrics.get('training_samples', 0),
            feature_count=len(TradeFeatures.feature_names()),
        )

    def _default_prediction(self, features: TradeFeatures) -> MLPrediction:
        """
        Return rule-based prediction when model not trained.

        Uses simple heuristics based on key features.
        """
        score = 50  # Base probability

        # Zone confidence contribution
        score += (features.zone_confidence - 50) * 0.3

        # Candle strength contribution
        score += (features.candle_strength - 50) * 0.2

        # VIX regime contribution (contrarian)
        if features.vix_regime >= 3:  # High/Extreme
            score += 5 if features.is_long else -5
        elif features.vix_regime <= 1:  # Low
            score += -5 if features.is_long else 5

        # Volume confirmation bonus
        if features.candle_volume_confirmed:
            score += 5

        # Fresh zone bonus
        if features.zone_freshness == 0:
            score += 5

        # Time of day effect (avoid first/last 30 min)
        if features.minutes_to_close < 30 or features.hour_of_day < 10:
            score -= 10

        score = max(0, min(100, score))

        return MLPrediction(
            win_probability=score,
            expected_rr=1.5,
            confidence=30,  # Low confidence for rule-based
            top_features=[('zone_confidence', 0.3), ('candle_strength', 0.2)],
            model_type='rule_based',
            training_samples=0,
            feature_count=len(TradeFeatures.feature_names()),
        )

    def save_model(self, path: str) -> None:
        """Save trained model to disk."""
        if not self.is_trained:
            raise ValueError("Model not trained yet")

        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'model_type': self.model_type,
            'metrics': self.training_metrics,
        }

        with open(path, 'wb') as f:
            pickle.dump(model_data, f)

    def load_model(self, path: str) -> None:
        """Load trained model from disk."""
        with open(path, 'rb') as f:
            model_data = pickle.load(f)

        self.model = model_data['model']
        self.scaler = model_data['scaler']
        self.model_type = model_data['model_type']
        self.training_metrics = model_data['metrics']
        self.is_trained = True

    def get_feature_importance(self) -> List[Tuple[str, float]]:
        """Get feature importance ranking."""
        if not self.is_trained or not hasattr(self.model, 'feature_importances_'):
            return []

        importances = self.model.feature_importances_
        feature_names = TradeFeatures.feature_names()

        return sorted(
            zip(feature_names, importances),
            key=lambda x: x[1],
            reverse=True
        )


def generate_synthetic_training_data(n_samples: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate synthetic training data for model development.

    In production, this would be replaced with actual historical trade data.
    """
    np.random.seed(42)

    features = []
    labels = []

    for _ in range(n_samples):
        # Generate random features
        zone_confidence = np.random.uniform(30, 100)
        zone_strength = np.random.randint(1, 5)
        zone_freshness = np.random.randint(0, 5)
        zone_height_atr = np.random.uniform(0.5, 2.5)

        candle_strength = np.random.uniform(20, 100)
        candle_volume_confirmed = np.random.randint(0, 2)
        candle_body_ratio = np.random.uniform(0.1, 0.9)
        candle_wick_ratio = np.random.uniform(0.1, 0.7)

        vix_level = np.random.uniform(12, 40)
        vix_regime = np.random.randint(0, 5)
        vix_percentile = np.random.uniform(10, 90)
        vix_divergence = np.random.randint(-1, 2)

        put_call_ratio = np.random.uniform(0.6, 1.5)
        distance_to_max_pain = np.random.uniform(-3, 3)
        is_pinned = np.random.randint(0, 2)

        hour_of_day = np.random.randint(9, 16)
        day_of_week = np.random.randint(0, 5)
        minutes_to_close = np.random.randint(30, 390)

        price_change_5bar = np.random.uniform(-3, 3)
        price_change_20bar = np.random.uniform(-5, 5)
        rsi_14 = np.random.uniform(20, 80)
        atr_percentile = np.random.uniform(20, 80)

        is_long = np.random.randint(0, 2)

        # Create feature object
        trade_features = TradeFeatures(
            zone_confidence=zone_confidence,
            zone_strength=zone_strength,
            zone_freshness=zone_freshness,
            zone_height_atr=zone_height_atr,
            candle_strength=candle_strength,
            candle_volume_confirmed=candle_volume_confirmed,
            candle_body_ratio=candle_body_ratio,
            candle_wick_ratio=candle_wick_ratio,
            vix_level=vix_level,
            vix_regime=vix_regime,
            vix_percentile=vix_percentile,
            vix_divergence=vix_divergence,
            put_call_ratio=put_call_ratio,
            distance_to_max_pain=distance_to_max_pain,
            is_pinned=is_pinned,
            hour_of_day=hour_of_day,
            day_of_week=day_of_week,
            minutes_to_close=minutes_to_close,
            price_change_5bar=price_change_5bar,
            price_change_20bar=price_change_20bar,
            rsi_14=rsi_14,
            atr_percentile=atr_percentile,
            is_long=is_long,
        )

        features.append(trade_features.to_array())

        # Generate label based on logical rules (simulating real outcomes)
        win_prob = 0.5

        # Zone quality effect
        win_prob += (zone_confidence - 50) / 200
        win_prob += (zone_strength - 2) / 10
        win_prob -= zone_freshness / 20

        # Candle confirmation effect
        win_prob += (candle_strength - 50) / 200
        win_prob += candle_volume_confirmed * 0.05

        # VIX effect (contrarian for longs)
        if is_long and vix_regime >= 3:
            win_prob += 0.1
        elif not is_long and vix_regime <= 1:
            win_prob += 0.1

        # Time effect
        if minutes_to_close < 30:
            win_prob -= 0.15

        # Add noise
        win_prob += np.random.normal(0, 0.1)
        win_prob = max(0, min(1, win_prob))

        labels.append(1 if np.random.random() < win_prob else 0)

    return np.array(features), np.array(labels)


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    print("=== ML SCORER TEST ===\n")

    # Generate synthetic data
    print("Generating synthetic training data...")
    X, y = generate_synthetic_training_data(2000)
    print(f"Generated {len(X)} samples")
    print(f"Win rate in data: {y.mean() * 100:.1f}%")

    # Train model
    print("\nTraining Gradient Boosting model...")
    scorer = MLScorer(model_type='gradient_boosting')
    metrics = scorer.train(X, y)

    print(f"\nTraining Metrics:")
    print(f"  Accuracy: {metrics['accuracy']:.3f}")
    print(f"  Precision: {metrics['precision']:.3f}")
    print(f"  Recall: {metrics['recall']:.3f}")
    print(f"  F1 Score: {metrics['f1']:.3f}")
    print(f"  CV Score: {metrics['cv_mean']:.3f} ± {metrics['cv_std']:.3f}")

    # Feature importance
    print("\nTop Feature Importances:")
    for name, importance in scorer.get_feature_importance()[:10]:
        print(f"  {name}: {importance:.4f}")

    # Make a prediction
    print("\n=== SAMPLE PREDICTION ===")
    sample_features = TradeFeatures(
        zone_confidence=75,
        zone_strength=3,
        zone_freshness=0,
        zone_height_atr=1.2,
        candle_strength=70,
        candle_volume_confirmed=1,
        candle_body_ratio=0.6,
        candle_wick_ratio=0.3,
        vix_level=22,
        vix_regime=2,
        vix_percentile=60,
        vix_divergence=1,
        put_call_ratio=1.1,
        distance_to_max_pain=0.5,
        is_pinned=0,
        hour_of_day=11,
        day_of_week=2,
        minutes_to_close=180,
        price_change_5bar=-0.5,
        price_change_20bar=-1.2,
        rsi_14=35,
        atr_percentile=55,
        is_long=1,
    )

    prediction = scorer.predict(sample_features)

    print(f"Win Probability: {prediction.win_probability:.1f}%")
    print(f"Expected R:R: {prediction.expected_rr:.1f}")
    print(f"Confidence: {prediction.confidence:.1f}%")
    print(f"Should Trade: {prediction.should_trade}")
    print(f"Edge: {prediction.edge:.3f}")
    print(f"\nTop Contributing Features:")
    for name, imp in prediction.top_features:
        print(f"  {name}: {imp:.4f}")
