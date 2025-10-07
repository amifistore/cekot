import config
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
import aiohttp
import aiosqlite
import database
import sqlite3
from datetime import datetime

DB_PATH = "bot_topup.db"

def is_admin(user):
    return str(user.id) in config.ADMIN_TELEGRAM_IDS

# Handler update produk dari API ke database
async def updateproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa update produk.")
        return

    api_key = config.API_KEY_PROVIDER
    url = f"https://panel.khfy-store.com/api_v2/list_product?api_key={api_key}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as resp:
                resp.raise_for_status()
                data = await resp.json()
    except Exception as e:
        await update.message.reply_text(f"🚫 Gagal mengambil data produk dari API: {e}")
        return

    produk_list = data.get("data", [])
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                code TEXT PRIMARY KEY,
                name TEXT,
                price REAL,
                status TEXT,
                updated_at TEXT,
                deskripsi TEXT
            )
        """)
        count = 0
        for prod in produk_list:
            code = str(prod.get("kode_produk", "")).strip()
            name = str(prod.get("nama_produk", "")).strip()
            price = float(prod.get("harga_final", 0))
            deskripsi = str(prod.get("deskripsi", "-"))
            if not code or not name or price <= 0:
                continue
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await conn.execute("""
                INSERT INTO products (code, name, price, status, updated_at, deskripsi)
                VALUES (?, ?, ?, 'active', ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name=excluded.name,
                    price=excluded.price,
                    status='active',
                    updated_at=excluded.updated_at,
                    deskripsi=excluded.deskripsi
            """, (code, name, price, now, deskripsi))
            count += 1
        await conn.commit()
        async with conn.execute("SELECT code, name, price, deskripsi FROM products WHERE status='active' ORDER BY name ASC LIMIT 5") as cursor:
            data_preview = await cursor.fetchall()
    if count == 0:
        await update.message.reply_text("⚠️ Tidak ada produk aktif yang berhasil diupdate.")
    else:
        msg = f"✅ Produk berhasil diupdate: *{count}* produk aktif.\nContoh produk:\n"
        for code, name, price, deskripsi in data_preview:
            msg += f"• *{name}* (`{code}`): Rp {price:,.0f}\n   └ _{deskripsi}_\n"
        await update.message.reply_text(msg, parse_mode="Markdown")

updateproduk_handler = CommandHandler("updateproduk", updateproduk)

# Handler list produk
async def listproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa melihat list produk.")
        return

    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                code TEXT PRIMARY KEY,
                name TEXT,
                price REAL,
                status TEXT,
                updated_at TEXT,
                deskripsi TEXT
            )
        """)
        async with conn.execute("SELECT code, name, price, deskripsi FROM products WHERE status='active' ORDER BY name ASC LIMIT 30") as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await update.message.reply_text("⚠️ Produk belum tersedia atau belum diupdate.")
        return

    msg = "📦 *List Produk Aktif:*\n━━━━━━━━━━━━━━━━━━━━━━━\n"
    for code, name, price, deskripsi in rows:
        msg += f"• *{name}* (`{code}`): Rp {price:,.0f}\n   └ _{deskripsi}_\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

listproduk_handler = CommandHandler("listproduk", listproduk)

# Handler konfirmasi topup
async def topup_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa konfirmasi.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Format: /topup_confirm <topup_id>")
        return
    topup_id = args[0]
    database.update_topup_status(topup_id, "paid")
    await update.message.reply_text(f"✅ Top up ID `{topup_id}` berhasil dikonfirmasi.", parse_mode="Markdown")

topup_confirm_handler = CommandHandler("topup_confirm", topup_confirm)

# Handler cek user
async def cek_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa cek user.")
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
        await update.message.reply_text("⚠️ User tidak ditemukan.")
        return
    saldo, telegram_id = row
    admin_status = "Ya" if telegram_id in config.ADMIN_TELEGRAM_IDS else "Tidak"
    await update.message.reply_text(
        f"👤 Username: {username}\n💰 Saldo: Rp {saldo}\n🔑 Admin: {admin_status}\n🆔 Telegram ID: {telegram_id}"
    )

cek_user_handler = CommandHandler("cek_user", cek_user)

# Handler jadikan admin
async def jadikan_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menjadikan admin.")
        return
    args = context.args
    telegram_id = args[0] if args else None
    if not telegram_id:
        await update.message.reply_text("Format: /jadikan_admin <telegram_id>")
        return
    database.add_user_admin(telegram_id)
    await update.message.reply_text(f"✅ User dengan telegram_id `{telegram_id}` sudah jadi admin.", parse_mode="Markdown")

jadikan_admin_handler = CommandHandler("jadikan_admin", jadikan_admin)

# Handler menu admin utama
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Menu admin hanya untuk admin.")
        return
    await update.message.reply_text(
        "🛠️ *Menu Admin*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "• /updateproduk - Update produk dari API provider\n"
        "• /listproduk - List produk aktif di database\n"
        "• /topup_confirm <topup_id> - Konfirmasi topup user\n"
        "• /cek_user <username> - Cek info user\n"
        "• /jadikan_admin <telegram_id> - Jadikan user sebagai admin\n"
        "• /broadcast pesan - Broadcast ke semua user\n",
        parse_mode="Markdown"
    )

admin_menu_handler = CommandHandler("admin", admin_menu)
