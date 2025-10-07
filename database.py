import sqlite3

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

def create_topup_request(user_id, amount, qris_base64):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO topup_requests (user_id, amount, qris_base64) VALUES (?, ?, ?)",
        (user_id, amount, qris_base64)
    )
    conn.commit()
    conn.close()

def get_topup_requests(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, amount, payment_status, created_at FROM topup_requests WHERE user_id=? ORDER BY id DESC",
        (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def update_topup_status(topup_id, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE topup_requests SET payment_status=?, paid_at=CURRENT_TIMESTAMP WHERE id=?",
        (status, topup_id)
    )
    conn.commit()
    conn.close()

def increment_user_saldo(user_id, amount):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE users SET saldo = saldo + ? WHERE id=?",
        (amount, user_id)
    )
    conn.commit()
    conn.close()
