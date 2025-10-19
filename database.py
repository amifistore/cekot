# database.py - Complete Database Management System
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
        """Context manager for database connections dengan error handling dan connection pooling"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA cache_size = -64000")
        conn.execute("PRAGMA synchronous = NORMAL")
        
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
                    cursor.execute(index)
                
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
    # database.py - Perbaiki fungsi add_pending_topup

def add_pending_topup(user_id: str, amount: int, proof_text: str = "", payment_method: str = "bank_transfer") -> str:
    """Add pending topup transaction - FIXED VERSION"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Generate transaction ID
        transaction_id = f"TOPUP_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        cursor.execute('''
            INSERT INTO topups (user_id, amount, unique_amount, proof_text, payment_method, transaction_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, amount, amount, proof_text, payment_method, transaction_id))
        
        conn.commit()
        conn.close()
        return transaction_id
        
    except Exception as e:
        logger.error(f"Error in add_pending_topup: {e}")
        return f"ERROR_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    def get_or_create_user(self, user_id: str, username: str = "", full_name: str = "") -> Dict[str, Any]:
        """Get existing user or create new one dengan update data"""
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

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user data by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (str(user_id),))
            result = cursor.fetchone()
            return dict(result) if result else None

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
                
                self.add_system_log('INFO', 'BALANCE_UPDATE', f"User {user_id}: {log_message}", user_id)
                logger.info(f"💰 Balance updated: {user_id} -> {amount:,.0f} | New balance: {new_balance:,.0f}")
                return True
                
        except Exception as e:
            logger.error(f"Error updating balance for {user_id}: {e}")
            raise

    def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get comprehensive user statistics"""
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
                    'is_banned': result['is_banned'],
                    'level': result['level']
                }
            return {}

    def update_user_last_active(self, user_id: str):
        """Update user last active timestamp"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE users SET last_active = ? WHERE user_id = ?',
                (datetime.now(), str(user_id))
            )

    # ==================== PRODUCT MANAGEMENT ====================
    def get_products_by_category(self, category: str = None) -> List[Dict[str, Any]]:
        """Get products by category"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if category:
                cursor.execute('''
                    SELECT * FROM products 
                    WHERE category = ? AND status = 'active' AND gangguan = 0 AND kosong = 0
                    ORDER BY price
                ''', (category,))
            else:
                cursor.execute('''
                    SELECT * FROM products 
                    WHERE status = 'active' AND gangguan = 0 AND kosong = 0
                    ORDER BY category, price
                ''')
            
            return [dict(row) for row in cursor.fetchall()]

    def get_product_categories(self) -> List[str]:
        """Get list of product categories"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT category FROM products 
                WHERE status = 'active' AND gangguan = 0 AND kosong = 0
                ORDER BY category
            ''')
            return [row[0] for row in cursor.fetchall()]

    def get_product_by_code(self, product_code: str) -> Optional[Dict[str, Any]]:
        """Get product by code"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM products WHERE code = ?', (product_code,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def update_product_stock(self, product_code: str, new_stock: int):
        """Update product stock"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE products SET stock = ?, updated_at = ? WHERE code = ?',
                (new_stock, datetime.now(), product_code)
            )

    # ==================== TOPUP MANAGEMENT ====================
    def add_pending_topup(self, user_id: str, amount: float, proof_text: str = "") -> int:
        """Add pending topup request"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get user info
            cursor.execute('SELECT username, full_name FROM users WHERE user_id = ?', (user_id,))
            user_info = cursor.fetchone()
            username = user_info['username'] if user_info else None
            full_name = user_info['full_name'] if user_info else None
            
            cursor.execute('''
                INSERT INTO topup_requests (user_id, username, full_name, amount, proof_image, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, full_name, amount, proof_text, datetime.now()))
            
            return cursor.lastrowid

    def get_pending_topups(self) -> List[Dict[str, Any]]:
        """Get all pending topup requests"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM topup_requests 
                WHERE status = 'pending'
                ORDER BY created_at DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def approve_topup(self, topup_id: int, admin_id: str) -> bool:
        """Approve a topup request"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                # Get topup details
                cursor.execute('SELECT user_id, amount FROM topup_requests WHERE id = ?', (topup_id,))
                result = cursor.fetchone()
                
                if not result:
                    return False
                
                user_id = result['user_id']
                amount = result['amount']
                
                # Update user balance
                self.update_user_balance(user_id, amount, f"Topup approved by admin {admin_id}")
                
                # Update topup status
                cursor.execute(
                    'UPDATE topup_requests SET status = ?, updated_at = ? WHERE id = ?',
                    ('approved', datetime.now(), topup_id)
                )
                
                # Add transaction record
                cursor.execute('''
                    INSERT INTO transactions (user_id, type, amount, status, details)
                    VALUES (?, 'topup', ?, 'completed', ?)
                ''', (user_id, amount, f'Topup approved by admin {admin_id}'))
                
                # Log admin action
                self.log_admin_action(admin_id, "APPROVE_TOPUP", f"Topup ID: {topup_id}, Amount: {amount}")
                
                return True
                
            except Exception as e:
                logger.error(f"Error approving topup {topup_id}: {e}")
                return False

    def reject_topup(self, topup_id: int, admin_id: str) -> bool:
        """Reject a topup request"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                cursor.execute(
                    'UPDATE topup_requests SET status = ?, updated_at = ? WHERE id = ?',
                    ('rejected', datetime.now(), topup_id)
                )
                
                # Log admin action
                self.log_admin_action(admin_id, "REJECT_TOPUP", f"Topup ID: {topup_id}")
                
                return True
                
            except Exception as e:
                logger.error(f"Error rejecting topup {topup_id}: {e}")
                return False

    # ==================== ORDER MANAGEMENT ====================
    def create_order(self, user_id: str, product_code: str, product_name: str, 
                    price: float, customer_input: str = "") -> int:
        """Create new order"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO orders (user_id, product_code, product_name, price, customer_input)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, product_code, product_name, price, customer_input))
            
            order_id = cursor.lastrowid
            
            # Update user stats
            cursor.execute(
                'UPDATE users SET total_orders = total_orders + 1, last_active = ? WHERE user_id = ?',
                (datetime.now(), user_id)
            )
            
            self.add_system_log('INFO', 'ORDER_CREATED', f"Order {order_id} created for user {user_id}", user_id)
            
            return order_id

    def update_order_status(self, order_id: int, status: str, note: str = "", 
                           provider_order_id: str = "", sn: str = ""):
        """Update order status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            update_fields = ["status = ?"]
            params = [status]
            
            if note:
                update_fields.append("note = ?")
                params.append(note)
            
            if provider_order_id:
                update_fields.append("provider_order_id = ?")
                params.append(provider_order_id)
            
            if sn:
                update_fields.append("sn = ?")
                params.append(sn)
            
            if status == 'completed':
                update_fields.append("completed_at = ?")
                params.append(datetime.now())
            elif status == 'processing':
                update_fields.append("processed_at = ?")
                params.append(datetime.now())
            
            params.append(order_id)
            
            query = f"UPDATE orders SET {', '.join(update_fields)} WHERE id = ?"
            cursor.execute(query, params)
            
            # If order completed, update user spent
            if status == 'completed':
                cursor.execute('SELECT user_id, price FROM orders WHERE id = ?', (order_id,))
                order = cursor.fetchone()
                if order:
                    cursor.execute(
                        'UPDATE users SET total_spent = total_spent + ? WHERE user_id = ?',
                        (order['price'], order['user_id'])
                    )

    # ==================== LOGGING SYSTEM ====================
    def log_admin_action(self, admin_id: str, action: str, details: str = "", 
                        target_type: str = None, target_id: str = None):
        """Log admin action untuk audit trail"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO admin_logs (admin_id, action, target_type, target_id, details)
                VALUES (?, ?, ?, ?, ?)
            ''', (str(admin_id), action, target_type, target_id, details))

    def add_system_log(self, level: str, module: str, message: str, 
                      details: str = "", user_id: str = None):
        """Add system log"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO system_logs (level, module, message, details, user_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (level, module, message, details, user_id))

    # ==================== STATISTICS & REPORTING ====================
    def get_bot_statistics(self) -> Dict[str, Any]:
        """Get comprehensive bot statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Basic counts
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 0")
            active_users = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM products WHERE status = 'active'")
            active_products = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'")
            completed_orders = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(price) FROM orders WHERE status = 'completed'")
            total_revenue = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(*) FROM topup_requests WHERE status = 'pending'")
            pending_topups = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
            pending_orders = cursor.fetchone()[0]
            
            # Today's stats
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(registered_at) = ?", (today,))
            new_users_today = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM orders WHERE DATE(created_at) = ? AND status = 'completed'", (today,))
            orders_today = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(price) FROM orders WHERE DATE(created_at) = ? AND status = 'completed'", (today,))
            revenue_today = cursor.fetchone()[0] or 0
            
            return {
                'total_users': total_users,
                'active_users': active_users,
                'active_products': active_products,
                'completed_orders': completed_orders,
                'total_revenue': total_revenue,
                'pending_topups': pending_topups,
                'pending_orders': pending_orders,
                'new_users_today': new_users_today,
                'orders_today': orders_today,
                'revenue_today': revenue_today
            }

    def get_user_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get user leaderboard by total spent"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, username, full_name, total_spent, total_orders, level
                FROM users 
                WHERE is_banned = 0
                ORDER BY total_spent DESC
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # ==================== SETTINGS MANAGEMENT ====================
    def get_setting(self, key: str, default: str = None) -> str:
        """Get setting value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            result = cursor.fetchone()
            return result['value'] if result else default

    def update_setting(self, key: str, value: str):
        """Update setting value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
            ''', (key, value, datetime.now()))

# ==================== GLOBAL INSTANCE & COMPATIBILITY FUNCTIONS ====================

# Create global instance
db_manager = DatabaseManager()

# Compatibility functions for existing code
def init_database():
    """Initialize database - compatibility function"""
    return db_manager.init_database()

def get_or_create_user(user_id: str, username: str = "", full_name: str = "") -> str:
    """Get or create user - compatibility function"""
    user_data = db_manager.get_or_create_user(user_id, username, full_name)
    return user_data.get('user_id', user_id) if user_data else user_id

def get_user_saldo(user_id: str) -> float:
    """Get user balance - compatibility function"""
    return db_manager.get_user_balance(user_id)

def get_current_timestamp() -> str:
    """Get current timestamp - compatibility function"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def add_pending_topup(user_id: str, amount: float, proof_text: str = "") -> int:
    """Add pending topup - compatibility function"""
    return db_manager.add_pending_topup(user_id, amount, proof_text)

def get_pending_topups() -> List[Dict[str, Any]]:
    """Get pending topups - compatibility function"""
    return db_manager.get_pending_topups()

def approve_topup(topup_id: int, admin_id: str) -> bool:
    """Approve topup - compatibility function"""
    return db_manager.approve_topup(topup_id, admin_id)

def reject_topup(topup_id: int, admin_id: str) -> bool:
    """Reject topup - compatibility function"""
    return db_manager.reject_topup(topup_id, admin_id)

def log_admin_action(admin_id: str, action: str, details: str = ""):
    """Log admin action - compatibility function"""
    return db_manager.log_admin_action(admin_id, action, details)

def get_bot_statistics() -> Dict[str, Any]:
    """Get bot statistics - compatibility function"""
    return db_manager.get_bot_statistics()

# Product management compatibility functions
def get_products_by_category(category: str = None) -> List[Dict[str, Any]]:
    """Get products by category - compatibility function"""
    return db_manager.get_products_by_category(category)

def get_product_categories() -> List[str]:
    """Get product categories - compatibility function"""
    return db_manager.get_product_categories()

def get_product_by_id(product_code: str) -> Optional[Dict[str, Any]]:
    """Get product by code - compatibility function"""
    return db_manager.get_product_by_code(product_code)

def update_product_stock(product_code: str, new_stock: int):
    """Update product stock - compatibility function"""
    return db_manager.update_product_stock(product_code, new_stock)
