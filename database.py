#!/usr/bin/env python3
"""
Database Handler untuk Bot Telegram - FIXED SCHEMA VERSION
"""

import sqlite3
import logging
import os
import json
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Dict, List, Optional, Any, Union
import threading

logger = logging.getLogger(__name__)

class DatabaseManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
    
    def __init__(self, db_path: str = "bot_database.db"):
        if not hasattr(self, '_initialized'):
            self.db_path = db_path
            self._initialized = True
            self.init_database()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    def init_database(self):
        """Initialize semua tabel database dengan schema yang konsisten"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # ==================== USERS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id TEXT UNIQUE NOT NULL,
                        username TEXT,
                        full_name TEXT NOT NULL,
                        saldo INTEGER DEFAULT 0,
                        is_admin BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # ==================== PRODUCTS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        category TEXT NOT NULL,
                        price INTEGER NOT NULL,
                        stock INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'active',
                        description TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # ==================== TOPUPS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS topups (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        amount INTEGER NOT NULL,
                        unique_code INTEGER NOT NULL,
                        total_amount INTEGER NOT NULL,
                        method TEXT NOT NULL,
                        status TEXT DEFAULT 'pending',
                        proof_image TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                ''')
                
                # ==================== ORDERS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        product_id INTEGER NOT NULL,
                        quantity INTEGER DEFAULT 1,
                        total_price INTEGER NOT NULL,
                        status TEXT DEFAULT 'pending',
                        customer_data TEXT,
                        sn TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id),
                        FOREIGN KEY (product_id) REFERENCES products (id)
                    )
                ''')
                
                # ==================== TRANSACTIONS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        type TEXT NOT NULL,
                        amount INTEGER NOT NULL,
                        description TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                ''')
                
                # Create indexes
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_admin ON users(is_admin)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_topups_user_id ON topups(user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_topups_status ON topups(status)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_status ON products(status)')
                
                logger.info("✅ Database initialized successfully with all tables")
                
                # Add sample data
                self.add_sample_data(conn)
                
                return True
                
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}", exc_info=True)
            return False

    def add_sample_data(self, conn):
        """Add sample data untuk testing"""
        try:
            cursor = conn.cursor()
            
            # Add sample products if none exist
            cursor.execute('SELECT COUNT(*) as count FROM products')
            if cursor.fetchone()[0] == 0:
                sample_products = [
                    ('Pulsa Telkomsel 5.000', 'Pulsa', 6000, 100),
                    ('Pulsa Telkomsel 10.000', 'Pulsa', 11000, 100),
                    ('Pulsa XL 5.000', 'Pulsa', 6000, 100),
                    ('Paket Data 1GB', 'Data', 15000, 50),
                    ('Paket Data 3GB', 'Data', 25000, 50),
                    ('Token Listrik 20.000', 'Token', 21000, 100),
                    ('Token Listrik 50.000', 'Token', 51000, 100),
                    ('Voucher Steam 10.000', 'Game', 11000, 50),
                    ('Voucher Mobile Legends', 'Game', 15000, 50),
                ]
                
                cursor.executemany(
                    'INSERT INTO products (name, category, price, stock) VALUES (?, ?, ?, ?)',
                    sample_products
                )
                logger.info("✅ Sample products added")
            
            # Add admin user if none exist
            cursor.execute('SELECT COUNT(*) as count FROM users WHERE is_admin = TRUE')
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    'INSERT INTO users (telegram_id, username, full_name, is_admin) VALUES (?, ?, ?, ?)',
                    ('123456789', 'admin', 'Administrator', True)
                )
                logger.info("✅ Admin user added")
                
        except Exception as e:
            logger.error(f"Error adding sample data: {e}")

    # ==================== USER MANAGEMENT ====================
    def get_or_create_user(self, telegram_id: str, username: str = "", full_name: str = "") -> int:
        """Get existing user or create new one, return user_id"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if user exists
                cursor.execute(
                    'SELECT id FROM users WHERE telegram_id = ?', 
                    (str(telegram_id),)
                )
                user = cursor.fetchone()
                
                if user:
                    user_id = user[0]
                    # Update last active and username if changed
                    cursor.execute(
                        'UPDATE users SET last_active = CURRENT_TIMESTAMP, username = ?, full_name = ? WHERE id = ?',
                        (username, full_name, user_id)
                    )
                else:
                    # Create new user
                    cursor.execute(
                        'INSERT INTO users (telegram_id, username, full_name) VALUES (?, ?, ?)',
                        (str(telegram_id), username, full_name)
                    )
                    user_id = cursor.lastrowid
                    logger.info(f"👤 New user created: {telegram_id} - {full_name}")
                
                return user_id
                
        except Exception as e:
            logger.error(f"Error in get_or_create_user: {e}")
            return 0

    def get_user(self, telegram_id: str) -> Optional[Dict[str, Any]]:
        """Get user data by telegram ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT * FROM users WHERE telegram_id = ?', 
                    (str(telegram_id),)
                )
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error in get_user: {e}")
            return None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user data by internal user ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error in get_user_by_id: {e}")
            return None

    def get_user_saldo(self, user_id: int) -> int:
        """Get user saldo/balance"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT saldo FROM users WHERE id = ?', (user_id,))
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error in get_user_saldo: {e}")
            return 0

    def update_user_saldo(self, user_id: int, amount: int) -> bool:
        """Update user saldo/balance"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE users SET saldo = saldo + ? WHERE id = ?',
                    (amount, user_id)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error in update_user_saldo: {e}")
            return False

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM users ORDER BY created_at DESC')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error in get_all_users: {e}")
            return []

    # ==================== TOPUP MANAGEMENT ====================
    def create_topup(self, user_id: int, amount: int, unique_code: int, total_amount: int, method: str, status: str = 'pending') -> int:
        """Create new topup request"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''INSERT INTO topups 
                    (user_id, amount, unique_code, total_amount, method, status) 
                    VALUES (?, ?, ?, ?, ?, ?)''',
                    (user_id, amount, unique_code, total_amount, method, status)
                )
                topup_id = cursor.lastrowid
                logger.info(f"💰 Topup created: ID {topup_id} - User {user_id} - Amount {amount}")
                return topup_id
        except Exception as e:
            logger.error(f"Error in create_topup: {e}")
            return 0

    def get_topup(self, topup_id: int) -> Optional[Dict[str, Any]]:
        """Get topup by ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM topups WHERE id = ?', (topup_id,))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error in get_topup: {e}")
            return None

    def update_topup_status(self, topup_id: int, status: str) -> bool:
        """Update topup status"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE topups SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (status, topup_id)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error in update_topup_status: {e}")
            return False

    def update_topup_proof(self, topup_id: int, proof_image: str) -> bool:
        """Update topup proof image"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE topups SET proof_image = ?, status = "waiting_approval", updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (proof_image, topup_id)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error in update_topup_proof: {e}")
            return False

    def get_user_topups(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get user's topup history"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT * FROM topups WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
                    (user_id, limit)
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error in get_user_topups: {e}")
            return []

    def get_pending_topups(self) -> List[Dict[str, Any]]:
        """Get all pending topups for admin"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT t.*, u.telegram_id, u.username, u.full_name 
                    FROM topups t 
                    JOIN users u ON t.user_id = u.id 
                    WHERE t.status IN ('pending', 'waiting_approval') 
                    ORDER BY t.created_at DESC
                ''')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error in get_pending_topups: {e}")
            return []

    def approve_topup(self, topup_id: int) -> bool:
        """Approve topup and add balance to user"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get topup details
                topup = self.get_topup(topup_id)
                if not topup:
                    return False
                
                # Update topup status
                cursor.execute(
                    'UPDATE topups SET status = "completed", updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (topup_id,)
                )
                
                # Add balance to user
                cursor.execute(
                    'UPDATE users SET saldo = saldo + ? WHERE id = ?',
                    (topup['amount'], topup['user_id'])
                )
                
                # Add transaction record
                cursor.execute(
                    'INSERT INTO transactions (user_id, type, amount, description) VALUES (?, "topup", ?, "Topup approved")',
                    (topup['user_id'], topup['amount'])
                )
                
                logger.info(f"✅ Topup approved: ID {topup_id} - User {topup['user_id']} - Amount {topup['amount']}")
                return True
                
        except Exception as e:
            logger.error(f"Error in approve_topup: {e}")
            return False

    # ==================== PRODUCT MANAGEMENT ====================
    def get_products(self, category: str = None, status: str = 'active') -> List[Dict[str, Any]]:
        """Get products with optional category filter"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if category:
                    cursor.execute(
                        'SELECT * FROM products WHERE category = ? AND status = ? ORDER BY name',
                        (category, status)
                    )
                else:
                    cursor.execute(
                        'SELECT * FROM products WHERE status = ? ORDER BY category, name',
                        (status,)
                    )
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error in get_products: {e}")
            return []

    def get_product(self, product_id: int) -> Optional[Dict[str, Any]]:
        """Get product by ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM products WHERE id = ?', (product_id,))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error in get_product: {e}")
            return None

    def update_product_stock(self, product_id: int, new_stock: int) -> bool:
        """Update product stock"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE products SET stock = ? WHERE id = ?',
                    (new_stock, product_id)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error in update_product_stock: {e}")
            return False

    def get_product_categories(self) -> List[str]:
        """Get all product categories"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT DISTINCT category FROM products WHERE status = "active"')
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error in get_product_categories: {e}")
            return []

    # ==================== ORDER MANAGEMENT ====================
    def create_order(self, user_id: int, product_id: int, quantity: int, total_price: int, customer_data: str = "") -> int:
        """Create new order"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''INSERT INTO orders 
                    (user_id, product_id, quantity, total_price, customer_data) 
                    VALUES (?, ?, ?, ?, ?)''',
                    (user_id, product_id, quantity, total_price, customer_data)
                )
                order_id = cursor.lastrowid
                return order_id
        except Exception as e:
            logger.error(f"Error in create_order: {e}")
            return 0

    def get_user_orders(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get user's order history"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT o.*, p.name as product_name, p.category 
                    FROM orders o 
                    JOIN products p ON o.product_id = p.id 
                    WHERE o.user_id = ? 
                    ORDER BY o.created_at DESC 
                    LIMIT ?
                ''', (user_id, limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error in get_user_orders: {e}")
            return []

    def update_order_status(self, order_id: int, status: str, sn: str = None) -> bool:
        """Update order status"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if sn:
                    cursor.execute(
                        'UPDATE orders SET status = ?, sn = ? WHERE id = ?',
                        (status, sn, order_id)
                    )
                else:
                    cursor.execute(
                        'UPDATE orders SET status = ? WHERE id = ?',
                        (status, order_id)
                    )
                
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error in update_order_status: {e}")
            return False

    # ==================== STATISTICS & REPORTING ====================
    def get_bot_statistics(self) -> Dict[str, Any]:
        """Get bot statistics for dashboard"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Total users
                cursor.execute('SELECT COUNT(*) as count FROM users')
                total_users = cursor.fetchone()[0]
                
                # Active users (last 30 days)
                cursor.execute('''
                    SELECT COUNT(*) as count FROM users 
                    WHERE last_active >= datetime('now', '-30 days')
                ''')
                active_users = cursor.fetchone()[0]
                
                # Active products
                cursor.execute('SELECT COUNT(*) as count FROM products WHERE status = "active"')
                active_products = cursor.fetchone()[0]
                
                # Total revenue from completed orders
                cursor.execute('''
                    SELECT COALESCE(SUM(total_price), 0) as total FROM orders 
                    WHERE status = 'completed'
                ''')
                total_revenue = cursor.fetchone()[0]
                
                # Pending topups
                cursor.execute('''
                    SELECT COUNT(*) as count FROM topups 
                    WHERE status IN ('pending', 'waiting_approval')
                ''')
                pending_topups = cursor.fetchone()[0]
                
                return {
                    'total_users': total_users,
                    'active_users': active_users,
                    'active_products': active_products,
                    'total_revenue': total_revenue,
                    'pending_topups': pending_topups
                }
                
        except Exception as e:
            logger.error(f"Error in get_bot_statistics: {e}")
            return {
                'total_users': 0,
                'active_users': 0,
                'active_products': 0,
                'total_revenue': 0,
                'pending_topups': 0
            }

    # ==================== ADMIN FUNCTIONS ====================
    def make_admin(self, telegram_id: str) -> bool:
        """Make user admin"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE users SET is_admin = TRUE WHERE telegram_id = ?',
                    (str(telegram_id),)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error in make_admin: {e}")
            return False

    def is_admin(self, telegram_id: str) -> bool:
        """Check if user is admin"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT is_admin FROM users WHERE telegram_id = ?',
                    (str(telegram_id),)
                )
                result = cursor.fetchone()
                return result[0] if result else False
        except Exception as e:
            logger.error(f"Error in is_admin: {e}")
            return False

# ==================== GLOBAL DATABASE INSTANCE ====================
db = DatabaseManager()

# ==================== COMPATIBILITY FUNCTIONS ====================
# Functions untuk compatibility dengan code yang sudah ada

def init_database():
    """Initialize database - compatibility function"""
    return db.init_database()

def get_or_create_user(telegram_id: str, username: str = "", full_name: str = "") -> int:
    """Get or create user - compatibility function"""
    return db.get_or_create_user(telegram_id, username, full_name)

def get_user_saldo(user_id: int) -> int:
    """Get user saldo - compatibility function"""
    return db.get_user_saldo(user_id)

def create_topup(user_id: int, amount: int, unique_code: int, total_amount: int, method: str, status: str = 'pending') -> int:
    """Create topup - compatibility function"""
    return db.create_topup(user_id, amount, unique_code, total_amount, method, status)

def update_topup_proof(topup_id: int, proof_image: str) -> bool:
    """Update topup proof - compatibility function"""
    return db.update_topup_proof(topup_id, proof_image)

def update_topup_status(topup_id: int, status: str) -> bool:
    """Update topup status - compatibility function"""
    return db.update_topup_status(topup_id, status)

def get_user_topups(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get user topups - compatibility function"""
    return db.get_user_topups(user_id, limit)

def get_pending_topups() -> List[Dict[str, Any]]:
    """Get pending topups - compatibility function"""
    return db.get_pending_topups()

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user by ID - compatibility function"""
    return db.get_user_by_id(user_id)

def get_bot_statistics() -> Dict[str, Any]:
    """Get bot statistics - compatibility function"""
    return db.get_bot_statistics()

def get_products(category: str = None, status: str = 'active') -> List[Dict[str, Any]]:
    """Get products - compatibility function"""
    return db.get_products(category, status)

def get_product(product_id: int) -> Optional[Dict[str, Any]]:
    """Get product - compatibility function"""
    return db.get_product(product_id)

def update_product_stock(product_id: int, new_stock: int) -> bool:
    """Update product stock - compatibility function"""
    return db.update_product_stock(product_id, new_stock)

def get_product_categories() -> List[str]:
    """Get product categories - compatibility function"""
    return db.get_product_categories()

def create_order(user_id: int, product_id: int, quantity: int, total_price: int, customer_data: str = "") -> int:
    """Create order - compatibility function"""
    return db.create_order(user_id, product_id, quantity, total_price, customer_data)

def update_order_status(order_id: int, status: str, sn: str = None) -> bool:
    """Update order status - compatibility function"""
    return db.update_order_status(order_id, status, sn)

def get_user_orders(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get user orders - compatibility function"""
    return db.get_user_orders(user_id, limit)

def update_user_saldo(user_id: int, amount: int) -> bool:
    """Update user saldo - compatibility function"""
    return db.update_user_saldo(user_id, amount)

def approve_topup(topup_id: int) -> bool:
    """Approve topup - compatibility function"""
    return db.approve_topup(topup_id)

def make_admin(telegram_id: str) -> bool:
    """Make admin - compatibility function"""
    return db.make_admin(telegram_id)

def is_admin(telegram_id: str) -> bool:
    """Check admin - compatibility function"""
    return db.is_admin(telegram_id)

def get_all_users() -> List[Dict[str, Any]]:
    """Get all users - compatibility function"""
    return db.get_all_users()

# Initialize database saat module diimport
if __name__ != "__main__":
    db.init_database()
