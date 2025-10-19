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
            return dict(cursor.fetchone())

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

    # ==================== TRANSACTION MANAGEMENT ====================
    def add_transaction(self, user_id: str, trans_type: str, amount: float, 
                       status: str = "pending", details: str = "", 
                       unique_code: int = 0, payment_method: str = "") -> int:
        """Add transaction record dengan validation"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Validate transaction type
            valid_types = ['topup', 'withdraw', 'refund', 'bonus']
            if trans_type not in valid_types:
                raise ValueError(f"Invalid transaction type. Must be one of: {valid_types}")
            
            cursor.execute(
                '''INSERT INTO transactions 
                (user_id, type, amount, status, details, unique_code, payment_method) 
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (str(user_id), trans_type, amount, status, details, unique_code, payment_method)
            )
            transaction_id = cursor.lastrowid
            
            # Update user last active
            self.update_user_last_active(user_id)
            
            logger.info(f"💳 Transaction added: {transaction_id} - {trans_type} - {amount:,.0f} - {status}")
            return transaction_id

    def update_transaction_status(self, transaction_id: int, status: str, 
                                details: str = "", admin_notes: str = "") -> bool:
        """Update transaction status dengan completion tracking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get transaction details first
            cursor.execute(
                'SELECT user_id, amount, type, status FROM transactions WHERE id = ?',
                (transaction_id,)
            )
            trans = cursor.fetchone()
            
            if not trans:
                raise ValueError(f"Transaction {transaction_id} not found")
            
            # If status not changed, do nothing
            if trans['status'] == status:
                logger.info(f"Transaction {transaction_id} status already {status}")
                return True
            
            completed_at = datetime.now() if status in ['completed', 'rejected', 'cancelled'] else None
            
            cursor.execute(
                '''UPDATE transactions SET 
                status = ?, details = ?, completed_at = ?, admin_notes = ?
                WHERE id = ?''',
                (status, details, completed_at, admin_notes, transaction_id)
            )
            
            # Jika topup completed, update user balance
            if status == 'completed' and trans['type'] == 'topup':
                self.update_user_balance(trans['user_id'], trans['amount'], 
                                       f"Topup completed - Transaction #{transaction_id}")
                logger.info(f"✅ Topup completed: {transaction_id} for user {trans['user_id']}")
            
            logger.info(f"📝 Transaction {transaction_id} status updated from {trans['status']} to {status}")
            return True

    def get_transaction(self, transaction_id: int) -> Optional[Dict[str, Any]]:
        """Get transaction details dengan user info"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    t.*,
                    u.username,
                    u.full_name,
                    u.balance as user_balance
                FROM transactions t 
                JOIN users u ON t.user_id = u.user_id 
                WHERE t.id = ?
            ''', (transaction_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_pending_transactions(self, trans_type: str = 'topup') -> List[Dict[str, Any]]:
        """Get all pending transactions dengan user info"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    t.*,
                    u.username,
                    u.full_name,
                    u.balance as user_balance
                FROM transactions t 
                JOIN users u ON t.user_id = u.user_id 
                WHERE t.status = 'pending' AND t.type = ?
                ORDER BY t.created_at DESC
            ''', (trans_type,))
            return [dict(row) for row in cursor.fetchall()]

    def get_user_transactions(self, user_id: str, limit: int = 10, 
                            trans_type: str = None) -> List[Dict[str, Any]]:
        """Get user transaction history dengan filtering"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = '''
                SELECT * FROM transactions 
                WHERE user_id = ?
            '''
            params = [str(user_id)]
            
            if trans_type:
                query += ' AND type = ?'
                params.append(trans_type)
            
            query += ' ORDER BY created_at DESC LIMIT ?'
            params.append(limit)
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    # ==================== PRODUCT MANAGEMENT ====================
    def get_active_products(self, category: Optional[str] = None, 
                          provider: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get active products dengan filtering"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = '''
                SELECT * FROM products 
                WHERE status = 'active'
            '''
            params = []
            
            if category and category != 'all':
                query += ' AND category = ?'
                params.append(category)
            
            if provider and provider != 'all':
                query += ' AND provider = ?'
                params.append(provider)
            
            query += ' ORDER BY category, name, price'
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_product_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Get product by code dengan error handling"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM products WHERE code = ?', (code,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def update_product(self, code: str, **kwargs) -> bool:
        """Update product information dengan comprehensive fields"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build dynamic update query
            valid_fields = ['name', 'price', 'status', 'description', 'category', 
                          'provider', 'gangguan', 'kosong', 'stock', 'min_stock', 
                          'max_stock', 'profit_margin']
            
            update_fields = []
            values = []
            
            for field, value in kwargs.items():
                if field in valid_fields and value is not None:
                    update_fields.append(f"{field} = ?")
                    values.append(value)
            
            if not update_fields:
                raise ValueError("No valid fields to update")
            
            values.append(code)
            values.append(datetime.now())  # for updated_at
            
            set_clause = ', '.join(update_fields)
            query = f'UPDATE products SET {set_clause}, updated_at = ? WHERE code = ?'
            
            cursor.execute(query, values)
            affected = cursor.rowcount > 0
            
            if affected:
                logger.info(f"📦 Product updated: {code} - Fields: {', '.join(update_fields)}")
            
            return affected

    def bulk_update_products(self, products: List[Dict]) -> int:
        """Bulk update products untuk sync dari provider"""
        count = 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Set all products to inactive first (will reactivate existing ones)
            cursor.execute("UPDATE products SET status = 'inactive'")
            
            for product in products:
                try:
                    cursor.execute('''
                        INSERT INTO products 
                        (code, name, price, status, description, category, provider, 
                         gangguan, kosong, stock, profit_margin, updated_at)
                        VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(code) DO UPDATE SET
                            name = excluded.name,
                            price = excluded.price,
                            status = 'active',
                            description = excluded.description,
                            category = excluded.category,
                            provider = excluded.provider,
                            gangguan = excluded.gangguan,
                            kosong = excluded.kosong,
                            stock = excluded.stock,
                            profit_margin = excluded.profit_margin,
                            updated_at = excluded.updated_at
                    ''', (
                        product['code'], 
                        product['name'], 
                        product['price'],
                        product.get('description', ''), 
                        product.get('category', 'Umum'),
                        product.get('provider', ''), 
                        product.get('gangguan', 0),
                        product.get('kosong', 0), 
                        product.get('stock', 0),
                        product.get('profit_margin', 0),
                        datetime.now()
                    ))
                    count += 1
                except Exception as e:
                    logger.error(f"Error updating product {product.get('code')}: {e}")
                    continue
            
            logger.info(f"🔄 Bulk updated {count} products")
            return count

    def get_categories(self) -> List[str]:
        """Get list of unique product categories"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT category FROM products 
                WHERE status = 'active' 
                ORDER BY category
            ''')
            return [row['category'] for row in cursor.fetchall()]

    def get_providers(self) -> List[str]:
        """Get list of unique providers"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT provider FROM products 
                WHERE status = 'active' AND provider IS NOT NULL AND provider != ''
                ORDER BY provider
            ''')
            return [row['provider'] for row in cursor.fetchall()]

    # ==================== ORDER MANAGEMENT ====================
    def create_order(self, user_id: str, product_code: str, product_name: str, 
                    price: float, customer_input: str = "") -> int:
        """Create new order dengan comprehensive tracking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check product availability
            product = self.get_product_by_code(product_code)
            if not product:
                raise ValueError(f"Product {product_code} not found")
            
            if product['status'] != 'active':
                raise ValueError(f"Product {product_code} is not active")
            
            if product['kosong'] == 1:
                raise ValueError(f"Product {product_code} is empty")
            
            if product['gangguan'] == 1:
                raise ValueError(f"Product {product_code} is experiencing issues")
            
            # Check user balance
            user_balance = self.get_user_balance(user_id)
            if user_balance < price:
                raise ValueError(f"Insufficient balance. Need: {price:,.0f}, Have: {user_balance:,.0f}")
            
            cursor.execute(
                '''INSERT INTO orders 
                (user_id, product_code, product_name, price, status, customer_input) 
                VALUES (?, ?, ?, ?, 'pending', ?)''',
                (str(user_id), product_code, product_name, price, customer_input)
            )
            order_id = cursor.lastrowid
            
            # Update user stats
            cursor.execute(
                'UPDATE users SET total_orders = total_orders + 1 WHERE user_id = ?',
                (str(user_id),)
            )
            
            # Update user last active
            self.update_user_last_active(user_id)
            
            logger.info(f"🛒 Order created: {order_id} - {product_code} by {user_id} - Price: {price:,.0f}")
            return order_id

    def update_order_status(self, order_id: int, status: str, provider_order_id: str = "", 
                          response_data: str = "", sn: str = "", note: str = "") -> bool:
        """Update order status dengan completion handling"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get order details first
            cursor.execute(
                'SELECT user_id, price, status FROM orders WHERE id = ?',
                (order_id,)
            )
            order = cursor.fetchone()
            
            if not order:
                raise ValueError(f"Order {order_id} not found")
            
            old_status = order['status']
            
            # Set timestamps based on status
            processed_at = None
            completed_at = None
            
            if status in ['processing'] and old_status == 'pending':
                processed_at = datetime.now()
            elif status in ['completed', 'failed', 'partial', 'refunded']:
                completed_at = datetime.now()
                if old_status != 'completed' and status == 'completed':
                    processed_at = order['processed_at'] or datetime.now()
            
            cursor.execute(
                '''UPDATE orders SET 
                status = ?, provider_order_id = ?, response_data = ?, 
                sn = ?, note = ?, processed_at = ?, completed_at = ?
                WHERE id = ?''',
                (status, provider_order_id, response_data, sn, note, 
                 processed_at, completed_at, order_id)
            )
            
            # Jika order completed, update user stats dan balance
            if status == 'completed' and old_status != 'completed':
                cursor.execute(
                    'UPDATE users SET total_spent = total_spent + ? WHERE user_id = ?',
                    (order['price'], order['user_id'])
                )
                # Balance already deducted when order was created
                logger.info(f"✅ Order completed: {order_id} - User: {order['user_id']}")
            
            # Jika order failed/refunded, refund balance
            elif status in ['failed', 'refunded'] and old_status not in ['failed', 'refunded']:
                self.update_user_balance(order['user_id'], order['price'], 
                                       f"Refund for order #{order_id}")
                logger.info(f"🔄 Order {status}: {order_id} - Refunded {order['price']:,.0f}")
            
            logger.info(f"📝 Order {order_id} status updated from {old_status} to {status}")
            return True

    def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        """Get order details dengan user info"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    o.*, 
                    u.username,
                    u.full_name,
                    p.description as product_description
                FROM orders o 
                JOIN users u ON o.user_id = u.user_id 
                LEFT JOIN products p ON o.product_code = p.code
                WHERE o.id = ?
            ''', (order_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_user_orders(self, user_id: str, limit: int = 10, 
                       status: str = None) -> List[Dict[str, Any]]:
        """Get user order history dengan filtering"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = '''
                SELECT o.*, p.description as product_description
                FROM orders o 
                LEFT JOIN products p ON o.product_code = p.code
                WHERE o.user_id = ?
            '''
            params = [str(user_id)]
            
            if status and status != 'all':
                query += ' AND o.status = ?'
                params.append(status)
            
            query += ' ORDER BY o.created_at DESC LIMIT ?'
            params.append(limit)
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """Get all pending orders untuk processing"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    o.*, 
                    u.username, 
                    u.full_name,
                    p.description as product_description
                FROM orders o 
                JOIN users u ON o.user_id = u.user_id 
                LEFT JOIN products p ON o.product_code = p.code
                WHERE o.status = 'pending'
                ORDER BY o.created_at ASC
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def get_orders_by_status(self, status: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get orders by status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    o.*, 
                    u.username, 
                    u.full_name
                FROM orders o 
                JOIN users u ON o.user_id = u.user_id 
                WHERE o.status = ?
                ORDER BY o.created_at DESC
                LIMIT ?
            ''', (status, limit))
            return [dict(row) for row in cursor.fetchall()]

    # ==================== ADMIN & REPORTING ====================
    def get_system_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive system statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            date_filter = datetime.now() - timedelta(days=days)
            
            # Total users, orders, transactions
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_users,
                    SUM(balance) as total_balance,
                    SUM(total_orders) as total_orders,
                    SUM(total_spent) as total_revenue,
                    SUM(total_topups) as total_topups,
                    COUNT(CASE WHEN is_banned = 1 THEN 1 END) as banned_users
                FROM users
            ''')
            stats = cursor.fetchone()
            
            # Today's activity
            cursor.execute('''
                SELECT 
                    COUNT(*) as today_orders,
                    SUM(price) as today_revenue
                FROM orders 
                WHERE DATE(created_at) = DATE('now') AND status = 'completed'
            ''')
            today_stats = cursor.fetchone()
            
            # Recent activity (last X days)
            cursor.execute('''
                SELECT 
                    COUNT(*) as recent_orders,
                    SUM(price) as recent_revenue,
                    COUNT(DISTINCT user_id) as active_users
                FROM orders 
                WHERE created_at > ? AND status = 'completed'
            ''', (date_filter,))
            recent_stats = cursor.fetchone()
            
            # Pending transactions and orders
            cursor.execute('''
                SELECT 
                    COUNT(*) as pending_topups,
                    COALESCE(SUM(amount), 0) as pending_amount
                FROM transactions 
                WHERE status = 'pending' AND type = 'topup'
            ''')
            pending_stats = cursor.fetchone()
            
            cursor.execute('''
                SELECT COUNT(*) as pending_orders
                FROM orders 
                WHERE status = 'pending'
            ''')
            pending_orders = cursor.fetchone()
            
            # Product stats
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_products,
                    COUNT(CASE WHEN status = 'active' THEN 1 END) as active_products,
                    COUNT(CASE WHEN gangguan = 1 THEN 1 END) as problem_products,
                    COUNT(CASE WHEN kosong = 1 THEN 1 END) as empty_products
                FROM products
            ''')
            product_stats = cursor.fetchone()
            
            return {
                'total_users': stats['total_users'] or 0,
                'banned_users': stats['banned_users'] or 0,
                'total_balance': stats['total_balance'] or 0,
                'total_orders': stats['total_orders'] or 0,
                'total_revenue': stats['total_revenue'] or 0,
                'total_topups': stats['total_topups'] or 0,
                'today_orders': today_stats['today_orders'] or 0,
                'today_revenue': today_stats['today_revenue'] or 0,
                'recent_orders': recent_stats['recent_orders'] or 0,
                'recent_revenue': recent_stats['recent_revenue'] or 0,
                'active_users': recent_stats['active_users'] or 0,
                'pending_topups': pending_stats['pending_topups'] or 0,
                'pending_amount': pending_stats['pending_amount'] or 0,
                'pending_orders': pending_orders['pending_orders'] or 0,
                'total_products': product_stats['total_products'] or 0,
                'active_products': product_stats['active_products'] or 0,
                'problem_products': product_stats['problem_products'] or 0,
                'empty_products': product_stats['empty_products'] or 0
            }

    def get_daily_stats(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get daily statistics untuk chart"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as order_count,
                    SUM(price) as revenue,
                    COUNT(DISTINCT user_id) as unique_customers
                FROM orders 
                WHERE created_at > DATE('now', ?) AND status = 'completed'
                GROUP BY DATE(created_at)
                ORDER BY date DESC
                LIMIT ?
            ''', (f'-{days} days', days))
            return [dict(row) for row in cursor.fetchall()]

    def get_top_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top users by spending"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    user_id, username, full_name,
                    total_spent, total_orders, balance,
                    last_active, registered_at
                FROM users 
                WHERE is_banned = 0
                ORDER BY total_spent DESC 
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_top_products(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top products by sales"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    p.code,
                    p.name,
                    p.category,
                    p.price,
                    COUNT(o.id) as sale_count,
                    SUM(o.price) as total_revenue
                FROM products p
                LEFT JOIN orders o ON p.code = o.product_code AND o.status = 'completed'
                GROUP BY p.code, p.name, p.category, p.price
                ORDER BY sale_count DESC, total_revenue DESC
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def ban_user(self, user_id: str, reason: str = "", admin_id: str = "") -> bool:
        """Ban user dengan comprehensive handling"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?',
                (reason, str(user_id))
            )
            
            if cursor.rowcount > 0:
                # Log admin action
                if admin_id:
                    self.add_admin_log(admin_id, 'BAN_USER', 'user', user_id, 
                                     f"Banned user {user_id}. Reason: {reason}")
                
                logger.warning(f"🚫 User banned: {user_id} - Reason: {reason}")
                return True
            return False

    def unban_user(self, user_id: str, admin_id: str = "") -> bool:
        """Unban user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?',
                (str(user_id),)
            )
            
            if cursor.rowcount > 0:
                # Log admin action
                if admin_id:
                    self.add_admin_log(admin_id, 'UNBAN_USER', 'user', user_id, 
                                     f"Unbanned user {user_id}")
                
                logger.info(f"✅ User unbanned: {user_id}")
                return True
            return False

    def get_banned_users(self) -> List[Dict[str, Any]]:
        """Get all banned users"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, username, full_name, ban_reason, last_active
                FROM users 
                WHERE is_banned = 1
                ORDER BY last_active DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]

    # ==================== SETTINGS MANAGEMENT ====================
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get setting value by key"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            result = cursor.fetchone()
            if result:
                try:
                    # Try to convert to int/float if possible
                    value = result['value']
                    if value.isdigit():
                        return int(value)
                    try:
                        return float(value)
                    except:
                        return value
                except:
                    return result['value']
            return default

    def set_setting(self, key: str, value: Any, description: str = "") -> bool:
        """Set setting value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value, description, updated_at)
                VALUES (?, ?, ?, ?)
            ''', (key, str(value), description, datetime.now()))
            return True

    def get_all_settings(self) -> Dict[str, Any]:
        """Get all settings"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT key, value, description FROM settings')
            return {row['key']: {'value': row['value'], 'description': row['description']} 
                   for row in cursor.fetchall()}

    # ==================== LOGGING SYSTEM ====================
    def add_admin_log(self, admin_id: str, action: str, target_type: str = "", 
                     target_id: str = "", details: str = "", ip: str = "", 
                     user_agent: str = ""):
        """Add admin action log"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO admin_logs 
                (admin_id, action, target_type, target_id, details, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (str(admin_id), action, target_type, target_id, details, ip, user_agent))

    def add_system_log(self, level: str, module: str, message: str, 
                      details: str = "", user_id: str = ""):
        """Add system log"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO system_logs 
                (level, module, message, details, user_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (level, module, message, details, user_id))

    def get_admin_logs(self, admin_id: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get admin logs dengan filtering"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if admin_id:
                cursor.execute('''
                    SELECT * FROM admin_logs 
                    WHERE admin_id = ?
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (str(admin_id), limit))
            else:
                cursor.execute('''
                    SELECT * FROM admin_logs 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (limit,))
            
            return [dict(row) for row in cursor.fetchall()]

    def get_system_logs(self, level: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get system logs dengan filtering"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if level:
                cursor.execute('''
                    SELECT * FROM system_logs 
                    WHERE level = ?
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (level, limit))
            else:
                cursor.execute('''
                    SELECT * FROM system_logs 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (limit,))
            
            return [dict(row) for row in cursor.fetchall()]

    # ==================== NOTIFICATION SYSTEM ====================
    def add_notification(self, user_id: str, title: str, message: str, 
                        notif_type: str = "info") -> int:
        """Add notification for user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO notifications 
                (user_id, title, message, type)
                VALUES (?, ?, ?, ?)
            ''', (str(user_id), title, message, notif_type))
            return cursor.lastrowid

    def get_user_notifications(self, user_id: str, unread_only: bool = False, 
                              limit: int = 20) -> List[Dict[str, Any]]:
        """Get user notifications"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT * FROM notifications WHERE user_id = ?'
            params = [str(user_id)]
            
            if unread_only:
                query += ' AND is_read = 0'
            
            query += ' ORDER BY created_at DESC LIMIT ?'
            params.append(limit)
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def mark_notification_read(self, notification_id: int) -> bool:
        """Mark notification as read"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE notifications SET is_read = 1 WHERE id = ?',
                (notification_id,)
            )
            return cursor.rowcount > 0

    def mark_all_notifications_read(self, user_id: str) -> bool:
        """Mark all user notifications as read"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE notifications SET is_read = 1 WHERE user_id = ?',
                (str(user_id),)
            )
            return cursor.rowcount > 0

    # ==================== MAINTENANCE & BACKUP ====================
    def cleanup_old_data(self, days: int = 30) -> Dict[str, int]:
        """Cleanup old data untuk maintenance"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Archive old completed transactions (keep recent for records)
            cursor.execute(
                'DELETE FROM transactions WHERE status = "completed" AND created_at < ?',
                (cutoff_date,)
            )
            trans_deleted = cursor.rowcount
            
            # Archive old completed orders (keep failed for analysis)
            cursor.execute(
                'DELETE FROM orders WHERE status IN ("completed", "failed", "refunded") AND created_at < ?',
                (cutoff_date,)
            )
            orders_deleted = cursor.rowcount
            
            # Clean old system logs (keep ERROR logs longer)
            error_cutoff = datetime.now() - timedelta(days=days*2)
            cursor.execute(
                'DELETE FROM system_logs WHERE level != "ERROR" AND timestamp < ?',
                (cutoff_date,)
            )
            logs_deleted = cursor.rowcount
            
            # Clean old admin logs
            cursor.execute(
                'DELETE FROM admin_logs WHERE timestamp < ?',
                (cutoff_date,)
            )
            admin_logs_deleted = cursor.rowcount
            
            # Clean old notifications
            cursor.execute(
                'DELETE FROM notifications WHERE is_read = 1 AND created_at < ?',
                (cutoff_date - timedelta(days=7),)
            )
            notif_deleted = cursor.rowcount
            
            # Vacuum database to optimize space
            cursor.execute('VACUUM')
            
            logger.info(f"🧹 Cleanup completed: {trans_deleted} transactions, {orders_deleted} orders, "
                       f"{logs_deleted} system logs, {admin_logs_deleted} admin logs, {notif_deleted} notifications")
            
            return {
                'transactions_deleted': trans_deleted,
                'orders_deleted': orders_deleted,
                'system_logs_deleted': logs_deleted,
                'admin_logs_deleted': admin_logs_deleted,
                'notifications_deleted': notif_deleted
            }

    def export_data(self, table: str, limit: int = None) -> List[Dict[str, Any]]:
        """Export table data untuk backup"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            valid_tables = ['users', 'products', 'transactions', 'orders', 
                          'admin_logs', 'system_logs', 'notifications', 'settings']
            if table not in valid_tables:
                raise ValueError(f"Invalid table. Must be one of: {valid_tables}")
            
            query = f'SELECT * FROM {table}'
            if limit:
                query += f' LIMIT {limit}'
            
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]

    def backup_database(self, backup_path: str) -> bool:
        """Create database backup"""
        import shutil
        try:
            # Create backup directory if not exists
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            
            # Copy database file
            shutil.copy2(self.db_path, backup_path)
            
            # Log backup activity
            self.add_system_log('INFO', 'BACKUP', f'Database backed up to: {backup_path}')
            logger.info(f"💾 Database backed up to: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            self.add_system_log('ERROR', 'BACKUP', f'Backup failed: {e}')
            return False

    def get_database_size(self) -> int:
        """Get database file size in bytes"""
        try:
            return os.path.getsize(self.db_path)
        except:
            return 0

    def optimize_database(self):
        """Optimize database performance"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('PRAGMA optimize')
            cursor.execute('PRAGMA vacuum')
            cursor.execute('PRAGMA analysis_limit=400')
            cursor.execute('PRAGMA auto_vacuum=INCREMENTAL')
            
            logger.info("🔧 Database optimized")
            self.add_system_log('INFO', 'MAINTENANCE', 'Database optimization completed')

    # ==================== ADVANCED QUERIES ====================
    def search_users(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search users by username, full name, or user ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            search_term = f"%{query}%"
            cursor.execute('''
                SELECT user_id, username, full_name, balance, total_orders, 
                       total_spent, last_active, is_banned
                FROM users 
                WHERE user_id LIKE ? OR username LIKE ? OR full_name LIKE ?
                ORDER BY 
                    CASE 
                        WHEN user_id = ? THEN 1
                        WHEN username = ? THEN 2
                        ELSE 3
                    END,
                    last_active DESC
                LIMIT ?
            ''', (search_term, search_term, search_term, query, query, limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_financial_report(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Get financial report for period"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Revenue from completed orders
            cursor.execute('''
                SELECT 
                    SUM(price) as revenue,
                    COUNT(*) as order_count
                FROM orders 
                WHERE status = 'completed' 
                AND created_at BETWEEN ? AND ?
            ''', (start_date, end_date))
            revenue_stats = cursor.fetchone()
            
            # Topup statistics
            cursor.execute('''
                SELECT 
                    SUM(amount) as topup_amount,
                    COUNT(*) as topup_count
                FROM transactions 
                WHERE type = 'topup' AND status = 'completed'
                AND created_at BETWEEN ? AND ?
            ''', (start_date, end_date))
            topup_stats = cursor.fetchone()
            
            # User growth
            cursor.execute('''
                SELECT COUNT(*) as new_users
                FROM users 
                WHERE registered_at BETWEEN ? AND ?
            ''', (start_date, end_date))
            user_stats = cursor.fetchone()
            
            # Top products
            cursor.execute('''
                SELECT 
                    p.name,
                    p.category,
                    COUNT(o.id) as sale_count,
                    SUM(o.price) as revenue
                FROM products p
                JOIN orders o ON p.code = o.product_code
                WHERE o.status = 'completed' AND o.created_at BETWEEN ? AND ?
                GROUP BY p.name, p.category
                ORDER BY revenue DESC
                LIMIT 10
            ''', (start_date, end_date))
            top_products = [dict(row) for row in cursor.fetchall()]
            
            return {
                'period': {'start': start_date, 'end': end_date},
                'revenue': revenue_stats['revenue'] or 0,
                'order_count': revenue_stats['order_count'] or 0,
                'topup_amount': topup_stats['topup_amount'] or 0,
                'topup_count': topup_stats['topup_count'] or 0,
                'new_users': user_stats['new_users'] or 0,
                'top_products': top_products
            }

# Singleton instance untuk easy access
db = DatabaseManager()

# Example usage and testing
if __name__ == "__main__":
    # Initialize logging
    logging.basicConfig(level=logging.INFO)
    
    # Test database initialization
    db.init_database()
    
    # Test user operations
    user_id = "12345"
    user = db.get_or_create_user(user_id, "test_user", "Test User")
    print(f"✅ User created: {user['full_name']}")
    
    # Test balance operations
    db.update_user_balance(user_id, 50000, "Initial topup")
    balance = db.get_user_balance(user_id)
    print(f"💰 User balance: {balance:,.0f}")
    
    # Test settings
    db.set_setting("test_setting", "123", "Test setting")
    setting = db.get_setting("test_setting")
    print(f"⚙️ Setting value: {setting}")
    
    # Test system stats
    stats = db.get_system_stats()
    print(f"📊 System stats: {stats}")
    
    print("✅ All database tests completed successfully!")
