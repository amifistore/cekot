import os

# Bot Configuration
BOT_TOKEN = "7381707221:AAFcOwFzHCSg8gTxzRVtv3takopJQoA8BW8"

# Admin Configuration
ADMIN_TELEGRAM_IDS = ["6738243352"]

# ==================== KHFYPAY API CONFIGURATION ====================
# API Configuration for KhfyPay (DIGUNAKAN oleh order_handler.py)
KHFYPAY_API_KEY = "369594EC-A601-402D-8B60-256FF8A75C54"  # NAMA VARIABEL YANG SESUAI

# Backup untuk kompatibilitas (opsional)
API_KEY_PROVIDER = "369594EC-A601-402D-8B60-256FF8A75C54"  # Tetap pertahankan

# KhfyPay API Base URL (DIBUTUHKAN oleh order_handler.py)
KHFYPAY_BASE_URL = "https://panel.khfy-store.com/api_v2"

# ==================== DATABASE CONFIGURATION ====================
DB_PATH = "bot_database.db"

# ==================== ORDER SYSTEM CONFIGURATION ====================
# Order Timeout Settings
ORDER_TIMEOUT_MINUTES = 30  # Timeout untuk order pending
MAX_RETRY_ATTEMPTS = 3      # Maksimal percobaan ulang order

# Stock Sync Configuration
STOCK_SYNC_INTERVAL_MINUTES = 5    # Interval sinkronisasi stok
AUTO_STOCK_SYNC = True             # Auto sync stok

# Refund Configuration
AUTO_REFUND_FAILED_ORDERS = True   # Auto refund untuk order gagal
REFUND_PROCESSING_TIME_HOURS = 1   # Waktu proses refund

# ==================== TOPUP SYSTEM CONFIGURATION ====================
MIN_TOPUP_AMOUNT = 10000
MAX_TOPUP_AMOUNT = 1000000

# QRIS Configuration
QRIS_API_URL = "https://qrisku.my.id/api"
QRIS_STATIC_CODE = "00020101021126610014COM.GO-JEK.WWW01189360091434506469550210G4506469550303UMI51440014ID.CO.QRIS.WWW0215ID10243341364120303UMI5204569753033605802ID5923Amifi Store, Kmb, TLGSR6009BONDOWOSO61056827262070703A01630431E8"

# Admin Chat ID untuk Notifikasi
ADMIN_CHAT_ID = "6738243352"

# Bank Account Information
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

# Payment Methods
PAYMENT_METHODS = {
    "qris": {
        "name": "QRIS",
        "description": "Pembayaran via QRIS",
        "enabled": True
    },
    "bank_transfer": {
        "name": "Transfer Bank",
        "description": "Transfer manual ke rekening bank",
        "enabled": True
    }
}

# ==================== FEATURE TOGGLES ====================
FEATURES = {
    'topup': True,
    'order': True, 
    'stock_check': True,
    'admin_panel': True,
    'automatic_refund': True,  # Diubah jadi True untuk support refund otomatis
    'webhook_processing': True  # Tambahkan untuk webhook
}

# ==================== SECURITY CONFIGURATION ====================
MAX_LOGIN_ATTEMPTS = 3
SESSION_TIMEOUT = 3600

# Rate Limiting untuk Order
RATE_LIMIT = {
    'messages_per_minute': 30,
    'orders_per_hour': 10,
    'topups_per_day': 5,
    'stock_checks_per_minute': 5  # Tambahkan limit untuk cek stok
}

# ==================== NOTIFICATION SETTINGS ====================
SEND_STARTUP_NOTIFICATION = True
SEND_TOPUP_NOTIFICATION = True
SEND_ORDER_NOTIFICATION = True
SEND_STOCK_ALERT = True           # Notifikasi stok menipis
SEND_REFUND_NOTIFICATION = True   # Notifikasi refund

# Log Channel (jika ada)
LOG_CHANNEL_ID = "-1001234567890"

# ==================== DATABASE & PERFORMANCE ====================
AUTO_BACKUP = True
BACKUP_INTERVAL_HOURS = 24
MAX_BACKUP_FILES = 7

DB_POOL_SIZE = 5
DB_MAX_OVERFLOW = 10
DB_POOL_RECYCLE = 3600

# Cache untuk produk dan stok
CACHE_TIMEOUT = 300  # 5 minutes
PRODUCT_CACHE_TIMEOUT = 60  # 1 minute untuk data produk

# ==================== EXTERNAL API SETTINGS ====================
API_TIMEOUT = 30
MAX_RETRIES = 3
KHFYPAY_TIMEOUT = 60  # Timeout khusus KhfyPay

# ==================== ORDER SPECIFIC SETTINGS ====================
# Validasi nomor telepon
PHONE_VALIDATION = {
    'min_length': 10,
    'max_length': 14,
    'allowed_prefixes': ['62', '08']
}

# Product Category Mapping
PRODUCT_CATEGORIES = [
    "Pulsa",
    "Data", 
    "E-Wallet",
    "Listrik",
    "Game",
    "Voucher",
    "Lainnya",
    "BPAL (Bonus Akrab L)",
    "BPAXXL (Bonus Akrab XXL)", 
    "XLA (Umum)"
]

# Order Status Mapping
ORDER_STATUS = {
    'pending': 'Menunggu Pembayaran',
    'processing': 'Sedang Diproses',
    'completed': 'Berhasil',
    'failed': 'Gagal',
    'refunded': 'Dikembalikan'
}

# ==================== MAINTENANCE MODE ====================
MAINTENANCE_MODE = False
MAINTENANCE_MESSAGE = "🛠️ Bot sedang dalam perbaikan. Silakan coba lagi nanti."

# ==================== DEVELOPMENT SETTINGS ====================
DEBUG = True

# Auto Cleanup
CLEANUP_INTERVAL_HOURS = 24
MAX_LOGFILE_AGE_DAYS = 7

# File Paths
PROOF_UPLOAD_DIR = "proofs"
LOG_FILE = "bot.log"
BACKUP_DIR = "backups"

# Ensure directories exist
os.makedirs(PROOF_UPLOAD_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# ==================== CURRENCY & LOCALIZATION ====================
CURRENCY = "IDR"
CURRENCY_SYMBOL = "Rp"
LANGUAGE = "id"
TIMEZONE = 'Asia/Jakarta'
