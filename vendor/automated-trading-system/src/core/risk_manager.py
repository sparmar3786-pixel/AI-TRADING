"""
Risk Manager
Risk management and position sizing calculations
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List

logger = logging.getLogger(__name__)


class RiskManager:
    """Risk management and position sizing"""
    
    def __init__(self, 
                 max_drawdown: float = 0.20,
                 position_limit: int = 20,
                 sector_limit: float = 0.40,
                 max_portfolio_allocation: float = 0.95):
        self.max_drawdown = max_drawdown
        self.position_limit = position_limit
        self.sector_limit = sector_limit
        self.max_portfolio_allocation = max_portfolio_allocation
    
    def calculate_kelly_criterion(self, win_rate: float, avg_win: float, 
                                 avg_loss: float) -> float:
        """Calculate optimal position size using Kelly Criterion"""
        if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
            return 0
        
        b = avg_win / abs(avg_loss)
        p = win_rate
        q = 1 - p
        
        kelly = (p * b - q) / b
        
        # Apply Kelly fraction (typically 0.25 for safety)
        kelly_fraction = max(0, min(kelly * 0.25, 0.25))
        
        logger.debug(f"Kelly Criterion: win_rate={win_rate:.3f}, avg_win={avg_win:.3f}, "
                    f"avg_loss={avg_loss:.3f}, kelly={kelly:.3f}, fraction={kelly_fraction:.3f}")
        
        return kelly_fraction
    
    def check_risk_limits(self, orders: pd.DataFrame) -> pd.DataFrame:
        """Apply risk management rules to orders"""
        original_count = len(orders)
        
        # Limit number of positions
        if len(orders) > self.position_limit:
            logger.warning(f"Reducing positions from {len(orders)} to {self.position_limit}")
            orders = orders.nlargest(self.position_limit, 'confidence_score')
        
        # Normalize allocations to stay within portfolio limit
        total_allocation = orders['desired_allocation'].sum()
        if total_allocation > self.max_portfolio_allocation:
            scaling_factor = self.max_portfolio_allocation / total_allocation
            orders['desired_allocation'] = orders['desired_allocation'] * scaling_factor
            logger.info(f"Scaled allocations by {scaling_factor:.3f} to stay within {self.max_portfolio_allocation*100}% limit")
        
        # Check individual position limits
        max_individual = orders['desired_allocation'].max()
        if max_individual > 0.30:  # 30% max per position
            logger.warning(f"Maximum individual allocation: {max_individual*100:.1f}%")
        
        logger.info(f"Risk check complete: {len(orders)}/{original_count} positions, "
                   f"total allocation: {orders['desired_allocation'].sum()*100:.1f}%")
        
        return orders
    
    def calculate_portfolio_var(self, returns: pd.DataFrame, confidence_level: float = 0.05) -> float:
        """Calculate portfolio Value at Risk"""
        if returns.empty:
            return 0.0
        
        portfolio_returns = returns.sum(axis=1)
        var = np.percentile(portfolio_returns, confidence_level * 100)
        
        logger.debug(f"Portfolio VaR ({confidence_level*100}%): {var:.4f}")
        return var
    
    def check_correlation_limits(self, symbols: List[str], 
                                correlation_matrix: pd.DataFrame = None) -> Dict:
        """Check correlation between positions"""
        # Mock correlation check - in real implementation, fetch actual correlations
        if correlation_matrix is None:
            # Create mock correlation matrix
            n = len(symbols)
            correlation_matrix = pd.DataFrame(
                np.random.uniform(0.3, 0.7, (n, n)),
                index=symbols,
                columns=symbols
            )
            np.fill_diagonal(correlation_matrix.values, 1.0)
        
        # Find highly correlated pairs
        high_correlation_pairs = []
        for i, symbol1 in enumerate(symbols):
            for j, symbol2 in enumerate(symbols[i+1:], i+1):
                corr = correlation_matrix.loc[symbol1, symbol2]
                if corr > 0.8:  # High correlation threshold
                    high_correlation_pairs.append((symbol1, symbol2, corr))
        
        if high_correlation_pairs:
            logger.warning(f"Found {len(high_correlation_pairs)} highly correlated pairs")
            for pair in high_correlation_pairs:
                logger.warning(f"High correlation: {pair[0]} - {pair[1]} ({pair[2]:.3f})")
        
        return {
            'high_correlation_pairs': high_correlation_pairs,
            'avg_correlation': correlation_matrix.values[np.triu_indices_from(correlation_matrix, k=1)].mean()
        }
    
    def calculate_position_sizes(self, signals: pd.DataFrame, 
                                historical_performance: Dict = None) -> pd.DataFrame:
        """Calculate position sizes based on risk metrics"""
        sized_signals = signals.copy()
        
        if historical_performance:
            # Use Kelly Criterion if performance data available
            for idx, row in sized_signals.iterrows():
                symbol = row['symbol']
                if symbol in historical_performance:
                    perf = historical_performance[symbol]
                    kelly_size = self.calculate_kelly_criterion(
                        perf.get('win_rate', 0.5),
                        perf.get('avg_win', 0.02),
                        perf.get('avg_loss', 0.02)
                    )
                    # Blend with confidence score
                    confidence = row.get('confidence_score', 0.5)
                    final_allocation = kelly_size * confidence
                    sized_signals.loc[idx, 'desired_allocation'] = min(final_allocation, 0.25)
        
        return self.check_risk_limits(sized_signals)
    
    def calculate_sector_exposure(self, orders: pd.DataFrame, 
                                 sector_mapping: Dict[str, str] = None) -> Dict:
        """Calculate sector exposure from orders"""
        if sector_mapping is None:
            # Mock sector mapping
            sector_mapping = {
                'NVDA': 'Technology', 'AMD': 'Technology', 'TSM': 'Technology',
                'AVGO': 'Technology', 'QCOM': 'Technology', 'AAPL': 'Technology',
                'GOOGL': 'Technology', 'MSFT': 'Technology'
            }
        
        # Calculate sector allocations
        sector_exposure = {}
        for _, row in orders.iterrows():
            symbol = row['symbol']
            sector = sector_mapping.get(symbol, 'Unknown')
            allocation = row['desired_allocation']
            
            if sector not in sector_exposure:
                sector_exposure[sector] = 0
            sector_exposure[sector] += allocation
        
        # Check sector limits
        over_limit_sectors = {k: v for k, v in sector_exposure.items() if v > self.sector_limit}
        
        if over_limit_sectors:
            logger.warning(f"Sectors over {self.sector_limit*100}% limit: {over_limit_sectors}")
        
        return sector_exposure
    
    def emergency_stop_check(self, current_drawdown: float) -> bool:
        """Check if emergency stop should be triggered"""
        if current_drawdown > self.max_drawdown:
            logger.critical(f"EMERGENCY STOP: Drawdown {current_drawdown*100:.1f}% exceeds limit {self.max_drawdown*100:.1f}%")
            return True
        return False
