# database.py
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
    """Initialize database tables"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Users table
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
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Error initializing database: {e}")

def get_user_saldo(user_id):
    """Get user balance"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT saldo FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        return 0

def increment_user_saldo(user_id, amount):
    """Add balance to user"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET saldo = saldo + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error incrementing user saldo: {e}")
        return False

def create_user(user_id, username, full_name):
    """Create new user if not exists"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
            (user_id, username, full_name)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return False

def add_user_admin(telegram_id):
    """Add user to admin list in config"""
    # This function should modify config.ADMIN_TELEGRAM_IDS
    # For now, we'll just log it
    logger.info(f"Admin added: {telegram_id}")
    return True

def get_all_users():
    """Get all users - placeholder function"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = [{'user_id': row[0]} for row in c.fetchall()]
        conn.close()
        return users
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        return []

# Initialize database when module is imported
init_db()
