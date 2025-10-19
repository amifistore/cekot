# config.py - Configuration menggunakan config_loader
import logging
from config_loader import json_config

logger = logging.getLogger(__name__)

class Config:
    """Main configuration class"""
    
    # Load from JSON config
    BOT_TOKEN = json_config.get_bot_token()
    BOT_USERNAME = json_config.get('bot.username', '')
    BOT_NAME = json_config.get('bot.name', 'Telegram Store Bot')
    
    # API Configuration
    API_KEY_PROVIDER = json_config.get_api_key()
    QRIS_STATIS = json_config.get('api.qris_static', '')
    
    # Admin Configuration
    ADMIN_TELEGRAM_IDS = json_config.get_admin_ids()
    
    # Database Configuration
    DB_PATH = json_config.get('database.path', 'bot_database.db')
    DB_BACKUP_PATH = json_config.get('database.backup_path', 'backups')
    
    # API URLs
    PRODUCT_API_URL = json_config.get('api.urls.product', 'https://panel.khfy-store.com/api_v2/list_product')
    STOCK_API_URL = json_config.get('api.urls.stock', 'https://panel.khfy-store.com/api_v3/cek_stock_akrab')
    ORDER_API_URL = json_config.get('api.urls.order', 'https://panel.khfy-store.com/api_v2/order')
    QRIS_API_URL = json_config.get('api.urls.qris', 'https://qrisku.my.id/api')
    
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
    PAYMENT_METHODS = json_config.get('payment.methods', ['QRIS', 'BANK_TRANSFER'])
    
    # Bank Accounts
    BANK_ACCOUNTS = json_config.get_bank_accounts()
    
    # Product Categories
    PRODUCT_CATEGORIES = json_config.get('products.categories', {})
    
    # Order Settings
    ORDER_STATUS = json_config.get('orders.status', {})
    
    # Transaction Settings  
    TRANSACTION_STATUS = json_config.get('transactions.status', {})
    
    # Features
    FEATURES = json_config.get('features', {})

    @classmethod
    def validate(cls) -> bool:
        """Validate configuration"""
        return json_config.validate()

# Global instance
config = Config()

# Validasi saat import
try:
    if config.validate():
        print("✅ Configuration validated successfully")
    else:
        print("❌ Configuration validation failed")
        print("⚠️ Please check your bot.json file")
except Exception as e:
    print(f"❌ Configuration error: {e}")
