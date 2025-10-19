# config_loader.py - JSON Configuration Loader
import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class JSONConfig:
    """JSON configuration loader"""
    
    def __init__(self, config_path: str = "config.json"):
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
                logger.warning(f"⚠️ Config file {self.config_path} not found, using defaults")
                self.create_default_config()
        except Exception as e:
            logger.error(f"❌ Error loading config: {e}")
            self.create_default_config()
    
    def create_default_config(self):
        """Create default configuration"""
        self.config_data = {
            "bot": {
                "token": os.getenv('BOT_TOKEN', ''),
                "username": "",
                "name": "Telegram Store Bot"
            },
            "api": {
                "provider_key": os.getenv('API_KEY_PROVIDER', ''),
                "qris_static": os.getenv('QRIS_STATIS', '')
            }
        }
        self.save_config()
    
    def save_config(self):
        """Save configuration to JSON file"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
            logger.info(f"✅ Configuration saved to {self.config_path}")
        except Exception as e:
            logger.error(f"❌ Error saving config: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation"""
        keys = key.split('.')
        value = self.config_data
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any):
        """Set configuration value using dot notation"""
        keys = key.split('.')
        config = self.config_data
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
        self.save_config()
    
    def validate(self) -> bool:
        """Validate required configuration"""
        required_keys = [
            'bot.token',
            'api.provider_key',
            'admin.telegram_ids'
        ]
        
        missing = []
        for key in required_keys:
            if not self.get(key):
                missing.append(key)
        
        if missing:
            logger.error(f"❌ Missing required configuration: {missing}")
            return False
        
        return True
    
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
    
    def get_message_template(self, template_name: str, **kwargs) -> str:
        """Get formatted message template"""
        template = self.get(f'messages.{template_name}', '')
        return template.format(**kwargs) if template else ''

# Global instance
json_config = JSONConfig()

# Untuk penggunaan: from config_loader import json_config
