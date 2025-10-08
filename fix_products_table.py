import sqlite3

db_path = "bot_database.db"  # Ubah jika pakai bot_topup.db
conn = sqlite3.connect(db_path)
c = conn.cursor()

try:
    c.execute("ALTER TABLE products ADD COLUMN stock INTEGER DEFAULT 0")
    print("Kolom 'stock' berhasil ditambahkan.")
except sqlite3.OperationalError as e:
    print("Kolom 'stock' mungkin sudah ada atau gagal ditambah:", e)

conn.commit()
conn.close()
