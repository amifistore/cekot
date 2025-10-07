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

# Handler untuk update produk dari API ke database
async def updateproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text(
            "❌ **Akses Ditolak**\n\n"
            "Hanya admin yang dapat menggunakan perintah ini.",
            parse_mode='Markdown'
        )
        return

    await update.message.reply_text("🔄 **Memperbarui Produk...**\n\nSedang mengambil data dari provider...")

    api_key = config.API_KEY_PROVIDER
    url = f"https://panel.khfy-store.com/api_v2/list_product?api_key={api_key}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as resp:
                resp.raise_for_status()
                data = await resp.json()
    except Exception as e:
        await update.message.reply_text(
            f"❌ **Gagal Mengambil Data**\n\n"
            f"Error: `{e}`\n\n"
            "Pastikan koneksi internet stabil dan API key valid.",
            parse_mode='Markdown'
        )
        return

    produk_list = data.get("data", [])
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
        for prod in produk_list:
            # GUNAKAN FIELD SESUAI DATA JSON PROVIDER
            code = str(prod.get("kode_produk", "")).strip()
            name = str(prod.get("nama_produk", "")).strip()
            price = float(prod.get("harga_final", 0))
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
        async with conn.execute("SELECT code, name, price FROM products WHERE status='active' ORDER BY name ASC LIMIT 5") as cursor:
            data_preview = await cursor.fetchall()
    
    if count == 0:
        await update.message.reply_text(
            "⚠️ **Tidak Ada Produk Diupdate**\n\n"
            "Tidak ada produk aktif yang berhasil diambil dari provider.",
            parse_mode='Markdown'
        )
    else:
        msg = (
            f"✅ **Produk Berhasil Diperbarui**\n\n"
            f"📊 **Total Produk Aktif:** {count} produk\n\n"
            "📦 **Contoh Produk:**\n"
        )
        for code, name, price in data_preview:
            msg += f"• **{name}**\n  `{code}` - Rp {price:,.0f}\n"
        
        msg += f"\n⏰ **Update Terakhir:** {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        
        await update.message.reply_text(msg, parse_mode='Markdown')

updateproduk_handler = CommandHandler("updateproduk", updateproduk)

# Handler untuk list produk dari database
async def listproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text(
            "❌ **Akses Ditolak**\n\n"
            "Hanya admin yang dapat menggunakan perintah ini.",
            parse_mode='Markdown'
        )
        return

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
        async with conn.execute("SELECT code, name, price FROM products WHERE status='active' ORDER BY name ASC LIMIT 30") as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await update.message.reply_text(
            "📭 **Database Produk Kosong**\n\n"
            "Belum ada produk yang tersedia. Gunakan `/updateproduk` untuk mengimpor produk.",
            parse_mode='Markdown'
        )
        return

    msg = "📋 **DAFTAR PRODUK AKTIF**\n\n"
    for code, name, price in rows:
        msg += f"🎯 **{name}**\n"
        msg += f"   📌 Kode: `{code}`\n"
        msg += f"   💰 Harga: Rp {price:,.0f}\n\n"
    
    msg += f"📊 **Total:** {len(rows)} produk aktif"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

listproduk_handler = CommandHandler("listproduk", listproduk)

# Handler untuk konfirmasi topup
async def topup_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text(
            "❌ **Akses Ditolak**\n\n"
            "Hanya admin yang dapat menggunakan perintah ini.",
            parse_mode='Markdown'
        )
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ **Format Salah**\n\n"
            "**Penggunaan:**\n"
            "`/topup_confirm <topup_id>`\n\n"
            "**Contoh:**\n"
            "`/topup_confirm topup_123456`",
            parse_mode='Markdown'
        )
        return
    
    topup_id = args[0]
    
    try:
        database.update_topup_status(topup_id, "paid")
        await update.message.reply_text(
            f"✅ **Topup Dikonfirmasi**\n\n"
            f"**ID Topup:** `{topup_id}`\n"
            f"**Status:** Berhasil dikonfirmasi sebagai PAID",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ **Gagal Konfirmasi**\n\n"
            f"**ID Topup:** `{topup_id}`\n"
            f"**Error:** `{e}`",
            parse_mode='Markdown'
        )

topup_confirm_handler = CommandHandler("topup_confirm", topup_confirm)

# Handler cek user
async def cek_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text(
            "❌ **Akses Ditolak**\n\n"
            "Hanya admin yang dapat menggunakan perintah ini.",
            parse_mode='Markdown'
        )
        return
    
    args = context.args
    username = args[0] if args else None
    
    if not username:
        await update.message.reply_text(
            "❌ **Format Salah**\n\n"
            "**Penggunaan:**\n"
            "`/cek_user <username>`\n\n"
            "**Contoh:**\n"
            "`/cek_user johndoe`",
            parse_mode='Markdown'
        )
        return
    
    conn = sqlite3.connect(database.DB_PATH)
    c = conn.cursor()
    c.execute("SELECT saldo, telegram_id FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        await update.message.reply_text(
            f"❌ **User Tidak Ditemukan**\n\n"
            f"Username: `{username}`\n"
            f"User tidak terdaftar dalam database.",
            parse_mode='Markdown'
        )
        return
    
    saldo, telegram_id = row
    admin_status = "✅ Ya" if str(telegram_id) in config.ADMIN_TELEGRAM_IDS else "❌ Tidak"
    
    await update.message.reply_text(
        f"👤 **INFORMASI USER**\n\n"
        f"📛 **Username:** `{username}`\n"
        f"💰 **Saldo:** Rp {saldo:,.0f}\n"
        f"🆔 **Telegram ID:** `{telegram_id}`\n"
        f"👑 **Status Admin:** {admin_status}",
        parse_mode='Markdown'
    )

cek_user_handler = CommandHandler("cek_user", cek_user)

# Handler jadikan admin
async def jadikan_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text(
            "❌ **Akses Ditolak**\n\n"
            "Hanya admin yang dapat menggunakan perintah ini.",
            parse_mode='Markdown'
        )
        return
    
    args = context.args
    telegram_id = args[0] if args else None
    
    if not telegram_id:
        await update.message.reply_text(
            "❌ **Format Salah**\n\n"
            "**Penggunaan:**\n"
            "`/jadikan_admin <telegram_id>`\n\n"
            "**Contoh:**\n"
            "`/jadikan_admin 123456789`",
            parse_mode='Markdown'
        )
        return
    
    try:
        database.add_user_admin(telegram_id)
        await update.message.reply_text(
            f"✅ **Admin Berhasil Ditambahkan**\n\n"
            f"**Telegram ID:** `{telegram_id}`\n"
            f"**Status:** Sekarang memiliki akses admin",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ **Gagal Menambahkan Admin**\n\n"
            f"**Telegram ID:** `{telegram_id}`\n"
            f"**Error:** `{e}`",
            parse_mode='Markdown'
        )

jadikan_admin_handler = CommandHandler("jadikan_admin", jadikan_admin)

# Handler menu admin utama
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text(
            "❌ **Akses Ditolak**\n\n"
            "Menu admin hanya untuk pengguna dengan hak akses admin.",
            parse_mode='Markdown'
        )
        return
    
    await update.message.reply_text(
        "👑 **MENU ADMIN**\n\n"
        "📦 **Manajemen Produk:**\n"
        "`/updateproduk` - Update produk dari API provider\n"
        "`/listproduk` - List produk aktif di database\n\n"
        "💳 **Manajemen Transaksi:**\n"
        "`/topup_confirm <topup_id>` - Konfirmasi topup user\n\n"
        "👥 **Manajemen User:**\n"
        "`/cek_user <username>` - Cek info user\n"
        "`/jadikan_admin <telegram_id>` - Jadikan user sebagai admin\n\n"
        "📢 **Broadcast:**\n"
        "`/broadcast pesan` - Broadcast ke semua user\n\n"
        "⏰ **Update Terakhir:** " + datetime.now().strftime('%d-%m-%Y %H:%M'),
        parse_mode='Markdown'
    )

admin_menu_handler = CommandHandler("admin", admin_menu)
