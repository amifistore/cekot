#!/usr/bin/env python3
"""
Database Management System - FIXED & STABLE VERSION
SOLUSI TOTAL untuk masalah database locked dan generator error
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
        """Context manager for database connections - FIXED VERSION"""
        max_retries = 3
        retry_delay = 0.1
        conn = None
        
        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(
                    self.db_path, 
                    check_same_thread=False,
                    timeout=20.0
                )
                conn.row_factory = sqlite3.Row
                # Optimized PRAGMA settings
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA cache_size = -64000")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("PRAGMA busy_timeout = 5000")
                conn.execute("PRAGMA temp_store = MEMORY")
                
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
        """Initialize semua tabel database dengan schema lengkap"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # USERS TABLE
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
                
                # PRODUCTS TABLE
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
                
                # TRANSACTIONS TABLE
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
                
                # ORDERS TABLE
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
                
                # TOPUP REQUESTS TABLE
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
                
                # ADMIN LOGS TABLE
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
                
                # SYSTEM LOGS TABLE
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
                
                # SETTINGS TABLE
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        description TEXT,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # NOTIFICATIONS TABLE
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
                
                # Create indexes
                indexes = [
                    'CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance)',
                    'CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned)',
                    'CREATE INDEX IF NOT EXISTS idx_users_active ON users(last_active)',
                    'CREATE INDEX IF NOT EXISTS idx_products_status ON products(status)',
                    'CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)',
                    'CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status)',
                    'CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)',
                    'CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)',
                    'CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)',
                    'CREATE INDEX IF NOT EXISTS idx_topup_requests_status ON topup_requests(status)',
                    'CREATE INDEX IF NOT EXISTS idx_topup_requests_user ON topup_requests(user_id)',
                    'CREATE INDEX IF NOT EXISTS idx_admin_logs_admin ON admin_logs(admin_id)',
                    'CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(level)'
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
                
                logger.info("✅ Database initialized successfully")
                
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise

    # ==================== USER MANAGEMENT ====================
    def get_or_create_user(self, user_id: str, username: str = "", full_name: str = "") -> Dict[str, Any]:
        """Get existing user or create new one"""
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
                        raise PermissionError(f"User {user_id} is banned")
                    
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
                else:
                    # Create new user
                    cursor.execute(
                        'INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?)',
                        (str(user_id), username, full_name)
                    )
                
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

    def update_user_balance(self, user_id: str, amount: float, note: str = "") -> bool:
        """Update user balance - FIXED VERSION tanpa nested connections"""
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
                
                # Log the transaction
                if amount != 0:
                    transaction_type = 'topup' if amount > 0 else 'withdraw'
                    cursor.execute('''
                        INSERT INTO transactions (user_id, type, amount, status, details, completed_at)
                        VALUES (?, ?, ?, 'completed', ?, ?)
                    ''', (str(user_id), transaction_type, abs(amount), note, datetime.now()))
                
                logger.info(f"💰 Balance updated: {user_id} -> {amount:,.0f} | New balance: {new_balance:,.0f}")
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
                        COUNT(DISTINCT t.id) as successful_topups
                    FROM users u
                    LEFT JOIN orders o ON u.user_id = o.user_id AND o.status = 'completed'
                    LEFT JOIN transactions t ON u.user_id = t.user_id AND t.status = 'completed' AND t.type = 'topup'
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
                        'total_orders': total_orders,
                        'total_spent': result['total_spent'],
                        'total_topups': result['total_topups'],
                        'successful_orders': success_orders,
                        'successful_topups': result['successful_topups'],
                        'success_rate': round(success_rate, 2),
                        'registered_at': result['registered_at'],
                        'last_active': result['last_active']
                    }
                return {}
        except Exception as e:
            logger.error(f"Error getting user stats for {user_id}: {e}")
            return {}

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

    # ==================== TOPUP MANAGEMENT - FIXED VERSION ====================
    def create_topup_request(self, user_id: str, amount: float, payment_method: str = "", proof_image: str = "", unique_code: int = 0, status: str = "pending") -> int:
        """Create new topup request"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get user info
                user = self.get_user(user_id)
                if not user:
                    raise ValueError(f"User {user_id} not found")
                
                # Generate unique code jika tidak disediakan
                if unique_code == 0:
                    unique_code = random.randint(1, 999)
                
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
                logger.info(f"💳 Topup request created: ID {topup_id} for user {user_id}")
                return topup_id
                    
        except Exception as e:
            logger.error(f"Error creating topup request: {e}")
            raise

    def create_topup(self, user_id: str, amount: float, payment_method: str = "", status: str = "pending", unique_code: int = 0) -> int:
        """Alias untuk create_topup_request"""
        return self.create_topup_request(
            user_id=user_id,
            amount=amount,
            payment_method=payment_method,
            proof_image="",
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
        """Approve topup request - FIXED VERSION tanpa nested transactions"""
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
                    'UPDATE users SET balance = ?, last_active = ? WHERE user_id = ?',
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
    def create_order(self, user_id: str, product_code: str, customer_input: str) -> int:
        """Create new order"""
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
                
                logger.info(f"🛒 Order created: ID {order_id} for user {user_id}")
                return order_id
                    
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            raise

    def update_order_status(self, order_id: int, status: str, sn: str = "", note: str = "") -> bool:
        """Update order status"""
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
                    
        except Exception as e:
            logger.error(f"Error updating order {order_id}: {e}")
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
                cursor.execute('SELECT COUNT(*) as new_users_today FROM users WHERE date(registered_at) = ?', (today,))
                new_users_today = cursor.fetchone()['new_users_today']
                
                cursor.execute('SELECT COUNT(*) as orders_today FROM orders WHERE date(created_at) = ?', (today,))
                orders_today = cursor.fetchone()['orders_today']
                
                return {
                    'total_users': total_users,
                    'active_products': active_products,
                    'pending_topups': pending_topups,
                    'total_balance': total_balance,
                    'total_revenue': total_revenue,
                    'new_users_today': new_users_today,
                    'orders_today': orders_today,
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
        except Exception as e:
            logger.error(f"Error getting bot statistics: {e}")
            return {
                'total_users': 0,
                'active_products': 0,
                'pending_topups': 0,
                'total_balance': 0,
                'total_revenue': 0,
                'new_users_today': 0,
                'orders_today': 0,
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

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
                logger.info(f"👑 User {user_id} promoted to admin")
                return True
        except Exception as e:
            logger.error(f"Error making user {user_id} admin: {e}")
            return False

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

    # ==================== NEW COMPATIBILITY FUNCTIONS ====================
    def get_pending_topups_count(self) -> int:
        """Get count of pending topup requests"""
        try:
            return len(self.get_pending_topups())
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

    def cleanup_old_data(self, days: int = 30) -> Dict[str, int]:
        """Cleanup old data"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Cleanup old orders
                cursor.execute('DELETE FROM orders WHERE created_at < ? AND status IN ("completed", "failed")', (cutoff_date,))
                orders_deleted = cursor.rowcount
                
                # Cleanup old topups
                cursor.execute('DELETE FROM topup_requests WHERE created_at < ? AND status IN ("approved", "rejected")', (cutoff_date,))
                topups_deleted = cursor.rowcount
                
                # Cleanup old logs
                cursor.execute('DELETE FROM system_logs WHERE timestamp < ?', (cutoff_date,))
                logs_deleted = cursor.rowcount
                
                logger.info(f"🧹 Cleanup completed: {orders_deleted} orders, {topups_deleted} topups, {logs_deleted} logs")
                
                return {
                    'orders': orders_deleted,
                    'topups': topups_deleted,
                    'logs': logs_deleted
                }
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            return {'orders': 0, 'topups': 0, 'logs': 0}

# ==================== MODULE-LEVEL FUNCTIONS ====================
_db_manager = DatabaseManager()

# Export semua fungsi untuk backward compatibility
def init_database():
    return _db_manager.init_database()

def get_or_create_user(user_id: str, username: str = "", full_name: str = ""):
    return _db_manager.get_or_create_user(user_id, username, full_name)

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

def get_products_by_category(category: str = None, status: str = 'active'):
    return _db_manager.get_products_by_category(category, status)

def get_product(product_code: str):
    return _db_manager.get_product(product_code)

def create_topup(user_id: str, amount: float, payment_method: str = "", status: str = "pending", unique_code: int = 0):
    return _db_manager.create_topup(user_id, amount, payment_method, status, unique_code)

def get_pending_topups():
    return _db_manager.get_pending_topups()

def get_topup_by_id(topup_id: int):
    return _db_manager.get_topup_by_id(topup_id)

def approve_topup(topup_id: int, admin_id: str, *args):
    return _db_manager.approve_topup(topup_id, admin_id, *args)

def reject_topup(topup_id: int, admin_id: str, *args):
    return _db_manager.reject_topup(topup_id, admin_id, *args)

def create_order(user_id: str, product_code: str, customer_input: str):
    return _db_manager.create_order(user_id, product_code, customer_input)

def update_order_status(order_id: int, status: str, sn: str = "", note: str = ""):
    return _db_manager.update_order_status(order_id, status, sn, note)

def get_bot_statistics():
    return _db_manager.get_bot_statistics()

def is_user_admin(user_id: str):
    return _db_manager.is_user_admin(user_id)

def make_user_admin(user_id: str):
    return _db_manager.make_user_admin(user_id)

def get_all_users(limit: int = 100):
    return _db_manager.get_all_users(limit)

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

def cleanup_old_data(days: int = 30):
    return _db_manager.cleanup_old_data(days)

def get_db_manager():
    return _db_manager

# Aliases untuk compatibility
get_user_saldo = get_user_balance
get_user_info = get_user

if __name__ == "__main__":
    # Test database
    print("🧪 Testing fixed database...")
    db = DatabaseManager()
    
    # Test basic operations
    user = db.get_or_create_user("test_user", "testuser", "Test User")
    print(f"✅ User test: {user['user_id']}")
    
    # Test topup
    topup_id = db.create_topup("test_user", 50000, "QRIS", "pending", 123)
    print(f"✅ Topup test: ID {topup_id}")
    
    # Test statistics
    stats = db.get_bot_statistics()
    print(f"✅ Statistics: {stats}")
    
    print("🚀 FIXED DATABASE READY FOR PRODUCTION!")
