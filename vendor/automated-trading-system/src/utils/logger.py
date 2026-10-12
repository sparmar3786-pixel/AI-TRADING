"""
Logging Utilities
Enhanced logging configuration for the trading system
"""

import os
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Optional


class TradingSystemFormatter(logging.Formatter):
    """Custom formatter for trading system logs"""
    
    def __init__(self):
        super().__init__()
        self.default_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        self.error_format = '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    
    def format(self, record):
        if record.levelno >= logging.ERROR:
            formatter = logging.Formatter(self.error_format)
        else:
            formatter = logging.Formatter(self.default_format)
        
        return formatter.format(record)


class TradingLogger:
    """Enhanced logger for trading system"""
    
    def __init__(self, name: str = "TradingSystem", 
                 log_dir: str = "logs",
                 log_level: str = "INFO"):
        
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        
        # Create log directory
        self.log_dir.mkdir(exist_ok=True)
        
        # Setup logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self.log_level)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Setup handlers
        self._setup_console_handler()
        self._setup_file_handler()
        self._setup_error_handler()
        self._setup_trade_handler()
    
    def _setup_console_handler(self):
        """Setup console logging handler"""
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.log_level)
        console_handler.setFormatter(TradingSystemFormatter())
        self.logger.addHandler(console_handler)
    
    def _setup_file_handler(self):
        """Setup main file logging handler with rotation"""
        file_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / 'trading_system.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(TradingSystemFormatter())
        self.logger.addHandler(file_handler)
    
    def _setup_error_handler(self):
        """Setup error-only file handler"""
        error_handler = logging.FileHandler(
            self.log_dir / 'errors.log'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(TradingSystemFormatter())
        self.logger.addHandler(error_handler)
    
    def _setup_trade_handler(self):
        """Setup trade-specific logging"""
        trade_handler = logging.FileHandler(
            self.log_dir / f'trades_{datetime.now().strftime("%Y%m%d")}.log'
        )
        trade_handler.setLevel(logging.INFO)
        trade_handler.setFormatter(logging.Formatter(
            '%(asctime)s - TRADE - %(message)s'
        ))
        
        # Create separate logger for trades
        trade_logger = logging.getLogger(f"{self.name}.trades")
        trade_logger.setLevel(logging.INFO)
        trade_logger.addHandler(trade_handler)
        trade_logger.propagate = False
    
    def get_logger(self) -> logging.Logger:
        """Get the main logger instance"""
        return self.logger
    
    def get_trade_logger(self) -> logging.Logger:
        """Get the trade-specific logger"""
        return logging.getLogger(f"{self.name}.trades")
    
    def log_trade(self, symbol: str, action: str, quantity: float, 
                  price: Optional[float] = None, **kwargs):
        """Log a trade execution"""
        trade_logger = self.get_trade_logger()
        
        trade_info = {
            'symbol': symbol,
            'action': action,
            'quantity': quantity,
            'price': price,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }
        
        trade_logger.info(str(trade_info))
    
    def log_performance(self, **metrics):
        """Log performance metrics"""
        perf_logger = logging.getLogger(f"{self.name}.performance")
        perf_logger.info(f"Performance: {metrics}")
    
    def log_risk_event(self, event_type: str, details: str):
        """Log risk management events"""
        risk_logger = logging.getLogger(f"{self.name}.risk")
        risk_logger.warning(f"RISK_{event_type}: {details}")


def setup_logging(log_level: str = None) -> TradingLogger:
    """Setup logging for the trading system"""
    log_level = log_level or os.getenv('LOG_LEVEL', 'INFO')
    
    trading_logger = TradingLogger(log_level=log_level)
    
    # Set as root logger for the application
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)  # Only show warnings/errors from other modules
    
    return trading_logger


# Global logger instance
_global_logger = None

def get_logger() -> logging.Logger:
    """Get global logger instance"""
    global _global_logger
    if _global_logger is None:
        trading_logger = setup_logging()
        _global_logger = trading_logger.get_logger()
    return _global_logger

def get_trade_logger() -> logging.Logger:
    """Get trade-specific logger"""
    return logging.getLogger("TradingSystem.trades")
