# config.py
import os

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '7381707221:AAFcOwFzHCSg8gTxzRVtv3takopJQoA8BW8')

# Admin Configuration
ADMIN_TELEGRAM_IDS = [191234567]  # Ganti dengan ID Telegram admin yang sebenarnya

# API Configuration
API_KEY_PROVIDER = os.getenv('API_KEY_PROVIDER', 'your_api_key_here')
PRODUCT_API_URL = os.getenv('PRODUCT_API_URL', 'https://panel.khfy-store.com/api_v2/list_product')

# System Configuration
REQUEST_TIMEOUT = 30
MAX_MESSAGE_LENGTH = 4096

# Database Configuration
DB_PATH = 'bot_database.db'

# Feature Flags
ENABLE_TOPUP = True
ENABLE_ORDERS = True
ENABLE_ADMIN = True
ENABLE_STOCK = True
