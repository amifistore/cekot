import sqlite3
import logging
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
import os

class Database:
    def __init__(self, db_path: str = "bot_database.db"):
        self.db_path = db_path
        self.init_database()

    def get_connection(self):
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self):
        """Initialize database tables"""
        with self.get_connection() as conn:
            # Users table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    balance INTEGER DEFAULT 0,
                    is_admin BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Topup requests table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS topup_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    base_amount INTEGER NOT NULL,
                    unique_amount INTEGER NOT NULL,
                    unique_digits INTEGER NOT NULL,
                    proof_image TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    admin_notes TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Transactions history table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    balance_before INTEGER NOT NULL,
                    balance_after INTEGER NOT NULL,
                    description TEXT,
                    reference_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Create indexes for better performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_topup_status ON topup_requests(status)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_topup_user_id ON topup_requests(user_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_topup_created ON topup_requests(created_at)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at)')

            conn.commit()

    # ===== USER MANAGEMENT =====
    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by user_id"""
        with self.get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM users WHERE user_id = ?', 
                (user_id,)
            ).fetchone()
            return dict(row) if row else None

    def create_user(self, user_id: int, username: str, full_name: str) -> bool:
        """Create new user"""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    'INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)',
                    (user_id, username, full_name)
                )
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"Error creating user: {e}")
            return False

    def update_user_balance(self, user_id: int, amount: int) -> bool:
        """Update user balance"""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    'UPDATE users SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                    (amount, user_id)
                )
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"Error updating user balance: {e}")
            return False

    def get_user_balance(self, user_id: int) -> int:
        """Get user current balance"""
        with self.get_connection() as conn:
            row = conn.execute(
                'SELECT balance FROM users WHERE user_id = ?', 
                (user_id,)
            ).fetchone()
            return row['balance'] if row else 0

    # ===== TOPUP MANAGEMENT =====
    def create_topup_request(self, user_id: int, base_amount: int, unique_digits: int, 
                           proof_image: str, username: str, full_name: str) -> bool:
        """Create new topup request"""
        try:
            unique_amount = base_amount + unique_digits
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with self.get_connection() as conn:
                # First, ensure user exists
                self.create_user(user_id, username, full_name)
                
                # Create topup request
                conn.execute('''
                    INSERT INTO topup_requests 
                    (user_id, base_amount, unique_amount, unique_digits, proof_image, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, base_amount, unique_amount, unique_digits, proof_image, created_at, created_at))
                
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"Error creating topup request: {e}")
            return False

    def get_topup_requests(self, status_filter: str = 'pending') -> List[Tuple]:
        """Get topup requests with optional status filter"""
        try:
            with self.get_connection() as conn:
                if status_filter == 'all':
                    query = '''
                        SELECT tr.*, u.username, u.full_name 
                        FROM topup_requests tr
                        LEFT JOIN users u ON tr.user_id = u.user_id
                        ORDER BY tr.created_at DESC
                    '''
                    rows = conn.execute(query).fetchall()
                else:
                    query = '''
                        SELECT tr.*, u.username, u.full_name 
                        FROM topup_requests tr
                        LEFT JOIN users u ON tr.user_id = u.user_id
                        WHERE tr.status = ?
                        ORDER BY tr.created_at DESC
                    '''
                    rows = conn.execute(query, (status_filter,)).fetchall()

                # Convert to tuples for backward compatibility
                result = []
                for row in rows:
                    result.append((
                        row['id'], row['user_id'], row['base_amount'], 
                        row['unique_amount'], row['unique_digits'], 
                        row['proof_image'], row['status'], row['created_at'],
                        row['updated_at'], row['username'], row['full_name']
                    ))
                return result
        except Exception as e:
            logging.error(f"Error getting topup requests: {e}")
            return []

    def get_topup_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        """Get specific topup request by ID"""
        with self.get_connection() as conn:
            row = conn.execute('''
                SELECT tr.*, u.username, u.full_name, u.balance
                FROM topup_requests tr
                LEFT JOIN users u ON tr.user_id = u.user_id
                WHERE tr.id = ?
            ''', (request_id,)).fetchone()
            return dict(row) if row else None

    def update_topup_status(self, request_id: int, status: str, admin_notes: str = None) -> bool:
        """Update topup request status"""
        try:
            updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with self.get_connection() as conn:
                conn.execute('''
                    UPDATE topup_requests 
                    SET status = ?, updated_at = ?, admin_notes = ?
                    WHERE id = ?
                ''', (status, updated_at, admin_notes, request_id))
                
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"Error updating topup status: {e}")
            return False

    def approve_topup(self, request_id: int) -> bool:
        """Approve topup request and add balance to user"""
        try:
            with self.get_connection() as conn:
                # Get topup request details
                request = self.get_topup_request(request_id)
                if not request:
                    return False

                user_id = request['user_id']
                base_amount = request['base_amount']
                current_balance = request['balance']

                # Start transaction
                conn.execute('BEGIN TRANSACTION')

                # Update topup status
                conn.execute('''
                    UPDATE topup_requests 
                    SET status = 'approved', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (request_id,))

                # Update user balance
                conn.execute('''
                    UPDATE users 
                    SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (base_amount, user_id))

                # Record transaction
                conn.execute('''
                    INSERT INTO transactions 
                    (user_id, type, amount, balance_before, balance_after, description, reference_id)
                    VALUES (?, 'topup', ?, ?, ?, ?, ?)
                ''', (user_id, base_amount, current_balance, current_balance + base_amount, 
                      f"Topup approved - Request #{request_id}", request_id))

                conn.commit()
                return True

        except Exception as e:
            logging.error(f"Error approving topup: {e}")
            with self.get_connection() as conn:
                conn.execute('ROLLBACK')
            return False

    def reject_topup(self, request_id: int, admin_notes: str = None) -> bool:
        """Reject topup request"""
        try:
            with self.get_connection() as conn:
                conn.execute('''
                    UPDATE topup_requests 
                    SET status = 'rejected', updated_at = CURRENT_TIMESTAMP, admin_notes = ?
                    WHERE id = ?
                ''', (admin_notes, request_id))
                
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"Error rejecting topup: {e}")
            return False

    # ===== TRANSACTION HISTORY =====
    def get_user_transactions(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get user transaction history"""
        with self.get_connection() as conn:
            rows = conn.execute('''
                SELECT * FROM transactions 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (user_id, limit)).fetchall()
            return [dict(row) for row in rows]

    def create_transaction(self, user_id: int, transaction_type: str, amount: int, 
                         description: str, reference_id: int = None) -> bool:
        """Create transaction record"""
        try:
            with self.get_connection() as conn:
                current_balance = self.get_user_balance(user_id)
                new_balance = current_balance + amount

                conn.execute('''
                    INSERT INTO transactions 
                    (user_id, type, amount, balance_before, balance_after, description, reference_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, transaction_type, amount, current_balance, new_balance, description, reference_id))

                # Update user balance
                conn.execute(
                    'UPDATE users SET balance = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                    (new_balance, user_id)
                )

                conn.commit()
                return True
        except Exception as e:
            logging.error(f"Error creating transaction: {e}")
            return False

    # ===== ADMIN STATISTICS =====
    def get_topup_statistics(self) -> Dict[str, Any]:
        """Get topup statistics for admin dashboard"""
        with self.get_connection() as conn:
            stats = {}
            
            # Total counts by status
            status_counts = conn.execute('''
                SELECT status, COUNT(*) as count 
                FROM topup_requests 
                GROUP BY status
            ''').fetchall()
            
            for row in status_counts:
                stats[f"{row['status']}_count"] = row['count']

            # Total amounts by status
            amount_totals = conn.execute('''
                SELECT status, SUM(base_amount) as total 
                FROM topup_requests 
                GROUP BY status
            ''').fetchall()
            
            for row in amount_totals:
                stats[f"{row['status']}_amount"] = row['total'] or 0

            # Today's requests
            today = datetime.now().strftime("%Y-%m-%d")
            today_stats = conn.execute('''
                SELECT COUNT(*) as count, SUM(base_amount) as total 
                FROM topup_requests 
                WHERE DATE(created_at) = ?
            ''', (today,)).fetchone()
            
            stats['today_count'] = today_stats['count'] or 0
            stats['today_amount'] = today_stats['total'] or 0

            return stats

    # ===== MAINTENANCE METHODS =====
    def backup_database(self, backup_path: str = None) -> bool:
        """Create database backup"""
        try:
            if not backup_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"backup_bot_database_{timestamp}.db"
            
            with self.get_connection() as source:
                with sqlite3.connect(backup_path) as target:
                    source.backup(target)
            return True
        except Exception as e:
            logging.error(f"Error backing up database: {e}")
            return False

    def cleanup_old_data(self, days: int = 30) -> bool:
        """Clean up data older than specified days"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            
            with self.get_connection() as conn:
                # Archive or delete old data here
                # Example: Delete old rejected requests
                conn.execute('''
                    DELETE FROM topup_requests 
                    WHERE status = 'rejected' AND DATE(created_at) < ?
                ''', (cutoff_date,))
                
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"Error cleaning up old data: {e}")
            return False

# Global database instance
database = Database()
