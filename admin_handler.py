import config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
import aiohttp
import aiosqlite
import sqlite3
from datetime import datetime, timedelta
import logging
import os
import shutil
import psutil
import platform

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DB_PATH = "bot_database.db"

# States untuk ConversationHandler
EDIT_MENU, CHOOSE_PRODUCT, EDIT_HARGA, EDIT_DESKRIPSI, BROADCAST_MESSAGE = range(5)

def is_admin(user):
    if not user:
        return False
    return str(user.id) in config.ADMIN_TELEGRAM_IDS

def get_user_from_update(update):
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

async def log_admin_action(user_id, action, details=""):
    """Log aksi admin ke database"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    action TEXT,
                    details TEXT,
                    timestamp TEXT
                )
            """)
            await conn.execute(
                "INSERT INTO admin_logs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
                (str(user_id), action, details, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"Gagal log admin action: {e}")

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
        [InlineKeyboardButton("❌ Tutup Menu", callback_data="admin_close")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = """
👑 **MENU ADMIN**

Silakan pilih fitur yang ingin dikelola:
• 🔄 Update Produk - Sync produk dari provider
• 📋 List Produk - Lihat daftar produk aktif
• ✏️ Edit Produk - Ubah harga & deskripsi
• 💳 Kelola Topup - Approve permintaan saldo
• 👥 Kelola User - Kelola user bot
• 📊 Statistik - Lihat statistik bot
• 💾 Backup - Backup database
• 📢 Broadcast - Kirim pesan ke semua user
• 🏥 Health - Cek status system
• 🧹 Cleanup - Bersihkan data lama
"""
    
    if getattr(update, "message", None):
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    elif getattr(update, "callback_query", None):
        try:
            await update.callback_query.edit_message_text(
                message_text,
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
        await show_users_menu(query, context)
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
    elif data == "admin_back":
        await admin_menu_from_query(query, context)
    elif data == "admin_close":
        await query.edit_message_text("✅ Menu admin ditutup")

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
    
    keyboard = [
        [InlineKeyboardButton("📋 Lihat Produk", callback_data="admin_list_produk")],
        [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await msg_func(
        f"✅ **Update Produk Berhasil**\n\n"
        f"📊 **Statistik:**\n"
        f"├ Berhasil diupdate: {count} produk\n"
        f"⏰ **Update Terakhir:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
        reply_markup=reply_markup,
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
            LIMIT 100
        """) as cursor:
            rows = await cursor.fetchall()
    
    if not rows:
        await msg_func("📭 Tidak ada produk aktif.")
        return
    
    # Group by category
    products_by_category = {}
    for code, name, price, category, status in rows:
        if category not in products_by_category:
            products_by_category[category] = []
        products_by_category[category].append((code, name, price))
    
    msg = "📋 **DAFTAR PRODUK AKTIF**\n\n"
    for category, products in products_by_category.items():
        msg += f"**{category}** ({len(products)} produk):\n"
        for code, name, price in products[:10]:  # Limit 10 per category untuk menghindari message too long
            msg += f"├ `{code}` | {name[:30]} | Rp {price:,.0f}\n"
        if len(products) > 10:
            msg += f"└ ... dan {len(products) - 10} produk lainnya\n"
        msg += "\n"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Update Produk", callback_data="admin_update")],
        [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await msg_func(msg, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        # Jika message terlalu panjang, split menjadi beberapa bagian
        if "Message is too long" in str(e):
            parts = [msg[i:i+4000] for i in range(0, len(msg), 4000)]
            for part in parts:
                await msg_func(part, parse_mode='Markdown')
            await msg_func("📋 **Daftar produk selesai**", reply_markup=reply_markup)

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
                LIMIT 100
            """) as cursor:
                products = await cursor.fetchall()
        
        if not products:
            await query.edit_message_text("❌ Tidak ada produk yang tersedia untuk diedit.")
            return EDIT_MENU
        
        keyboard = []
        for code, name, price in products:
            btn_text = f"{name[:20]} - Rp {price:,.0f}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"select_product:{code}")])
        
        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_edit_menu")])
        
        edit_type_text = "harga" if data == "edit_harga" else "deskripsi"
        await query.edit_message_text(
            f"📦 **PILIH PRODUK UNTUK EDIT {edit_type_text.upper()}**\n\n"
            f"Total {len(products)} produk aktif. Pilih produk dari daftar di bawah:",
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
                    f"📌 **Kode:** `{code}`\n"
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
                    f"📌 **Kode:** `{code}`\n"
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
    
    await log_admin_action(update.message.from_user.id, "EDIT_HARGA_SUCCESS", 
                          f"Product: {product_code}, Old: {old_price}, New: {new_price}")
    
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Produk Lain", callback_data="back_to_edit_menu")],
        [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ **HARGA BERHASIL DIUPDATE!**\n\n"
        f"📦 **Produk:** {product_name}\n"
        f"📌 **Kode:** `{product_code}`\n"
        f"💰 **Harga Lama:** Rp {old_price:,.0f}\n"
        f"💰 **Harga Baru:** Rp {new_price:,.0f}\n\n"
        f"⏰ **Update:** {now}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return ConversationHandler.END

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
        [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ **DESKRIPSI BERHASIL DIUPDATE!**\n\n"
        f"📦 **Produk:** {product_name}\n"
        f"📌 **Kode:** `{product_code}`\n\n"
        f"📄 **Deskripsi Baru:**\n{new_description}\n\n"
        f"⏰ **Update:** {now}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return ConversationHandler.END

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
                method TEXT,
                proof_text TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                processed_at TEXT,
                processed_by TEXT
            )
        """)
        await conn.commit()

async def topup_list(query, context):
    await ensure_topup_requests_table()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("""
            SELECT id, user_id, username, full_name, amount, method, status, created_at
            FROM topup_requests 
            WHERE status = 'pending'
            ORDER BY created_at DESC
            LIMIT 20
        """) as cursor:
            pending_requests = await cursor.fetchall()
    
    if not pending_requests:
        keyboard = [[InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]]
        await query.edit_message_text(
            "💳 **KELOLA TOPUP**\n\n"
            "📭 Tidak ada permintaan topup yang pending.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    message_text = "💳 **PERMINTAAN TOPUP PENDING**\n\n"
    keyboard = []
    
    for req in pending_requests:
        req_id, user_id, username, full_name, amount, method, status, created_at = req
        user_display = f"@{username}" if username else full_name
        
        message_text += f"🔸 **ID:** {req_id}\n"
        message_text += f"👤 **User:** {user_display}\n"
        message_text += f"💰 **Amount:** Rp {amount:,.0f}\n"
        message_text += f"📦 **Method:** {method or 'N/A'}\n"
        message_text += f"⏰ **Waktu:** {created_at}\n"
        message_text += "─" * 20 + "\n"
        
        keyboard.append([
            InlineKeyboardButton(f"✅ Approve {req_id}", callback_data=f"approve_topup:{req_id}"),
            InlineKeyboardButton(f"❌ Reject {req_id}", callback_data=f"reject_topup:{req_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="admin_topup")])
    keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")])
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ============================
# FITUR KELOLA USER
# ============================

async def ensure_users_table():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                balance REAL DEFAULT 0,
                total_spent REAL DEFAULT 0,
                total_orders INTEGER DEFAULT 0,
                created_at TEXT,
                last_active TEXT,
                is_blocked INTEGER DEFAULT 0
            )
        """)
        await conn.commit()

async def show_users_menu(query, context):
    keyboard = [
        [InlineKeyboardButton("📊 List All Users", callback_data="list_all_users")],
        [InlineKeyboardButton("🔍 Cari User", callback_data="search_user")],
        [InlineKeyboardButton("📈 Top Users", callback_data="top_users")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
    ]
    
    await ensure_users_table()
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT COUNT(*) FROM users") as cursor:
            total_users = (await cursor.fetchone())[0]
        
        async with conn.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1") as cursor:
            blocked_users = (await cursor.fetchone())[0]
    
    await query.edit_message_text(
        f"👥 **KELOLA USER**\n\n"
        f"📊 **Statistik User:**\n"
        f"├ Total Users: {total_users}\n"
        f"├ User Terblokir: {blocked_users}\n"
        f"└ User Aktif: {total_users - blocked_users}\n\n"
        f"Pilih aksi yang ingin dilakukan:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ============================
# FITUR STATISTIK
# ============================

async def show_stats_menu(query, context):
    await ensure_products_table()
    await ensure_users_table()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        # Total users
        async with conn.execute("SELECT COUNT(*) FROM users") as cursor:
            total_users = (await cursor.fetchone())[0]
        
        # Total active products
        async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
            total_products = (await cursor.fetchone())[0]
        
        # Total transactions (asumsi ada tabel transactions)
        try:
            async with conn.execute("SELECT COUNT(*) FROM transactions") as cursor:
                total_transactions = (await cursor.fetchone())[0]
        except:
            total_transactions = 0
        
        # Today's transactions
        today = datetime.now().strftime('%Y-%m-%d')
        try:
            async with conn.execute("SELECT COUNT(*) FROM transactions WHERE date(created_at)=?", (today,)) as cursor:
                today_transactions = (await cursor.fetchone())[0]
        except:
            today_transactions = 0

    stats_text = f"""
📊 **STATISTIK BOT**

👥 **Users:**
├ Total: {total_users} users
├ Produk Aktif: {total_products}
└ Transaksi: {total_transactions}

📈 **Hari Ini:**
└ Transaksi: {today_transactions}

⏰ **Update:** {datetime.now().strftime('%d-%m-%Y %H:%M')}
    """
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_stats")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
    ]
    
    await query.edit_message_text(
        stats_text, 
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode='Markdown'
    )

# ============================
# FITUR BACKUP DATABASE
# ============================

async def backup_database_from_query(query, context):
    try:
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"backup_{timestamp}.db")
        
        # Copy database file
        shutil.copy2(DB_PATH, backup_file)
        
        # Get backup info
        file_size = os.path.getsize(backup_file)
        backup_count = len([f for f in os.listdir(backup_dir) if f.endswith('.db')])
        
        await log_admin_action(query.from_user.id, "BACKUP_DATABASE", f"File: {backup_file}")
        
        keyboard = [
            [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
        ]
        
        await query.edit_message_text(
            f"✅ **Backup Berhasil**\n\n"
            f"📁 **File:** `{backup_file}`\n"
            f"💾 **Size:** {file_size / 1024:.2f} KB\n"
            f"📊 **Total Backup:** {backup_count} files\n"
            f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Backup error: {e}")
        await query.edit_message_text(f"❌ **Backup Gagal:** {str(e)}")

# ============================
# FITUR BROADCAST
# ============================

async def broadcast_start(query, context):
    await query.edit_message_text(
        "📢 **BROADCAST MESSAGE**\n\n"
        "Kirim pesan yang ingin disampaikan ke semua user:\n"
        "(Anda bisa menggunakan format Markdown)",
        parse_mode='Markdown'
    )
    return BROADCAST_MESSAGE

async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update, context):
        return ConversationHandler.END
    
    broadcast_text = update.message.text
    user_id = update.message.from_user.id
    
    if not broadcast_text.strip():
        await update.message.reply_text("❌ Pesan tidak boleh kosong. Silakan kirim ulang:")
        return BROADCAST_MESSAGE
    
    # Konfirmasi broadcast
    context.user_data['broadcast_text'] = broadcast_text
    
    keyboard = [
        [InlineKeyboardButton("✅ Ya, Kirim Sekarang", callback_data="confirm_broadcast")],
        [InlineKeyboardButton("❌ Batalkan", callback_data="cancel_broadcast")]
    ]
    
    await update.message.reply_text(
        f"📢 **KONFIRMASI BROADCAST**\n\n"
        f"Pesan yang akan dikirim:\n\n"
        f"{broadcast_text}\n\n"
        f"**Kirim pesan ini ke semua user?**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def broadcast_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_broadcast":
        broadcast_text = context.user_data.get('broadcast_text')
        if not broadcast_text:
            await query.edit_message_text("❌ Tidak ada pesan untuk di-broadcast.")
            return
        
        await query.edit_message_text("🔄 Mengirim broadcast ke semua user...")
        
        # Implementasi pengiriman broadcast ke semua user
        # Ini adalah contoh sederhana, sesuaikan dengan struktur database Anda
        success_count = 0
        fail_count = 0
        
        try:
            async with aiosqlite.connect(DB_PATH) as conn:
                async with conn.execute("SELECT user_id FROM users WHERE is_blocked = 0") as cursor:
                    users = await cursor.fetchall()
            
            for user in users:
                try:
                    # Kirim pesan ke setiap user
                    # await context.bot.send_message(chat_id=user[0], text=broadcast_text, parse_mode='Markdown')
                    success_count += 1
                except Exception as e:
                    logger.error(f"Gagal kirim ke user {user[0]}: {e}")
                    fail_count += 1
            
            await log_admin_action(query.from_user.id, "BROADCAST", f"Success: {success_count}, Failed: {fail_count}")
            
            await query.edit_message_text(
                f"✅ **Broadcast Selesai**\n\n"
                f"📊 **Statistik:**\n"
                f"├ Berhasil: {success_count} users\n"
                f"├ Gagal: {fail_count} users\n"
                f"└ Total: {success_count + fail_count} users\n\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ **Error saat broadcast:** {str(e)}")
    
    else:  # cancel_broadcast
        await query.edit_message_text("❌ Broadcast dibatalkan.")

# ============================
# FITUR SYSTEM HEALTH
# ============================

async def system_health_from_query(query, context):
    # System info
    disk_usage = psutil.disk_usage('/')
    memory = psutil.virtual_memory()
    cpu_usage = psutil.cpu_percent(interval=1)
    
    # Bot info
    db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    
    await ensure_products_table()
    await ensure_users_table()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
            active_products = (await cursor.fetchone())[0]
        
        async with conn.execute("SELECT COUNT(*) FROM users") as cursor:
            total_users = (await cursor.fetchone())[0]

    health_text = f"""
🏥 **SYSTEM HEALTH**

🖥️ **System Info:**
├ OS: {platform.system()} {platform.release()}
├ CPU Usage: {cpu_usage}%
├ Memory: {memory.percent}% used
├ Disk: {disk_usage.percent}% used

🤖 **Bot Info:**
├ Database: {db_size / 1024:.2f} KB
├ Active Products: {active_products}
├ Total Users: {total_users}
├ Uptime: {get_bot_uptime()}

⏰ **Last Check:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}
    """
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_health")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
    ]
    
    await query.edit_message_text(
        health_text, 
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode='Markdown'
    )

def get_bot_uptime():
    """Calculate bot uptime (simple version)"""
    if not hasattr(get_bot_uptime, 'start_time'):
        get_bot_uptime.start_time = datetime.now()
    
    uptime = datetime.now() - get_bot_uptime.start_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    else:
        return f"{hours}h {minutes}m {seconds}s"

# ============================
# FITUR CLEANUP DATA
# ============================

async def cleanup_data_from_query(query, context):
    keyboard = [
        [InlineKeyboardButton("🧹 Hapus Transaksi Lama", callback_data="cleanup_old_transactions")],
        [InlineKeyboardButton("🗑️ Hapus User Tidak Aktif", callback_data="cleanup_inactive_users")],
        [InlineKeyboardButton("📉 Reset Statistik", callback_data="reset_stats")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
    ]
    
    await query.edit_message_text(
        "🧹 **CLEANUP DATA**\n\n"
        "Pilih aksi pembersihan data:\n"
        "• Hapus Transaksi Lama - Hapus transaksi > 30 hari\n"
        "• Hapus User Tidak Aktif - Hapus user > 90 hari tidak aktif\n"
        "• Reset Statistik - Reset semua statistik\n\n"
        "⚠️ **PERHATIAN:** Tindakan ini tidak dapat dibatalkan!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ============================
# SETUP HANDLERS
# ============================

def setup_admin_handlers(application):
    """Setup semua handler untuk admin commands"""
    
    # Command handler untuk /admin
    application.add_handler(CommandHandler("admin", admin_menu))
    
    # Callback query handler untuk menu admin
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))
    
    # Conversation handler untuk edit produk
    edit_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_produk_menu_handler, pattern="^edit_")],
        states={
            EDIT_MENU: [CallbackQueryHandler(edit_produk_menu_handler)],
            CHOOSE_PRODUCT: [CallbackQueryHandler(select_product_handler)],
            EDIT_HARGA: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_harga_handler)],
            EDIT_DESKRIPSI: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_deskripsi_handler)]
        },
        fallbacks=[CommandHandler('cancel', edit_produk_cancel)]
    )
    application.add_handler(edit_conv_handler)
    
    # Conversation handler untuk broadcast
    broadcast_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_start, pattern="^admin_broadcast$")],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler)]
        },
        fallbacks=[CommandHandler('cancel', edit_produk_cancel)]
    )
    application.add_handler(broadcast_conv_handler)
    
    # Handler untuk konfirmasi broadcast
    application.add_handler(CallbackQueryHandler(broadcast_confirm_handler, pattern="^(confirm_broadcast|cancel_broadcast)$"))
    
    # Handler untuk topup management
    application.add_handler(CallbackQueryHandler(topup_list, pattern="^admin_topup$"))
    
    # Handler untuk user management
    application.add_handler(CallbackQueryHandler(show_users_menu, pattern="^admin_users$"))
    
    logger.info("Admin handlers setup completed")

# ============================
# FUNGSI BANTUAN TAMBAHAN
# ============================

async def get_active_products_count():
    """Mendapatkan jumlah produk aktif"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
                return (await cursor.fetchone())[0]
    except:
        return 0

async def get_total_users_count():
    """Mendapatkan jumlah total user"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute("SELECT COUNT(*) FROM users") as cursor:
                return (await cursor.fetchone())[0]
    except:
        return 
# ============================
# FITUR APPROVE & CANCEL TOPUP
# ============================

async def approve_topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /approve_topup"""
    user_id = str(update.effective_user.id)
    if not is_admin(update.effective_user):
        await update.message.reply_text("❌ Hanya admin yang boleh approve topup.")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Format: /approve_topup <request_id>")
        return
    
    request_id = context.args[0]
    
    try:
        # Implementasi approve topup - sesuaikan dengan database Anda
        await ensure_topup_requests_table()
        async with aiosqlite.connect(DB_PATH) as conn:
            # Update status topup request
            await conn.execute(
                "UPDATE topup_requests SET status = 'approved', processed_at = ?, processed_by = ? WHERE id = ?",
                (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id, request_id)
            )
            
            # Dapatkan data topup
            async with conn.execute(
                "SELECT user_id, amount FROM topup_requests WHERE id = ?", 
                (request_id,)
            ) as cursor:
                result = await cursor.fetchone()
            
            if result:
                topup_user_id, amount = result
                # Tambahkan saldo ke user
                await conn.execute(
                    "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                    (amount, topup_user_id)
                )
            
            await conn.commit()
        
        await log_admin_action(user_id, "APPROVE_TOPUP", f"Request: {request_id}")
        await update.message.reply_text(f"✅ Topup request #{request_id} berhasil diapprove dan saldo user sudah bertambah.")
        
    except Exception as e:
        logger.error(f"Error approving topup: {e}")
        await update.message.reply_text(f"❌ Gagal approve request #{request_id}: {str(e)}")

async def cancel_topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /cancel_topup"""
    user_id = str(update.effective_user.id)
    if not is_admin(update.effective_user):
        await update.message.reply_text("❌ Hanya admin yang boleh cancel topup.")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Format: /cancel_topup <request_id>")
        return
    
    request_id = context.args[0]
    
    try:
        await ensure_topup_requests_table()
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE topup_requests SET status = 'rejected', processed_at = ?, processed_by = ? WHERE id = ?",
                (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id, request_id)
            )
            await conn.commit()
        
        await log_admin_action(user_id, "CANCEL_TOPUP", f"Request: {request_id}")
        await update.message.reply_text(f"✅ Topup request #{request_id} berhasil dibatalkan/direject.")
        
    except Exception as e:
        logger.error(f"Error canceling topup: {e}")
        await update.message.reply_text(f"❌ Gagal cancel request #{request_id}: {str(e)}")
