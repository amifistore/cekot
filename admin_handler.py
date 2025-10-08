import config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes, CallbackQueryHandler
import aiohttp
import aiosqlite
import database
import sqlite3
from datetime import datetime

DB_PATH = "bot_topup.db"

def is_admin(user):
    return str(user.id) in config.ADMIN_TELEGRAM_IDS

async def ensure_products_table():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                code TEXT PRIMARY KEY,
                name TEXT,
                price REAL,
                status TEXT,
                description TEXT,
                category TEXT,
                provider TEXT,
                gangguan INTEGER DEFAULT 0,
                kosong INTEGER DEFAULT 0,
                updated_at TEXT
            )
        """)
        await conn.commit()

# Handler untuk update produk
async def updateproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return

    await update.message.reply_text("🔄 Memperbarui Produk...")

    api_key = config.API_KEY_PROVIDER
    url = f"https://panel.khfy-store.com/api_v2/list_product?api_key={api_key}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as resp:
                resp.raise_for_status()
                data = await resp.json()
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal mengambil data: {e}")
        return

    if not data.get("ok", False):
        await update.message.reply_text("❌ Response error dari provider.")
        return

    produk_list = data.get("data", [])
    
    if not produk_list:
        await update.message.reply_text("⚠️ Tidak ada data dari provider.")
        return

    await ensure_products_table()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE products SET status = 'inactive'")
        
        count = 0
        for prod in produk_list:
            code = str(prod.get("kode_produk", "")).strip()
            name = str(prod.get("nama_produk", "")).strip()
            price = float(prod.get("harga_final", 0))
            gangguan = int(prod.get("gangguan", 0))
            kosong = int(prod.get("kosong", 0))
            
            if not code or not name or price <= 0 or gangguan == 1 or kosong == 1:
                continue
                
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await conn.execute("""
                INSERT INTO products (code, name, price, status, description, category, provider, gangguan, kosong, updated_at)
                VALUES (?, ?, ?, 'active', ?, 'Umum', ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name=excluded.name,
                    price=excluded.price,
                    status='active',
                    description=excluded.description,
                    category=excluded.category,
                    provider=excluded.provider,
                    gangguan=excluded.gangguan,
                    kosong=excluded.kosong,
                    updated_at=excluded.updated_at
            """, (code, name, price, f"Produk {name}", "Provider", gangguan, kosong, now))
            count += 1
        
        await conn.commit()

    msg = (
        f"✅ **Update Produk Berhasil**\n\n"
        f"📊 **Statistik:**\n"
        f"├ Total dari Provider: {len(produk_list)} produk\n"
        f"└ Berhasil diupdate: {count} produk\n\n"
        f"⏰ **Update Terakhir:** {datetime.now().strftime('%d-%m-%Y %H:%M')}"
    )
    
    await update.message.reply_text(msg, parse_mode='Markdown')

# Handler untuk list produk
async def listproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return

    await ensure_products_table()
    
    page = int(context.args[0]) if context.args and context.args[0].isdigit() else 1
    limit = 20
    offset = (page - 1) * limit

    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
            total_count = (await cursor.fetchone())[0]
        
        async with conn.execute("""
            SELECT code, name, price, description, category, provider, gangguan, kosong 
            FROM products 
            WHERE status='active' 
            ORDER BY name ASC 
            LIMIT ? OFFSET ?
        """, (limit, offset)) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await update.message.reply_text("📭 Database produk kosong.")
        return

    total_pages = (total_count + limit - 1) // limit
    
    msg = f"📋 **DAFTAR PRODUK AKTIF**\n\n"
    msg += f"📊 **Halaman {page} dari {total_pages}**\n"
    msg += f"📈 **Total Produk:** {total_count} produk\n\n"

    for code, name, price, description, category, provider, gangguan, kosong in rows:
        status_emoji = "✅" if gangguan == 0 and kosong == 0 else "⚠️"
        msg += f"{status_emoji} **{name}**\n"
        msg += f"   Kode: `{code}`\n"
        msg += f"   Harga: Rp {price:,.0f}\n"
        msg += f"   Kategori: {category}\n\n"

    if total_pages > 1:
        msg += f"\n**Navigasi:** `/listproduk <nomor_halaman>`"

    await update.message.reply_text(msg, parse_mode='Markdown')

# Handler menu admin utama
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Menu admin hanya untuk admin.")
        return
    
    await ensure_products_table()
    
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
                active_products = (await cursor.fetchone())[0]
    except Exception as e:
        active_products = 0

    keyboard = [
        [InlineKeyboardButton("🔄 Update Produk", callback_data="admin_update")],
        [InlineKeyboardButton("📋 List Produk", callback_data="admin_list")],
        [InlineKeyboardButton("📊 Statistik", callback_data="admin_stats")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👑 **MENU ADMIN**\n\n"
        f"📦 **Produk Aktif:** {active_products}\n"
        f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}\n\n"
        f"Pilih menu di bawah:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Handler untuk callback queries
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user = query.from_user

    if not is_admin(user):
        await query.edit_message_text("❌ Tidak memiliki akses admin.")
        return

    if data == "admin_update":
        await update_produk_from_menu(query, context)
    elif data == "admin_list":
        await list_produk_from_menu(query, context)
    elif data == "admin_stats":
        await show_stats_menu(query, context)
    elif data == "admin_back":
        await admin_menu_back(query, context)

async def update_produk_from_menu(query, context):
    await query.edit_message_text("🔄 Memperbarui produk...")
    
    try:
        api_key = config.API_KEY_PROVIDER
        url = f"https://panel.khfy-store.com/api_v2/list_product?api_key={api_key}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as resp:
                resp.raise_for_status()
                data = await resp.json()

        if not data.get("ok", False):
            await query.edit_message_text("❌ Gagal mengambil data dari provider.")
            return

        produk_list = data.get("data", [])
        
        if not produk_list:
            await query.edit_message_text("⚠️ Tidak ada data dari provider.")
            return

        await ensure_products_table()
        
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute("UPDATE products SET status = 'inactive'")
            
            count = 0
            for prod in produk_list:
                code = str(prod.get("kode_produk", "")).strip()
                name = str(prod.get("nama_produk", "")).strip()
                price = float(prod.get("harga_final", 0))
                gangguan = int(prod.get("gangguan", 0))
                kosong = int(prod.get("kosong", 0))
                
                if not code or not name or price <= 0 or gangguan == 1 or kosong == 1:
                    continue
                    
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                await conn.execute("""
                    INSERT INTO products (code, name, price, status, description, category, provider, gangguan, kosong, updated_at)
                    VALUES (?, ?, ?, 'active', ?, 'Umum', ?, ?, ?, ?)
                    ON CONFLICT(code) DO UPDATE SET
                        name=excluded.name,
                        price=excluded.price,
                        status='active',
                        description=excluded.description,
                        category=excluded.category,
                        provider=excluded.provider,
                        gangguan=excluded.gangguan,
                        kosong=excluded.kosong,
                        updated_at=excluded.updated_at
                """, (code, name, price, f"Produk {name}", "Provider", gangguan, kosong, now))
                count += 1
            
            await conn.commit()

        keyboard = [
            [InlineKeyboardButton("📋 Lihat Produk", callback_data="admin_list")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"✅ **Update Berhasil!**\n\n"
            f"📊 **Statistik:**\n"
            f"├ Dari Provider: {len(produk_list)} produk\n"
            f"└ Berhasil diupdate: {count} produk\n\n"
            f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    except Exception as e:
        await query.edit_message_text(f"❌ Error: {str(e)}")

async def list_produk_from_menu(query, context):
    await ensure_products_table()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
            total_count = (await cursor.fetchone())[0]
        
        async with conn.execute("""
            SELECT code, name, price, category 
            FROM products 
            WHERE status='active' 
            ORDER BY name ASC 
            LIMIT 10
        """) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await query.edit_message_text("📭 Tidak ada produk yang tersedia.")
        return

    msg = f"📋 **PRODUK AKTIF**\n\n"
    msg += f"📈 **Total:** {total_count} produk\n\n"

    for code, name, price, category in rows:
        msg += f"• **{name}**\n"
        msg += f"  Kode: `{code}`\n"
        msg += f"  Harga: Rp {price:,.0f}\n"
        msg += f"  Kategori: {category}\n\n"

    keyboard = [
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

async def show_stats_menu(query, context):
    await ensure_products_table()
    
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
                total_products = (await cursor.fetchone())[0]
            async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active' AND gangguan = 0 AND kosong = 0") as cursor:
                available_products = (await cursor.fetchone())[0]
    except Exception as e:
        total_products = available_products = 0

    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_stats")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📊 **STATISTIK SISTEM**\n\n"
        f"📦 **PRODUK:**\n"
        f"├ Total Produk: {total_products}\n"
        f"└ Tersedia: {available_products}\n\n"
        f"⏰ **Update:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def admin_menu_back(query, context):
    await admin_menu_from_query(query, context)

async def admin_menu_from_query(query, context):
    user = query.from_user
    
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
                active_products = (await cursor.fetchone())[0]
    except Exception as e:
        active_products = 0

    keyboard = [
        [InlineKeyboardButton("🔄 Update Produk", callback_data="admin_update")],
        [InlineKeyboardButton("📋 List Produk", callback_data="admin_list")],
        [InlineKeyboardButton("📊 Statistik", callback_data="admin_stats")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"👑 **MENU ADMIN**\n\n"
        f"📦 **Produk Aktif:** {active_products}\n"
        f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}\n\n"
        f"Pilih menu di bawah:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Handler konfirmasi topup
async def topup_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Format: `/topup_confirm <request_id>`")
        return
    
    request_id = args[0]
    
    try:
        database.update_topup_status(request_id, "paid")
        await update.message.reply_text(f"✅ Topup ID {request_id} berhasil dikonfirmasi.")
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal konfirmasi: {e}")

# Handler cek user
async def cek_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return
    
    args = context.args
    username = args[0] if args else None
    
    if not username:
        await update.message.reply_text("❌ Format: `/cek_user <username>`")
        return
    
    conn = sqlite3.connect(database.DB_PATH)
    c = conn.cursor()
    c.execute("SELECT saldo, telegram_id FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        await update.message.reply_text(f"❌ User tidak ditemukan: `{username}`")
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

# Handler jadikan admin
async def jadikan_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return
    
    args = context.args
    telegram_id = args[0] if args else None
    
    if not telegram_id:
        await update.message.reply_text("❌ Format: `/jadikan_admin <telegram_id>`")
        return
    
    try:
        database.add_user_admin(telegram_id)
        await update.message.reply_text(
            f"✅ **Admin Berhasil Ditambahkan**\n\n"
            f"**Telegram ID:** `{telegram_id}`",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ **Gagal Menambahkan Admin**\n\n"
            f"**Error:** `{e}`",
            parse_mode='Markdown'
        )

# Define handlers
admin_menu_handler = CommandHandler("admin", admin_menu)
updateproduk_handler = CommandHandler("updateproduk", updateproduk)
listproduk_handler = CommandHandler("listproduk", listproduk)
topup_confirm_handler = CommandHandler("topup_confirm", topup_confirm)
cek_user_handler = CommandHandler("cek_user", cek_user)
jadikan_admin_handler = CommandHandler("jadikan_admin", jadikan_admin)
admin_callback_handler = CallbackQueryHandler(callback_handler)
