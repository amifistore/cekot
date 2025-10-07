import requests
import sqlite3
from datetime import datetime

DB_PATH = "bot_topup.db"
API_KEY = "B66AB76B-A7AF-40BF-B037-1E58332E12EA"  # Ganti sesuai config!

def update_produk():
    url = f"https://panel.khfy-store.com/api_v2/list_product?api_key={API_KEY}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print("Gagal mengambil data produk dari API:", e)
        return

    if not data or "data" not in data or not isinstance(data["data"], list):
        print("Format data produk tidak valid.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Buat tabel jika belum ada
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            code TEXT PRIMARY KEY,
            name TEXT,
            price REAL,
            status TEXT,
            updated_at TEXT
        )
    """)

    count = 0
    for prod in data["data"]:
        code = str(prod.get("kode", "")).strip()
        name = str(prod.get("nama", "")).strip()
        price = float(prod.get("harga", 0))
        if not code or not name:
            continue
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # Upsert
        c.execute("""
            INSERT INTO products (code, name, price, status, updated_at)
            VALUES (?, ?, ?, 'active', ?)
            ON CONFLICT(code) DO UPDATE SET
                name=excluded.name,
                price=excluded.price,
                status='active',
                updated_at=excluded.updated_at
        """, (code, name, price, now))
        count += 1
    conn.commit()
    conn.close()
    print(f"Produk berhasil diupdate! {count} produk aktif.")

if __name__ == "__main__":
    update_produk()
