import os

# Bot Configuration
BOT_TOKEN = "7381707221:AAFcOwFzHCSg8gTxzRVtv3takopJQoA8BW8"

# Admin Configuration - GUNAKAN TELEGRAM ID ANDA YANG SEBENARNYA
ADMIN_TELEGRAM_IDS = ["6738243352"]  # Ganti dengan Telegram ID admin yang sebenarnya

# API Configuration
API_KEY_PROVIDER = "369594EC-A601-402D-8B60-256FF8A75C54"  # Ganti dengan API key yang valid dari provider

# Database Configuration
DB_PATH = "bot_database.db"

# Other Configurations
LOG_CHANNEL_ID = "-1001234567890"  # Optional: Untuk logging ke channel

# ==================== TOPUP SYSTEM CONFIGURATION ====================
# Minimum dan Maximum Topup Amount
MIN_TOPUP_AMOUNT = 10000  # Rp 10.000
MAX_TOPUP_AMOUNT = 1000000  # Rp 1.000.000

# QRIS Configuration
QRIS_API_URL = "https://qrisku.my.id/api/qris"  # API URL untuk generate QRIS
QRIS_STATIS = "00020101021126610014COM.GO-JEK.WWW01189360091434506469550210G4506469550303UMI51440014ID.CO.QRIS.WWW0215ID10243341364120303UMI5204569753033605802ID5923Amifi Store, Kmb, TLGSR6009BONDOWOSO61056827262070703A01630431E8"  # Ganti dengan QRIS static data Anda

# Admin Chat ID untuk Notifikasi Topup (gunakan ID pribadi atau group admin)
ADMIN_CHAT_ID = "6738243352"  # Ganti dengan Chat ID admin untuk notifikasi topup

# Bank Account Information (untuk transfer manual)
BANK_ACCOUNTS = {
    "BCA": {
        "number": "1234-5678-9012",
        "name": "BOT STORE",
        "description": "Bank Central Asia"
    },
    "BRI": {
        "number": "1234-5678-9012", 
        "name": "BOT STORE",
        "description": "Bank Rakyat Indonesia"
    },
    "BNI": {
        "number": "1234-5678-9012",
        "name": "BOT STORE",
        "description": "Bank Negara Indonesia"
    },
    "Mandiri": {
        "number": "1234-5678-9012",
        "name": "BOT STORE",
        "description": "Bank Mandiri"
    }
}

# Payment Method Configuration
PAYMENT_METHODS = {
    "qris": {
        "name": "QRIS",
        "description": "Pembayaran via QRIS (Gopay, OVO, Dana, LinkAja, dll)",
        "enabled": True
    },
    "bank_transfer": {
        "name": "Transfer Bank",
        "description": "Transfer manual ke rekening bank",
        "enabled": True
    }
}

# Auto Approval Configuration (jika ingin otomatis approve topup tertentu)
AUTO_APPROVE_TOPUP = False  # Set True jika ingin auto approve
AUTO_APPROVE_MAX_AMOUNT = 50000  # Maksimal nominal untuk auto approve

# Timezone Configuration
import pytz
TIMEZONE = pytz.timezone('Asia/Jakarta')

# Logging Configuration
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'handlers': ['file', 'console']
}

# Feature Toggles
FEATURES = {
    'topup': True,
    'order': True, 
    'stock_check': True,
    'admin_panel': True,
    'automatic_refund': False
}

# Security Configuration
MAX_LOGIN_ATTEMPTS = 3
SESSION_TIMEOUT = 3600  # 1 hour in seconds

# Notification Settings
SEND_STARTUP_NOTIFICATION = True
SEND_TOPUP_NOTIFICATION = True
SEND_ORDER_NOTIFICATION = True

# Database Backup Configuration
AUTO_BACKUP = True
BACKUP_INTERVAL_HOURS = 24
MAX_BACKUP_FILES = 7

# Price Configuration (jika ada ketentuan harga khusus)
PRICE_SETTINGS = {
    'markup_percentage': 0,  # Persentase markup dari harga supplier
    'min_profit': 1000,      # Keuntungan minimal per produk
    'round_to_nearest': 500  # Pembulatan harga ke kelipatan
}

# Maintenance Mode
MAINTENANCE_MODE = False
MAINTENANCE_MESSAGE = "🛠️ Bot sedang dalam perbaikan. Silakan coba lagi nanti."

# Rate Limiting
RATE_LIMIT = {
    'messages_per_minute': 30,
    'orders_per_hour': 10,
    'topups_per_day': 5
}

# Webhook Configuration (jika menggunakan webhook)
WEBHOOK_URL = ""  # URL webhook jika menggunakan mode webhook
WEBHOOK_PORT = 8443
WEBHOOK_LISTEN = "0.0.0.0"

# SSL Certificate (jika menggunakan webhook dengan SSL)
SSL_CERT = ""
SSL_PRIV = ""

# Development Mode
DEBUG = True  # Set False untuk production

# Database Connection Pool
DB_POOL_SIZE = 5
DB_MAX_OVERFLOW = 10
DB_POOL_RECYCLE = 3600

# Cache Configuration
CACHE_TIMEOUT = 300  # 5 minutes in seconds

# External API Timeouts
API_TIMEOUT = 30  # seconds
MAX_RETRIES = 3

# Currency Configuration
CURRENCY = "IDR"
CURRENCY_SYMBOL = "Rp"

# Language Configuration
LANGUAGE = "id"  # Indonesian

# Auto Cleanup Configuration
CLEANUP_INTERVAL_HOURS = 24
MAX_LOGFILE_AGE_DAYS = 7
MAX_TEMP_FILES_AGE_HOURS = 24

# Product Categories (untuk organisasi produk)
PRODUCT_CATEGORIES = [
    "Pulsa",
    "Data",
    "E-Wallet", 
    "Listrik",
    "Game",
    "Voucher",
    "Lainnya"
]

# Order Status Configuration
ORDER_STATUS = {
    'pending': 'Menunggu Pembayaran',
    'processing': 'Sedang Diproses',
    'success': 'Berhasil',
    'failed': 'Gagal',
    'refunded': 'Dikembalikan'
}

# Topup Status Configuration
TOPUP_STATUS = {
    'pending': 'Menunggu Pembayaran',
    'processing': 'Sedang Diproses', 
    'completed': 'Selesai',
    'rejected': 'Ditolak',
    'expired': 'Kadaluarsa'
}

# Auto Cancellation Settings
AUTO_CANCEL_PENDING_TOPUP_HOURS = 24  # Batalkan topup pending setelah 24 jam
AUTO_CANCEL_PENDING_ORDER_MINUTES = 30  # Batalkan order pending setelah 30 menit

# Notification Templates
MESSAGE_TEMPLATES = {
    'welcome': "🤖 Selamat datang {name}!",
    'topup_success': "✅ Topup sebesar {amount} berhasil! Saldo Anda sekarang: {balance}",
    'order_success': "✅ Order {product} berhasil! Kode: {code}",
    'admin_alert': "🔔 {message}"
}

# File Paths
PROOF_UPLOAD_DIR = "proofs"
LOG_FILE = "bot.log"
BACKUP_DIR = "backups"

# Ensure directories exist
os.makedirs(PROOF_UPLOAD_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
