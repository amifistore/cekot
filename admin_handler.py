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

def get_user_from_update(update):
    # Robust admin user extraction for both Update and CallbackQuery
    if hasattr(update, "effective_user"):
        return update.effective_user
    elif hasattr(update, "from_user"):
        return update.from_user
    elif hasattr(update, "callback_query") and hasattr(update.callback_query, "from_user"):
        return update.callback_query.from_user
    elif hasattr(update, "message") and hasattr(update.message, "from_user"):
        return update.message.from_user
    return None

async def admin_check(update, context) -> bool:
    user = get_user_from_update(update)
    if not is_admin(user):
        if getattr(update, "message", None):
            await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        elif getattr(update, "callback_query", None):
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
    if getattr(update, "message", None):
        await update.message.reply_text(
            "👑 **MENU ADMIN**\n\nSilakan pilih fitur:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    elif getattr(update, "callback_query", None):
        try:
            await update.callback_query.edit_message_text(
                "👑 **MENU ADMIN**\n\nSilakan pilih fitur:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Menu admin edit message text failed: {e}")

async def admin_menu_from_query(query, context):
    class FakeUpdate:
        def __init__(self, callback_query):
            self.callback_query = callback_query
            self.message = None
    await admin_menu(FakeUpdate(query), context)

# Handler khusus untuk menu_admin callback
async def admin_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await admin_menu(update, context)

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

async def updateproduk(update_or_query, context):
    if hasattr(update_or_query, "message") and update_or_query.message:
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
    if hasattr(update_or_query, "message") and update_or_query.message:
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

# ============================
# FITUR KELOLA TOPUP
# ============================

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

async def topup_list(update_or_query, context):
    if hasattr(update_or_query, "message") and update_or_query.message:
        msg_func = update_or_query.message.reply_text
    else:
        msg_func = update_or_query.edit_message_text
    await ensure_topup_requests_table()
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("""
            SELECT id, user_id, username, full_name, amount, status, created_at 
            FROM topup_requests 
            ORDER BY created_at DESC LIMIT 20
        """) as cursor:
            rows = await cursor.fetchall()
    if not rows:
        await msg_func("📭 Tidak ada permintaan topup.")
        return
    msg = f"💳 **DAFTAR PERMINTAAN TOPUP (20 terbaru):**\n\n"
    for req_id, user_id, username, full_name, amount, status, created_at in rows:
        status_emoji = "⏳" if status == 'pending' else "✅" if status == 'approved' else "❌"
        msg += f"{status_emoji} ID:`{req_id}` User:{full_name or username or user_id} Jumlah:Rp{amount:,.0f} Status:{status} Waktu:{created_at}\n"
    await msg_func(msg, parse_mode='Markdown')

# ============================
# FITUR KELOLA USER
# ============================

async def show_users_menu(query):
    keyboard = [
        [InlineKeyboardButton("Cek User", callback_data="cek_user")],
        [InlineKeyboardButton("Jadikan Admin", callback_data="jadikan_admin")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "👥 **MENU USER ADMIN**\n\nGunakan perintah:\n`/cek_user <username>` untuk cek saldo user.\n`/jadikan_admin <telegram_id>` untuk jadikan admin.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def cek_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    username = args[0] if args else None
    if not username:
        await update.message.reply_text("❌ Format: `/cek_user <username>`")
        return
    conn = sqlite3.connect(DB_PATH)
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

async def jadikan_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    telegram_id = args[0] if args else None
    if not telegram_id:
        await update.message.reply_text("❌ Format: `/jadikan_admin <telegram_id>`")
        return
    config.ADMIN_TELEGRAM_IDS.append(str(telegram_id))
    await update.message.reply_text(
        f"✅ **Admin Berhasil Ditambahkan**\n\n"
        f"**Telegram ID:** `{telegram_id}`",
        parse_mode='Markdown'
    )

# ============================
# FITUR STATISTIK
# ============================

async def show_stats_menu(query, context):
    await ensure_products_table()
    await ensure_topup_requests_table()
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
            total_products = (await cursor.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active' AND gangguan = 0 AND kosong = 0") as cursor:
            available_products = (await cursor.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM topup_requests WHERE status='pending'") as cursor:
            pending_topups = (await cursor.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM topup_requests WHERE status='approved'") as cursor:
            approved_topups = (await cursor.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM topup_requests") as cursor:
            total_topups = (await cursor.fetchone())[0]
    await query.edit_message_text(
        f"📊 **STATISTIK SISTEM**\n\n"
        f"📦 **PRODUK:**\n"
        f"├ Total Produk: {total_products}\n"
        f"└ Tersedia: {available_products}\n\n"
        f"💳 **TOPUP:**\n"
        f"├ Total: {total_topups}\n"
        f"├ Pending: {pending_topups}\n"
        f"└ Approved: {approved_topups}\n\n"
        f"⏰ **Update:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
        parse_mode='Markdown'
    )

# ============================
# FITUR BROADCAST
# ============================

async def broadcast_start(query, context):
    await query.edit_message_text(
        "📢 Kirim pesan broadcast ke semua user.\n\nFormat: /broadcast <pesan>",
        parse_mode='Markdown'
    )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Format: /broadcast <pesan>")
        return
    message = " ".join(context.args)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users")
    users = c.fetchall()
    conn.close()
    success_count, fail_count = 0, 0
    for (user_id,) in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 **BROADCAST FROM ADMIN**\n\n{message}",
                parse_mode='Markdown'
            )
            success_count += 1
        except Exception:
            fail_count += 1
    await update.message.reply_text(
        f"✅ **Broadcast Selesai**\n\n"
        f"Berhasil: {success_count}, Gagal: {fail_count}, Total: {success_count+fail_count}",
        parse_mode='Markdown'
    )

# ============================
# FITUR BACKUP DATABASE
# ============================

async def backup_database_from_query(query, context):
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"backup_{timestamp}.db"
        shutil.copy2(DB_PATH, backup_file)
        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=open(backup_file, 'rb'),
            filename=backup_file,
            caption=f"📦 Backup database berhasil\n🕒 {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        )
        os.remove(backup_file)
    except Exception as e:
        await query.edit_message_text(f"❌ Gagal backup: {str(e)}")

# ============================
# FITUR SYSTEM HEALTH
# ============================

async def system_health_from_query(query, context):
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute("SELECT 1")
            db_status = "✅ Connected"
        api_key = config.API_KEY_PROVIDER
        url = f"https://panel.khfy-store.com/api_v2/list_product?api_key={api_key}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    api_status = "✅ Connected" if resp.status == 200 else "❌ Disconnected"
        except:
            api_status = "❌ Disconnected"
        stat = shutil.disk_usage(".")
        free_gb = stat.free / (1024**3)
        disk_status = f"✅ {free_gb:.1f} GB free"
        await query.edit_message_text(
            f"🏥 **SYSTEM HEALTH CHECK**\n\n"
            f"📦 Database: {db_status}\n"
            f"🌐 API Provider: {api_status}\n"
            f"💾 Disk Space: {disk_status}\n"
            f"🕒 Check Time: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}",
            parse_mode='Markdown'
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Health check failed: {str(e)}")

# ============================
# FITUR CLEANUP DATA
# ============================

async def cleanup_data_from_query(query, context):
    try:
        cutoff_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute(
                "DELETE FROM topup_requests WHERE status='rejected' AND created_at < ?",
                (cutoff_date,)
            )
            rejected_deleted = cursor.rowcount
            cursor = await conn.execute(
                "DELETE FROM admin_logs WHERE created_at < ?",
                (cutoff_date,)
            )
            logs_deleted = cursor.rowcount
            await conn.commit()
        await query.edit_message_text(
            f"🧹 **Cleanup Data Berhasil**\n\n"
            f"📊 **Data yang dihapus:**\n"
            f"├ Topup rejected: {rejected_deleted}\n"
            f"└ Logs admin: {logs_deleted}\n\n"
            f"⏰ **Cutoff date:** {cutoff_date}",
            parse_mode='Markdown'
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Gagal cleanup: {str(e)}")

# ============================
# HANDLER UNTUK KEMBALI KE MENU ADMIN
# ============================

# ============================
# FIX UNTUK INTEGRASI DENGAN BOT.PY
# ============================

async def admin_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "admin_back":
        await admin_menu(update, context)
    return ConversationHandler.END

# Handler untuk broadcast start
async def broadcast_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update, context):
        return
    await update.message.reply_text(
        "📢 **BROADCAST MESSAGE**\n\n"
        "Kirim pesan broadcast dalam format:\n"
        "`/broadcast <pesan anda>`\n\n"
        "Contoh:\n"
        "`/broadcast Hai semua! Ini pesan broadcast dari admin.`",
        parse_mode='Markdown'
    )

# ============================
# REGISTER HANDLERS & EXPORTS - YANG DIPERBAIKI
# ============================

admin_menu_handler = CommandHandler("admin", admin_menu)
admin_callback_query_handler = CallbackQueryHandler(admin_callback_handler, pattern=r'^admin_')
admin_menu_callback_handler = CallbackQueryHandler(admin_menu_callback_handler, pattern=r'^menu_admin$')
admin_back_handler_callback = CallbackQueryHandler(admin_back_handler, pattern=r'^admin_back$')
broadcast_handler = CommandHandler("broadcast", broadcast)
broadcast_start_handler_cmd = CommandHandler("broadcast_start", broadcast_start_handler)
cek_user_handler = CommandHandler("cek_user", cek_user)
jadikan_admin_handler = CommandHandler("jadikan_admin", jadikan_admin)
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
topup_list_handler = CommandHandler("topup_list", topup_list)

def get_admin_handlers():
    return [
        admin_menu_handler,
        admin_callback_query_handler,
        admin_menu_callback_handler,
        admin_back_handler_callback,
        edit_produk_conv_handler,
        broadcast_handler,
        broadcast_start_handler_cmd,
        cek_user_handler,
        jadikan_admin_handler,
        topup_list_handler,
    ]

# ============================
# LOGGING ADMIN ACTIONS
# ============================

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
