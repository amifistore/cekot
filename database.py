#!/usr/bin/env python3
"""
Database Management System - FULL VERSION SEMPURNA
Dengan semua fungsi yang diperlukan untuk kompatibilitas dengan topup_handler dan admin_handler
"""

import sqlite3
import logging
import os
import json
import time
import random
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
            self._connection_lock = threading.Lock()
            self.init_database()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections dengan retry mechanism"""
        max_retries = 5
        retry_delay = 0.1
        conn = None
        
        for attempt in range(max_retries):
            try:
                with self._connection_lock:
                    conn = sqlite3.connect(
                        self.db_path, 
                        check_same_thread=False,
                        timeout=30.0
                    )
                    conn.row_factory = sqlite3.Row
                    # Optimized PRAGMA settings
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.execute("PRAGMA journal_mode = WAL")
                    conn.execute("PRAGMA cache_size = -10000")
                    conn.execute("PRAGMA synchronous = NORMAL")
                    conn.execute("PRAGMA busy_timeout = 10000")
                    conn.execute("PRAGMA temp_store = MEMORY")
                    conn.execute("PRAGMA mmap_size = 268435456")
                
                yield conn
                
                # Commit only if no exception
                if conn:
                    conn.commit()
                break
                
            except sqlite3.OperationalError as e:
                if conn:
                    try:
                        conn.rollback()
                    except:
                        pass
                    finally:
                        conn.close()
                        conn = None
                
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt) + random.uniform(0, 0.1)
                    logger.warning(f"Database locked, retry {attempt + 1}/{max_retries} in {wait_time:.2f}s")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Database operational error after {attempt + 1} attempts: {e}")
                    raise
                    
            except Exception as e:
                if conn:
                    try:
                        conn.rollback()
                    except:
                        pass
                    finally:
                        conn.close()
                        conn = None
                logger.error(f"Unexpected database error: {e}")
                raise
                
        if conn:
            try:
                conn.close()
            except:
                pass

    def init_database(self):
        """Initialize semua tabel database dengan schema lengkap dan constraints"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # ==================== USERS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        username TEXT,
                        full_name TEXT NOT NULL,
                        balance REAL DEFAULT 0 CHECK(balance >= 0),
                        total_spent REAL DEFAULT 0 CHECK(total_spent >= 0),
                        total_orders INTEGER DEFAULT 0 CHECK(total_orders >= 0),
                        total_topups INTEGER DEFAULT 0 CHECK(total_topups >= 0),
                        registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
                        is_banned INTEGER DEFAULT 0 CHECK(is_banned IN (0,1)),
                        ban_reason TEXT,
                        language TEXT DEFAULT 'id',
                        level INTEGER DEFAULT 1 CHECK(level >= 1)
                    )
                ''')
                
                # ==================== PRODUCTS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS products (
                        code TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        price REAL NOT NULL CHECK(price >= 0),
                        status TEXT DEFAULT 'active' CHECK(status IN ('active','inactive','empty','disturb')),
                        description TEXT,
                        category TEXT DEFAULT 'Umum',
                        provider TEXT,
                        gangguan INTEGER DEFAULT 0 CHECK(gangguan IN (0,1)),
                        kosong INTEGER DEFAULT 0 CHECK(kosong IN (0,1)),
                        stock INTEGER DEFAULT 0 CHECK(stock >= 0),
                        min_stock INTEGER DEFAULT 0 CHECK(min_stock >= 0),
                        max_stock INTEGER DEFAULT 1000 CHECK(max_stock >= 0),
                        profit_margin REAL DEFAULT 0,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # ==================== TRANSACTIONS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        type TEXT NOT NULL CHECK(type IN ('topup','withdraw','refund','bonus')),
                        amount REAL NOT NULL CHECK(amount > 0),
                        status TEXT DEFAULT 'pending' CHECK(status IN ('pending','completed','rejected','cancelled')),
                        details TEXT,
                        unique_code INTEGER DEFAULT 0,
                        payment_method TEXT,
                        admin_notes TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        completed_at DATETIME,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                # ==================== ORDERS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        product_code TEXT NOT NULL,
                        product_name TEXT NOT NULL,
                        price REAL NOT NULL CHECK(price >= 0),
                        status TEXT DEFAULT 'pending' CHECK(status IN ('pending','processing','completed','failed','partial','refunded')),
                        provider_order_id TEXT,
                        customer_input TEXT,
                        response_data TEXT,
                        sn TEXT,
                        note TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        processed_at DATETIME,
                        completed_at DATETIME,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                        FOREIGN KEY (product_code) REFERENCES products (code)
                    )
                ''')
                
                # ==================== TOPUP REQUESTS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS topup_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        username TEXT,
                        full_name TEXT,
                        amount REAL NOT NULL,
                        status TEXT DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
                        proof_image TEXT,
                        unique_code INTEGER DEFAULT 0,
                        payment_method TEXT,
                        total_amount REAL DEFAULT 0,
                        admin_notes TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                # ==================== ADMIN LOGS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS admin_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        admin_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        target_type TEXT,
                        target_id TEXT,
                        details TEXT,
                        ip_address TEXT,
                        user_agent TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # ==================== SYSTEM LOGS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS system_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        level TEXT NOT NULL CHECK(level IN ('INFO','WARNING','ERROR','DEBUG','CRITICAL')),
                        module TEXT NOT NULL,
                        message TEXT NOT NULL,
                        details TEXT,
                        user_id TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # ==================== SETTINGS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        description TEXT,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # ==================== NOTIFICATIONS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS notifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        type TEXT DEFAULT 'info' CHECK(type IN ('info','success','warning','error')),
                        is_read INTEGER DEFAULT 0 CHECK(is_read IN (0,1)),
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                # Create indexes untuk performa
                indexes = [
                    'CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance)',
                    'CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned)',
                    'CREATE INDEX IF NOT EXISTS idx_users_active ON users(last_active)',
                    'CREATE INDEX IF NOT EXISTS idx_products_status ON products(status)',
                    'CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)',
                    'CREATE INDEX IF NOT EXISTS idx_products_price ON products(price)',
                    'CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status)',
                    'CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type)',
                    'CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)',
                    'CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at)',
                    'CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)',
                    'CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)',
                    'CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at)',
                    'CREATE INDEX IF NOT EXISTS idx_orders_product ON orders(product_code)',
                    'CREATE INDEX IF NOT EXISTS idx_topup_requests_status ON topup_requests(status)',
                    'CREATE INDEX IF NOT EXISTS idx_topup_requests_user ON topup_requests(user_id)',
                    'CREATE INDEX IF NOT EXISTS idx_admin_logs_admin ON admin_logs(admin_id)',
                    'CREATE INDEX IF NOT EXISTS idx_admin_logs_time ON admin_logs(timestamp)',
                    'CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(level)',
                    'CREATE INDEX IF NOT EXISTS idx_system_logs_time ON system_logs(timestamp)',
                    'CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)',
                    'CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read)'
                ]
                
                for index in indexes:
                    try:
                        cursor.execute(index)
                    except Exception as e:
                        logger.warning(f"Could not create index {index}: {e}")
                
                # Insert default settings
                default_settings = [
                    ('system_name', 'Bot System', 'Nama sistem bot'),
                    ('maintenance_mode', '0', 'Mode maintenance (1=aktif, 0=nonaktif)'),
                    ('min_topup', '10000', 'Minimum topup'),
                    ('max_topup', '1000000', 'Maksimum topup'),
                    ('admin_contact', '@admin', 'Kontak admin'),
                    ('auto_sync_products', '1', 'Auto sync products (1=aktif, 0=nonaktif)'),
                    ('profit_margin', '0', 'Margin profit default (%)')
                ]
                
                cursor.executemany('''
                    INSERT OR IGNORE INTO settings (key, value, description) 
                    VALUES (?, ?, ?)
                ''', default_settings)
                
                logger.info("✅ Database initialized successfully with all tables")
                
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}", exc_info=True)
            raise

    # ==================== USER MANAGEMENT ====================
    def get_or_create_user(self, user_id: str, username: str = "", full_name: str = "") -> Dict[str, Any]:
        """Get existing user or create new one dengan update data"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Check if user exists
                    cursor.execute(
                        'SELECT * FROM users WHERE user_id = ?', 
                        (str(user_id),)
                    )
                    user = cursor.fetchone()
                    
                    if user:
                        if user['is_banned']:
                            raise PermissionError(f"User {user_id} is banned. Reason: {user['ban_reason']}")
                        
                        # Update user info jika berubah
                        update_fields = []
                        params = []
                        
                        if username and username != user['username']:
                            update_fields.append("username = ?")
                            params.append(username)
                        
                        if full_name and full_name != user['full_name']:
                            update_fields.append("full_name = ?")
                            params.append(full_name)
                        
                        if update_fields:
                            update_fields.append("last_active = ?")
                            params.extend([datetime.now(), str(user_id)])
                            
                            update_query = f"UPDATE users SET {', '.join(update_fields)} WHERE user_id = ?"
                            cursor.execute(update_query, params)
                            logger.info(f"📝 User updated: {user_id} - {full_name}")
                    else:
                        # Create new user
                        cursor.execute(
                            'INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?)',
                            (str(user_id), username, full_name)
                        )
                        logger.info(f"👤 New user created: {user_id} - {full_name}")
                    
                    # Return user data
                    cursor.execute('SELECT * FROM users WHERE user_id = ?', (str(user_id),))
                    result = cursor.fetchone()
                    return dict(result) if result else {}
                    
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)
                    logger.warning(f"User operation locked, retrying... Attempt {attempt + 1}")
                    time.sleep(wait_time)
                    continue
                else:
                    raise
            except Exception as e:
                logger.error(f"Error in get_or_create_user for {user_id}: {e}")
                raise

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user data by ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM users WHERE user_id = ?', (str(user_id),))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None

    def get_user_balance(self, user_id: str) -> float:
        """Get user balance dengan error handling"""
        try:
            user = self.get_user(user_id)
            return user['balance'] if user else 0.0
        except Exception as e:
            logger.error(f"Error getting balance for {user_id}: {e}")
            return 0.0

    def update_user_balance(self, user_id: str, amount: float, note: str = "") -> bool:
        """Update user balance dengan validation dan logging"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Check if user exists and not banned
                    cursor.execute(
                        'SELECT balance, is_banned FROM users WHERE user_id = ?', 
                        (str(user_id),)
                    )
                    user = cursor.fetchone()
                    
                    if not user:
                        raise ValueError(f"User {user_id} not found")
                    
                    if user['is_banned']:
                        raise PermissionError(f"User {user_id} is banned")
                    
                    new_balance = user['balance'] + amount
                    if new_balance < 0:
                        raise ValueError("Insufficient balance")
                    
                    cursor.execute(
                        'UPDATE users SET balance = ?, last_active = ? WHERE user_id = ?',
                        (new_balance, datetime.now(), str(user_id))
                    )
                    
                    # Log the balance change
                    if amount > 0:
                        cursor.execute(
                            'UPDATE users SET total_topups = total_topups + 1 WHERE user_id = ?',
                            (str(user_id),)
                        )
                        log_message = f"Balance increased: {amount:,.0f} - {note}"
                    else:
                        log_message = f"Balance decreased: {amount:,.0f} - {note}"
                    
                    # Simplified logging to avoid nested transactions
                    try:
                        cursor.execute('''
                            INSERT INTO system_logs (level, module, message, user_id)
                            VALUES (?, ?, ?, ?)
                        ''', ('INFO', 'BALANCE_UPDATE', f"User {user_id}: {log_message}", user_id))
                    except Exception as log_error:
                        logger.warning(f"Could not log balance update: {log_error}")
                    
                    logger.info(f"💰 Balance updated: {user_id} -> {amount:,.0f} | New balance: {new_balance:,.0f}")
                    return True
                    
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)
                    logger.warning(f"Balance update locked, retrying... Attempt {attempt + 1}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Error updating balance for {user_id} after {attempt + 1} attempts: {e}")
                    raise
            except Exception as e:
                logger.error(f"Error updating balance for {user_id}: {e}")
                raise
        
        return False

    def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get comprehensive user statistics"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT 
                        u.*,
                        COUNT(DISTINCT o.id) as successful_orders,
                        COUNT(DISTINCT t.id) as successful_topups,
                        SUM(CASE WHEN o.status = 'completed' THEN o.price ELSE 0 END) as total_success_spent,
                        COUNT(DISTINCT CASE WHEN o.status = 'completed' THEN o.id ELSE NULL END) as total_success_orders
                    FROM users u
                    LEFT JOIN orders o ON u.user_id = o.user_id
                    LEFT JOIN transactions t ON u.user_id = t.user_id AND t.status = 'completed' AND t.type = 'topup'
                    WHERE u.user_id = ?
                    GROUP BY u.user_id
                ''', (str(user_id),))
                
                result = cursor.fetchone()
                
                if result:
                    # Calculate success rate
                    total_orders = result['total_orders'] or 0
                    success_orders = result['total_success_orders'] or 0
                    success_rate = (success_orders / total_orders * 100) if total_orders > 0 else 0
                    
                    return {
                        'user_id': result['user_id'],
                        'username': result['username'],
                        'full_name': result['full_name'],
                        'balance': result['balance'],
                        'total_orders': total_orders,
                        'total_spent': result['total_spent'],
                        'total_topups': result['total_topups'],
                        'successful_orders': success_orders,
                        'successful_topups': result['successful_topups'],
                        'total_success_spent': result['total_success_spent'] or 0,
                        'success_rate': round(success_rate, 2),
                        'registered_at': result['registered_at'],
                        'last_active': result['last_active'],
                        'is_banned': result['is_banned']
                    }
                return {}
        except Exception as e:
            logger.error(f"Error getting user stats for {user_id}: {e}")
            return {}

    def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get user info untuk admin panel"""
        return self.get_user(user_id) or {}

    def get_recent_users(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent active users untuk admin panel"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, username, full_name, balance, last_active, registered_at
                    FROM users 
                    WHERE is_banned = 0
                    ORDER BY last_active DESC 
                    LIMIT ?
                ''', (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting recent users: {e}")
            return []

    def get_active_users(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get active users dalam X hari terakhir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute('''
                    SELECT user_id, username, full_name, balance, last_active
                    FROM users 
                    WHERE last_active >= ? AND is_banned = 0
                    ORDER BY last_active DESC
                ''', (cutoff_date,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting active users: {e}")
            return []

    def count_inactive_users(self, days: int = 30) -> int:
        """Count inactive users (tidak aktif dalam X hari)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute('''
                    SELECT COUNT(*) as count
                    FROM users 
                    WHERE last_active < ? AND is_banned = 0
                ''', (cutoff_date,))
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            logger.error(f"Error counting inactive users: {e}")
            return 0

    def delete_inactive_users(self, days: int = 30) -> int:
        """Delete inactive users dan return count yang dihapus"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Get users to delete for logging
                    cursor.execute('''
                        SELECT user_id, username, full_name, last_active
                        FROM users 
                        WHERE last_active < ? AND is_banned = 0
                    ''', (cutoff_date,))
                    users_to_delete = cursor.fetchall()
                    
                    if not users_to_delete:
                        return 0
                    
                    # Delete users
                    cursor.execute('''
                        DELETE FROM users 
                        WHERE last_active < ? AND is_banned = 0
                    ''', (cutoff_date,))
                    
                    deleted_count = len(users_to_delete)
                    
                    # Log the cleanup
                    for user in users_to_delete:
                        try:
                            cursor.execute('''
                                INSERT INTO system_logs (level, module, message)
                                VALUES (?, ?, ?)
                            ''', ('INFO', 'CLEANUP_USER', 
                                f"Deleted inactive user: {user['user_id']} - {user['full_name']} "
                                f"(Last active: {user['last_active']})"))
                        except Exception as log_error:
                            logger.warning(f"Could not log user cleanup: {log_error}")
                    
                    logger.info(f"🧹 Deleted {deleted_count} inactive users")
                    return deleted_count
                    
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)
                    logger.warning(f"Delete inactive users locked, retrying... Attempt {attempt + 1}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Error deleting inactive users after {attempt + 1} attempts: {e}")
                    return 0
            except Exception as e:
                logger.error(f"Error deleting inactive users: {e}")
                return 0
        
        return 0

    # ==================== PRODUCT MANAGEMENT ====================
    def get_products_by_category(self, category: str = None, status: str = 'active') -> List[Dict[str, Any]]:
        """Get products filtered by category and status"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if category:
                    cursor.execute('''
                        SELECT * FROM products 
                        WHERE category = ? AND status = ?
                        ORDER BY name ASC
                    ''', (category, status))
                else:
                    cursor.execute('''
                        SELECT * FROM products 
                        WHERE status = ?
                        ORDER BY category, name ASC
                    ''', (status,))
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting products by category: {e}")
            return []

    def get_product(self, product_code: str) -> Optional[Dict[str, Any]]:
        """Get product by code"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM products WHERE code = ?', (product_code,))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting product {product_code}: {e}")
            return None

    def update_product(self, product_code: str, **kwargs) -> bool:
        """Update product data"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    valid_fields = ['name', 'price', 'status', 'description', 'category', 
                                  'provider', 'gangguan', 'kosong', 'stock']
                    update_fields = []
                    params = []
                    
                    for field, value in kwargs.items():
                        if field in valid_fields:
                            update_fields.append(f"{field} = ?")
                            params.append(value)
                    
                    if not update_fields:
                        return False
                    
                    update_fields.append("updated_at = ?")
                    params.extend([datetime.now(), product_code])
                    
                    query = f"UPDATE products SET {', '.join(update_fields)} WHERE code = ?"
                    cursor.execute(query, params)
                    
                    logger.info(f"📦 Product updated: {product_code}")
                    return True
                    
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)
                    logger.warning(f"Product update locked, retrying... Attempt {attempt + 1}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Error updating product {product_code} after {attempt + 1} attempts: {e}")
                    return False
            except Exception as e:
                logger.error(f"Error updating product {product_code}: {e}")
                return False
        
        return False

    def count_inactive_products(self) -> int:
        """Count inactive products"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) as count FROM products WHERE status = "inactive"')
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            logger.error(f"Error counting inactive products: {e}")
            return 0

    def delete_inactive_products(self) -> int:
        """Delete inactive products dan return count yang dihapus"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Get products to delete for logging
                    cursor.execute('SELECT code, name FROM products WHERE status = "inactive"')
                    products_to_delete = cursor.fetchall()
                    
                    if not products_to_delete:
                        return 0
                    
                    # Delete products
                    cursor.execute('DELETE FROM products WHERE status = "inactive"')
                    
                    deleted_count = len(products_to_delete)
                    
                    # Log the cleanup
                    for product in products_to_delete:
                        try:
                            cursor.execute('''
                                INSERT INTO system_logs (level, module, message)
                                VALUES (?, ?, ?)
                            ''', ('INFO', 'CLEANUP_PRODUCT', 
                                f"Deleted inactive product: {product['code']} - {product['name']}"))
                        except Exception as log_error:
                            logger.warning(f"Could not log product cleanup: {log_error}")
                    
                    logger.info(f"🧹 Deleted {deleted_count} inactive products")
                    return deleted_count
                    
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)
                    logger.warning(f"Delete products locked, retrying... Attempt {attempt + 1}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Error deleting inactive products after {attempt + 1} attempts: {e}")
                    return 0
            except Exception as e:
                logger.error(f"Error deleting inactive products: {e}")
                return 0
        
        return 0

    # ==================== TOPUP MANAGEMENT - FIXED VERSION ====================
    def create_topup_request(self, user_id: str, amount: float, payment_method: str = "", proof_image: str = "", unique_code: int = 0, status: str = "pending") -> int:
        """Create new topup request dengan semua parameter yang diperlukan"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Get user info
                    user = self.get_user(user_id)
                    if not user:
                        raise ValueError(f"User {user_id} not found")
                    
                    # Generate unique code jika tidak disediakan
                    if unique_code == 0:
                        unique_code = int(datetime.now().timestamp() % 1000)
                    
                    total_amount = amount + unique_code
                    
                    cursor.execute('''
                        INSERT INTO topup_requests 
                        (user_id, username, full_name, amount, proof_image, unique_code, payment_method, total_amount, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        str(user_id), user.get('username'), user.get('full_name'), 
                        amount, proof_image, unique_code, payment_method, total_amount, status
                    ))
                    
                    topup_id = cursor.lastrowid
                    logger.info(f"💳 Topup request created: ID {topup_id} for user {user_id} - Amount: {amount:,.0f}, Unique Code: {unique_code}")
                    return topup_id
                    
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)
                    logger.warning(f"Create topup locked, retrying... Attempt {attempt + 1}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Error creating topup request after {attempt + 1} attempts: {e}")
                    raise
            except Exception as e:
                logger.error(f"Error creating topup request: {e}")
                raise
        
        raise Exception("Failed to create topup request after retries")

    def create_topup(self, user_id: str, amount: float, payment_method: str = "", status: str = "pending", unique_code: int = 0) -> int:
        """Alias untuk create_topup_request dengan parameter yang sesuai untuk topup_handler"""
        return self.create_topup_request(
            user_id=user_id,
            amount=amount,
            payment_method=payment_method,
            proof_image="",  # Default empty untuk QRIS
            unique_code=unique_code,
            status=status
        )

    def get_pending_topups(self) -> List[Dict[str, Any]]:
        """Get all pending topup requests"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM topup_requests 
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                ''')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting pending topups: {e}")
            return []

    def get_topup_by_id(self, topup_id: int) -> Optional[Dict[str, Any]]:
        """Get topup request by ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM topup_requests WHERE id = ?', (topup_id,))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting topup {topup_id}: {e}")
            return None

    def approve_topup(self, topup_id: int, admin_id: str, *args) -> bool:
        """Approve topup request dan tambahkan saldo - FIXED VERSION dengan *args"""
        max_retries = 5
        
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Get topup details
                    topup = self.get_topup_by_id(topup_id)
                    if not topup:
                        raise ValueError(f"Topup {topup_id} not found")
                    
                    if topup['status'] != 'pending':
                        raise ValueError(f"Topup {topup_id} already processed")
                    
                    user_id = topup['user_id']
                    amount = topup['amount']
                    
                    # Update topup status
                    cursor.execute('''
                        UPDATE topup_requests 
                        SET status = 'approved', updated_at = ?, admin_notes = ?
                        WHERE id = ?
                    ''', (datetime.now(), f"Approved by admin {admin_id}", topup_id))
                    
                    # Add balance to user
                    success = self.update_user_balance(user_id, amount, f"Topup approved - ID: {topup_id}")
                    
                    if not success:
                        raise Exception("Failed to update user balance")
                    
                    # Create transaction record
                    cursor.execute('''
                        INSERT INTO transactions (user_id, type, amount, status, details, completed_at)
                        VALUES (?, 'topup', ?, 'completed', ?, ?)
                    ''', (user_id, amount, f"Topup approved - ID: {topup_id}", datetime.now()))
                    
                    logger.info(f"✅ Topup approved: ID {topup_id} for user {user_id}, amount: {amount}")
                    return True
                    
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.2 * (2 ** attempt)
                    logger.warning(f"Approve topup locked, retrying... Attempt {attempt + 1}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Error approving topup {topup_id} after {attempt + 1} attempts: {e}")
                    return False
            except Exception as e:
                logger.error(f"Error approving topup {topup_id}: {e}")
                return False
        
        return False

    def reject_topup(self, topup_id: int, admin_id: str, *args) -> bool:
        """Reject topup request - FIXED VERSION dengan *args"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute('''
                        UPDATE topup_requests 
                        SET status = 'rejected', updated_at = ?, admin_notes = ?
                        WHERE id = ?
                    ''', (datetime.now(), f"Rejected by admin {admin_id}", topup_id))
                    
                    logger.info(f"❌ Topup rejected: ID {topup_id}")
                    return True
                    
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)
                    logger.warning(f"Reject topup locked, retrying... Attempt {attempt + 1}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Error rejecting topup {topup_id} after {attempt + 1} attempts: {e}")
                    return False
            except Exception as e:
                logger.error(f"Error rejecting topup {topup_id}: {e}")
                return False
        
        return False

    # ==================== ORDER MANAGEMENT ====================
    def create_order(self, user_id: str, product_code: str, customer_input: str) -> int:
        """Create new order"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Get product details
                    product = self.get_product(product_code)
                    if not product:
                        raise ValueError(f"Product {product_code} not found")
                    
                    if product['status'] != 'active':
                        raise ValueError(f"Product {product_code} is not active")
                    
                    # Check user balance
                    user_balance = self.get_user_balance(user_id)
                    if user_balance < product['price']:
                        raise ValueError("Insufficient balance")
                    
                    # Deduct balance
                    success = self.update_user_balance(user_id, -product['price'], f"Order product: {product['name']}")
                    if not success:
                        raise Exception("Failed to deduct balance")
                    
                    # Create order
                    cursor.execute('''
                        INSERT INTO orders 
                        (user_id, product_code, product_name, price, customer_input, status)
                        VALUES (?, ?, ?, ?, ?, 'pending')
                    ''', (str(user_id), product_code, product['name'], product['price'], customer_input))
                    
                    order_id = cursor.lastrowid
                    
                    # Update user stats
                    cursor.execute('''
                        UPDATE users 
                        SET total_orders = total_orders + 1, 
                            total_spent = total_spent + ?,
                            last_active = ?
                        WHERE user_id = ?
                    ''', (product['price'], datetime.now(), str(user_id)))
                    
                    logger.info(f"🛒 Order created: ID {order_id} for user {user_id} - Product: {product['name']}")
                    return order_id
                    
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)
                    logger.warning(f"Create order locked, retrying... Attempt {attempt + 1}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Error creating order after {attempt + 1} attempts: {e}")
                    raise
            except Exception as e:
                logger.error(f"Error creating order: {e}")
                raise
        
        raise Exception("Failed to create order after retries")

    def update_order_status(self, order_id: int, status: str, sn: str = "", note: str = "") -> bool:
        """Update order status"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    update_fields = ["status = ?"]
                    params = [status]
                    
                    if sn:
                        update_fields.append("sn = ?")
                        params.append(sn)
                    
                    if note:
                        update_fields.append("note = ?")
                        params.append(note)
                    
                    if status == 'completed':
                        update_fields.append("completed_at = ?")
                        params.append(datetime.now())
                    elif status == 'processing':
                        update_fields.append("processed_at = ?")
                        params.append(datetime.now())
                    
                    params.append(order_id)
                    
                    query = f"UPDATE orders SET {', '.join(update_fields)} WHERE id = ?"
                    cursor.execute(query, params)
                    
                    logger.info(f"📦 Order {order_id} status updated to: {status}")
                    return True
                    
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)
                    logger.warning(f"Update order status locked, retrying... Attempt {attempt + 1}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Error updating order {order_id} after {attempt + 1} attempts: {e}")
                    return False
            except Exception as e:
                logger.error(f"Error updating order {order_id}: {e}")
                return False
        
        return False

    # ==================== STATISTICS & ANALYTICS ====================
    def get_bot_statistics(self) -> Dict[str, Any]:
        """Get comprehensive bot statistics"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Basic counts
                cursor.execute('SELECT COUNT(*) as total_users FROM users WHERE is_banned = 0')
                total_users = cursor.fetchone()['total_users']
                
                cursor.execute('''
                    SELECT COUNT(*) as active_users FROM users 
                    WHERE last_active >= datetime('now', '-30 days') AND is_banned = 0
                ''')
                active_users = cursor.fetchone()['active_users']
                
                cursor.execute('SELECT COUNT(*) as active_products FROM products WHERE status = "active"')
                active_products = cursor.fetchone()['active_products']
                
                cursor.execute('SELECT COUNT(*) as pending_topups FROM topup_requests WHERE status = "pending"')
                pending_topups = cursor.fetchone()['pending_topups']
                
                # Financial stats
                cursor.execute('SELECT SUM(balance) as total_balance FROM users WHERE is_banned = 0')
                total_balance = cursor.fetchone()['total_balance'] or 0
                
                cursor.execute('SELECT SUM(total_spent) as total_revenue FROM users')
                total_revenue = cursor.fetchone()['total_revenue'] or 0
                
                # Today's stats
                today = datetime.now().strftime('%Y-%m-%d')
                cursor.execute('''
                    SELECT COUNT(*) as new_users_today FROM users 
                    WHERE date(registered_at) = ?
                ''', (today,))
                new_users_today = cursor.fetchone()['new_users_today']
                
                cursor.execute('''
                    SELECT COUNT(*) as orders_today FROM orders 
                    WHERE date(created_at) = ?
                ''', (today,))
                orders_today = cursor.fetchone()['orders_today']
                
                cursor.execute('''
                    SELECT SUM(price) as revenue_today FROM orders 
                    WHERE date(created_at) = ? AND status = 'completed'
                ''', (today,))
                revenue_today = cursor.fetchone()['revenue_today'] or 0
                
                # Order success rate
                cursor.execute('SELECT COUNT(*) as total_orders FROM orders')
                total_orders = cursor.fetchone()['total_orders'] or 0
                
                cursor.execute('SELECT COUNT(*) as success_orders FROM orders WHERE status = "completed"')
                success_orders = cursor.fetchone()['success_orders'] or 0
                
                success_rate = (success_orders / total_orders * 100) if total_orders > 0 else 0
                
                # Topup stats
                cursor.execute('SELECT SUM(amount) as total_topup FROM transactions WHERE type = "topup" AND status = "completed"')
                total_topup = cursor.fetchone()['total_topup'] or 0
                
                return {
                    'total_users': total_users,
                    'active_users': active_users,
                    'active_products': active_products,
                    'pending_topups': pending_topups,
                    'total_balance': total_balance,
                    'total_revenue': total_revenue,
                    'new_users_today': new_users_today,
                    'orders_today': orders_today,
                    'revenue_today': revenue_today,
                    'total_orders': total_orders,
                    'success_orders': success_orders,
                    'success_rate': round(success_rate, 2),
                    'total_topup': total_topup,
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
        except Exception as e:
            logger.error(f"Error getting bot statistics: {e}")
            # Return default values
            return {
                'total_users': 0,
                'active_users': 0,
                'active_products': 0,
                'pending_topups': 0,
                'total_balance': 0,
                'total_revenue': 0,
                'new_users_today': 0,
                'orders_today': 0,
                'revenue_today': 0,
                'total_orders': 0,
                'success_orders': 0,
                'success_rate': 0,
                'total_topup': 0,
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

    def get_user_statistics(self) -> Dict[str, Any]:
        """Get user statistics untuk admin panel"""
        stats = self.get_bot_statistics()
        
        # Additional user stats
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Count admins
                cursor.execute('SELECT COUNT(*) as total_admins FROM users WHERE level >= 10')
                total_admins = cursor.fetchone()['total_admins']
                
                stats['total_admins'] = total_admins
                return stats
        except Exception as e:
            logger.error(f"Error getting user statistics: {e}")
            stats['total_admins'] = 0
            return stats

    # ==================== ADMIN MANAGEMENT ====================
    def is_user_admin(self, user_id: str) -> bool:
        """Check if user is admin"""
        user = self.get_user(user_id)
        return user and user.get('level', 0) >= 10 if user else False

    def make_user_admin(self, user_id: str) -> bool:
        """Make user an admin"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE users SET level = 10 WHERE user_id = ?
                    ''', (str(user_id),))
                    
                    logger.info(f"👑 User {user_id} promoted to admin")
                    return True
                    
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)
                    logger.warning(f"Make admin locked, retrying... Attempt {attempt + 1}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Error making user {user_id} admin after {attempt + 1} attempts: {e}")
                    return False
            except Exception as e:
                logger.error(f"Error making user {user_id} admin: {e}")
                return False
        
        return False

    def remove_user_admin(self, user_id: str) -> bool:
        """Remove admin privileges from user"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE users SET level = 1 WHERE user_id = ?
                    ''', (str(user_id),))
                    
                    logger.info(f"👑 User {user_id} admin privileges removed")
                    return True
                    
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)
                    logger.warning(f"Remove admin locked, retrying... Attempt {attempt + 1}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Error removing admin from user {user_id} after {attempt + 1} attempts: {e}")
                    return False
            except Exception as e:
                logger.error(f"Error removing admin from user {user_id}: {e}")
                return False
        
        return False

    # ==================== LOGGING ====================
    def add_system_log(self, level: str, module: str, message: str, user_id: str = None):
        """Add system log entry"""
        try:
            # Use a separate connection for logging to avoid transaction conflicts
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO system_logs (level, module, message, user_id)
                VALUES (?, ?, ?, ?)
            ''', (level, module, message, user_id))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"LOG [{level}] {module}: {message} (User: {user_id}) - DB Error: {e}")

    def add_admin_log(self, admin_id: str, action: str, target_type: str = None, target_id: str = None, details: str = None):
        """Add admin action log"""
        try:
            # Use a separate connection for logging to avoid transaction conflicts
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO admin_logs (admin_id, action, target_type, target_id, details)
                VALUES (?, ?, ?, ?, ?)
            ''', (admin_id, action, target_type, target_id, details))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"ADMIN LOG: {admin_id} - {action} - {target_type} - {target_id} - {details} - DB Error: {e}")

    # ==================== UTILITY METHODS ====================
    def add_user_balance(self, user_id: str, amount: float) -> bool:
        """Add balance to user (for admin)"""
        return self.update_user_balance(user_id, amount, "Admin manual adjustment")

    def subtract_user_balance(self, user_id: str, amount: float) -> bool:
        """Subtract balance from user (for admin)"""
        return self.update_user_balance(user_id, -amount, "Admin manual adjustment")

    def get_all_users(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all users dengan pagination"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, username, full_name, balance, last_active, registered_at, is_banned
                    FROM users 
                    ORDER BY registered_at DESC 
                    LIMIT ?
                ''', (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []

    # ==================== NEW FUNCTIONS FOR COMPATIBILITY ====================
    def get_pending_topups_count(self) -> int:
        """Get count of pending topup requests"""
        try:
            topups = self.get_pending_topups()
            return len(topups)
        except Exception as e:
            logger.error(f"Error getting pending topups count: {e}")
            return 0

    def get_total_users_count(self) -> int:
        """Get total number of users"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) as count FROM users WHERE is_banned = 0')
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            logger.error(f"Error getting total users count: {e}")
            return 0

    def get_total_products_count(self) -> int:
        """Get total number of products"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) as count FROM products WHERE status = "active"')
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            logger.error(f"Error getting total products count: {e}")
            return 0

    def get_total_orders_count(self) -> int:
        """Get total number of orders"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) as count FROM orders')
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            logger.error(f"Error getting total orders count: {e}")
            return 0

    def get_total_revenue_amount(self) -> float:
        """Get total revenue from orders"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT SUM(price) as total FROM orders WHERE status = "completed"')
                result = cursor.fetchone()
                return result['total'] or 0
        except Exception as e:
            logger.error(f"Error getting total revenue: {e}")
            return 0

    def cleanup_old_orders(self, days: int = 30) -> int:
        """Cleanup old orders"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM orders WHERE created_at < ? AND status IN ("completed", "failed")', (cutoff_date,))
                deleted_count = cursor.rowcount
                logger.info(f"Cleaned up {deleted_count} old orders")
                return deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up old orders: {e}")
            return 0

    def cleanup_old_topups(self, days: int = 30) -> int:
        """Cleanup old topup requests"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM topup_requests WHERE created_at < ? AND status IN ("approved", "rejected")', (cutoff_date,))
                deleted_count = cursor.rowcount
                logger.info(f"Cleaned up {deleted_count} old topups")
                return deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up old topups: {e}")
            return 0

# ==================== MODULE-LEVEL FUNCTIONS ====================
# Create global instance
_db_manager = DatabaseManager()

# Export module-level functions untuk backward compatibility
def init_database():
    return _db_manager.init_database()

def get_or_create_user(user_id: str, username: str = "", full_name: str = ""):
    return _db_manager.get_or_create_user(user_id, username, full_name)

def get_user(user_id: str):
    return _db_manager.get_user(user_id)

def get_user_saldo(user_id: str):
    return _db_manager.get_user_balance(user_id)

def get_user_info(user_id: str):
    return _db_manager.get_user_info(user_id)

def get_user_balance(user_id: str):
    return _db_manager.get_user_balance(user_id)

def update_user_balance(user_id: str, amount: float, note: str = ""):
    return _db_manager.update_user_balance(user_id, amount, note)

def add_user_balance(user_id: str, amount: float):
    return _db_manager.add_user_balance(user_id, amount)

def subtract_user_balance(user_id: str, amount: float):
    return _db_manager.subtract_user_balance(user_id, amount)

def get_recent_users(limit: int = 20):
    return _db_manager.get_recent_users(limit)

def get_active_users(days: int = 30):
    return _db_manager.get_active_users(days)

def count_inactive_users(days: int = 30):
    return _db_manager.count_inactive_users(days)

def delete_inactive_users(days: int = 30):
    return _db_manager.delete_inactive_users(days)

def get_products_by_category(category: str = None, status: str = 'active'):
    return _db_manager.get_products_by_category(category, status)

def get_product(product_code: str):
    return _db_manager.get_product(product_code)

def update_product(product_code: str, **kwargs):
    return _db_manager.update_product(product_code, **kwargs)

def count_inactive_products():
    return _db_manager.count_inactive_products()

def delete_inactive_products():
    return _db_manager.delete_inactive_products()

def create_topup_request(user_id: str, amount: float, payment_method: str = "", proof_image: str = "", unique_code: int = 0, status: str = "pending"):
    return _db_manager.create_topup_request(user_id, amount, payment_method, proof_image, unique_code, status)

# FIXED: Fungsi create_topup yang menerima semua parameter yang diperlukan oleh topup_handler
def create_topup(user_id: str, amount: float, payment_method: str = "", status: str = "pending", unique_code: int = 0):
    """Fungsi create_topup yang kompatibel dengan topup_handler - menerima parameter unique_code"""
    return _db_manager.create_topup(user_id, amount, payment_method, status, unique_code)

def get_pending_topups():
    return _db_manager.get_pending_topups()

def get_topup_by_id(topup_id: int):
    return _db_manager.get_topup_by_id(topup_id)

def approve_topup(topup_id: int, admin_id: str, *args):
    """Approve topup request - FIXED dengan *args untuk kompatibilitas"""
    return _db_manager.approve_topup(topup_id, admin_id, *args)

def reject_topup(topup_id: int, admin_id: str, *args):
    """Reject topup request - FIXED dengan *args untuk kompatibilitas"""
    return _db_manager.reject_topup(topup_id, admin_id, *args)

def create_order(user_id: str, product_code: str, customer_input: str):
    return _db_manager.create_order(user_id, product_code, customer_input)

def update_order_status(order_id: int, status: str, sn: str = "", note: str = ""):
    return _db_manager.update_order_status(order_id, status, sn, note)

def get_bot_statistics():
    return _db_manager.get_bot_statistics()

def get_user_statistics():
    return _db_manager.get_user_statistics()

def is_user_admin(user_id: str):
    return _db_manager.is_user_admin(user_id)

def make_user_admin(user_id: str):
    return _db_manager.make_user_admin(user_id)

def remove_user_admin(user_id: str):
    return _db_manager.remove_user_admin(user_id)

def add_system_log(level: str, module: str, message: str, user_id: str = None):
    return _db_manager.add_system_log(level, module, message, user_id)

def add_admin_log(admin_id: str, action: str, target_type: str = None, target_id: str = None, details: str = None):
    return _db_manager.add_admin_log(admin_id, action, target_type, target_id, details)

def get_all_users(limit: int = 100):
    return _db_manager.get_all_users(limit)

# NEW FUNCTIONS untuk kompatibilitas dengan admin_handler dan topup_handler
def get_pending_topups_count():
    return _db_manager.get_pending_topups_count()

def get_total_users():
    return _db_manager.get_total_users_count()

def get_total_products():
    return _db_manager.get_total_products_count()

def get_total_orders():
    return _db_manager.get_total_orders_count()

def get_total_revenue():
    return _db_manager.get_total_revenue_amount()

def cleanup_old_orders(days: int = 30):
    return _db_manager.cleanup_old_orders(days)

def cleanup_old_topups(days: int = 30):
    return _db_manager.cleanup_old_topups(days)

# Export the manager untuk advanced usage
def get_db_manager():
    return _db_manager

if __name__ == "__main__":
    # Test the database
    print("🧪 Testing database...")
    db = DatabaseManager()
    print("✅ Database initialized successfully!")
    
    # Test user creation
    user = db.get_or_create_user("test_user", "testuser", "Test User")
    print(f"✅ User test: {user}")
    
    # Test topup creation dengan unique_code
    topup_id = db.create_topup("test_user", 50000, "QRIS", "pending", 123)
    print(f"✅ Topup creation test: ID {topup_id}")
    
    # Test statistics
    stats = db.get_bot_statistics()
    print(f"✅ Statistics: {stats}")
    
    # Test new functions
    print(f"✅ Total users: {get_total_users()}")
    print(f"✅ Total products: {get_total_products()}")
    print(f"✅ Total orders: {get_total_orders()}")
    print(f"✅ Total revenue: {get_total_revenue()}")
    print(f"✅ Pending topups count: {get_pending_topups_count()}")
    
    print("🚀 Database FULL VERSION SEMPURNA ready!")
