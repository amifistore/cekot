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
    """Initialize database tables with proper column structure"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Users table - dengan pengecekan dan alter table jika diperlukan
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                saldo REAL DEFAULT 0,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Check if saldo column exists, if not add it
        try:
            c.execute("SELECT saldo FROM users LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("Adding saldo column to users table")
            c.execute("ALTER TABLE users ADD COLUMN saldo REAL DEFAULT 0")
        
        # Transactions table
        c.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                amount REAL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
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

        # Products table (fix: ensure stock column exists!)
        c.execute('''
            CREATE TABLE IF NOT EXISTS products (
                code TEXT PRIMARY KEY,
                name TEXT,
                price REAL,
                status TEXT DEFAULT 'active',
                description TEXT,
                category TEXT,
                stock INTEGER DEFAULT 0,
                updated_at TEXT
            )
        ''')
        # Emergency fix: add stock column if missing
        try:
            c.execute("SELECT stock FROM products LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("Adding stock column to products table")
            c.execute("ALTER TABLE products ADD COLUMN stock INTEGER DEFAULT 0")

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
        
        # Cek apakah user sudah ada
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (telegram_id,))
        result = c.fetchone()
        
        if result:
            user_id = result[0]
        else:
            # Buat user baru
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
            # Jika user tidak ditemukan, buat user baru
            return 0
    except sqlite3.OperationalError as e:
        if "no such column: saldo" in str(e):
            # Jika kolom saldo tidak ada, perbaiki database
            logger.error("Kolom saldo tidak ditemukan, memperbaiki database...")
            init_db()  # Re-initialize database
            return 0
        else:
            logger.error(f"Error getting user saldo: {e}")
            return 0
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        return 0

def increment_user_saldo(user_id, amount):
    """Add balance to user"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Pastikan user exists
        get_or_create_user(user_id, None, None)
        
        c.execute("UPDATE users SET saldo = saldo + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error incrementing user saldo: {e}")
        return False

def create_user(user_id, username, full_name):
    """Create new user if not exists - compatibility function"""
    return get_or_create_user(user_id, username, full_name)

def add_user_admin(telegram_id):
    """Add user to admin list in config"""
    logger.info(f"Admin added: {telegram_id}")
    return True

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

# Emergency fix function
def emergency_fix_database():
    """Emergency function to fix database structure"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Drop and recreate users table with correct structure
        c.execute("DROP TABLE IF EXISTS users")
        c.execute('''
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                saldo REAL DEFAULT 0,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Recreate other tables
        c.execute("DROP TABLE IF EXISTS transactions")
        c.execute('''
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                amount REAL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
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

        # Recreate products table with stock
        c.execute("DROP TABLE IF EXISTS products")
        c.execute('''
            CREATE TABLE products (
                code TEXT PRIMARY KEY,
                name TEXT,
                price REAL,
                status TEXT DEFAULT 'active',
                description TEXT,
                category TEXT,
                stock INTEGER DEFAULT 0,
                updated_at TEXT
            )
        ''')

        conn.commit()
        conn.close()
        logger.info("Emergency database fix completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error in emergency_fix_database: {e}")
        return False

# Initialize database when module is imported
init_db()

# Jika masih ada error, jalankan emergency fix
try:
    # Test database connection and structure
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT saldo FROM users LIMIT 1")
    c.execute("SELECT stock FROM products LIMIT 1")
    conn.close()
except sqlite3.OperationalError as e:
    if "no such column: saldo" in str(e) or "no such column: stock" in str(e):
        logger.warning("Database structure issue detected, running emergency fix...")
        emergency_fix_database()
