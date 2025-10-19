# config.py - Complete Configuration File
import os
import json
from typing import List, Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Main configuration class untuk bot"""
    
    # ==================== BOT CONFIGURATION ====================
    BOT_TOKEN = os.getenv('BOT_TOKEN', '')
    BOT_USERNAME = os.getenv('BOT_USERNAME', '')
    BOT_NAME = os.getenv('BOT_NAME', 'Telegram Store Bot')
    
    # ==================== API CONFIGURATION ====================
    API_KEY_PROVIDER = os.getenv('API_KEY_PROVIDER', '')
    QRIS_STATIS = os.getenv('QRIS_STATIS', '')
    
    # ==================== ADMIN CONFIGURATION ====================
    ADMIN_TELEGRAM_IDS = [
        int(admin_id.strip()) for admin_id in 
        os.getenv('ADMIN_TELEGRAM_IDS', '').split(',') 
        if admin_id.strip().isdigit()
    ]
    
    # ==================== DATABASE CONFIGURATION ====================
    DB_PATH = os.getenv('DB_PATH', 'bot_database.db')
    DB_BACKUP_PATH = os.getenv('DB_BACKUP_PATH', 'backups')
    
    # ==================== API URLS ====================
    PRODUCT_API_URL = "https://panel.khfy-store.com/api_v2/list_product"
    STOCK_API_URL = "https://panel.khfy-store.com/api_v3/cek_stock_akrab"
    ORDER_API_URL = "https://panel.khfy-store.com/api_v2/order"
    QRIS_API_URL = "https://qrisku.my.id/api"
    
    # ==================== BOT SETTINGS ====================
    MIN_TOPUP_AMOUNT = 10000
    MAX_TOPUP_AMOUNT = 1000000
    MAX_PRODUCT_DISPLAY = 50
    MAX_MESSAGE_LENGTH = 4000
    REQUEST_TIMEOUT = 30
    MAX_RETRY_ATTEMPTS = 3
    
    # ==================== PAYMENT SETTINGS ====================
    UNIQUE_DIGITS = 3
    AUTO_CANCEL_MINUTES = 30
    PAYMENT_METHODS = ['QRIS', 'BANK_TRANSFER']
    
    # ==================== BANK ACCOUNTS ====================
    BANK_ACCOUNTS = {
        'BCA': {
            'number': '1234567890',
            'name': 'BOT STORE',
            'bank': 'BCA'
        },
        'BRI': {
            'number': '1234567890', 
            'name': 'BOT STORE',
            'bank': 'BRI'
        },
        'BNI': {
            'number': '1234567890',
            'name': 'BOT STORE',
            'bank': 'BNI'
        },
        'MANDIRI': {
            'number': '1234567890',
            'name': 'BOT STORE',
            'bank': 'MANDIRI'
        }
    }
    
    # ==================== PRODUCT CATEGORIES ====================
    PRODUCT_CATEGORIES = {
        'PULSA': ['pulsa', 'telkomsel', 'indosat', 'xl', 'axis', 'three', 'smartfren'],
        'INTERNET': ['data', 'internet', 'kuota', 'bandwidth'],
        'LISTRIK': ['listrik', 'pln', 'token'],
        'GAME': ['game', 'voucher', 'steam', 'mobile legends', 'free fire', 'pubg'],
        'E-MONEY': ['emoney', 'gopay', 'dana', 'ovo', 'shopeepay', 'linkaja'],
        'PAKET_BONUS': ['akrab', 'bonus', 'paket'],
        'VOUCHER': ['voucher', 'belanja', 'marketplace'],
        'OTHER': ['umum', 'lainnya']
    }
    
    # ==================== ORDER SETTINGS ====================
    ORDER_STATUS = {
        'PENDING': 'pending',
        'PROCESSING': 'processing', 
        'COMPLETED': 'completed',
        'FAILED': 'failed',
        'CANCELLED': 'cancelled'
    }
    
    TRANSACTION_STATUS = {
        'PENDING': 'pending',
        'COMPLETED': 'completed',
        'REJECTED': 'rejected',
        'CANCELLED': 'cancelled'
    }
    
    # ==================== LOGGING CONFIG ====================
    LOGGING = {
        'LEVEL': 'INFO',
        'FORMAT': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'FILE': 'bot.log',
        'MAX_SIZE_MB': 10,
        'BACKUP_COUNT': 5
    }
    
    # ==================== PERFORMANCE SETTINGS ====================
    PERFORMANCE = {
        'DB_TIMEOUT': 30,
        'API_TIMEOUT': 30,
        'MAX_CONCURRENT_REQUESTS': 5,
        'RATE_LIMIT_PER_USER': 10,  # requests per minute
        'CACHE_TTL': 300  # 5 minutes
    }
    
    # ==================== SECURITY SETTINGS ====================
    SECURITY = {
        'MAX_LOGIN_ATTEMPTS': 5,
        'SESSION_TIMEOUT': 3600,  # 1 hour
        'ALLOWED_UPDATES': ['message', 'callback_query', 'inline_query'],
        'BLACKLISTED_IDS': []
    }
    
    # ==================== NOTIFICATION SETTINGS ====================
    NOTIFICATIONS = {
        'NEW_ORDER': True,
        'NEW_TOPUP': True,
        'SYSTEM_ALERTS': True,
        'BROADCAST_ENABLED': True
    }
    
    # ==================== MESSAGE TEMPLATES ====================
    MESSAGES = {
        'WELCOME': """
👋 **Selamat Datang di {bot_name}!**

🤖 **Bot Features:**
• 🛒 Beli produk pulsa, data, listrik, game
• 💳 Top up saldo mudah & cepat  
• 📊 Cek stok real-time
• 📜 Riwayat transaksi lengkap
• 👑 Admin panel untuk management

💡 **Tips:** Gunakan menu di bawah untuk mulai!
        """,
        
        'INSUFFICIENT_BALANCE': """
❌ **Saldo Tidak Mencukupi!**

💰 **Harga Produk:** Rp {product_price:,}
💳 **Saldo Anda:** Rp {user_balance:,}
📊 **Kekurangan:** Rp {deficit:,}

💡 Silakan top up saldo terlebih dahulu.
        """,
        
        'ORDER_SUCCESS': """
✅ **Pesanan Berhasil!**

📦 **Produk:** {product_name}
💰 **Harga:** Rp {product_price:,}
👤 **Data:** {customer_data}
🆔 **Order ID:** `{order_id}`

📋 **Status:** {status}
⏰ **Waktu:** {timestamp}
        """,
        
        'TOPUP_INSTRUCTIONS': """
💳 **TOP UP SALDO - {method}**

💰 **Detail Pembayaran:**
├ Nominal: Rp {base_amount:,}
├ Kode Unik: {unique_digits:03d}
├ Total Transfer: **Rp {total_amount:,}**
└ Metode: {method}

{payment_instructions}

⏰ **Penting:** 
• Transfer tepat sesuai nominal
• Simpan bukti transfer
• Proses verifikasi 1-10 menit
        """
    }

    @classmethod
    def validate(cls) -> bool:
        """Validasi konfigurasi yang diperlukan"""
        errors = []
        
        # Check required environment variables
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN is required")
        
        if not cls.API_KEY_PROVIDER:
            errors.append("API_KEY_PROVIDER is required")
            
        if not cls.ADMIN_TELEGRAM_IDS:
            errors.append("ADMIN_TELEGRAM_IDS must contain at least one admin ID")
        
        # Validate numeric values
        if cls.MIN_TOPUP_AMOUNT <= 0:
            errors.append("MIN_TOPUP_AMOUNT must be greater than 0")
            
        if cls.MAX_TOPUP_AMOUNT <= cls.MIN_TOPUP_AMOUNT:
            errors.append("MAX_TOPUP_AMOUNT must be greater than MIN_TOPUP_AMOUNT")
        
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
        
        return True
    
    @classmethod
    def get_bank_instructions(cls, bank_code: str) -> str:
        """Get bank transfer instructions"""
        bank = cls.BANK_ACCOUNTS.get(bank_code.upper())
        if not bank:
            return ""
            
        return f"""
🏦 **{bank['bank']}**
📤 No. Rekening: `{bank['number']}`
👤 Atas Nama: **{bank['name']}**
        """
    
    @classmethod
    def get_all_bank_instructions(cls) -> str:
        """Get instructions for all banks"""
        instructions = ""
        for bank_code, bank_info in cls.BANK_ACCOUNTS.items():
            instructions += f"**{bank_info['bank']}**: `{bank_info['number']}` - {bank_info['name']}\n"
        return instructions
    
    @classmethod
    def get_category_for_product(cls, product_name: str) -> str:
        """Determine category for product name"""
        product_name_lower = product_name.lower()
        
        for category, keywords in cls.PRODUCT_CATEGORIES.items():
            if any(keyword in product_name_lower for keyword in keywords):
                return category
                
        return 'OTHER'

# Alias untuk backward compatibility
def validate_config():
    """Validasi konfigurasi (alias untuk backward compatibility)"""
    return Config.validate()

# Global instance
config = Config()

# Validasi saat import
try:
    config.validate()
    print("✅ Configuration validated successfully")
except ValueError as e:
    print(f"❌ Configuration error: {e}")
    print("⚠️ Please check your environment variables")
