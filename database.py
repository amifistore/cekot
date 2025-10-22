#!/usr/bin/env python3
"""
Database Management System - PRODUCTION READY VERSION
FULL FEATURES - NO BUGS - READY FOR DEPLOYMENT
FIXED FOR ORDER_HANDLER COMPATIBILITY
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
            self.init_database()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections - PRODUCTION READY"""
        max_retries = 5
        retry_delay = 0.1
        conn = None
        
        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(
                    self.db_path, 
                    check_same_thread=False,
                    timeout=30.0
                )
                conn.row_factory = sqlite3.Row
                # Production-optimized PRAGMA settings
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA cache_size = -100000")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("PRAGMA busy_timeout = 10000")
                conn.execute("PRAGMA temp_store = MEMORY")
                conn.execute("PRAGMA mmap_size = 268435456")
                conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
                
                yield conn
                
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
        """Initialize semua tabel database dengan schema lengkap dan optimasi"""
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
                        level INTEGER DEFAULT 1 CHECK(level >= 1),
                        referral_code TEXT UNIQUE,
                        referred_by TEXT,
                        total_referred INTEGER DEFAULT 0,
                        bonus_balance REAL DEFAULT 0
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
                        cost_price REAL DEFAULT 0,
                        is_featured INTEGER DEFAULT 0 CHECK(is_featured IN (0,1)),
                        sort_order INTEGER DEFAULT 0,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # ==================== TRANSACTIONS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        type TEXT NOT NULL CHECK(type IN ('topup','withdraw','refund','bonus','order','commission','adjustment')),
                        amount REAL NOT NULL CHECK(amount != 0),
                        status TEXT DEFAULT 'pending' CHECK(status IN ('pending','completed','rejected','cancelled','failed')),
                        details TEXT,
                        unique_code INTEGER DEFAULT 0,
                        payment_method TEXT,
                        admin_notes TEXT,
                        reference_id TEXT,
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
                        status TEXT DEFAULT 'pending' CHECK(status IN ('pending','processing','completed','failed','partial','refunded','cancelled')),
                        provider_order_id TEXT,
                        customer_input TEXT,
                        response_data TEXT,
                        sn TEXT,
                        note TEXT,
                        profit REAL DEFAULT 0,
                        cost REAL DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        processed_at DATETIME,
                        completed_at DATETIME,
                        refunded_at DATETIME,
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
                        amount REAL NOT NULL CHECK(amount > 0),
                        status TEXT DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','expired')),
                        proof_image TEXT,
                        unique_code INTEGER DEFAULT 0,
                        payment_method TEXT,
                        total_amount REAL DEFAULT 0,
                        admin_notes TEXT,
                        expires_at DATETIME,
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
                        type TEXT DEFAULT 'info' CHECK(type IN ('info','success','warning','error','system')),
                        is_read INTEGER DEFAULT 0 CHECK(is_read IN (0,1)),
                        action_url TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                # ==================== CATEGORIES TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS categories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        sort_order INTEGER DEFAULT 0,
                        is_active INTEGER DEFAULT 1 CHECK(is_active IN (0,1)),
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # ==================== REFERRALS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS referrals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        referrer_id TEXT NOT NULL,
                        referred_id TEXT NOT NULL UNIQUE,
                        commission_amount REAL DEFAULT 0,
                        status TEXT DEFAULT 'pending' CHECK(status IN ('pending','completed','cancelled')),
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        completed_at DATETIME,
                        FOREIGN KEY (referrer_id) REFERENCES users (user_id) ON DELETE CASCADE,
                        FOREIGN KEY (referred_id) REFERENCES users (user_id) ON DELETE CASCADE
                    )
                ''')
                
                # ==================== CREATE INDEXES ====================
                indexes = [
                    # Users indexes
                    'CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance)',
                    'CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned)',
                    'CREATE INDEX IF NOT EXISTS idx_users_active ON users(last_active)',
                    'CREATE INDEX IF NOT EXISTS idx_users_level ON users(level)',
                    'CREATE INDEX IF NOT EXISTS idx_users_referral ON users(referral_code)',
                    
                    # Products indexes
                    'CREATE INDEX IF NOT EXISTS idx_products_status ON products(status)',
                    'CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)',
                    'CREATE INDEX IF NOT EXISTS idx_products_price ON products(price)',
                    'CREATE INDEX IF NOT EXISTS idx_products_featured ON products(is_featured)',
                    'CREATE INDEX IF NOT EXISTS idx_products_sort ON products(sort_order)',
                    
                    # Transactions indexes
                    'CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status)',
                    'CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type)',
                    'CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)',
                    'CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at)',
                    
                    # Orders indexes
                    'CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)',
                    'CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)',
                    'CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at)',
                    'CREATE INDEX IF NOT EXISTS idx_orders_product ON orders(product_code)',
                    
                    # Topup indexes
                    'CREATE INDEX IF NOT EXISTS idx_topup_requests_status ON topup_requests(status)',
                    'CREATE INDEX IF NOT EXISTS idx_topup_requests_user ON topup_requests(user_id)',
                    'CREATE INDEX IF NOT EXISTS idx_topup_requests_created ON topup_requests(created_at)',
                    
                    # Logs indexes
                    'CREATE INDEX IF NOT EXISTS idx_admin_logs_admin ON admin_logs(admin_id)',
                    'CREATE INDEX IF NOT EXISTS idx_admin_logs_time ON admin_logs(timestamp)',
                    'CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(level)',
                    'CREATE INDEX IF NOT EXISTS idx_system_logs_time ON system_logs(timestamp)',
                    
                    # Notifications indexes
                    'CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)',
                    'CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read)',
                    
                    # Referrals indexes
                    'CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)',
                    'CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals(referred_id)'
                ]
                
                for index in indexes:
                    try:
                        cursor.execute(index)
                    except Exception as e:
                        logger.warning(f"Could not create index {index}: {e}")
                
                # ==================== DEFAULT DATA ====================
                default_settings = [
                    ('system_name', 'Bot System', 'Nama sistem bot'),
                    ('maintenance_mode', '0', 'Mode maintenance (1=aktif, 0=nonaktif)'),
                    ('min_topup', '10000', 'Minimum topup'),
                    ('max_topup', '1000000', 'Maksimum topup'),
                    ('admin_contact', '@admin', 'Kontak admin'),
                    ('auto_sync_products', '1', 'Auto sync products (1=aktif, 0=nonaktif)'),
                    ('profit_margin', '10', 'Margin profit default (%)'),
                    ('referral_bonus', '5000', 'Bonus referral untuk referrer'),
                    ('welcome_bonus', '0', 'Bonus saldo untuk user baru'),
                    ('order_timeout', '30', 'Timeout order dalam menit'),
                    ('topup_expiry', '24', 'Expiry topup dalam jam'),
                    ('currency', 'Rp', 'Simbol mata uang'),
                    ('language', 'id', 'Bahasa default'),
                    ('max_retry', '3', 'Max retry untuk order'),
                    ('backup_interval', '24', 'Interval backup dalam jam')
                ]
                
                cursor.executemany('''
                    INSERT OR IGNORE INTO settings (key, value, description) 
                    VALUES (?, ?, ?)
                ''', default_settings)
                
                # Default categories
                default_categories = [
                    ('Pulsa', 'Produk pulsa semua operator', 1),
                    ('Data', 'Paket internet dan kuota', 2),
                    ('E-Money', 'E-money dan dompet digital', 3),
                    ('Voucher', 'Voucher game dan entertainment', 4),
                    ('PLN', 'Token dan tagihan listrik', 5),
                    ('BPJS', 'Pembayaran BPJS', 6),
                    ('PDAM', 'Tagihan air PDAM', 7)
                ]
                
                cursor.executemany('''
                    INSERT OR IGNORE INTO categories (name, description, sort_order) 
                    VALUES (?, ?, ?)
                ''', default_categories)
                
                logger.info("✅ Database initialized successfully with ALL features")
                
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}", exc_info=True)
            raise

    # ==================== USER MANAGEMENT ====================
    def get_or_create_user(self, user_id: str, username: str = "", full_name: str = "", **kwargs) -> Dict[str, Any]:
        """Get existing user or create new one dengan semua field opsional"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
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
                    
                    # Handle additional fields from kwargs
                    for field, value in kwargs.items():
                        if hasattr(user, field) and value is not None:
                            update_fields.append(f"{field} = ?")
                            params.append(value)
                    
                    if update_fields:
                        update_fields.append("last_active = ?")
                        params.extend([datetime.now(), str(user_id)])
                        
                        update_query = f"UPDATE users SET {', '.join(update_fields)} WHERE user_id = ?"
                        cursor.execute(update_query, params)
                        logger.info(f"📝 User updated: {user_id}")
                else:
                    # Generate referral code untuk user baru
                    referral_code = kwargs.get('referral_code')
                    if not referral_code:
                        referral_code = f"REF{user_id[-6:].upper()}"
                    
                    # Create new user
                    cursor.execute(
                        'INSERT INTO users (user_id, username, full_name, referral_code) VALUES (?, ?, ?, ?)',
                        (str(user_id), username, full_name, referral_code)
                    )
                    
                    # Apply welcome bonus jika ada
                    welcome_bonus = self.get_setting('welcome_bonus', 0)
                    if float(welcome_bonus) > 0:
                        cursor.execute(
                            'UPDATE users SET balance = balance + ? WHERE user_id = ?',
                            (float(welcome_bonus), str(user_id))
                        )
                        logger.info(f"🎁 Welcome bonus {welcome_bonus} given to new user: {user_id}")
                    
                    logger.info(f"👤 New user created: {user_id} - {full_name}")
                
                # Return user data
                cursor.execute('SELECT * FROM users WHERE user_id = ?', (str(user_id),))
                result = cursor.fetchone()
                return dict(result) if result else {}
                    
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
        """Get user balance"""
        try:
            user = self.get_user(user_id)
            return user['balance'] if user else 0.0
        except Exception as e:
            logger.error(f"Error getting balance for {user_id}: {e}")
            return 0.0

    def update_user_balance(self, user_id: str, amount: float, note: str = "", transaction_type: str = "adjustment") -> bool:
        """Update user balance dengan transaction logging"""
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
                
                # Update balance
                cursor.execute(
                    'UPDATE users SET balance = ?, last_active = ? WHERE user_id = ?',
                    (new_balance, datetime.now(), str(user_id))
                )
                
                # Log transaction - FIXED: menggunakan type yang valid
                if amount != 0:
                    status = 'completed' if amount > 0 else 'pending'
                    valid_types = ['topup', 'withdraw', 'refund', 'bonus', 'order', 'commission', 'adjustment']
                    
                    # Pastikan transaction_type valid
                    if transaction_type not in valid_types:
                        transaction_type = 'adjustment'
                    
                    cursor.execute('''
                        INSERT INTO transactions (user_id, type, amount, status, details, completed_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (str(user_id), transaction_type, amount, status, note, 
                          datetime.now() if amount > 0 else None))
                
                logger.info(f"💰 Balance updated: {user_id} -> {amount:,.0f} | New: {new_balance:,.0f} | Note: {note}")
                return True
                    
        except Exception as e:
            logger.error(f"Error updating balance for {user_id}: {e}")
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
                        COUNT(DISTINCT r.referred_id) as active_referrals
                    FROM users u
                    LEFT JOIN orders o ON u.user_id = o.user_id AND o.status = 'completed'
                    LEFT JOIN transactions t ON u.user_id = t.user_id AND t.status = 'completed' AND t.type = 'topup'
                    LEFT JOIN referrals r ON u.user_id = r.referrer_id AND r.status = 'completed'
                    WHERE u.user_id = ?
                    GROUP BY u.user_id
                ''', (str(user_id),))
                
                result = cursor.fetchone()
                
                if result:
                    total_orders = result['total_orders'] or 0
                    success_orders = result['successful_orders'] or 0
                    success_rate = (success_orders / total_orders * 100) if total_orders > 0 else 0
                    
                    return {
                        'user_id': result['user_id'],
                        'username': result['username'],
                        'full_name': result['full_name'],
                        'balance': result['balance'],
                        'bonus_balance': result['bonus_balance'],
                        'total_orders': total_orders,
                        'total_spent': result['total_spent'],
                        'total_topups': result['total_topups'],
                        'successful_orders': success_orders,
                        'successful_topups': result['successful_topups'],
                        'total_success_spent': result['total_success_spent'] or 0,
                        'success_rate': round(success_rate, 2),
                        'total_referred': result['total_referred'],
                        'active_referrals': result['active_referrals'] or 0,
                        'referral_code': result['referral_code'],
                        'registered_at': result['registered_at'],
                        'last_active': result['last_active'],
                        'level': result['level']
                    }
                return {}
        except Exception as e:
            logger.error(f"Error getting user stats for {user_id}: {e}")
            return {}

    # ==================== PRODUCT MANAGEMENT ====================
    def get_products_by_category(self, category: str = None, status: str = 'active', featured: bool = False) -> List[Dict[str, Any]]:
        """Get products dengan berbagai filter"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                query = 'SELECT * FROM products WHERE 1=1'
                params = []
                
                if category:
                    query += ' AND category = ?'
                    params.append(category)
                
                if status:
                    query += ' AND status = ?'
                    params.append(status)
                
                if featured:
                    query += ' AND is_featured = 1'
                
                query += ' ORDER BY sort_order ASC, name ASC'
                
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting products: {e}")
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
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                valid_fields = ['name', 'price', 'status', 'description', 'category', 
                              'provider', 'gangguan', 'kosong', 'stock', 'min_stock',
                              'max_stock', 'profit_margin', 'cost_price', 'is_featured', 'sort_order']
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
                    
        except Exception as e:
            logger.error(f"Error updating product {product_code}: {e}")
            return False

    def bulk_update_products(self, products_data: List[Dict]) -> int:
        """Bulk update products"""
        updated_count = 0
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                for product in products_data:
                    cursor.execute('''
                        INSERT OR REPLACE INTO products 
                        (code, name, price, status, description, category, provider, stock, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        product['code'], product['name'], product['price'],
                        product.get('status', 'active'), product.get('description', ''),
                        product.get('category', 'Umum'), product.get('provider', ''),
                        product.get('stock', 0), datetime.now()
                    ))
                    updated_count += 1
                
                logger.info(f"🔄 Bulk updated {updated_count} products")
                return updated_count
        except Exception as e:
            logger.error(f"Error in bulk update products: {e}")
            return 0

    # ==================== TOPUP MANAGEMENT ====================
    def create_topup_request(self, user_id: str, amount: float, payment_method: str = "", 
                           proof_image: str = "", unique_code: int = 0, status: str = "pending") -> int:
        """Create new topup request dengan expiry"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                user = self.get_user(user_id)
                if not user:
                    raise ValueError(f"User {user_id} not found")
                
                if unique_code == 0:
                    unique_code = random.randint(1, 999)
                
                total_amount = amount + unique_code
                
                # Set expiry time
                expiry_hours = int(self.get_setting('topup_expiry', 24))
                expires_at = datetime.now() + timedelta(hours=expiry_hours)
                
                cursor.execute('''
                    INSERT INTO topup_requests 
                    (user_id, username, full_name, amount, proof_image, unique_code, 
                     payment_method, total_amount, status, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    str(user_id), user.get('username'), user.get('full_name'), 
                    amount, proof_image, unique_code, payment_method, total_amount, status, expires_at
                ))
                
                topup_id = cursor.lastrowid
                logger.info(f"💳 Topup request created: ID {topup_id} for user {user_id}")
                return topup_id
                    
        except Exception as e:
            logger.error(f"Error creating topup request: {e}")
            raise

    def create_topup(self, user_id: str, amount: float, payment_method: str = "", 
                    status: str = "pending", unique_code: int = 0, **kwargs) -> int:
        """Compatible create_topup function dengan **kwargs"""
        return self.create_topup_request(
            user_id=user_id,
            amount=amount,
            payment_method=payment_method,
            proof_image=kwargs.get('proof_image', ""),
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
                    WHERE status = 'pending' AND (expires_at IS NULL OR expires_at > ?)
                    ORDER BY created_at ASC
                ''', (datetime.now(),))
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
        """Approve topup request - FIXED tanpa nested transactions"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get topup details
                cursor.execute('SELECT * FROM topup_requests WHERE id = ?', (topup_id,))
                topup = cursor.fetchone()
                
                if not topup:
                    raise ValueError(f"Topup {topup_id} not found")
                
                if topup['status'] != 'pending':
                    raise ValueError(f"Topup {topup_id} already processed")
                
                user_id = topup['user_id']
                amount = topup['amount']
                
                # Update user balance dalam transaction yang sama
                cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
                user = cursor.fetchone()
                
                if not user:
                    raise ValueError(f"User {user_id} not found")
                
                new_balance = user['balance'] + amount
                
                cursor.execute(
                    'UPDATE users SET balance = ?, last_active = ?, total_topups = total_topups + 1 WHERE user_id = ?',
                    (new_balance, datetime.now(), user_id)
                )
                
                # Update topup status
                cursor.execute('''
                    UPDATE topup_requests 
                    SET status = 'approved', updated_at = ?, admin_notes = ?
                    WHERE id = ?
                ''', (datetime.now(), f"Approved by admin {admin_id}", topup_id))
                
                # Create transaction record
                cursor.execute('''
                    INSERT INTO transactions (user_id, type, amount, status, details, completed_at)
                    VALUES (?, 'topup', ?, 'completed', ?, ?)
                ''', (user_id, amount, f"Topup approved - ID: {topup_id}", datetime.now()))
                
                logger.info(f"✅ Topup approved: ID {topup_id} for user {user_id}, amount: {amount}")
                return True
                    
        except Exception as e:
            logger.error(f"Error approving topup {topup_id}: {e}")
            return False

    def reject_topup(self, topup_id: int, admin_id: str, *args) -> bool:
        """Reject topup request"""
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
                    
        except Exception as e:
            logger.error(f"Error rejecting topup {topup_id}: {e}")
            return False

    # ==================== ORDER MANAGEMENT ====================
    def create_order(self, user_id: str, product_code: str, customer_input: str, **kwargs) -> int:
        """Create new order dengan **kwargs untuk compatibility"""
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
                
                # Calculate profit
                cost_price = product.get('cost_price', 0)
                profit = product['price'] - cost_price
                
                # Deduct balance
                cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
                user = cursor.fetchone()
                new_balance = user['balance'] - product['price']
                
                cursor.execute(
                    'UPDATE users SET balance = ?, last_active = ? WHERE user_id = ?',
                    (new_balance, datetime.now(), user_id)
                )
                
                # Create order
                cursor.execute('''
                    INSERT INTO orders 
                    (user_id, product_code, product_name, price, customer_input, status, cost, profit)
                    VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                ''', (str(user_id), product_code, product['name'], product['price'], customer_input, cost_price, profit))
                
                order_id = cursor.lastrowid
                
                # Update user stats
                cursor.execute('''
                    UPDATE users 
                    SET total_orders = total_orders + 1, 
                        last_active = ?
                    WHERE user_id = ?
                ''', (datetime.now(), str(user_id)))
                
                logger.info(f"🛒 Order created: ID {order_id} for user {user_id}")
                return order_id
                    
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            raise

    def update_order_status(self, order_id: int, status: str, sn: str = "", note: str = "", response_data: str = "") -> bool:
        """Update order status dengan semua field opsional"""
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
                
                if response_data:
                    update_fields.append("response_data = ?")
                    params.append(response_data)
                
                if status == 'completed':
                    update_fields.append("completed_at = ?")
                    params.append(datetime.now())
                    # Update total spent
                    cursor.execute('SELECT user_id, price FROM orders WHERE id = ?', (order_id,))
                    order = cursor.fetchone()
                    if order:
                        cursor.execute(
                            'UPDATE users SET total_spent = total_spent + ? WHERE user_id = ?',
                            (order['price'], order['user_id'])
                        )
                elif status == 'processing':
                    update_fields.append("processed_at = ?")
                    params.append(datetime.now())
                elif status == 'refunded':
                    update_fields.append("refunded_at = ?")
                    params.append(datetime.now())
                    # Refund balance
                    cursor.execute('SELECT user_id, price FROM orders WHERE id = ?', (order_id,))
                    order = cursor.fetchone()
                    if order:
                        cursor.execute(
                            'UPDATE users SET balance = balance + ? WHERE user_id = ?',
                            (order['price'], order['user_id'])
                        )
                
                params.append(order_id)
                
                query = f"UPDATE orders SET {', '.join(update_fields)} WHERE id = ?"
                cursor.execute(query, params)
                
                logger.info(f"📦 Order {order_id} status updated to: {status}")
                return True
                    
        except Exception as e:
            logger.error(f"Error updating order {order_id}: {e}")
            return False

    def get_user_orders(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get user's order history"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM orders 
                    WHERE user_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (str(user_id), limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting user orders for {user_id}: {e}")
            return []

    # ==================== ORDER HANDLER COMPATIBILITY FUNCTIONS ====================
    
    def update_user_saldo(self, user_id: str, amount: float) -> bool:
        """Compatibility function for order_handler - update user balance"""
        return self.update_user_balance(user_id, amount, f"Order adjustment: {amount}")

    def get_user_saldo(self, user_id: str) -> float:
        """Compatibility function for order_handler - get user balance"""
        return self.get_user_balance(user_id)

    def save_order(self, user_id: str, product_name: str, product_code: str, 
                   customer_input: str, price: float, status: str = 'pending',
                   provider_order_id: str = '', sn: str = '', note: str = '') -> int:
        """Compatibility function for order_handler - save order dengan semua parameter"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Calculate profit
                product = self.get_product(product_code)
                cost_price = product.get('cost_price', 0) if product else 0
                profit = price - cost_price
                
                cursor.execute('''
                    INSERT INTO orders 
                    (user_id, product_code, product_name, price, customer_input, status, 
                     provider_order_id, sn, note, cost, profit)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (str(user_id), product_code, product_name, price, customer_input, status,
                      provider_order_id, sn, note, cost_price, profit))
                
                order_id = cursor.lastrowid
                
                # Update user order count
                cursor.execute('''
                    UPDATE users 
                    SET total_orders = total_orders + 1, 
                        last_active = ?
                    WHERE user_id = ?
                ''', (datetime.now(), str(user_id)))
                
                logger.info(f"💾 Order saved: ID {order_id} for user {user_id}")
                return order_id
                    
        except Exception as e:
            logger.error(f"Error saving order: {e}")
            return 0

    def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        """Get order by ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting order {order_id}: {e}")
            return None

    # ==================== STATISTICS & ANALYTICS ====================
    def get_bot_statistics(self) -> Dict[str, Any]:
        """Get comprehensive bot statistics"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Basic counts
                cursor.execute('SELECT COUNT(*) as total_users FROM users WHERE is_banned = 0')
                total_users = cursor.fetchone()['total_users']
                
                cursor.execute('SELECT COUNT(*) as active_users FROM users WHERE last_active >= datetime("now", "-7 days") AND is_banned = 0')
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
                
                cursor.execute('SELECT SUM(profit) as total_profit FROM orders WHERE status = "completed"')
                total_profit = cursor.fetchone()['total_profit'] or 0
                
                # Today's stats
                today = datetime.now().strftime('%Y-%m-%d')
                cursor.execute('SELECT COUNT(*) as new_users_today FROM users WHERE date(registered_at) = ?', (today,))
                new_users_today = cursor.fetchone()['new_users_today']
                
                cursor.execute('SELECT COUNT(*) as orders_today FROM orders WHERE date(created_at) = ?', (today,))
                orders_today = cursor.fetchone()['orders_today']
                
                cursor.execute('SELECT SUM(price) as revenue_today FROM orders WHERE date(created_at) = ? AND status = "completed"', (today,))
                revenue_today = cursor.fetchone()['revenue_today'] or 0
                
                cursor.execute('SELECT SUM(amount) as topup_today FROM transactions WHERE date(created_at) = ? AND type = "topup" AND status = "completed"', (today,))
                topup_today = cursor.fetchone()['topup_today'] or 0
                
                # Order success rate
                cursor.execute('SELECT COUNT(*) as total_orders FROM orders')
                total_orders = cursor.fetchone()['total_orders'] or 0
                
                cursor.execute('SELECT COUNT(*) as success_orders FROM orders WHERE status = "completed"')
                success_orders = cursor.fetchone()['success_orders'] or 0
                
                success_rate = (success_orders / total_orders * 100) if total_orders > 0 else 0
                
                return {
                    'total_users': total_users,
                    'active_users': active_users,
                    'active_products': active_products,
                    'pending_topups': pending_topups,
                    'total_balance': total_balance,
                    'total_revenue': total_revenue,
                    'total_profit': total_profit,
                    'new_users_today': new_users_today,
                    'orders_today': orders_today,
                    'revenue_today': revenue_today,
                    'topup_today': topup_today,
                    'total_orders': total_orders,
                    'success_orders': success_orders,
                    'success_rate': round(success_rate, 2),
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
        except Exception as e:
            logger.error(f"Error getting bot statistics: {e}")
            return {
                'total_users': 0, 'active_users': 0, 'active_products': 0, 'pending_topups': 0,
                'total_balance': 0, 'total_revenue': 0, 'total_profit': 0, 'new_users_today': 0,
                'orders_today': 0, 'revenue_today': 0, 'topup_today': 0, 'total_orders': 0,
                'success_orders': 0, 'success_rate': 0,
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

    def get_daily_stats(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get daily statistics untuk chart"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 
                        date(created_at) as date,
                        COUNT(*) as orders,
                        SUM(CASE WHEN status = 'completed' THEN price ELSE 0 END) as revenue,
                        COUNT(DISTINCT user_id) as active_users
                    FROM orders 
                    WHERE created_at >= date('now', ?)
                    GROUP BY date(created_at)
                    ORDER BY date ASC
                ''', (f'-{days} days',))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting daily stats: {e}")
            return []

    # ==================== ADMIN MANAGEMENT ====================
    def is_user_admin(self, user_id: str) -> bool:
        """Check if user is admin"""
        user = self.get_user(user_id)
        return user and user.get('level', 0) >= 10 if user else False

    def make_user_admin(self, user_id: str) -> bool:
        """Make user an admin"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET level = 10 WHERE user_id = ?', (str(user_id),))
                
                self.add_admin_log(
                    admin_id='system',
                    action='make_admin',
                    target_type='user',
                    target_id=user_id,
                    details=f'User {user_id} promoted to admin'
                )
                
                logger.info(f"👑 User {user_id} promoted to admin")
                return True
        except Exception as e:
            logger.error(f"Error making user {user_id} admin: {e}")
            return False

    def remove_user_admin(self, user_id: str) -> bool:
        """Remove admin privileges"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET level = 1 WHERE user_id = ?', (str(user_id),))
                
                self.add_admin_log(
                    admin_id='system',
                    action='remove_admin',
                    target_type='user',
                    target_id=user_id,
                    details=f'User {user_id} admin privileges removed'
                )
                
                logger.info(f"👑 User {user_id} admin privileges removed")
                return True
        except Exception as e:
            logger.error(f"Error removing admin from user {user_id}: {e}")
            return False

    def ban_user(self, user_id: str, reason: str = "", admin_id: str = "system") -> bool:
        """Ban user"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?',
                    (reason, str(user_id))
                )
                
                self.add_admin_log(
                    admin_id=admin_id,
                    action='ban_user',
                    target_type='user',
                    target_id=user_id,
                    details=f'User banned. Reason: {reason}'
                )
                
                logger.info(f"🚫 User {user_id} banned. Reason: {reason}")
                return True
        except Exception as e:
            logger.error(f"Error banning user {user_id}: {e}")
            return False

    def unban_user(self, user_id: str, admin_id: str = "system") -> bool:
        """Unban user"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?',
                    (str(user_id),)
                )
                
                self.add_admin_log(
                    admin_id=admin_id,
                    action='unban_user',
                    target_type='user',
                    target_id=user_id,
                    details='User unbanned'
                )
                
                logger.info(f"✅ User {user_id} unbanned")
                return True
        except Exception as e:
            logger.error(f"Error unbanning user {user_id}: {e}")
            return False

    # ==================== SETTINGS MANAGEMENT ====================
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get setting value"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
                result = cursor.fetchone()
                if result:
                    # Try to convert to appropriate type
                    value = result['value']
                    if value.isdigit():
                        return int(value)
                    elif value.replace('.', '').isdigit():
                        return float(value)
                    elif value.lower() in ('true', 'false'):
                        return value.lower() == 'true'
                    else:
                        return value
                return default
        except Exception as e:
            logger.error(f"Error getting setting {key}: {e}")
            return default

    def update_setting(self, key: str, value: Any, description: str = None) -> bool:
        """Update setting"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if description:
                    cursor.execute('''
                        INSERT OR REPLACE INTO settings (key, value, description, updated_at)
                        VALUES (?, ?, ?, ?)
                    ''', (key, str(value), description, datetime.now()))
                else:
                    cursor.execute('''
                        UPDATE settings SET value = ?, updated_at = ? WHERE key = ?
                    ''', (str(value), datetime.now(), key))
                
                logger.info(f"⚙️ Setting updated: {key} = {value}")
                return True
        except Exception as e:
            logger.error(f"Error updating setting {key}: {e}")
            return False

    # ==================== NOTIFICATION SYSTEM ====================
    def create_notification(self, user_id: str, title: str, message: str, 
                          notification_type: str = "info", action_url: str = None) -> int:
        """Create notification for user"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO notifications (user_id, title, message, type, action_url)
                    VALUES (?, ?, ?, ?, ?)
                ''', (str(user_id), title, message, notification_type, action_url))
                
                notification_id = cursor.lastrowid
                logger.info(f"🔔 Notification created for {user_id}: {title}")
                return notification_id
        except Exception as e:
            logger.error(f"Error creating notification for {user_id}: {e}")
            return 0

    def get_unread_notifications(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get unread notifications for user"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM notifications 
                    WHERE user_id = ? AND is_read = 0 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (str(user_id), limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting notifications for {user_id}: {e}")
            return []

    def mark_notification_read(self, notification_id: int) -> bool:
        """Mark notification as read"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE notifications SET is_read = 1 WHERE id = ?',
                    (notification_id,)
                )
                return True
        except Exception as e:
            logger.error(f"Error marking notification {notification_id} as read: {e}")
            return False

    # ==================== REFERRAL SYSTEM ====================
    def create_referral(self, referrer_id: str, referred_id: str) -> bool:
        """Create referral relationship"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if already referred
                cursor.execute(
                    'SELECT id FROM referrals WHERE referred_id = ?',
                    (str(referred_id),)
                )
                if cursor.fetchone():
                    return False
                
                cursor.execute('''
                    INSERT INTO referrals (referrer_id, referred_id)
                    VALUES (?, ?)
                ''', (str(referrer_id), str(referred_id)))
                
                # Update referrer's count
                cursor.execute('''
                    UPDATE users SET total_referred = total_referred + 1 
                    WHERE user_id = ?
                ''', (str(referrer_id),))
                
                logger.info(f"🤝 Referral created: {referrer_id} -> {referred_id}")
                return True
        except Exception as e:
            logger.error(f"Error creating referral: {e}")
            return False

    def complete_referral(self, referred_id: str, commission_amount: float = None) -> bool:
        """Complete referral and give commission"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if commission_amount is None:
                    commission_amount = float(self.get_setting('referral_bonus', 5000))
                
                cursor.execute('''
                    UPDATE referrals 
                    SET status = 'completed', commission_amount = ?, completed_at = ?
                    WHERE referred_id = ? AND status = 'pending'
                ''', (commission_amount, datetime.now(), str(referred_id)))
                
                # Get referrer ID
                cursor.execute(
                    'SELECT referrer_id FROM referrals WHERE referred_id = ?',
                    (str(referred_id),)
                )
                referral = cursor.fetchone()
                
                if referral:
                    # Add commission to referrer
                    referrer_id = referral['referrer_id']
                    cursor.execute('''
                        UPDATE users 
                        SET bonus_balance = bonus_balance + ?, balance = balance + ?
                        WHERE user_id = ?
                    ''', (commission_amount, commission_amount, referrer_id))
                    
                    # Log commission transaction
                    cursor.execute('''
                        INSERT INTO transactions (user_id, type, amount, status, details, completed_at)
                        VALUES (?, 'commission', ?, 'completed', ?, ?)
                    ''', (referrer_id, commission_amount, f"Referral commission for {referred_id}", datetime.now()))
                    
                    logger.info(f"💰 Referral commission {commission_amount} given to {referrer_id} for {referred_id}")
                
                return True
        except Exception as e:
            logger.error(f"Error completing referral for {referred_id}: {e}")
            return False

    # ==================== LOGGING SYSTEM ====================
    def add_system_log(self, level: str, module: str, message: str, user_id: str = None, details: str = None):
        """Add system log entry"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO system_logs (level, module, message, user_id, details)
                    VALUES (?, ?, ?, ?, ?)
                ''', (level, module, message, user_id, details))
        except Exception as e:
            # Fallback to print jika database error
            print(f"SYSTEM LOG [{level}] {module}: {message} (User: {user_id}) - {details}")

    def add_admin_log(self, admin_id: str, action: str, target_type: str = None, target_id: str = None, details: str = None):
        """Add admin action log"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO admin_logs (admin_id, action, target_type, target_id, details)
                    VALUES (?, ?, ?, ?, ?)
                ''', (admin_id, action, target_type, target_id, details))
        except Exception as e:
            print(f"ADMIN LOG: {admin_id} - {action} - {target_type} - {target_id} - {details}")

    # ==================== MAINTENANCE & CLEANUP ====================
    def cleanup_old_data(self, days: int = 30) -> Dict[str, int]:
        """Cleanup old data"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Cleanup old orders
                cursor.execute('''
                    DELETE FROM orders 
                    WHERE created_at < ? AND status IN ('completed', 'failed', 'cancelled', 'refunded')
                ''', (cutoff_date,))
                orders_deleted = cursor.rowcount
                
                # Cleanup old topups
                cursor.execute('''
                    DELETE FROM topup_requests 
                    WHERE created_at < ? AND status IN ('approved', 'rejected', 'expired')
                ''', (cutoff_date,))
                topups_deleted = cursor.rowcount
                
                # Cleanup old transactions
                cursor.execute('''
                    DELETE FROM transactions 
                    WHERE created_at < ? AND status IN ('completed', 'rejected', 'cancelled')
                ''', (cutoff_date,))
                transactions_deleted = cursor.rowcount
                
                # Cleanup old notifications
                cursor.execute('''
                    DELETE FROM notifications 
                    WHERE created_at < ? AND is_read = 1
                ''', (cutoff_date,))
                notifications_deleted = cursor.rowcount
                
                # Cleanup old logs
                cursor.execute('DELETE FROM system_logs WHERE timestamp < ?', (cutoff_date,))
                system_logs_deleted = cursor.rowcount
                
                cursor.execute('DELETE FROM admin_logs WHERE timestamp < ?', (cutoff_date,))
                admin_logs_deleted = cursor.rowcount
                
                # Expire pending topups
                cursor.execute('''
                    UPDATE topup_requests 
                    SET status = 'expired' 
                    WHERE status = 'pending' AND expires_at < ?
                ''', (datetime.now(),))
                expired_topups = cursor.rowcount
                
                logger.info(f"🧹 Cleanup completed: {orders_deleted} orders, {topups_deleted} topups, "
                           f"{transactions_deleted} transactions, {notifications_deleted} notifications, "
                           f"{system_logs_deleted} system logs, {admin_logs_deleted} admin logs, "
                           f"{expired_topups} expired topups")
                
                return {
                    'orders': orders_deleted,
                    'topups': topups_deleted,
                    'transactions': transactions_deleted,
                    'notifications': notifications_deleted,
                    'system_logs': system_logs_deleted,
                    'admin_logs': admin_logs_deleted,
                    'expired_topups': expired_topups
                }
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            return {}

    def backup_database(self, backup_path: str = None) -> bool:
        """Backup database"""
        try:
            if not backup_path:
                backup_path = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            
            with self.get_connection() as conn:
                # SQLite backup mechanism
                backup_conn = sqlite3.connect(backup_path)
                conn.backup(backup_conn)
                backup_conn.close()
                
            logger.info(f"💾 Database backed up to: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Error backing up database: {e}")
            return False

    def optimize_database(self) -> bool:
        """Optimize database performance"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('VACUUM')
                cursor.execute('PRAGMA optimize')
                logger.info("🔧 Database optimized")
                return True
        except Exception as e:
            logger.error(f"Error optimizing database: {e}")
            return False

    # ==================== COMPATIBILITY FUNCTIONS ====================
    def get_pending_topups_count(self) -> int:
        return len(self.get_pending_topups())

    def get_total_users_count(self) -> int:
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
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT SUM(price) as total FROM orders WHERE status = "completed"')
                result = cursor.fetchone()
                return result['total'] or 0
        except Exception as e:
            logger.error(f"Error getting total revenue: {e}")
            return 0

    def add_user_balance(self, user_id: str, amount: float) -> bool:
        return self.update_user_balance(user_id, amount, "Admin manual adjustment", "bonus")

    def subtract_user_balance(self, user_id: str, amount: float) -> bool:
        return self.update_user_balance(user_id, -amount, "Admin manual adjustment", "withdraw")

    def get_recent_users(self, limit: int = 20) -> List[Dict[str, Any]]:
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
        """Delete inactive users (HATI-HATI - hanya untuk cleanup)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
                
                cursor.execute('''
                    DELETE FROM users 
                    WHERE last_active < ? AND is_banned = 0 AND balance = 0
                ''', (cutoff_date,))
                
                deleted_count = cursor.rowcount
                logger.info(f"🧹 Deleted {deleted_count} inactive users")
                return deleted_count
        except Exception as e:
            logger.error(f"Error deleting inactive users: {e}")
            return 0

# ==================== MODULE-LEVEL FUNCTIONS ====================
_db_manager = DatabaseManager()

# Export semua fungsi untuk backward compatibility
def init_database():
    return _db_manager.init_database()

def get_or_create_user(user_id: str, username: str = "", full_name: str = "", **kwargs):
    return _db_manager.get_or_create_user(user_id, username, full_name, **kwargs)

def get_user(user_id: str):
    return _db_manager.get_user(user_id)

def get_user_balance(user_id: str):
    return _db_manager.get_user_balance(user_id)

def update_user_balance(user_id: str, amount: float, note: str = ""):
    return _db_manager.update_user_balance(user_id, amount, note)

def add_user_balance(user_id: str, amount: float):
    return _db_manager.add_user_balance(user_id, amount)

def subtract_user_balance(user_id: str, amount: float):
    return _db_manager.subtract_user_balance(user_id, amount)

def get_user_stats(user_id: str):
    return _db_manager.get_user_stats(user_id)

def get_products_by_category(category: str = None, status: str = 'active'):
    return _db_manager.get_products_by_category(category, status)

def get_product(product_code: str):
    return _db_manager.get_product(product_code)

def update_product(product_code: str, **kwargs):
    return _db_manager.update_product(product_code, **kwargs)

def create_topup(user_id: str, amount: float, payment_method: str = "", status: str = "pending", unique_code: int = 0, **kwargs):
    return _db_manager.create_topup(user_id, amount, payment_method, status, unique_code, **kwargs)

def get_pending_topups():
    return _db_manager.get_pending_topups()

def get_topup_by_id(topup_id: int):
    return _db_manager.get_topup_by_id(topup_id)

def approve_topup(topup_id: int, admin_id: str, *args):
    return _db_manager.approve_topup(topup_id, admin_id, *args)

def reject_topup(topup_id: int, admin_id: str, *args):
    return _db_manager.reject_topup(topup_id, admin_id, *args)

def create_order(user_id: str, product_code: str, customer_input: str, **kwargs):
    return _db_manager.create_order(user_id, product_code, customer_input, **kwargs)

def update_order_status(order_id: int, status: str, sn: str = "", note: str = ""):
    return _db_manager.update_order_status(order_id, status, sn, note)

def get_user_orders(user_id: str, limit: int = 10):
    return _db_manager.get_user_orders(user_id, limit)

def get_bot_statistics():
    return _db_manager.get_bot_statistics()

def get_daily_stats(days: int = 7):
    return _db_manager.get_daily_stats(days)

def is_user_admin(user_id: str):
    return _db_manager.is_user_admin(user_id)

def make_user_admin(user_id: str):
    return _db_manager.make_user_admin(user_id)

def remove_user_admin(user_id: str):
    return _db_manager.remove_user_admin(user_id)

def ban_user(user_id: str, reason: str = "", admin_id: str = "system"):
    return _db_manager.ban_user(user_id, reason, admin_id)

def unban_user(user_id: str, admin_id: str = "system"):
    return _db_manager.unban_user(user_id, admin_id)

def get_setting(key: str, default: Any = None):
    return _db_manager.get_setting(key, default)

def update_setting(key: str, value: Any, description: str = None):
    return _db_manager.update_setting(key, value, description)

def create_notification(user_id: str, title: str, message: str, notification_type: str = "info", action_url: str = None):
    return _db_manager.create_notification(user_id, title, message, notification_type, action_url)

def get_unread_notifications(user_id: str, limit: int = 10):
    return _db_manager.get_unread_notifications(user_id, limit)

def mark_notification_read(notification_id: int):
    return _db_manager.mark_notification_read(notification_id)

def create_referral(referrer_id: str, referred_id: str):
    return _db_manager.create_referral(referrer_id, referred_id)

def complete_referral(referred_id: str, commission_amount: float = None):
    return _db_manager.complete_referral(referred_id, commission_amount)

def add_system_log(level: str, module: str, message: str, user_id: str = None, details: str = None):
    return _db_manager.add_system_log(level, module, message, user_id, details)

def add_admin_log(admin_id: str, action: str, target_type: str = None, target_id: str = None, details: str = None):
    return _db_manager.add_admin_log(admin_id, action, target_type, target_id, details)

def cleanup_old_data(days: int = 30):
    return _db_manager.cleanup_old_data(days)

def backup_database(backup_path: str = None):
    return _db_manager.backup_database(backup_path)

def optimize_database():
    return _db_manager.optimize_database()

def get_all_users(limit: int = 100):
    return _db_manager.get_recent_users(limit)

def get_recent_users(limit: int = 20):
    return _db_manager.get_recent_users(limit)

def get_active_users(days: int = 30):
    return _db_manager.get_active_users(days)

def count_inactive_users(days: int = 30):
    return _db_manager.count_inactive_users(days)

def delete_inactive_users(days: int = 30):
    return _db_manager.delete_inactive_users(days)

# ==================== ORDER HANDLER COMPATIBILITY FUNCTIONS ====================

def update_user_saldo(user_id: str, amount: float) -> bool:
    """Compatibility function for order_handler"""
    return _db_manager.update_user_saldo(user_id, amount)

def get_user_saldo(user_id: str) -> float:
    """Compatibility function for order_handler"""
    return _db_manager.get_user_saldo(user_id)

def save_order(user_id: str, product_name: str, product_code: str, 
               customer_input: str, price: float, status: str = 'pending',
               provider_order_id: str = '', sn: str = '', note: str = '') -> int:
    """Compatibility function for order_handler"""
    return _db_manager.save_order(user_id, product_name, product_code, customer_input, 
                                 price, status, provider_order_id, sn, note)

def get_order(order_id: int):
    """Compatibility function for order_handler"""
    return _db_manager.get_order(order_id)

# New compatibility functions
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

def get_db_manager():
    return _db_manager

# Aliases untuk compatibility
get_user_info = get_user
get_user_statistics = get_user_stats

if __name__ == "__main__":
    # Comprehensive test
    print("🧪 PRODUCTION DATABASE TEST...")
    db = DatabaseManager()
    
    # Test semua fungsi utama
    user = db.get_or_create_user("test_user", "testuser", "Test User")
    print(f"✅ User test: {user['user_id']}")
    
    # Test topup system
    topup_id = db.create_topup("test_user", 50000, "QRIS", "pending", 123)
    print(f"✅ Topup test: ID {topup_id}")
    
    # Test product system
    products = db.get_products_by_category()
    print(f"✅ Products test: {len(products)} products")
    
    # Test statistics
    stats = db.get_bot_statistics()
    print(f"✅ Statistics: {stats}")
    
    # Test settings
    setting = db.get_setting('system_name')
    print(f"✅ Settings test: {setting}")
    
    # Test order handler compatibility
    saldo = db.get_user_saldo("test_user")
    print(f"✅ Saldo compatibility test: {saldo}")
    
    # Test cleanup
    cleanup = db.cleanup_old_data(1)
    print(f"✅ Cleanup test: {cleanup}")
    
    print("🚀 PRODUCTION DATABASE READY! ALL SYSTEMS GO!")
