"""
Test suite for the trading system core components
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.omega_wrapper import TradingApp, Contract, omega_trades_from_zipline
from core.backtest_engine import BacktestEngine
from core.position_manager import PositionManager
from core.order_executor import OrderExecutor
from core.risk_manager import RiskManager


class TestOmegaWrapper:
    """Test Omega wrapper functionality"""
    
    def test_trading_app_connection(self):
        """Test TradingApp initialization and connection"""
        app = TradingApp(broker='IBKR', paper_trading=True)
        assert app.connected == True
        assert app.broker == 'IBKR'
        assert app.paper_trading == True
    
    def test_get_positions(self):
        """Test getting positions from broker"""
        app = TradingApp(paper_trading=True)
        positions = app.get_positions()
        assert isinstance(positions, list)
        assert len(positions) > 0
        assert 'symbol' in positions[0]
    
    def test_get_account_value(self):
        """Test getting account value"""
        app = TradingApp(paper_trading=True)
        account_value = app.get_account_value()
        assert isinstance(account_value, float)
        assert account_value > 0
    
    def test_contract_creation(self):
        """Test Contract object creation"""
        contract = Contract('AAPL', 'NASDAQ', 'USD', 'STK')
        assert contract.symbol == 'AAPL'
        assert contract.exchange == 'NASDAQ'
        assert contract.currency == 'USD'
        assert contract.sec_type == 'STK'
    
    def test_omega_trades_conversion(self):
        """Test converting backtest orders to Omega format"""
        backtest_orders = pd.DataFrame({
            'symbol': ['AAPL', 'GOOGL'],
            'desired_allocation': [0.1, 0.15],
            'action': ['BUY', 'BUY'],
            'quantity': [100, 50],
            'order_type': ['market', 'limit'],
            'limit_price': [None, 2800.0]
        })
        
        omega_orders = omega_trades_from_zipline(backtest_orders)
        assert len(omega_orders) == 2
        assert omega_orders[0]['symbol'] == 'AAPL'
        assert omega_orders[0]['desired_allocation'] == 0.1


class TestBacktestEngine:
    """Test backtest engine functionality"""
    
    def test_backtest_engine_init(self):
        """Test BacktestEngine initialization"""
        engine = BacktestEngine('Test_Strategy', lookback_days=100)
        assert engine.strategy_name == 'Test_Strategy'
        assert engine.lookback_days == 100
    
    def test_run_backtest(self):
        """Test running a backtest"""
        engine = BacktestEngine('Test_Strategy')
        orders = engine.run_backtest()
        
        assert isinstance(orders, pd.DataFrame)
        assert len(orders) > 0
        assert 'symbol' in orders.columns
        assert 'desired_allocation' in orders.columns
        assert 'confidence_score' in orders.columns
    
    def test_calculate_metrics(self):
        """Test backtest metrics calculation"""
        engine = BacktestEngine('Test_Strategy')
        
        # Create sample returns
        returns = pd.Series(np.random.normal(0.001, 0.02, 252))
        metrics = engine.calculate_metrics(returns)
        
        assert 'total_return' in metrics
        assert 'sharpe_ratio' in metrics
        assert 'max_drawdown' in metrics
        assert isinstance(metrics['sharpe_ratio'], float)


class TestPositionManager:
    """Test position manager functionality"""
    
    @pytest.fixture
    def position_manager(self):
        """Create a position manager for testing"""
        app = TradingApp(paper_trading=True)
        return PositionManager(app)
    
    def test_get_current_symbols(self, position_manager):
        """Test getting current position symbols"""
        symbols = position_manager.get_current_symbols()
        assert isinstance(symbols, set)
        assert len(symbols) > 0
    
    def test_get_target_symbols(self, position_manager):
        """Test getting target symbols from orders"""
        orders = pd.DataFrame({
            'symbol': ['NVDA', 'AMD', 'TSM'],
            'desired_allocation': [0.2, 0.15, 0.1]
        })
        
        target_symbols = position_manager.get_target_symbols(orders)
        assert target_symbols == {'NVDA', 'AMD', 'TSM'}
    
    def test_identify_liquidations(self, position_manager):
        """Test identifying positions to liquidate"""
        current = {'AAPL', 'GOOGL', 'MSFT'}
        target = {'NVDA', 'AMD', 'GOOGL'}
        
        to_liquidate = position_manager.identify_liquidations(current, target)
        assert to_liquidate == {'AAPL', 'MSFT'}


class TestOrderExecutor:
    """Test order executor functionality"""
    
    @pytest.fixture
    def order_executor(self):
        """Create an order executor for testing"""
        app = TradingApp(paper_trading=True)
        return OrderExecutor(app, max_position_size=0.25)
    
    def test_validate_allocation(self, order_executor):
        """Test allocation validation"""
        # Test normal allocation
        allocation = order_executor.validate_allocation(0.15)
        assert allocation == 0.15
        
        # Test allocation over limit
        allocation = order_executor.validate_allocation(0.35)
        assert allocation == 0.25  # Should be capped at max
    
    def test_execute_orders(self, order_executor):
        """Test order execution"""
        orders = [
            {
                'symbol': 'AAPL',
                'desired_allocation': 0.1,
                'type': 'market'
            },
            {
                'symbol': 'GOOGL', 
                'desired_allocation': 0.15,
                'type': 'limit',
                'limit_price': 2800.0
            }
        ]
        
        successful, failed = order_executor.execute_orders(orders)
        assert successful == 2
        assert failed == 0


class TestRiskManager:
    """Test risk manager functionality"""
    
    @pytest.fixture
    def risk_manager(self):
        """Create a risk manager for testing"""
        return RiskManager(
            max_drawdown=0.2,
            position_limit=10,
            sector_limit=0.3
        )
    
    def test_calculate_kelly_criterion(self, risk_manager):
        """Test Kelly Criterion calculation"""
        kelly = risk_manager.calculate_kelly_criterion(
            win_rate=0.6,
            avg_win=0.03,
            avg_loss=0.02
        )
        
        assert isinstance(kelly, float)
        assert 0 <= kelly <= 0.25  # Should be capped at 25%
    
    def test_check_risk_limits(self, risk_manager):
        """Test risk limit checking"""
        orders = pd.DataFrame({
            'symbol': [f'STOCK_{i}' for i in range(15)],  # More than limit
            'desired_allocation': [0.08] * 15,  # 8% each = 120% total
            'confidence_score': np.random.uniform(0.6, 0.9, 15)
        })
        
        adjusted_orders = risk_manager.check_risk_limits(orders)
        
        # Should be limited to position_limit
        assert len(adjusted_orders) == risk_manager.position_limit
        
        # Total allocation should be <= max_portfolio_allocation
        total_allocation = adjusted_orders['desired_allocation'].sum()
        assert total_allocation <= 0.95
    
    def test_emergency_stop_check(self, risk_manager):
        """Test emergency stop functionality"""
        # Normal drawdown
        assert risk_manager.emergency_stop_check(0.05) == False
        
        # Excessive drawdown
        assert risk_manager.emergency_stop_check(0.25) == True


class TestIntegration:
    """Integration tests for complete workflow"""
    
    def test_full_trading_workflow(self):
        """Test the complete trading workflow"""
        # Initialize components
        app = TradingApp(paper_trading=True)
        backtest_engine = BacktestEngine('Test_Strategy')
        position_manager = PositionManager(app)
        order_executor = OrderExecutor(app)
        risk_manager = RiskManager()
        
        # Step 1: Run backtest
        backtest_orders = backtest_engine.run_backtest()
        assert len(backtest_orders) > 0
        
        # Step 2: Apply risk management
        risk_adjusted_orders = risk_manager.check_risk_limits(backtest_orders)
        assert len(risk_adjusted_orders) <= len(backtest_orders)
        
        # Step 3: Convert to Omega format
        omega_orders = omega_trades_from_zipline(risk_adjusted_orders)
        assert len(omega_orders) == len(risk_adjusted_orders)
        
        # Step 4: Execute orders
        successful, failed = order_executor.execute_orders(omega_orders)
        assert successful > 0
        assert failed == 0


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
