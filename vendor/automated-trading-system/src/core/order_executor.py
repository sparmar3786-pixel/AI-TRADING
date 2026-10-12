"""
Order Executor
Handles order execution logic and validation
"""

import logging
from typing import Dict, List, Tuple
from .omega_wrapper import TradingApp, Contract

logger = logging.getLogger(__name__)


class OrderExecutor:
    """Handles order execution logic"""
    
    def __init__(self, app: TradingApp, 
                 max_position_size: float = 0.30,
                 use_limit_orders: bool = True):
        self.app = app
        self.max_position_size = max_position_size
        self.use_limit_orders = use_limit_orders
        self.order_history = []
    
    def validate_allocation(self, allocation: float) -> float:
        """Ensure allocation doesn't exceed max position size"""
        if allocation > self.max_position_size:
            logger.warning(f"Allocation {allocation:.3f} exceeds max {self.max_position_size:.3f}")
            return self.max_position_size
        return allocation
    
    def execute_orders(self, omega_orders: List[Dict]) -> Tuple[int, int]:
        """Execute list of orders"""
        successful = 0
        failed = 0
        executed_orders = []
        
        for order in omega_orders:
            try:
                symbol = order['symbol']
                allocation = self.validate_allocation(order['desired_allocation'])
                
                contract = Contract(symbol=symbol)
                
                # Determine order type
                order_type = order.get('type', 'market')
                if self.use_limit_orders and order_type == 'limit':
                    limit_price = order.get('limit_price')
                else:
                    order_type = 'market'
                    limit_price = None
                
                # Submit order
                executed_order = self.app.order_target_percent(
                    contract,
                    percent=allocation,
                    order_type=order_type,
                    limit_price=limit_price
                )
                
                executed_orders.append(executed_order)
                successful += 1
                logger.info(f"Order submitted: {symbol} @ {allocation*100:.2f}%")
                
            except Exception as e:
                failed += 1
                logger.error(f"Failed to execute order for {symbol}: {e}")
        
        # Store order history
        self.order_history.extend(executed_orders)
        
        logger.info(f"Order execution complete: {successful} successful, {failed} failed")
        return successful, failed
    
    def execute_single_order(self, symbol: str, allocation: float, 
                           order_type: str = 'market', limit_price: float = None) -> bool:
        """Execute a single order"""
        try:
            allocation = self.validate_allocation(allocation)
            contract = Contract(symbol=symbol)
            
            order = self.app.order_target_percent(
                contract,
                percent=allocation,
                order_type=order_type,
                limit_price=limit_price
            )
            
            self.order_history.append(order)
            logger.info(f"Single order executed: {symbol} @ {allocation*100:.2f}%")
            return True
            
        except Exception as e:
            logger.error(f"Failed to execute single order for {symbol}: {e}")
            return False
    
    def cancel_pending_orders(self, symbol: str = None) -> int:
        """
        Cancel pending orders (mock implementation)
        In real implementation, this would cancel actual pending orders
        """
        # Mock cancellation logic
        cancelled_count = 0
        
        if symbol:
            logger.info(f"Cancelling pending orders for {symbol}")
            cancelled_count = 1  # Mock
        else:
            logger.info("Cancelling all pending orders")
            cancelled_count = 3  # Mock
        
        logger.info(f"Cancelled {cancelled_count} pending orders")
        return cancelled_count
    
    def get_order_status(self, order_id: str = None) -> List[Dict]:
        """
        Get status of orders (mock implementation)
        In real implementation, this would query actual order status
        """
        # Mock order status
        if order_id:
            return [{'order_id': order_id, 'status': 'filled', 'filled_qty': 100}]
        else:
            return [
                {'order_id': 'order_1', 'status': 'filled', 'filled_qty': 100},
                {'order_id': 'order_2', 'status': 'pending', 'filled_qty': 0},
                {'order_id': 'order_3', 'status': 'cancelled', 'filled_qty': 0}
            ]
    
    def validate_orders_before_execution(self, orders: List[Dict]) -> List[Dict]:
        """Validate orders before execution"""
        valid_orders = []
        
        for order in orders:
            # Basic validation
            if not order.get('symbol'):
                logger.warning("Skipping order without symbol")
                continue
            
            if order.get('desired_allocation', 0) <= 0:
                logger.warning(f"Skipping order with invalid allocation: {order.get('symbol')}")
                continue
            
            if order.get('desired_allocation', 0) > 1.0:
                logger.warning(f"Capping allocation for {order.get('symbol')} at 100%")
                order['desired_allocation'] = 1.0
            
            valid_orders.append(order)
        
        logger.info(f"Validated {len(valid_orders)} out of {len(orders)} orders")
        return valid_orders
