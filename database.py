# database.py - Complete Database Management
import sqlite3
import logging
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Dict, List, Optional, Any
import json

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: str = "bot_database.db"):
        self.db_path = db_path
        self.init_database()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections dengan error handling"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise e
        finally:
            conn.close()

    def init_database(self):
        """Initialize semua tabel database dengan schema lengkap"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # ==================== USERS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        username TEXT,
                        full_name TEXT NOT NULL,
                        balance REAL DEFAULT 0,
                        total_spent REAL DEFAULT 0,
                        total_orders INTEGER DEFAULT 0,
                        total_topups INTEGER DEFAULT 0,
                        registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
                        is_banned INTEGER DEFAULT 0,
                        ban_reason TEXT
                    )
                ''')
                
                # ==================== PRODUCTS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS products (
                        code TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        price REAL NOT NULL,
                        status TEXT DEFAULT 'active',
                        description TEXT,
                        category TEXT,
                        provider TEXT,
                        gangguan INTEGER DEFAULT 0,
                        kosong INTEGER DEFAULT 0,
                        stock INTEGER DEFAULT 0,
                        min_stock INTEGER DEFAULT 0,
                        max_stock INTEGER DEFAULT 1000,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # ==================== TRANSACTIONS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        type TEXT NOT NULL,
                        amount REAL NOT NULL,
                        status TEXT DEFAULT 'pending',
                        details TEXT,
                        unique_code INTEGER DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        completed_at DATETIME,
                        admin_notes TEXT,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # ==================== ORDERS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        product_code TEXT NOT NULL,
                        product_name TEXT NOT NULL,
                        price REAL NOT NULL,
                        status TEXT DEFAULT 'pending',
                        provider_order_id TEXT,
                        customer_input TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        completed_at DATETIME,
                        response_data TEXT,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # ==================== ADMIN LOGS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS admin_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        details TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # ==================== SYSTEM LOGS TABLE ====================
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS system_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        level TEXT NOT NULL,
                        message TEXT NOT NULL,
                        details TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create indexes untuk performa
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_status ON products(status)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)')
                
                logger.info("✅ Database initialized successfully")
                
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise

    # ==================== USER MANAGEMENT ====================
    def get_or_create_user(self, user_id: str, username: str, full_name: str) -> str:
        """Get existing user or create new one dengan update data"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if user exists
            cursor.execute(
                'SELECT user_id, is_banned FROM users WHERE user_id = ?', 
                (str(user_id),)
            )
            user = cursor.fetchone()
            
            if user:
                if user['is_banned']:
                    raise PermissionError(f"User {user_id} is banned")
                # Update user info jika berubah
                cursor.execute(
                    '''UPDATE users SET 
                    username = ?, full_name = ?, last_active = ? 
                    WHERE user_id = ?''',
                    (username, full_name, datetime.now(), str(user_id))
                )
                logger.info(f"📝 User updated: {user_id} - {full_name}")
            else:
                # Create new user
                cursor.execute(
                    'INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?)',
                    (str(user_id), username, full_name)
                )
                logger.info(f"👤 New user created: {user_id} - {full_name}")
            
            return str(user_id)

    def get_user_balance(self, user_id: str) -> float:
        """Get user balance dengan error handling"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT balance FROM users WHERE user_id = ? AND is_banned = 0', 
                    (str(user_id),)
                )
                result = cursor.fetchone()
                return result['balance'] if result else 0.0
        except Exception as e:
            logger.error(f"Error getting balance for {user_id}: {e}")
            return 0.0

    def update_user_balance(self, user_id: str, amount: float) -> bool:
        """Update user balance dengan validation"""
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
                    'UPDATE users SET balance = ? WHERE user_id = ?',
                    (new_balance, str(user_id))
                )
                
                # Update total_topups jika topup
                if amount > 0:
                    cursor.execute(
                        'UPDATE users SET total_topups = total_topups + 1 WHERE user_id = ?',
                        (str(user_id),)
                    )
                
                logger.info(f"💰 Balance updated: {user_id} -> {amount:,.0f}")
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
                    u.balance,
                    u.total_orders,
                    u.total_spent,
                    u.total_topups,
                    u.registered_at,
                    u.last_active,
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
                return {
                    'balance': result['balance'],
                    'total_orders': result['total_orders'],
                    'total_spent': result['total_spent'],
                    'total_topups': result['total_topups'],
                    'successful_orders': result['successful_orders'],
                    'successful_topups': result['successful_topups'],
                    'registered_at': result['registered_at'],
                    'last_active': result['last_active']
                }
            return {}

    # ==================== TRANSACTION MANAGEMENT ====================
    def add_transaction(self, user_id: str, trans_type: str, amount: float, 
                       status: str = "pending", details: str = "", unique_code: int = 0) -> int:
        """Add transaction record dengan validation"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO transactions 
                (user_id, type, amount, status, details, unique_code) 
                VALUES (?, ?, ?, ?, ?, ?)''',
                (str(user_id), trans_type, amount, status, details, unique_code)
            )
            transaction_id = cursor.lastrowid
            logger.info(f"💳 Transaction added: {transaction_id} - {trans_type} - {amount:,.0f}")
            return transaction_id

    def update_transaction_status(self, transaction_id: int, status: str, details: str = "", admin_notes: str = "") -> bool:
        """Update transaction status dengan completion tracking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get transaction details first
            cursor.execute(
                'SELECT user_id, amount, type FROM transactions WHERE id = ?',
                (transaction_id,)
            )
            trans = cursor.fetchone()
            
            if not trans:
                raise ValueError(f"Transaction {transaction_id} not found")
            
            completed_at = datetime.now() if status in ['completed', 'rejected'] else None
            
            cursor.execute(
                '''UPDATE transactions SET 
                status = ?, details = ?, completed_at = ?, admin_notes = ?
                WHERE id = ?''',
                (status, details, completed_at, admin_notes, transaction_id)
            )
            
            # Jika topup completed, update user balance
            if status == 'completed' and trans['type'] == 'topup':
                self.update_user_balance(trans['user_id'], trans['amount'])
                logger.info(f"✅ Topup completed: {transaction_id} for user {trans['user_id']}")
            
            logger.info(f"📝 Transaction {transaction_id} status updated to {status}")
            return True

    def get_pending_transactions(self, trans_type: str = 'topup') -> List[Dict]:
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

    def get_user_transactions(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Get user transaction history"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM transactions 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (str(user_id), limit))
            return [dict(row) for row in cursor.fetchall()]

    # ==================== PRODUCT MANAGEMENT ====================
    def get_active_products(self, category: Optional[str] = None) -> List[Dict]:
        """Get active products dengan filtering"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if category and category != 'all':
                cursor.execute('''
                    SELECT * FROM products 
                    WHERE status = 'active' AND category = ?
                    ORDER BY category, name
                ''', (category,))
            else:
                cursor.execute('''
                    SELECT * FROM products 
                    WHERE status = 'active' 
                    ORDER BY category, name
                ''')
            
            return [dict(row) for row in cursor.fetchall()]

    def get_product_by_code(self, code: str) -> Optional[Dict]:
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
                          'provider', 'gangguan', 'kosong', 'stock', 'min_stock', 'max_stock']
            
            update_fields = []
            values = []
            
            for field, value in kwargs.items():
                if field in valid_fields:
                    update_fields.append(f"{field} = ?")
                    values.append(value)
            
            if not update_fields:
                raise ValueError("No valid fields to update")
            
            values.append(code)
            values.append(datetime.now())  # for updated_at
            
            set_clause = ', '.join(update_fields)
            query = f'UPDATE products SET {set_clause}, updated_at = ? WHERE code = ?'
            
            cursor.execute(query, values)
            return cursor.rowcount > 0

    def bulk_update_products(self, products: List[Dict]) -> int:
        """Bulk update products untuk sync dari provider"""
        count = 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Set all products to inactive first
            cursor.execute("UPDATE products SET status = 'inactive'")
            
            for product in products:
                try:
                    cursor.execute('''
                        INSERT INTO products 
                        (code, name, price, status, description, category, provider, 
                         gangguan, kosong, stock, updated_at)
                        VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(code) DO UPDATE SET
                            name=excluded.name,
                            price=excluded.price,
                            status='active',
                            description=excluded.description,
                            category=excluded.category,
                            provider=excluded.provider,
                            gangguan=excluded.gangguan,
                            kosong=excluded.kosong,
                            stock=excluded.stock,
                            updated_at=excluded.updated_at
                    ''', (
                        product['code'], product['name'], product['price'],
                        product.get('description', ''), product.get('category', 'Umum'),
                        product.get('provider', ''), product.get('gangguan', 0),
                        product.get('kosong', 0), product.get('stock', 0),
                        datetime.now()
                    ))
                    count += 1
                except Exception as e:
                    logger.error(f"Error updating product {product.get('code')}: {e}")
                    continue
            
            logger.info(f"🔄 Bulk updated {count} products")
            return count

    # ==================== ORDER MANAGEMENT ====================
    def create_order(self, user_id: str, product_code: str, product_name: str, 
                    price: float, customer_input: str = "") -> int:
        """Create new order dengan comprehensive tracking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
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
            
            logger.info(f"🛒 Order created: {order_id} - {product_name}")
            return order_id

    def update_order_status(self, order_id: int, status: str, 
                          provider_order_id: str = None, response_data: str = None) -> bool:
        """Update order status dengan response tracking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            completed_at = datetime.now() if status == 'completed' else None
            
            cursor.execute(
                '''UPDATE orders SET 
                status = ?, provider_order_id = ?, completed_at = ?, response_data = ?
                WHERE id = ?''',
                (status, provider_order_id, completed_at, response_data, order_id)
            )
            
            # Jika order completed, update user balance dan spending
            if status == 'completed':
                cursor.execute(
                    'SELECT user_id, price FROM orders WHERE id = ?',
                    (order_id,)
                )
                order = cursor.fetchone()
                
                if order:
                    # Kurangi saldo user
                    cursor.execute(
                        'UPDATE users SET balance = balance - ?, total_spent = total_spent + ? WHERE user_id = ?',
                        (order['price'], order['price'], order['user_id'])
                    )
            
            logger.info(f"📦 Order {order_id} status updated to {status}")
            return True

    def get_user_orders(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Get user order history"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM orders 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (str(user_id), limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_orders(self) -> List[Dict]:
        """Get all pending orders"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT o.*, u.username, u.full_name 
                FROM orders o 
                JOIN users u ON o.user_id = u.user_id 
                WHERE o.status = 'pending'
                ORDER BY o.created_at DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]

    # ==================== ADMIN & LOGGING ====================
    def log_admin_action(self, user_id: str, action: str, details: str = ""):
        """Log admin action untuk audit trail"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO admin_logs (user_id, action, details) VALUES (?, ?, ?)',
                (str(user_id), action, details)
            )

    def log_system_event(self, level: str, message: str, details: str = ""):
        """Log system events untuk debugging"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO system_logs (level, message, details) VALUES (?, ?, ?)',
                (level, message, details)
            )

    # ==================== STATISTICS & REPORTING ====================
    def get_bot_statistics(self) -> Dict[str, Any]:
        """Get comprehensive bot statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Total users
            cursor.execute('SELECT COUNT(*) as total_users FROM users WHERE is_banned = 0')
            total_users = cursor.fetchone()['total_users']
            
            # New users today
            cursor.execute('''
                SELECT COUNT(*) as today_users 
                FROM users 
                WHERE DATE(registered_at) = DATE('now') AND is_banned = 0
            ''')
            today_users = cursor.fetchone()['today_users']
            
            # Total orders
            cursor.execute('SELECT COUNT(*) as total_orders FROM orders')
            total_orders = cursor.fetchone()['total_orders']
            
            # Successful orders
            cursor.execute('SELECT COUNT(*) as successful_orders FROM orders WHERE status = "completed"')
            successful_orders = cursor.fetchone()['successful_orders']
            
            # Total transactions
            cursor.execute('SELECT COUNT(*) as total_transactions FROM transactions')
            total_transactions = cursor.fetchone()['total_transactions']
            
            # Total revenue (completed topups)
            cursor.execute('SELECT SUM(amount) as total_revenue FROM transactions WHERE status = "completed" AND type = "topup"')
            total_revenue = cursor.fetchone()['total_revenue'] or 0
            
            # Total spending (completed orders)
            cursor.execute('SELECT SUM(price) as total_spending FROM orders WHERE status = "completed"')
            total_spending = cursor.fetchone()['total_spending'] or 0
            
            # Active products
            cursor.execute('SELECT COUNT(*) as active_products FROM products WHERE status = "active"')
            active_products = cursor.fetchone()['active_products']
            
            # Pending transactions
            cursor.execute('SELECT COUNT(*) as pending_topups FROM transactions WHERE status = "pending" AND type = "topup"')
            pending_topups = cursor.fetchone()['pending_topups']
            
            # Pending orders
            cursor.execute('SELECT COUNT(*) as pending_orders FROM orders WHERE status = "pending"')
            pending_orders = cursor.fetchone()['pending_orders']
            
            return {
                'total_users': total_users,
                'today_users': today_users,
                'total_orders': total_orders,
                'successful_orders': successful_orders,
                'total_transactions': total_transactions,
                'total_revenue': total_revenue,
                'total_spending': total_spending,
                'active_products': active_products,
                'pending_topups': pending_topups,
                'pending_orders': pending_orders,
                'net_profit': total_revenue - total_spending
            }

    def get_daily_stats(self, days: int = 7) -> List[Dict]:
        """Get daily statistics untuk chart"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as order_count,
                    SUM(CASE WHEN status = 'completed' THEN price ELSE 0 END) as revenue
                FROM orders 
                WHERE created_at >= date('now', ?)
                GROUP BY DATE(created_at)
                ORDER BY date DESC
            ''', (f'-{days} days',))
            
            return [dict(row) for row in cursor.fetchall()]

    # ==================== MAINTENANCE & CLEANUP ====================
    def cleanup_old_data(self, days: int = 30) -> Dict[str, int]:
        """Cleanup old data untuk optimize database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Cleanup old completed transactions
            cursor.execute('''
                DELETE FROM transactions 
                WHERE status = 'completed' 
                AND created_at < datetime('now', ?)
            ''', (f'-{days} days',))
            trans_deleted = cursor.rowcount
            
            # Cleanup old completed orders
            cursor.execute('''
                DELETE FROM orders 
                WHERE status = 'completed' 
                AND created_at < datetime('now', ?)
            ''', (f'-{days} days',))
            orders_deleted = cursor.rowcount
            
            # Cleanup old admin logs
            cursor.execute('''
                DELETE FROM admin_logs 
                WHERE timestamp < datetime('now', ?)
            ''', (f'-{days} days',))
            logs_deleted = cursor.rowcount
            
            # Cleanup old system logs (keep error logs longer)
            cursor.execute('''
                DELETE FROM system_logs 
                WHERE timestamp < datetime('now', ?)
                AND level != 'ERROR'
            ''', (f'-{days} days',))
            system_logs_deleted = cursor.rowcount
            
            # Vacuum database untuk optimize space
            cursor.execute('VACUUM')
            
            return {
                'transactions': trans_deleted,
                'orders': orders_deleted,
                'admin_logs': logs_deleted,
                'system_logs': system_logs_deleted
            }

    def backup_database(self, backup_path: str) -> bool:
        """Backup database ke file external"""
        import shutil
        try:
            shutil.copy2(self.db_path, backup_path)
            self.log_system_event('INFO', 'Database backup created', f'Backup: {backup_path}')
            return True
        except Exception as e:
            self.log_system_event('ERROR', 'Database backup failed', str(e))
            return False

# Global database instance
db = DatabaseManager()
