# config.py - Configuration menggunakan config_loader
import logging
from config_loader import json_config

logger = logging.getLogger(__name__)

class Config:
    """Main configuration class"""
    
    # Load from JSON config
    BOT_TOKEN = json_config.get('bot.token', '')
    BOT_USERNAME = json_config.get('bot.username', '')
    BOT_NAME = json_config.get('bot.name', 'Telegram Store Bot')
    BOT_VERSION = json_config.get('bot.version', '1.0.0')
    
    # API Configuration
    API_KEY_PROVIDER = json_config.get('api.provider_key', '')
    QRIS_STATIS = json_config.get('api.qris_static', '')
    
    # Admin Configuration
    ADMIN_TELEGRAM_IDS = json_config.get('admin.telegram_ids', [])
    BOT_OWNER_ID = ADMIN_TELEGRAM_IDS[0] if ADMIN_TELEGRAM_IDS else 0
    
    # Database Configuration
    DB_PATH = json_config.get('database.path', 'bot_database.db')
    DB_BACKUP_PATH = json_config.get('database.backup_path', 'backups')
    
    # API URLs
    PRODUCT_API_URL = json_config.get('api.urls.product', '')
    STOCK_API_URL = json_config.get('api.urls.stock', '')
    ORDER_API_URL = json_config.get('api.urls.order', '')
    QRIS_API_URL = json_config.get('api.urls.qris', '')
    
    # Bot Settings
    MIN_TOPUP_AMOUNT = json_config.get('payment.min_topup_amount', 10000)
    MAX_TOPUP_AMOUNT = json_config.get('payment.max_topup_amount', 1000000)
    MAX_PRODUCT_DISPLAY = json_config.get('products.max_display', 50)
    MAX_MESSAGE_LENGTH = 4000
    REQUEST_TIMEOUT = json_config.get('api.timeout', 30)
    MAX_RETRY_ATTEMPTS = json_config.get('api.max_retries', 3)
    
    # Payment Settings
    UNIQUE_DIGITS = json_config.get('payment.unique_digits', 3)
    AUTO_CANCEL_MINUTES = json_config.get('payment.auto_cancel_minutes', 30)
    PAYMENT_METHODS = json_config.get('payment.methods', [])
    
    # Bank Accounts
    BANK_ACCOUNTS = json_config.get('payment.banks', {})
    
    # Product Categories
    PRODUCT_CATEGORIES = json_config.get('products.categories', {})
    
    # Order Settings
    ORDER_STATUS = json_config.get('orders.status', {})
    
    # Transaction Settings  
    TRANSACTION_STATUS = json_config.get('transactions.status', {})
    
    # Features
    FEATURES = json_config.get('features', {})
    
    # Messages
    MESSAGES = json_config.get('messages', {})

    @classmethod
    def validate(cls) -> bool:
        """Validate configuration"""
        required_fields = [
            ('bot.token', cls.BOT_TOKEN),
            ('api.provider_key', cls.API_KEY_PROVIDER),
            ('admin.telegram_ids', cls.ADMIN_TELEGRAM_IDS)
        ]
        
        for field_name, field_value in required_fields:
            if not field_value:
                logger.error(f"❌ Missing required configuration: {field_name}")
                return False
        
        if not cls.ADMIN_TELEGRAM_IDS:
            logger.error("❌ No admin Telegram IDs configured")
            return False
            
        logger.info("✅ Configuration validated successfully")
        return True

# Global instance
config = Config()

# Validasi saat import
try:
    if config.validate():
        print("✅ Configuration validated successfully")
    else:
        print("❌ Configuration validation failed")
        print("⚠️ Please check your bot.json file")
        exit(1)
except Exception as e:
    print(f"❌ Configuration error: {e}")
    exit(1)
