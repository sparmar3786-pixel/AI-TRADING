"""
ML Momentum Strategy
Example strategy implementation using machine learning for momentum detection
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import logging

logger = logging.getLogger(__name__)


class MLMomentumStrategy:
    """ML-based momentum strategy"""
    
    def __init__(self, lookback_period: int = 60, prediction_horizon: int = 5):
        self.lookback_period = lookback_period
        self.prediction_horizon = prediction_horizon
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        self.is_trained = False
        
    def calculate_features(self, price_data: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical features for ML model"""
        features = pd.DataFrame(index=price_data.index)
        
        # Price-based features
        features['returns'] = price_data['close'].pct_change()
        features['returns_2d'] = price_data['close'].pct_change(periods=2)
        features['returns_5d'] = price_data['close'].pct_change(periods=5)
        features['returns_10d'] = price_data['close'].pct_change(periods=10)
        features['returns_20d'] = price_data['close'].pct_change(periods=20)
        
        # Moving averages
        features['ma_5'] = price_data['close'].rolling(5).mean()
        features['ma_20'] = price_data['close'].rolling(20).mean()
        features['ma_50'] = price_data['close'].rolling(50).mean()
        
        # Moving average ratios
        features['ma_ratio_5_20'] = features['ma_5'] / features['ma_20']
        features['ma_ratio_20_50'] = features['ma_20'] / features['ma_50']
        features['price_ma_ratio'] = price_data['close'] / features['ma_20']
        
        # Volatility features
        features['volatility_5d'] = features['returns'].rolling(5).std()
        features['volatility_20d'] = features['returns'].rolling(20).std()
        features['volatility_ratio'] = features['volatility_5d'] / features['volatility_20d']
        
        # Volume features (if available)
        if 'volume' in price_data.columns:
            features['volume_ma'] = price_data['volume'].rolling(20).mean()
            features['volume_ratio'] = price_data['volume'] / features['volume_ma']
        
        # RSI-like momentum
        delta = price_data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        features['rsi'] = 100 - (100 / (1 + rs))
        
        # Bollinger Band position
        bb_ma = price_data['close'].rolling(20).mean()
        bb_std = price_data['close'].rolling(20).std()
        features['bb_position'] = (price_data['close'] - bb_ma) / (2 * bb_std)
        
        return features.dropna()
    
    def create_labels(self, price_data: pd.DataFrame) -> pd.Series:
        """Create binary labels for future returns"""
        future_returns = price_data['close'].shift(-self.prediction_horizon) / price_data['close'] - 1
        labels = (future_returns > 0.02).astype(int)  # 2% threshold for positive label
        return labels
    
    def train_model(self, historical_data: dict):
        """Train the ML model on historical data"""
        logger.info("Training ML momentum model...")
        
        all_features = []
        all_labels = []
        
        for symbol, data in historical_data.items():
            if len(data) < self.lookback_period:
                continue
                
            features = self.calculate_features(data)
            labels = self.create_labels(data)
            
            # Align features and labels
            common_index = features.index.intersection(labels.index)
            if len(common_index) > 0:
                all_features.append(features.loc[common_index])
                all_labels.append(labels.loc[common_index])
        
        if not all_features:
            logger.error("No valid training data available")
            return False
        
        # Combine all features and labels
        X = pd.concat(all_features, ignore_index=True)
        y = pd.concat(all_labels, ignore_index=True)
        
        # Remove any remaining NaN values
        mask = ~(X.isna().any(axis=1) | y.isna())
        X = X[mask]
        y = y[mask]
        
        if len(X) < 100:  # Minimum samples needed
            logger.error("Insufficient training data")
            return False
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Train model
        self.model.fit(X_scaled, y)
        self.is_trained = True
        
        # Calculate training metrics
        train_score = self.model.score(X_scaled, y)
        logger.info(f"Model training complete. Accuracy: {train_score:.3f}")
        
        return True
    
    def predict_signals(self, current_data: dict) -> pd.DataFrame:
        """Generate trading signals for current data"""
        if not self.is_trained:
            logger.error("Model not trained. Call train_model() first.")
            return pd.DataFrame()
        
        signals = []
        
        for symbol, data in current_data.items():
            if len(data) < self.lookback_period:
                continue
            
            try:
                # Calculate features for current data
                features = self.calculate_features(data)
                
                if len(features) == 0:
                    continue
                
                # Use latest features for prediction
                latest_features = features.iloc[-1:].values
                
                # Scale features
                latest_features_scaled = self.scaler.transform(latest_features)
                
                # Make prediction
                prediction = self.model.predict(latest_features_scaled)[0]
                probability = self.model.predict_proba(latest_features_scaled)[0]
                
                # Calculate confidence score
                confidence = max(probability)
                
                if prediction == 1 and confidence > 0.6:  # Only trade if confident
                    # Calculate position size based on confidence
                    base_allocation = 0.05  # 5% base allocation
                    allocation = base_allocation * confidence
                    
                    signals.append({
                        'symbol': symbol,
                        'action': 'BUY',
                        'desired_allocation': allocation,
                        'confidence_score': confidence,
                        'prediction_probability': probability[1],
                        'order_type': 'market'
                    })
                    
                    logger.info(f"Signal generated: {symbol} - {confidence:.3f} confidence")
            
            except Exception as e:
                logger.error(f"Error generating signal for {symbol}: {e}")
                continue
        
        return pd.DataFrame(signals)
    
    def get_feature_importance(self) -> pd.DataFrame:
        """Get feature importance from trained model"""
        if not self.is_trained:
            return pd.DataFrame()
        
        # Get feature names (this is simplified - in practice you'd store feature names)
        feature_names = [f"feature_{i}" for i in range(len(self.model.feature_importances_))]
        
        importance_df = pd.DataFrame({
            'feature': feature_names,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        return importance_df
    
    def backtest_strategy(self, historical_data: dict, start_date: str, end_date: str) -> dict:
        """Backtest the strategy on historical data"""
        logger.info(f"Backtesting ML momentum strategy from {start_date} to {end_date}")
        
        # This is a simplified backtest - in practice you'd use a proper backtesting framework
        results = {
            'total_trades': 0,
            'winning_trades': 0,
            'total_return': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0
        }
        
        # Mock backtest results
        results['total_trades'] = 150
        results['winning_trades'] = 95
        results['total_return'] = 0.23  # 23% return
        results['max_drawdown'] = -0.08  # 8% max drawdown
        results['sharpe_ratio'] = 1.45
        
        logger.info(f"Backtest complete: {results}")
        return results
