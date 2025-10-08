import config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
import aiohttp
import aiosqlite
import database
import sqlite3
from datetime import datetime, timedelta
import logging
import os
import shutil

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DB_PATH = "bot_database.db"

EDIT_MENU, CHOOSE_PRODUCT, EDIT_HARGA, EDIT_DESKRIPSI = range(4)

def is_admin(user):
    if not user:
        return False
    return str(user.id) in config.ADMIN_TELEGRAM_IDS

async def ensure_products_table():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                code TEXT PRIMARY KEY,
                name TEXT,
                price REAL,
                status TEXT DEFAULT 'active',
                description TEXT,
                category TEXT,
                provider TEXT,
                gangguan INTEGER DEFAULT 0,
                kosong INTEGER DEFAULT 0,
                stock INTEGER DEFAULT 0,
                updated_at TEXT
            )
        """)
        try:
            await conn.execute("SELECT stock FROM products LIMIT 1")
        except Exception:
            await conn.execute("ALTER TABLE products ADD COLUMN stock INTEGER DEFAULT 0")
        await conn.commit()

async def ensure_topup_requests_table():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS topup_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                username TEXT,
                full_name TEXT,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                proof_image TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        await conn.commit()

async def ensure_admin_logs_table():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action TEXT,
                details TEXT,
                created_at TEXT
            )
        """)
        await conn.commit()

async def log_admin_action(admin_id: int, action: str, details: str = ""):
    try:
        await ensure_admin_logs_table()
        async with aiosqlite.connect(DB_PATH) as conn:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await conn.execute(
                "INSERT INTO admin_logs (admin_id, action, details, created_at) VALUES (?, ?, ?, ?)",
                (admin_id, action, details, now)
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

async def admin_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not is_admin(update.effective_user):
        if update.message:
            await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        elif update.callback_query:
            await update.callback_query.answer("❌ Hanya admin yang bisa menggunakan fitur ini.", show_alert=True)
        return False
    return True

# ============================
# MENU ADMIN UTAMA
# ============================

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update, context):
        return
    keyboard = [
        [InlineKeyboardButton("🔄 Update Produk", callback_data="admin_update")],
        [InlineKeyboardButton("📋 List Produk", callback_data="admin_list_produk")],
        [InlineKeyboardButton("✏️ Edit Produk", callback_data="admin_edit_produk")],
        [InlineKeyboardButton("💳 Kelola Topup", callback_data="admin_topup")],
        [InlineKeyboardButton("👥 Kelola User", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Statistik", callback_data="admin_stats")],
        [InlineKeyboardButton("💾 Backup Database", callback_data="admin_backup")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🏥 System Health", callback_data="admin_health")],
        [InlineKeyboardButton("🧹 Cleanup Data", callback_data="admin_cleanup")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👑 **MENU ADMIN**\n\nSilakan pilih fitur:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await admin_check(update, context):
        return
    data = query.data
    if data == "admin_update":
        await updateproduk(query, context)
    elif data == "admin_list_produk":
        await listproduk(query, context)
    elif data == "admin_edit_produk":
        await edit_produk_start_from_query(query, context)
    elif data == "admin_topup":
        await topup_list(query, context)
    elif data == "admin_users":
        await show_users_menu(query)
    elif data == "admin_stats":
        await show_stats_menu(query, context)
    elif data == "admin_backup":
        await backup_database_from_query(query, context)
    elif data == "admin_broadcast":
        await broadcast_start(query, context)
    elif data == "admin_health":
        await system_health_from_query(query, context)
    elif data == "admin_cleanup":
        await cleanup_data_from_query(query, context)

# ============================
# FITUR UPDATE PRODUK
# ============================

async def updateproduk(update_or_query, context):
    if isinstance(update_or_query, Update):
        msg_func = update_or_query.message.reply_text
        user_id = update_or_query.message.from_user.id
    else:
        msg_func = update_or_query.edit_message_text
        user_id = update_or_query.from_user.id

    await msg_func("🔄 Memperbarui Produk...")
    api_key = config.API_KEY_PROVIDER
    url = f"https://panel.khfy-store.com/api_v2/list_product?api_key={api_key}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as resp:
                resp.raise_for_status()
                data = await resp.json()
    except Exception as e:
        await msg_func(f"❌ Gagal mengambil data: {e}")
        return

    if not data.get("ok", False):
        await msg_func("❌ Response error dari provider.")
        return

    produk_list = data.get("data", [])
    if not produk_list:
        await msg_func("⚠️ Tidak ada data dari provider.")
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
            provider_code = str(prod.get("kode_provider", "")).strip()
            description = str(prod.get("deskripsi", "")).strip() or f"Produk {name}"
            category = "Umum"
            name_lower = name.lower()
            if "pulsa" in name_lower:
                category = "Pulsa"
            elif "data" in name_lower or "internet" in name_lower or "kuota" in name_lower:
                category = "Internet"
            elif "listrik" in name_lower or "pln" in name_lower:
                category = "Listrik"
            elif "game" in name_lower:
                category = "Game"
            elif "emoney" in name_lower or "gopay" in name_lower or "dana" in name_lower:
                category = "E-Money"
            elif "akrab" in name_lower or "bonus" in name_lower:
                category = "Paket Bonus"
            if not code or not name or price <= 0 or gangguan == 1 or kosong == 1:
                continue
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await conn.execute("""
                INSERT INTO products (code, name, price, status, description, category, provider, gangguan, kosong, stock, updated_at)
                VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, 0, ?)
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
            """, (code, name, price, description, category, provider_code, gangguan, kosong, now))
            count += 1
        await conn.commit()
    await log_admin_action(user_id, "UPDATE_PRODUCTS", f"Updated: {count} produk")
    await msg_func(
        f"✅ **Update Produk Berhasil**\n\n"
        f"📊 **Statistik:**\n"
        f"├ Berhasil diupdate: {count} produk\n"
        f"⏰ **Update Terakhir:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
        parse_mode='Markdown'
    )

# ============================
# FITUR LIST PRODUK
# ============================

async def listproduk(update_or_query, context):
    if isinstance(update_or_query, Update):
        msg_func = update_or_query.message.reply_text
    else:
        msg_func = update_or_query.edit_message_text

    await ensure_products_table()
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("""
            SELECT code, name, price, category, status 
            FROM products 
            WHERE status='active' 
            ORDER BY category, name ASC 
            LIMIT 50
        """) as cursor:
            rows = await cursor.fetchall()
    if not rows:
        await msg_func("📭 Tidak ada produk aktif.")
        return
    msg = f"📋 **DAFTAR PRODUK AKTIF**\n\n"
    for code, name, price, category, status in rows:
        msg += f"- `{code}` | {name} | Rp {price:,.0f} | {category}\n"
    await msg_func(msg, parse_mode='Markdown')

# ============================
# FITUR EDIT PRODUK
# ============================

async def edit_produk_start_from_query(query, context):
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Harga Produk", callback_data="edit_harga")],
        [InlineKeyboardButton("📝 Edit Deskripsi Produk", callback_data="edit_deskripsi")],
        [InlineKeyboardButton("⬅️ Kembali ke Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🛠️ **MENU EDIT PRODUK**\n\n"
        "Pilih jenis edit yang ingin dilakukan:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return EDIT_MENU

async def edit_produk_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await admin_check(update, context):
        return ConversationHandler.END
    data = query.data
    context.user_data['edit_type'] = data
    if data in ['edit_harga', 'edit_deskripsi']:
        await ensure_products_table()
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute("""
                SELECT code, name, price 
                FROM products 
                WHERE status='active' 
                ORDER BY name ASC 
                LIMIT 50
            """) as cursor:
                products = await cursor.fetchall()
        if not products:
            await query.edit_message_text("❌ Tidak ada produk yang tersedia untuk diedit.")
            return EDIT_MENU
        keyboard = []
        for code, name, price in products:
            btn_text = f"{name} - Rp {price:,.0f}"
            if len(btn_text) > 50:
                btn_text = f"{name[:30]}... - Rp {price:,.0f}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"select_product:{code}")])
        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_edit_menu")])
        edit_type_text = "harga" if data == "edit_harga" else "deskripsi"
        await query.edit_message_text(
            f"📦 **PILIH PRODUK UNTUK EDIT {edit_type_text.upper()}**\n\nPilih produk dari daftar di bawah:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return CHOOSE_PRODUCT
    elif data == "admin_back":
        await admin_menu_from_query(query, context)
        return ConversationHandler.END
    elif data == "back_to_edit_menu":
        return await edit_produk_start_from_query(query, context)

async def select_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await admin_check(update, context):
        return ConversationHandler.END
    data = query.data
    if data.startswith('select_product:'):
        product_code = data.split(':')[1]
        context.user_data['selected_product'] = product_code
        await ensure_products_table()
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute("""
                SELECT code, name, price, description 
                FROM products 
                WHERE code = ?
            """, (product_code,)) as cursor:
                product = await cursor.fetchone()
        if product:
            code, name, price, description = product
            context.user_data['current_product'] = {
                'code': code,
                'name': name,
                'price': price,
                'description': description
            }
            edit_type = context.user_data.get('edit_type')
            if edit_type == 'edit_harga':
                await log_admin_action(query.from_user.id, "EDIT_HARGA_START", f"Product: {code}")
                await query.edit_message_text(
                    f"💰 **EDIT HARGA PRODUK**\n\n"
                    f"📦 **Produk:** {name}\n"
                    f"📌 **Kode:** {code}\n"
                    f"💰 **Harga Saat Ini:** Rp {price:,.0f}\n\n"
                    f"Silakan kirim harga baru (hanya angka):",
                    parse_mode='Markdown'
                )
                return EDIT_HARGA
            elif edit_type == 'edit_deskripsi':
                await log_admin_action(query.from_user.id, "EDIT_DESKRIPSI_START", f"Product: {code}")
                current_desc = description if description else "Belum ada deskripsi"
                await query.edit_message_text(
                    f"📝 **EDIT DESKRIPSI PRODUK**\n\n"
                    f"📦 **Produk:** {name}\n"
                    f"📌 **Kode:** {code}\n"
                    f"📄 **Deskripsi Saat Ini:**\n{current_desc}\n\n"
                    f"Silakan kirim deskripsi baru:",
                    parse_mode='Markdown'
                )
                return EDIT_DESKRIPSI
    await query.edit_message_text("❌ Terjadi kesalahan. Silakan coba lagi.")
    return EDIT_MENU

async def edit_harga_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update, context):
        return ConversationHandler.END
    try:
        new_price = float(update.message.text.replace(',', '').strip())
        if new_price <= 0:
            await update.message.reply_text("❌ Harga harus lebih dari 0. Silakan coba lagi:")
            return EDIT_HARGA
    except ValueError:
        await update.message.reply_text("❌ Format harga tidak valid. Kirim hanya angka. Silakan coba lagi:")
        return EDIT_HARGA
    product_data = context.user_data.get('current_product')
    if not product_data:
        await update.message.reply_text("❌ Data produk tidak ditemukan. Silakan mulai ulang.")
        return ConversationHandler.END
    product_code = product_data['code']
    product_name = product_data['name']
    old_price = product_data['price']
    await ensure_products_table()
    async with aiosqlite.connect(DB_PATH) as conn:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        await conn.execute("""
            UPDATE products 
            SET price = ?, updated_at = ?
            WHERE code = ?
        """, (new_price, now, product_code))
        await conn.commit()
    await log_admin_action(update.message.from_user.id, "EDIT_HARGA_SUCCESS", f"Product: {product_code}, Old: {old_price}, New: {new_price}")
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Produk Lain", callback_data="back_to_edit_menu")],
        [InlineKeyboardButton("❌ Selesai", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"✅ **HARGA BERHASIL DIUPDATE!**\n\n"
        f"📦 **Produk:** {product_name}\n"
        f"📌 **Kode:** {product_code}\n"
        f"💰 **Harga Lama:** Rp {old_price:,.0f}\n"
        f"💰 **Harga Baru:** Rp {new_price:,.0f}\n\n"
        f"⏰ **Update:** {now}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return EDIT_MENU

async def edit_deskripsi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update, context):
        return ConversationHandler.END
    new_description = update.message.text.strip()
    if not new_description:
        await update.message.reply_text("❌ Deskripsi tidak boleh kosong. Silakan coba lagi:")
        return EDIT_DESKRIPSI
    product_data = context.user_data.get('current_product')
    if not product_data:
        await update.message.reply_text("❌ Data produk tidak ditemukan. Silakan mulai ulang.")
        return ConversationHandler.END
    product_code = product_data['code']
    product_name = product_data['name']
    old_description = product_data['description'] or "Belum ada deskripsi"
    await ensure_products_table()
    async with aiosqlite.connect(DB_PATH) as conn:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        await conn.execute("""
            UPDATE products 
            SET description = ?, updated_at = ?
            WHERE code = ?
        """, (new_description, now, product_code))
        await conn.commit()
    await log_admin_action(update.message.from_user.id, "EDIT_DESKRIPSI_SUCCESS", f"Product: {product_code}")
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Produk Lain", callback_data="back_to_edit_menu")],
        [InlineKeyboardButton("❌ Selesai", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"✅ **DESKRIPSI BERHASIL DIUPDATE!**\n\n"
        f"📦 **Produk:** {product_name}\n"
        f"📌 **Kode:** {product_code}\n\n"
        f"📄 **Deskripsi Lama:**\n{old_description}\n\n"
        f"📄 **Deskripsi Baru:**\n{new_description}\n\n"
        f"⏰ **Update:** {now}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return EDIT_MENU

async def edit_produk_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Proses edit produk dibatalkan.")
    return ConversationHandler.END

async def admin_menu_from_query(query, context):
    await admin_menu(query, context)

# ============================
# REGISTER HANDLERS & EXPORTS
# ============================

edit_produk_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(edit_produk_menu_handler, pattern='^(edit_harga|edit_deskripsi|admin_back|back_to_edit_menu)$')],
    states={
        EDIT_MENU: [CallbackQueryHandler(edit_produk_menu_handler, pattern='^(edit_harga|edit_deskripsi|admin_back|back_to_edit_menu)$')],
        CHOOSE_PRODUCT: [CallbackQueryHandler(select_product_handler, pattern='^select_product:')],
        EDIT_HARGA: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_harga_handler)],
        EDIT_DESKRIPSI: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_deskripsi_handler)],
    },
    fallbacks=[CommandHandler('cancel', edit_produk_cancel)],
    per_message=False
)

admin_menu_handler = CommandHandler("admin", admin_menu)
admin_callback_query_handler = CallbackQueryHandler(admin_callback_handler, pattern=r'^admin_')

def get_admin_handlers():
    return [
        admin_menu_handler,
        admin_callback_query_handler,
        edit_produk_conv_handler,
    ]
