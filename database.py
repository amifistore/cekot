import sqlite3
import logging
from datetime import datetime
import os

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DB_PATH = "bot_database.db"

def init_db():
    """Initialize database tables with all needed columns (full fitur)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Users table
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                saldo REAL DEFAULT 0,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Transactions table
        c.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                type TEXT,
                amount REAL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Riwayat pembelian table
        c.execute('''
            CREATE TABLE IF NOT EXISTS riwayat_pembelian (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                kode_produk TEXT,
                nama_produk TEXT,
                tujuan TEXT,
                harga REAL,
                saldo_awal REAL,
                reff_id TEXT,
                status_api TEXT,
                keterangan TEXT,
                waktu TEXT
            )
        ''')

        # Products table
        c.execute('''
            CREATE TABLE IF NOT EXISTS products (
                code TEXT PRIMARY KEY,
                name TEXT,
                price REAL,
                status TEXT DEFAULT 'active',
                description TEXT,
                category TEXT,
                provider TEXT,
                gangguan INTEGER DEFAULT 0,
                kosong INTEGER DEFAULT 0,
                stock INTEGER DEFAULT 0,
                updated_at TEXT
            )
        ''')

        # Topup requests table
        c.execute('''
            CREATE TABLE IF NOT EXISTS topup_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                username TEXT,
                full_name TEXT,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                proof_image TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')

        # Admin logs table
        c.execute('''
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id TEXT,
                action TEXT,
                details TEXT,
                created_at TEXT
            )
        ''')

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")

def get_or_create_user(telegram_id, username, full_name):
    """Get user ID or create new user if not exists"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (telegram_id,))
        result = c.fetchone()
        if result:
            user_id = result[0]
        else:
            c.execute(
                "INSERT INTO users (user_id, username, full_name, saldo) VALUES (?, ?, ?, ?)",
                (telegram_id, username, full_name, 0)
            )
            user_id = telegram_id
            conn.commit()
        conn.close()
        return user_id
    except Exception as e:
        logger.error(f"Error in get_or_create_user: {e}")
        return telegram_id

def get_user_saldo(user_id):
    """Get user balance"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT saldo FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        conn.close()
        if result:
            return result[0]
        else:
            return 0
    except sqlite3.OperationalError as e:
        if "no such column: saldo" in str(e):
            logger.error("Kolom saldo tidak ditemukan, memperbaiki database...")
            init_db()
            return 0
        else:
            logger.error(f"Error getting user saldo: {e}")
            return 0
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        return 0

def increment_user_saldo(user_id, amount):
    """Add/Subtract balance to user"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        get_or_create_user(user_id, None, None)
        c.execute("UPDATE users SET saldo = saldo + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error incrementing user saldo: {e}")
        return False

def get_all_users():
    """Get all users"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id, username, full_name, saldo FROM users")
        users = [{'user_id': row[0], 'username': row[1], 'full_name': row[2], 'saldo': row[3]} for row in c.fetchall()]
        conn.close()
        return users
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        return []

def create_topup_request(user_id, base_amount, unique_amount, unique_digits, qris_base64):
    """
    Simpan permintaan topup ke tabel topup_requests.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Ambil username & full_name jika ada
        c.execute("SELECT username, full_name FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        username = row[0] if row else ""
        full_name = row[1] if row else ""

        c.execute("""
            INSERT INTO topup_requests (
                user_id, username, full_name, amount, status, proof_image, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
        """, (user_id, username, full_name, unique_amount, qris_base64, now, now))

        request_id = c.lastrowid
        conn.commit()
        conn.close()
        return request_id
    except Exception as e:
        logger.error(f"Error create_topup_request: {e}")
        return None

def approve_topup_request(request_id, admin_id=None):
    """
    Set status permintaan topup jadi approved.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute("UPDATE topup_requests SET status = 'approved', updated_at = ? WHERE id = ?", (now, request_id))
        # Tambahkan saldo ke user
        c.execute("SELECT user_id, amount FROM topup_requests WHERE id = ?", (request_id,))
        row = c.fetchone()
        if row:
            user_id, amount = row
            c.execute("UPDATE users SET saldo = saldo + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()
        logger.info(f"Topup request {request_id} approved.")
        return True
    except Exception as e:
        logger.error(f"Error approve_topup_request: {e}")
        return False

def reject_topup_request(request_id, admin_id=None):
    """
    Set status permintaan topup jadi rejected.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute("UPDATE topup_requests SET status = 'rejected', updated_at = ? WHERE id = ?", (now, request_id))
        conn.commit()
        conn.close()
        logger.info(f"Topup request {request_id} rejected.")
        return True
    except Exception as e:
        logger.error(f"Error reject_topup_request: {e}")
        return False

def get_topup_requests(status=None, limit=20):
    """
    Ambil daftar permintaan topup, filter status jika diisi.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if status:
            c.execute("SELECT * FROM topup_requests WHERE status = ? ORDER BY created_at DESC LIMIT ?", (status, limit))
        else:
            c.execute("SELECT * FROM topup_requests ORDER BY created_at DESC LIMIT ?", (limit,))
        items = c.fetchall()
        conn.close()
        return items
    except Exception as e:
        logger.error(f"Error get_topup_requests: {e}")
        return []

def add_transaction(user_id, type, amount, description):
    """Log transaksi ke tabel transactions"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute("""
            INSERT INTO transactions (user_id, type, amount, description, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, type, amount, description, now))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error add_transaction: {e}")
        return False

def log_admin_action(admin_id, action, details=""):
    """Log aksi admin ke tabel admin_logs"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute("""
            INSERT INTO admin_logs (admin_id, action, details, created_at)
            VALUES (?, ?, ?, ?)
        """, (admin_id, action, details, now))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error log_admin_action: {e}")
        return False

# Emergency fix checker (run fix if columns missing)
def emergency_fix_database():
    """Emergency function to fix database structure (drop and recreate)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DROP TABLE IF EXISTS users")
        c.execute('''
            CREATE TABLE users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                saldo REAL DEFAULT 0,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute("DROP TABLE IF EXISTS transactions")
        c.execute('''
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                type TEXT,
                amount REAL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute("DROP TABLE IF EXISTS riwayat_pembelian")
        c.execute('''
            CREATE TABLE riwayat_pembelian (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                kode_produk TEXT,
                nama_produk TEXT,
                tujuan TEXT,
                harga REAL,
                saldo_awal REAL,
                reff_id TEXT,
                status_api TEXT,
                keterangan TEXT,
                waktu TEXT
            )
        ''')
        c.execute("DROP TABLE IF EXISTS products")
        c.execute('''
            CREATE TABLE products (
                code TEXT PRIMARY KEY,
                name TEXT,
                price REAL,
                status TEXT DEFAULT 'active',
                description TEXT,
                category TEXT,
                provider TEXT,
                gangguan INTEGER DEFAULT 0,
                kosong INTEGER DEFAULT 0,
                stock INTEGER DEFAULT 0,
                updated_at TEXT
            )
        ''')
        c.execute("DROP TABLE IF EXISTS topup_requests")
        c.execute('''
            CREATE TABLE topup_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                username TEXT,
                full_name TEXT,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                proof_image TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        c.execute("DROP TABLE IF EXISTS admin_logs")
        c.execute('''
            CREATE TABLE admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id TEXT,
                action TEXT,
                details TEXT,
                created_at TEXT
            )
        ''')
        conn.commit()
        conn.close()
        logger.info("Emergency database fix completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error in emergency_fix_database: {e}")
        return False

# Auto-init database
init_db()
