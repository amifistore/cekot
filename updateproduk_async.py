import aiohttp
import aiosqlite
from datetime import datetime
import config

DB_PATH = "bot_topup.db"
API_KEY = config.API_KEY_PROVIDER  # Ambil dari config.json

async def update_produk_async():
    url = f"https://panel.khfy-store.com/api_v2/list_product?api_key={API_KEY}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=15) as resp:
                resp.raise_for_status()
                data = await resp.json()
        except Exception as e:
            return False, f"Gagal mengambil data produk dari API: {e}"

    if not data or "data" not in data or not isinstance(data["data"], list):
        return False, "Format data produk tidak valid."

    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
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
            if not code or not name or price <= 0:
                continue
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await conn.execute("""
                INSERT INTO products (code, name, price, status, updated_at)
                VALUES (?, ?, ?, 'active', ?)
                ON CONFLICT(code) DO UPDATE SET
                    name=excluded.name,
                    price=excluded.price,
                    status='active',
                    updated_at=excluded.updated_at
            """, (code, name, price, now))
            count += 1
        await conn.commit()
    return True, f"Produk berhasil diupdate: {count} produk aktif."

# Contoh pemakaian di handler Telegram:
# from updateproduk_async import update_produk_async
# async def updateproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if not is_admin(update.message.from_user):
#         await update.message.reply_text("Hanya admin yang bisa update produk.")
#         return
#     status, msg = await update_produk_async()
#     await update.message.reply_text(msg)
