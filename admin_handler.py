import config
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
import sqlite3
from datetime import datetime
import database

DB_PATH = "bot_topup.db"

def is_admin(user):
    return str(user.id) in config.ADMIN_TELEGRAM_IDS

# Handler untuk update produk dari API ke database
async def updateproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("Hanya admin yang bisa update produk.")
        return

    import requests
    api_key = config.API_KEY_PROVIDER
    url = f"https://panel.khfy-store.com/api_v2/list_product?api_key={api_key}"

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        await update.message.reply_text(f"Gagal mengambil data produk dari API: {e}")
        return

    if not data or "data" not in data or not isinstance(data["data"], list):
        await update.message.reply_text("Format data produk tidak valid.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Pastikan tabel products ada
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
        # Upsert produk
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
    await update.message.reply_text(f"Produk berhasil diupdate: {count} produk aktif.")

updateproduk_handler = CommandHandler("updateproduk", updateproduk)

# Handler untuk list produk dari database
async def listproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("Hanya admin yang bisa melihat list produk.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT code, name, price FROM products WHERE status='active' ORDER BY name ASC LIMIT 30")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("Produk belum tersedia atau belum diupdate.")
        return

    msg = "List Produk Aktif:\n"
    for code, name, price in rows:
        msg += f"- {name} ({code}): Rp {price:,.0f}\n"
    await update.message.reply_text(msg)

listproduk_handler = CommandHandler("listproduk", listproduk)

# Handler untuk konfirmasi topup
async def topup_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("Hanya admin yang bisa konfirmasi.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Format: /topup_confirm <topup_id>")
        return
    topup_id = args[0]
    database.update_topup_status(topup_id, "paid")
    await update.message.reply_text(f"Top up ID {topup_id} berhasil dikonfirmasi.")

topup_confirm_handler = CommandHandler("topup_confirm", topup_confirm)

# Handler cek user
async def cek_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("Hanya admin yang bisa cek user.")
        return
    args = context.args
    username = args[0] if args else None
    if not username:
        await update.message.reply_text("Format: /cek_user <username>")
        return
    conn = sqlite3.connect(database.DB_PATH)
    c = conn.cursor()
    c.execute("SELECT saldo, telegram_id FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if not row:
        await update.message.reply_text("User tidak ditemukan.")
        return
    saldo, telegram_id = row
    admin_status = "Ya" if telegram_id in config.ADMIN_TELEGRAM_IDS else "Tidak"
    await update.message.reply_text(
        f"Username: {username}\nSaldo: Rp {saldo}\nAdmin: {admin_status}\nTelegram ID: {telegram_id}"
    )

cek_user_handler = CommandHandler("cek_user", cek_user)

# Handler jadikan admin
async def jadikan_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("Hanya admin yang bisa menjadikan admin.")
        return
    args = context.args
    telegram_id = args[0] if args else None
    if not telegram_id:
        await update.message.reply_text("Format: /jadikan_admin <telegram_id>")
        return
    database.add_user_admin(telegram_id)
    await update.message.reply_text(f"User dengan telegram_id {telegram_id} sudah jadi admin.")

jadikan_admin_handler = CommandHandler("jadikan_admin", jadikan_admin)

# Handler menu admin utama
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("Menu admin hanya untuk admin.")
        return
    await update.message.reply_text(
        "/updateproduk - Update produk dari API provider\n"
        "/listproduk - List produk aktif di database\n"
        "/topup_confirm <topup_id> - Konfirmasi topup user\n"
        "/cek_user <username> - Cek info user\n"
        "/jadikan_admin <telegram_id> - Jadikan user sebagai admin\n"
        "/broadcast pesan - Broadcast ke semua user\n"
    )

admin_menu_handler = CommandHandler("admin", admin_menu)
