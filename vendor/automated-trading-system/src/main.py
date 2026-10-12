"""
Automated Trading System with Omega Integration
Based on Quant Science methodology for running automated hedge fund strategies
"""

import os
import pickle
import logging
import pandas as pd
import numpy as np
from datetime import datetime, time
from typing import Dict, List, Any, Optional
import schedule
import time as time_module

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_system.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== Omega Library Wrapper ====================
class Omega:
    """Mock Omega library structure based on video description"""
    
    class TradingApp:
        def __init__(self, api_key: str = None, api_secret: str = None, 
                     broker: str = 'IBKR', paper_trading: bool = True):
            """Initialize connection to broker"""
            self.api_key = api_key or os.getenv('BROKER_API_KEY')
            self.api_secret = api_secret or os.getenv('BROKER_API_SECRET')
            self.broker = broker
            self.paper_trading = paper_trading
            self.connected = False
            self._connect()
        
        def _connect(self):
            """Establish connection to broker API"""
            try:
                # In real implementation, this would connect to actual broker
                logger.info(f"Connecting to {self.broker}...")
                self.connected = True
                logger.info("Successfully connected to broker")
            except Exception as e:
                logger.error(f"Failed to connect to broker: {e}")
                raise
        
        def get_positions(self) -> List[Dict]:
            """Fetch current portfolio positions"""
            if not self.connected:
                raise ConnectionError("Not connected to broker")
            
            # Mock positions - replace with actual broker API call
            positions = [
                {'symbol': 'AAPL', 'quantity': 100, 'avg_cost': 150.00},
                {'symbol': 'GOOGL', 'quantity': 50, 'avg_cost': 2800.00},
                {'symbol': 'MSFT', 'quantity': 75, 'avg_cost': 300.00}
            ]
            logger.info(f"Fetched {len(positions)} positions from broker")
            return positions
        
        def get_account_value(self) -> float:
            """Get total account value"""
            if not self.connected:
                raise ConnectionError("Not connected to broker")
            
            # Mock account value - replace with actual broker API call
            return 1000000.00
        
        def order_target_percent(self, contract: 'Contract', percent: float, 
                                order_type: str = 'market', limit_price: float = None):
            """
            Order to target a specific portfolio percentage
            percent=0.0 means liquidate position
            """
            try:
                account_value = self.get_account_value()
                target_value = account_value * percent
                
                if percent == 0.0:
                    logger.info(f"Liquidating position: {contract.symbol}")
                else:
                    logger.info(f"Adjusting {contract.symbol} to {percent*100:.2f}% of portfolio")
                
                # Mock order execution - replace with actual broker API call
                order = {
                    'symbol': contract.symbol,
                    'target_percent': percent,
                    'target_value': target_value,
                    'order_type': order_type,
                    'limit_price': limit_price,
                    'timestamp': datetime.now(),
                    'status': 'submitted'
                }
                
                return order
            except Exception as e:
                logger.error(f"Failed to submit order for {contract.symbol}: {e}")
                raise
    
    class Contract:
        """Contract/Asset representation"""
        def __init__(self, symbol: str, exchange: str = 'SMART', 
                     currency: str = 'USD', sec_type: str = 'STK'):
            self.symbol = symbol
            self.exchange = exchange
            self.currency = currency
            self.sec_type = sec_type
    
    @staticmethod
    def omega_trades_from_zipline(backtest_orders: pd.DataFrame) -> List[Dict]:
        """
        Convert Zipline/backtest orders to Omega format
        
        Args:
            backtest_orders: DataFrame with columns like 
                            [symbol, action, quantity, desired_allocation]
        
        Returns:
            List of Omega-formatted order dictionaries
        """
        omega_orders = []
        
        for idx, row in backtest_orders.iterrows():
            order = {
                'symbol': row['symbol'],
                'desired_allocation': row.get('desired_allocation', 0),
                'action': row.get('action', 'BUY'),
                'quantity': row.get('quantity', 0),
                'type': row.get('order_type', 'market'),
                'limit_price': row.get('limit_price', None),
                'stop_price': row.get('stop_price', None),
                'time_in_force': row.get('time_in_force', 'DAY')
            }
            omega_orders.append(order)
        
        logger.info(f"Converted {len(omega_orders)} orders from backtest format")
        return omega_orders


# ==================== Backtest Integration ====================
class BacktestEngine:
    """Engine for running nightly backtests"""
    
    def __init__(self, strategy_name: str, lookback_days: int = 252):
        self.strategy_name = strategy_name
        self.lookback_days = lookback_days
    
    def run_backtest(self) -> pd.DataFrame:
        """
        Run the backtest and generate order signals
        This would typically use Zipline, Backtrader, or custom engine
        """
        logger.info(f"Running backtest for strategy: {self.strategy_name}")
        
        # Mock backtest results - replace with actual backtest logic
        orders = pd.DataFrame({
            'symbol': ['NVDA', 'AMD', 'TSM', 'AVGO', 'QCOM'],
            'desired_allocation': [0.25, 0.20, 0.15, 0.10, 0.05],
            'action': ['BUY', 'BUY', 'BUY', 'BUY', 'BUY'],
            'quantity': [100, 150, 200, 50, 75],
            'order_type': ['market', 'limit', 'market', 'limit', 'market'],
            'limit_price': [None, 150.50, None, 900.00, None],
            'confidence_score': [0.85, 0.78, 0.82, 0.75, 0.71]
        })
        
        # Add timestamp
        orders['signal_date'] = datetime.now()
        
        logger.info(f"Backtest completed. Generated {len(orders)} signals")
        return orders
    
    def save_orders(self, orders: pd.DataFrame, filepath: str = 'data/backtest_results/backtest_orders.pkl'):
        """Save backtest orders to file"""
        output = {
            'orders': orders,
            'timestamp': datetime.now(),
            'strategy': self.strategy_name
        }
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'wb') as f:
            pickle.dump(output, f)
        
        logger.info(f"Saved backtest orders to {filepath}")


# ==================== Position Management ====================
class PositionManager:
    """Manages position reconciliation and liquidation"""
    
    def __init__(self, app: Omega.TradingApp):
        self.app = app
    
    def get_current_symbols(self) -> set:
        """Get set of symbols from current positions"""
        positions = self.app.get_positions()
        return {pos['symbol'] for pos in positions}
    
    def get_target_symbols(self, orders: pd.DataFrame) -> set:
        """Get set of symbols from target orders"""
        return set(orders['symbol'].tolist())
    
    def identify_liquidations(self, current: set, target: set) -> set:
        """Identify positions that need to be liquidated"""
        to_liquidate = current - target
        if to_liquidate:
            logger.info(f"Positions to liquidate: {to_liquidate}")
        return to_liquidate
    
    def liquidate_positions(self, symbols: set, order_type: str = 'market'):
        """Liquidate specified positions"""
        for symbol in symbols:
            try:
                contract = Omega.Contract(symbol=symbol)
                self.app.order_target_percent(
                    contract, 
                    percent=0.0, 
                    order_type=order_type
                )
                logger.info(f"Liquidation order submitted for {symbol}")
            except Exception as e:
                logger.error(f"Failed to liquidate {symbol}: {e}")


# ==================== Order Execution ====================
class OrderExecutor:
    """Handles order execution logic"""
    
    def __init__(self, app: Omega.TradingApp, 
                 max_position_size: float = 0.30,
                 use_limit_orders: bool = True):
        self.app = app
        self.max_position_size = max_position_size
        self.use_limit_orders = use_limit_orders
    
    def validate_allocation(self, allocation: float) -> float:
        """Ensure allocation doesn't exceed max position size"""
        if allocation > self.max_position_size:
            logger.warning(f"Allocation {allocation} exceeds max {self.max_position_size}")
            return self.max_position_size
        return allocation
    
    def execute_orders(self, omega_orders: List[Dict]):
        """Execute list of orders"""
        successful = 0
        failed = 0
        
        for order in omega_orders:
            try:
                symbol = order['symbol']
                allocation = self.validate_allocation(order['desired_allocation'])
                
                contract = Omega.Contract(symbol=symbol)
                
                # Determine order type
                order_type = order.get('type', 'market')
                if self.use_limit_orders and order_type == 'limit':
                    limit_price = order.get('limit_price')
                else:
                    order_type = 'market'
                    limit_price = None
                
                # Submit order
                self.app.order_target_percent(
                    contract,
                    percent=allocation,
                    order_type=order_type,
                    limit_price=limit_price
                )
                
                successful += 1
                logger.info(f"Order submitted: {symbol} @ {allocation*100:.2f}%")
                
            except Exception as e:
                failed += 1
                logger.error(f"Failed to execute order for {symbol}: {e}")
        
        logger.info(f"Order execution complete: {successful} successful, {failed} failed")
        return successful, failed


# ==================== Main Trading System ====================
class AutomatedTradingSystem:
    """Main system orchestrator"""
    
    def __init__(self, 
                 strategy_name: str = "ML_Momentum_Strategy",
                 broker: str = "IBKR",
                 paper_trading: bool = True):
        
        self.strategy_name = strategy_name
        self.broker = broker
        self.paper_trading = paper_trading
        
        # Initialize components
        self.app = None
        self.backtest_engine = BacktestEngine(strategy_name)
        self.position_manager = None
        self.order_executor = None
        
        # Performance tracking
        self.performance_history = []
    
    def initialize(self):
        """Initialize trading system components"""
        try:
            logger.info("Initializing Automated Trading System...")
            
            # Connect to broker
            self.app = Omega.TradingApp(
                broker=self.broker,
                paper_trading=self.paper_trading
            )
            
            # Initialize managers
            self.position_manager = PositionManager(self.app)
            self.order_executor = OrderExecutor(self.app)
            
            logger.info("System initialization complete")
            return True
            
        except Exception as e:
            logger.error(f"System initialization failed: {e}")
            return False
    
    def run_nightly_process(self):
        """Execute the complete nightly trading process"""
        try:
            logger.info("="*50)
            logger.info("Starting nightly trading process")
            logger.info(f"Timestamp: {datetime.now()}")
            
            # Step 1: Run backtest
            backtest_orders = self.backtest_engine.run_backtest()
            
            # Step 2: Save backtest results
            self.backtest_engine.save_orders(backtest_orders)
            
            # Step 3: Get current positions
            current_positions = self.position_manager.get_current_symbols()
            target_positions = self.position_manager.get_target_symbols(backtest_orders)
            
            # Step 4: Liquidate unwanted positions
            to_liquidate = self.position_manager.identify_liquidations(
                current_positions, 
                target_positions
            )
            if to_liquidate:
                self.position_manager.liquidate_positions(to_liquidate)
            
            # Step 5: Convert and execute new orders
            omega_orders = Omega.omega_trades_from_zipline(backtest_orders)
            successful, failed = self.order_executor.execute_orders(omega_orders)
            
            # Step 6: Log performance
            self.log_performance(successful, failed, len(to_liquidate))
            
            logger.info("Nightly trading process completed successfully")
            logger.info("="*50)
            
            return True
            
        except Exception as e:
            logger.error(f"Nightly process failed: {e}")
            self.send_alert(f"Trading system error: {e}")
            return False
    
    def log_performance(self, orders_successful: int, orders_failed: int, 
                       liquidations: int):
        """Track system performance"""
        performance = {
            'timestamp': datetime.now(),
            'orders_successful': orders_successful,
            'orders_failed': orders_failed,
            'liquidations': liquidations,
            'account_value': self.app.get_account_value()
        }
        self.performance_history.append(performance)
        
        # Ensure directory exists
        os.makedirs('data/performance', exist_ok=True)
        
        # Save to file
        pd.DataFrame(self.performance_history).to_csv(
            'data/performance/performance_history.csv', 
            index=False
        )
    
    def send_alert(self, message: str):
        """Send alert notifications (email, SMS, etc.)"""
        # Implement your notification logic here
        logger.critical(f"ALERT: {message}")
    
    def schedule_daily_run(self, run_time: str = "16:30"):
        """Schedule daily execution after market close"""
        schedule.every().day.at(run_time).do(self.run_nightly_process)
        
        logger.info(f"Scheduled daily run at {run_time}")
        
        while True:
            schedule.run_pending()
            time_module.sleep(60)  # Check every minute


# ==================== Risk Management ====================
class RiskManager:
    """Risk management and position sizing"""
    
    def __init__(self, 
                 max_drawdown: float = 0.20,
                 position_limit: int = 20,
                 sector_limit: float = 0.40):
        self.max_drawdown = max_drawdown
        self.position_limit = position_limit
        self.sector_limit = sector_limit
    
    def calculate_kelly_criterion(self, win_rate: float, avg_win: float, 
                                 avg_loss: float) -> float:
        """Calculate optimal position size using Kelly Criterion"""
        if avg_loss == 0:
            return 0
        
        b = avg_win / abs(avg_loss)
        p = win_rate
        q = 1 - p
        
        kelly = (p * b - q) / b
        
        # Apply Kelly fraction (typically 0.25 for safety)
        return max(0, min(kelly * 0.25, 0.25))
    
    def check_risk_limits(self, orders: pd.DataFrame) -> pd.DataFrame:
        """Apply risk management rules to orders"""
        # Limit number of positions
        if len(orders) > self.position_limit:
            logger.warning(f"Reducing positions from {len(orders)} to {self.position_limit}")
            orders = orders.nlargest(self.position_limit, 'confidence_score')
        
        # Normalize allocations
        total_allocation = orders['desired_allocation'].sum()
        if total_allocation > 0.95:  # Leave some cash
            orders['desired_allocation'] = orders['desired_allocation'] * 0.95 / total_allocation
        
        return orders


# ==================== Main Execution ====================
def main():
    """Main execution function"""
    # Configuration
    STRATEGY_NAME = "ML_Momentum_Strategy"
    BROKER = "IBKR"  # Interactive Brokers
    PAPER_TRADING = True  # Use paper trading for testing
    RUN_TIME = "16:30"  # Run at 4:30 PM after market close
    
    # Initialize system
    trading_system = AutomatedTradingSystem(
        strategy_name=STRATEGY_NAME,
        broker=BROKER,
        paper_trading=PAPER_TRADING
    )
    
    if not trading_system.initialize():
        logger.error("Failed to initialize trading system")
        return
    
    # Choose execution mode
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        # Run once immediately
        trading_system.run_nightly_process()
    else:
        # Schedule daily runs
        logger.info(f"Starting scheduled execution at {RUN_TIME} daily")
        trading_system.schedule_daily_run(RUN_TIME)


if __name__ == "__main__":
    main()
