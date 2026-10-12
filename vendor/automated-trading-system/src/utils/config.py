"""
Configuration Management
Handles loading and managing configuration files
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages configuration loading and validation"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.config_cache = {}
    
    def load_config(self, config_name: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if config_name in self.config_cache:
            return self.config_cache[config_name]
        
        config_path = self.config_dir / f"{config_name}.yaml"
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            self.config_cache[config_name] = config
            logger.info(f"Loaded configuration: {config_name}")
            return config
            
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_path}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML config {config_name}: {e}")
            return {}
    
    def get_trading_config(self) -> Dict[str, Any]:
        """Get trading configuration"""
        return self.load_config("trading_config")
    
    def get_risk_config(self) -> Dict[str, Any]:
        """Get risk management configuration"""
        return self.load_config("risk_config")
    
    def get_broker_config(self) -> Dict[str, Any]:
        """Get broker configuration"""
        config = self.get_trading_config()
        return config.get('broker', {})
    
    def validate_config(self, config: Dict[str, Any], required_keys: list) -> bool:
        """Validate that required configuration keys are present"""
        missing_keys = [key for key in required_keys if key not in config]
        
        if missing_keys:
            logger.error(f"Missing required configuration keys: {missing_keys}")
            return False
        
        return True


class EnvironmentManager:
    """Manages environment variables and secrets"""
    
    @staticmethod
    def load_env_file(filepath: str = ".env"):
        """Load environment variables from file"""
        env_path = Path(filepath)
        
        if not env_path.exists():
            logger.warning(f"Environment file not found: {filepath}")
            return
        
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key] = value
        
        logger.info(f"Loaded environment variables from {filepath}")
    
    @staticmethod
    def get_required_env(key: str) -> str:
        """Get required environment variable or raise error"""
        value = os.getenv(key)
        if not value:
            raise EnvironmentError(f"Required environment variable not set: {key}")
        return value
    
    @staticmethod
    def get_optional_env(key: str, default: str = None) -> str:
        """Get optional environment variable with default"""
        return os.getenv(key, default)
    
    @staticmethod
    def validate_api_credentials() -> bool:
        """Validate that API credentials are available"""
        required_vars = ['BROKER_API_KEY', 'BROKER_API_SECRET']
        
        for var in required_vars:
            if not os.getenv(var):
                logger.error(f"Missing required environment variable: {var}")
                return False
        
        logger.info("API credentials validated")
        return True


# Global configuration instance
config_manager = ConfigManager()

def get_config() -> ConfigManager:
    """Get global configuration manager instance"""
    return config_manager
