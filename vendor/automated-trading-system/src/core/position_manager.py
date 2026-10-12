"""
Position Manager
Handles position reconciliation and liquidation
"""

import logging
import pandas as pd
from typing import Set
from .omega_wrapper import TradingApp, Contract

logger = logging.getLogger(__name__)


class PositionManager:
    """Manages position reconciliation and liquidation"""
    
    def __init__(self, app: TradingApp):
        self.app = app
    
    def get_current_symbols(self) -> Set[str]:
        """Get set of symbols from current positions"""
        positions = self.app.get_positions()
        return {pos['symbol'] for pos in positions}
    
    def get_target_symbols(self, orders: pd.DataFrame) -> Set[str]:
        """Get set of symbols from target orders"""
        return set(orders['symbol'].tolist())
    
    def identify_liquidations(self, current: Set[str], target: Set[str]) -> Set[str]:
        """Identify positions that need to be liquidated"""
        to_liquidate = current - target
        if to_liquidate:
            logger.info(f"Positions to liquidate: {to_liquidate}")
        return to_liquidate
    
    def liquidate_positions(self, symbols: Set[str], order_type: str = 'market'):
        """Liquidate specified positions"""
        liquidated = []
        failed = []
        
        for symbol in symbols:
            try:
                contract = Contract(symbol=symbol)
                self.app.order_target_percent(
                    contract, 
                    percent=0.0, 
                    order_type=order_type
                )
                liquidated.append(symbol)
                logger.info(f"Liquidation order submitted for {symbol}")
            except Exception as e:
                failed.append(symbol)
                logger.error(f"Failed to liquidate {symbol}: {e}")
        
        return liquidated, failed
    
    def get_position_details(self) -> pd.DataFrame:
        """Get detailed position information"""
        positions = self.app.get_positions()
        df = pd.DataFrame(positions)
        
        if not df.empty:
            # Calculate additional metrics
            df['market_value'] = df['quantity'] * df['avg_cost']  # Simplified
            df['weight'] = df['market_value'] / df['market_value'].sum()
        
        return df
    
    def check_position_limits(self, target_allocations: pd.DataFrame, 
                            max_position_size: float = 0.30) -> pd.DataFrame:
        """Check and adjust positions that exceed limits"""
        adjusted = target_allocations.copy()
        
        # Cap individual position sizes
        over_limit = adjusted['desired_allocation'] > max_position_size
        if over_limit.any():
            logger.warning(f"Capping {over_limit.sum()} positions at {max_position_size*100}%")
            adjusted.loc[over_limit, 'desired_allocation'] = max_position_size
        
        return adjusted
    
    def reconcile_positions(self, target_orders: pd.DataFrame) -> dict:
        """
        Reconcile current positions with target allocations
        Returns summary of changes needed
        """
        current_positions = self.get_position_details()
        current_symbols = set(current_positions['symbol']) if not current_positions.empty else set()
        target_symbols = set(target_orders['symbol'])
        
        reconciliation = {
            'current_positions': len(current_symbols),
            'target_positions': len(target_symbols),
            'to_liquidate': current_symbols - target_symbols,
            'to_add': target_symbols - current_symbols,
            'to_adjust': current_symbols & target_symbols,
            'total_changes': len((current_symbols - target_symbols) | (target_symbols - current_symbols))
        }
        
        logger.info(f"Position reconciliation: {reconciliation['total_changes']} total changes needed")
        return reconciliation
