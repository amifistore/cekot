import sqlite3
from datetime import datetime

DB_PATH = "bot_topup.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id TEXT UNIQUE NOT NULL,
        username TEXT,
        full_name TEXT,
        saldo INTEGER DEFAULT 0,
        is_admin INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS topup_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        qris_base64 TEXT,
        payment_status TEXT DEFAULT 'waiting',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        paid_at DATETIME,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS products (
        code TEXT PRIMARY KEY,
        name TEXT,
        price REAL,
        status TEXT,
        updated_at TEXT,
        deskripsi TEXT
    );
    CREATE TABLE IF NOT EXISTS riwayat_pembelian (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        kode_produk TEXT,
        nama_produk TEXT,
        tujuan TEXT,
        harga INTEGER,
        saldo_awal INTEGER,
        reff_id TEXT,
        status_api TEXT,
        keterangan TEXT,
        waktu DATETIME,
        refund INTEGER DEFAULT 0
    );
    """)
    conn.commit()
    conn.close()

def get_or_create_user(telegram_id, username, full_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,))
    user = c.fetchone()
    if user:
        user_id = user[0]
    else:
        c.execute(
            "INSERT INTO users (telegram_id, username, full_name) VALUES (?, ?, ?)",
            (telegram_id, username, full_name)
        )
        user_id = c.lastrowid
        conn.commit()
    conn.close()
    return user_id

def get_user_saldo(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT saldo FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0]
    return 0

def increment_user_saldo(user_id, amount):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE users SET saldo = saldo + ? WHERE id=?",
        (amount, user_id)
    )
    conn.commit()
    conn.close()

def create_topup_request(user_id, amount, qris_base64):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO topup_requests (user_id, amount, qris_base64) VALUES (?, ?, ?)",
        (user_id, amount, qris_base64)
    )
    conn.commit()
    conn.close()

def update_topup_status(topup_id, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE topup_requests SET payment_status=?, paid_at=? WHERE id=?",
        (status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), topup_id)
    )
    conn.commit()
    conn.close()

def add_user_admin(telegram_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_admin=1 WHERE telegram_id=?", (telegram_id,))
    conn.commit()
    conn.close()

def get_telegram_id_by_username(username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if row: return row[0]
    return None

def get_all_telegram_ids():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]
