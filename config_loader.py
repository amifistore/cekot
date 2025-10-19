# config_loader.py - JSON Configuration Loader
import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class JSONConfig:
    """JSON configuration loader"""
    
    def __init__(self, config_path: str = "bot.json"):
        self.config_path = config_path
        self.config_data = {}
        self.load_config()
    
    def load_config(self):
        """Load configuration from JSON file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config_data = json.load(f)
                logger.info(f"✅ Configuration loaded from {self.config_path}")
            else:
                logger.warning(f"⚠️ Config file {self.config_path} not found")
                # Don't create default, just use empty dict
        except Exception as e:
            logger.error(f"❌ Error loading config: {e}")
            self.config_data = {}
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation"""
        if not self.config_data:
            return default
            
        keys = key.split('.')
        value = self.config_data
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_bot_token(self) -> str:
        """Get bot token"""
        return self.get('bot.token', '')
    
    def get_admin_ids(self) -> list:
        """Get admin IDs"""
        return self.get('admin.telegram_ids', [])
    
    def get_api_key(self) -> str:
        """Get API key"""
        return self.get('api.provider_key', '')
    
    def get_bank_accounts(self) -> Dict:
        """Get bank accounts"""
        return self.get('payment.banks', {})
    
    def validate(self) -> bool:
        """Validate required configuration"""
        required_configs = {
            'bot.token': 'BOT_TOKEN',
            'api.provider_key': 'API_KEY_PROVIDER', 
            'admin.telegram_ids': 'ADMIN_TELEGRAM_IDS'
        }
        
        missing = []
        for config_key, config_name in required_configs.items():
            if not self.get(config_key):
                missing.append(config_name)
        
        if missing:
            logger.error(f"❌ Missing required configuration: {missing}")
            return False
        
        return True

# Global instance
json_config = JSONConfig('bot.json')
