"""Backtest Engine and Strategy Base Class

This module provides the core backtesting infrastructure for the automated trading system.
It includes a base strategy class and a backtest engine that simulates trading scenarios
with mocked data for demonstration purposes.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from abc import ABC, abstractmethod
import logging


class TradingStrategy(ABC):
    """Abstract base class for trading strategies.
    
    All trading strategies must implement the generate_signals method.
    """
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"strategy.{name}")
    
    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate trading signals based on market data.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with signals column (1 for buy, -1 for sell, 0 for hold)
        """
        pass


class SimpleMovingAverageStrategy(TradingStrategy):
    """Simple Moving Average crossover strategy.
    
    Generates buy signals when short MA crosses above long MA,
    and sell signals when short MA crosses below long MA.
    """
    
    def __init__(self, short_window: int = 20, long_window: int = 50):
        super().__init__("SMA_Crossover")
        self.short_window = short_window
        self.long_window = long_window
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate SMA crossover signals."""
        signals = data.copy()
        
        # Calculate moving averages
        signals['sma_short'] = data['close'].rolling(window=self.short_window).mean()
        signals['sma_long'] = data['close'].rolling(window=self.long_window).mean()
        
        # Generate signals
        signals['signal'] = 0
        signals['signal'][self.short_window:] = np.where(
            signals['sma_short'][self.short_window:] > signals['sma_long'][self.short_window:], 1, 0
        )
        
        # Convert to position changes
        signals['positions'] = signals['signal'].diff()
        
        return signals


class BacktestEngine:
    """Backtesting engine for trading strategies.
    
    Simulates trading with historical data and calculates performance metrics.
    """
    
    def __init__(self, initial_capital: float = 100000.0, commission: float = 0.001):
        """
        Initialize the backtest engine.
        
        Args:
            initial_capital: Starting capital for backtesting
            commission: Commission rate per trade (e.g., 0.001 = 0.1%)
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.logger = logging.getLogger("backtest_engine")
        
    def generate_mock_data(self, symbol: str, days: int = 252) -> pd.DataFrame:
        """Generate mock OHLCV data for backtesting.
        
        Args:
            symbol: Stock symbol
            days: Number of days of data to generate
            
        Returns:
            DataFrame with OHLCV data
        """
        # Set random seed for reproducible results
        np.random.seed(42)
        
        # Generate dates
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        
        # Generate price data with random walk
        initial_price = 100.0
        returns = np.random.normal(0.001, 0.02, len(dates))  # Daily returns
        
        prices = [initial_price]
        for ret in returns[1:]:
            prices.append(prices[-1] * (1 + ret))
        
        # Create OHLCV data
        data = []
        for i, (date, price) in enumerate(zip(dates, prices)):
            # Generate realistic OHLC from close price
            volatility = np.random.uniform(0.005, 0.03)
            high = price * (1 + volatility * np.random.uniform(0, 1))
            low = price * (1 - volatility * np.random.uniform(0, 1))
            open_price = prices[i-1] if i > 0 else price
            volume = int(np.random.uniform(1000000, 5000000))
            
            data.append({
                'date': date,
                'symbol': symbol,
                'open': open_price,
                'high': high,
                'low': low,
                'close': price,
                'volume': volume
            })
        
        df = pd.DataFrame(data)
        df.set_index('date', inplace=True)
        return df
    
    def run_backtest(self, strategy: TradingStrategy, data: pd.DataFrame) -> Dict:
        """Run backtest for a given strategy and data.
        
        Args:
            strategy: Trading strategy to test
            data: Historical OHLCV data
            
        Returns:
            Dictionary containing backtest results
        """
        self.logger.info(f"Starting backtest for strategy: {strategy.name}")
        
        # Generate signals
        signals = strategy.generate_signals(data)
        
        # Initialize portfolio
        portfolio = self._simulate_portfolio(signals)
        
        # Calculate performance metrics
        metrics = self._calculate_metrics(portfolio, signals)
        
        results = {
            'strategy': strategy.name,
            'signals': signals,
            'portfolio': portfolio,
            'metrics': metrics
        }
        
        self.logger.info(f"Backtest completed. Total return: {metrics['total_return']:.2%}")
        return results
    
    def _simulate_portfolio(self, signals: pd.DataFrame) -> pd.DataFrame:
        """Simulate portfolio performance based on signals."""
        portfolio = signals.copy()
        
        # Initialize portfolio columns
        portfolio['holdings'] = 0
        portfolio['cash'] = self.initial_capital
        portfolio['total'] = self.initial_capital
        portfolio['returns'] = 0
        
        # Track current position
        current_position = 0
        cash = self.initial_capital
        
        for i, (date, row) in enumerate(portfolio.iterrows()):
            if i == 0:
                continue
                
            # Check for position changes
            if 'positions' in row and row['positions'] != 0:
                if row['positions'] > 0 and current_position == 0:  # Buy signal
                    # Buy as many shares as possible
                    shares_to_buy = int(cash / (row['close'] * (1 + self.commission)))
                    cost = shares_to_buy * row['close'] * (1 + self.commission)
                    
                    if shares_to_buy > 0:
                        current_position = shares_to_buy
                        cash -= cost
                        self.logger.debug(f"Buy: {shares_to_buy} shares at ${row['close']:.2f}")
                        
                elif row['positions'] < 0 and current_position > 0:  # Sell signal
                    # Sell all shares
                    proceeds = current_position * row['close'] * (1 - self.commission)
                    cash += proceeds
                    self.logger.debug(f"Sell: {current_position} shares at ${row['close']:.2f}")
                    current_position = 0
            
            # Update portfolio values
            holdings_value = current_position * row['close']
            total_value = cash + holdings_value
            
            portfolio.loc[date, 'holdings'] = holdings_value
            portfolio.loc[date, 'cash'] = cash
            portfolio.loc[date, 'total'] = total_value
            portfolio.loc[date, 'returns'] = (total_value / self.initial_capital) - 1
        
        return portfolio
    
    def _calculate_metrics(self, portfolio: pd.DataFrame, signals: pd.DataFrame) -> Dict:
        """Calculate performance metrics."""
        total_return = portfolio['returns'].iloc[-1]
        
        # Calculate daily returns
        daily_returns = portfolio['total'].pct_change().dropna()
        
        # Risk metrics
        volatility = daily_returns.std() * np.sqrt(252)  # Annualized
        sharpe_ratio = (daily_returns.mean() * 252) / volatility if volatility > 0 else 0
        
        # Drawdown
        running_max = portfolio['total'].expanding().max()
        drawdown = (portfolio['total'] - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # Trade statistics
        trades = signals[signals['positions'] != 0]
        num_trades = len(trades)
        
        return {
            'total_return': total_return,
            'annualized_return': (1 + total_return) ** (252 / len(portfolio)) - 1,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'num_trades': num_trades,
            'final_value': portfolio['total'].iloc[-1]
        }


def main():
    """Demonstration of the backtest engine."""
    # Set up logging
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Create backtest engine
    engine = BacktestEngine(initial_capital=100000, commission=0.001)
    
    # Generate mock data
    data = engine.generate_mock_data('AAPL', days=252)
    print(f"Generated {len(data)} days of mock data")
    print(data.head())
    
    # Create and test strategy
    strategy = SimpleMovingAverageStrategy(short_window=20, long_window=50)
    
    # Run backtest
    results = engine.run_backtest(strategy, data)
    
    # Print results
    print(f"\n=== Backtest Results for {results['strategy']} ===")
    metrics = results['metrics']
    print(f"Total Return: {metrics['total_return']:.2%}")
    print(f"Annualized Return: {metrics['annualized_return']:.2%}")
    print(f"Volatility: {metrics['volatility']:.2%}")
    print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
    print(f"Max Drawdown: {metrics['max_drawdown']:.2%}")
    print(f"Number of Trades: {metrics['num_trades']}")
    print(f"Final Portfolio Value: ${metrics['final_value']:,.2f}")


if __name__ == "__main__":
    main()
