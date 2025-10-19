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

# States untuk Conversation Handlers
EDIT_MENU, CHOOSE_PRODUCT, EDIT_HARGA, EDIT_DESKRIPSI = range(4)
MANAGE_BALANCE, CHOOSE_USER_BALANCE, INPUT_AMOUNT, CONFIRM_BALANCE = range(4, 8)
BROADCAST_MESSAGE = range(8, 9)

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
        [InlineKeyboardButton("💰 Kelola Saldo User", callback_data="admin_manage_balance")],
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
        await topup_list_interactive(query, context)
    elif data == "admin_manage_balance":
        await manage_balance_start(query, context)
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
    elif data.startswith('topup_detail:'):
        await topup_detail(update, context)
    elif data.startswith('approve_topup:'):
        await approve_topup(update, context)
    elif data.startswith('reject_topup:'):
        await reject_topup(update, context)
    elif data == "admin_back":
        await admin_menu_from_query(query, context)
    else:
        await query.message.reply_text("❌ Perintah tidak dikenali.")

# ============================
# FITUR UPDATE PRODUK
# ============================

async def ensure_products_table():
    try:
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
            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error ensuring products table: {e}")
        return False

async def updateproduk(update_or_query, context):
    if hasattr(update_or_query, "message") and update_or_query.message:
        msg_func = update_or_query.message.reply_text
        user_id = update_or_query.message.from_user.id
    else:
        msg_func = update_or_query.edit_message_text
        user_id = update_or_query.from_user.id

    await msg_func("🔄 Memperbarui Produk...")
    
    # Check API key
    if not hasattr(config, 'API_KEY_PROVIDER') or not config.API_KEY_PROVIDER:
        await msg_func("❌ API Key Provider tidak ditemukan di config.py")
        return

    api_key = config.API_KEY_PROVIDER
    url = f"https://panel.khfy-store.com/api_v2/list_product?api_key={api_key}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as resp:
                if resp.status != 200:
                    await msg_func(f"❌ Gagal mengambil data: Status {resp.status}")
                    return
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

    if not await ensure_products_table():
        await msg_func("❌ Gagal memastikan tabel produk.")
        return

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
            
            # Kategorisasi produk
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

    if not await ensure_products_table():
        await msg_func("❌ Gagal mengakses database produk.")
        return

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
        
    msg = "📋 **DAFTAR PRODUK AKTIF**\n\n"
    current_category = ""
    
    for code, name, price, category, status in rows:
        if category != current_category:
            msg += f"\n**{category.upper()}:**\n"
            current_category = category
        msg += f"- `{code}` | {name} | Rp {price:,.0f}\n"
        
    await msg_func(msg, parse_mode='Markdown')

# ============================
# FITUR EDIT PRODUK - FIXED
# ============================

async def edit_produk_start_from_query(query, context):
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Harga Produk", callback_data="edit_harga")],
        [InlineKeyboardButton("📝 Edit Deskripsi Produk", callback_data="edit_deskripsi")],
        [InlineKeyboardButton("⬅️ Kembali ke Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            "🛠️ **MENU EDIT PRODUK**\n\n"
            "Pilih jenis edit yang ingin dilakukan:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return EDIT_MENU
    except Exception as e:
        logger.error(f"Error in edit_produk_start_from_query: {e}")
        await query.message.reply_text(
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
    
    if data in ['edit_harga', 'edit_deskripsi']:
        context.user_data['edit_type'] = data
        
        if not await ensure_products_table():
            await query.edit_message_text("❌ Gagal mengakses database produk.")
            return EDIT_MENU

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
        
    return EDIT_MENU

async def select_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return ConversationHandler.END
        
    data = query.data
    
    if data.startswith('select_product:'):
        product_code = data.split(':')[1]
        context.user_data['selected_product'] = product_code
        
        if not await ensure_products_table():
            await query.edit_message_text("❌ Gagal mengakses database produk.")
            return EDIT_MENU

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
    
    if not await ensure_products_table():
        await update.message.reply_text("❌ Gagal mengakses database produk.")
        return ConversationHandler.END

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
    
    if not await ensure_products_table():
        await update.message.reply_text("❌ Gagal mengakses database produk.")
        return ConversationHandler.END

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
# FITUR KELOLA TOPUP - FIXED
# ============================

async def ensure_topup_requests_table():
    try:
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
            return True
    except Exception as e:
        logger.error(f"Error ensuring topup table: {e}")
        return False

async def topup_list_interactive(update_or_query, context):
    """Menampilkan daftar topup dengan tombol interaktif"""
    if hasattr(update_or_query, "message") and update_or_query.message:
        msg_func = update_or_query.message.reply_text
    else:
        msg_func = update_or_query.edit_message_text
        
    if not await ensure_topup_requests_table():
        await msg_func("❌ Gagal mengakses database topup.")
        return

    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("""
            SELECT id, user_id, username, full_name, amount, status, created_at 
            FROM topup_requests 
            ORDER BY 
                CASE WHEN status = 'pending' THEN 1 ELSE 2 END,
                created_at DESC 
            LIMIT 20
        """) as cursor:
            rows = await cursor.fetchall()
            
    if not rows:
        await msg_func("📭 Tidak ada permintaan topup.")
        return

    # Buat keyboard dengan daftar topup
    keyboard = []
    for req_id, user_id, username, full_name, amount, status, created_at in rows:
        status_emoji = "⏳" if status == 'pending' else "✅" if status == 'approved' else "❌"
        display_name = full_name or username or f"User {user_id}"
        
        # Potong nama jika terlalu panjang
        if len(display_name) > 20:
            display_name = display_name[:17] + "..."
            
        btn_text = f"{status_emoji} {display_name} - Rp {amount:,.0f}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"topup_detail:{req_id}")])
    
    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="admin_topup")])
    keyboard.append([InlineKeyboardButton("👑 Menu Admin", callback_data="admin_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Hitung statistik
    pending_count = sum(1 for row in rows if row[5] == 'pending')
    approved_count = sum(1 for row in rows if row[5] == 'approved')
    rejected_count = sum(1 for row in rows if row[5] == 'rejected')
    
    await msg_func(
        f"💳 **DAFTAR PERMINTAAN TOPUP**\n\n"
        f"📊 **Statistik:**\n"
        f"├ ⏳ Pending: {pending_count}\n"
        f"├ ✅ Approved: {approved_count}\n"
        f"└ ❌ Rejected: {rejected_count}\n\n"
        f"📋 **Klik request untuk melihat detail:**",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def topup_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan detail topup request dengan opsi approve/reject"""
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return

    request_id = query.data.split(':')[1]
    
    if not await ensure_topup_requests_table():
        await query.edit_message_text("❌ Gagal mengakses database topup.")
        return

    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("""
            SELECT id, user_id, username, full_name, amount, status, proof_image, created_at 
            FROM topup_requests 
            WHERE id = ?
        """, (request_id,)) as cursor:
            request = await cursor.fetchone()

    if not request:
        await query.edit_message_text("❌ Request topup tidak ditemukan.")
        return

    req_id, user_id, username, full_name, amount, status, proof_image, created_at = request
    
    # Buat keyboard dengan opsi approve/reject
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_topup:{req_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_topup:{req_id}")
        ],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"topup_detail:{req_id}")],
        [InlineKeyboardButton("📋 Kembali ke Daftar", callback_data="admin_topup")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    status_text = {
        'pending': '⏳ Menunggu',
        'approved': '✅ Disetujui',
        'rejected': '❌ Ditolak'
    }.get(status, status)

    message_text = (
        f"💳 **DETAIL REQUEST TOPUP**\n\n"
        f"🆔 **ID Request:** `{req_id}`\n"
        f"👤 **User:** {full_name or username or user_id}\n"
        f"📛 **Username:** @{username if username else 'Tidak ada'}\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"💰 **Jumlah:** Rp {amount:,.0f}\n"
        f"📊 **Status:** {status_text}\n"
        f"🕒 **Waktu Request:** {created_at}\n"
    )

    try:
        await query.edit_message_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        await query.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def approve_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approve topup request dan tambah saldo user"""
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return

    request_id = query.data.split(':')[1]
    
    if not await ensure_topup_requests_table():
        await query.edit_message_text("❌ Gagal mengakses database topup.")
        return

    async with aiosqlite.connect(DB_PATH) as conn:
        # Dapatkan data request
        async with conn.execute("""
            SELECT id, user_id, username, full_name, amount 
            FROM topup_requests 
            WHERE id = ? AND status = 'pending'
        """, (request_id,)) as cursor:
            request = await cursor.fetchone()

        if not request:
            await query.edit_message_text("❌ Request topup tidak ditemukan atau sudah diproses.")
            return

        req_id, user_id, username, full_name, amount = request
        
        # Update status topup
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        await conn.execute("""
            UPDATE topup_requests 
            SET status = 'approved', updated_at = ?
            WHERE id = ?
        """, (now, req_id))
        
        # Tambah saldo user menggunakan database manager
        try:
            current_saldo = database.get_user_saldo(user_id)
            new_saldo = current_saldo + amount
            database.db_manager.get_or_create_user(user_id, username, full_name)
            
            import sqlite3
            user_conn = sqlite3.connect(DB_PATH)
            user_c = user_conn.cursor()
            user_c.execute("UPDATE users SET saldo = ? WHERE telegram_id = ?", (new_saldo, user_id))
            user_conn.commit()
            user_conn.close()
            
        except Exception as e:
            logger.error(f"Error updating user balance: {e}")
        
        await conn.commit()

    # Log admin action
    await log_admin_action(
        query.from_user.id, 
        "APPROVE_TOPUP", 
        f"Request ID: {req_id}, User: {user_id}, Amount: {amount}"
    )

    # Kirim notifikasi ke user
    try:
        user_message = (
            f"✅ **TOPUP ANDA TELAH DISETUJUI!**\n\n"
            f"💰 **Jumlah:** Rp {amount:,.0f}\n"
            f"🆔 **ID Transaksi:** `{req_id}`\n"
            f"🕒 **Waktu:** {now}\n\n"
            f"💳 **Saldo Anda Bertambah!**"
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=user_message,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Gagal mengirim notifikasi ke user {user_id}: {e}")

    # Update message admin
    keyboard = [
        [InlineKeyboardButton("📋 Kembali ke Daftar Topup", callback_data="admin_topup")],
        [InlineKeyboardButton("👑 Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✅ **TOPUP BERHASIL DISETUJUI!**\n\n"
        f"🆔 **ID Request:** `{req_id}`\n"
        f"👤 **User:** {full_name or username or user_id}\n"
        f"💰 **Jumlah:** Rp {amount:,.0f}\n"
        f"🕒 **Waktu Approve:** {now}\n\n"
        f"✅ Saldo user telah ditambahkan secara otomatis.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def reject_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reject topup request"""
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return

    request_id = query.data.split(':')[1]
    
    if not await ensure_topup_requests_table():
        await query.edit_message_text("❌ Gagal mengakses database topup.")
        return

    async with aiosqlite.connect(DB_PATH) as conn:
        # Dapatkan data request
        async with conn.execute("""
            SELECT id, user_id, username, full_name, amount 
            FROM topup_requests 
            WHERE id = ? AND status = 'pending'
        """, (request_id,)) as cursor:
            request = await cursor.fetchone()

        if not request:
            await query.edit_message_text("❌ Request topup tidak ditemukan atau sudah diproses.")
            return

        req_id, user_id, username, full_name, amount = request
        
        # Update status topup
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        await conn.execute("""
            UPDATE topup_requests 
            SET status = 'rejected', updated_at = ?
            WHERE id = ?
        """, (now, req_id))
        
        await conn.commit()

    # Log admin action
    await log_admin_action(
        query.from_user.id, 
        "REJECT_TOPUP", 
        f"Request ID: {req_id}, User: {user_id}, Amount: {amount}"
    )

    # Kirim notifikasi ke user
    try:
        user_message = (
            f"❌ **TOPUP ANDA DITOLAK**\n\n"
            f"💰 **Jumlah:** Rp {amount:,.0f}\n"
            f"🆔 **ID Transaksi:** `{req_id}`\n"
            f"🕒 **Waktu:** {now}\n\n"
            f"ℹ️ **Silakan hubungi admin untuk informasi lebih lanjut.**"
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=user_message,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Gagal mengirim notifikasi ke user {user_id}: {e}")

    # Update message admin
    keyboard = [
        [InlineKeyboardButton("📋 Kembali ke Daftar Topup", callback_data="admin_topup")],
        [InlineKeyboardButton("👑 Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"❌ **TOPUP TELAH DITOLAK**\n\n"
        f"🆔 **ID Request:** `{req_id}`\n"
        f"👤 **User:** {full_name or username or user_id}\n"
        f"💰 **Jumlah:** Rp {amount:,.0f}\n"
        f"🕒 **Waktu Reject:** {now}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ============================
# FITUR KELOLA SALDO USER - FIXED
# ============================

async def manage_balance_start(query, context):
    """Memulai proses pengelolaan saldo user"""
    keyboard = [
        [InlineKeyboardButton("➕ Tambah Saldo", callback_data="add_balance")],
        [InlineKeyboardButton("➖ Kurangi Saldo", callback_data="subtract_balance")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            "💰 **KELOLA SALDO USER**\n\n"
            "Pilih aksi yang ingin dilakukan:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return MANAGE_BALANCE
    except Exception as e:
        logger.error(f"Error in manage_balance_start: {e}")
        await query.message.reply_text(
            "💰 **KELOLA SALDO USER**\n\n"
            "Pilih aksi yang ingin dilakukan:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return MANAGE_BALANCE

async def choose_balance_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Memilih aksi tambah atau kurangi saldo"""
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return ConversationHandler.END
    
    data = query.data
    context.user_data['balance_action'] = data
    
    action_text = "menambah" if data == "add_balance" else "mengurangi"
    
    try:
        await query.edit_message_text(
            f"💰 **{action_text.upper()} SALDO USER**\n\n"
            f"Silakan kirim username atau user ID yang ingin {action_text} saldo:",
            parse_mode='Markdown'
        )
        return CHOOSE_USER_BALANCE
    except Exception as e:
        logger.error(f"Error in choose_balance_action: {e}")
        await query.message.reply_text(
            f"💰 **{action_text.upper()} SALDO USER**\n\n"
            f"Silakan kirim username atau user ID yang ingin {action_text} saldo:",
            parse_mode='Markdown'
        )
        return CHOOSE_USER_BALANCE

async def get_user_for_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mendapatkan user untuk dikelola saldonya"""
    if not await admin_check(update, context):
        return ConversationHandler.END
    
    user_input = update.message.text.strip()
    
    # Cari user di database
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Coba cari berdasarkan username (dengan atau tanpa @)
    if user_input.startswith('@'):
        user_input = user_input[1:]
    
    c.execute("""
        SELECT telegram_id, username, full_name, saldo 
        FROM users 
        WHERE username = ? OR telegram_id = ? OR full_name LIKE ?
    """, (user_input, user_input, f'%{user_input}%'))
    
    user = c.fetchone()
    conn.close()
    
    if not user:
        await update.message.reply_text(
            "❌ User tidak ditemukan.\n"
            "Silakan kirim username atau user ID yang valid:"
        )
        return CHOOSE_USER_BALANCE
    
    telegram_id, username, full_name, current_balance = user
    
    # Simpan data user di context
    context.user_data['target_user'] = {
        'telegram_id': telegram_id,
        'username': username,
        'full_name': full_name,
        'current_balance': current_balance
    }
    
    action_text = "ditambahkan" if context.user_data['balance_action'] == "add_balance" else "dikurangi"
    
    await update.message.reply_text(
        f"👤 **User Ditemukan**\n\n"
        f"📛 **Nama:** {full_name or 'Tidak ada'}\n"
        f"📎 **Username:** @{username or 'Tidak ada'}\n"
        f"🆔 **User ID:** `{telegram_id}`\n"
        f"💰 **Saldo Saat Ini:** Rp {current_balance:,.0f}\n\n"
        f"Silakan kirim jumlah saldo yang ingin {action_text} (hanya angka):",
        parse_mode='Markdown'
    )
    return INPUT_AMOUNT

async def get_amount_for_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mendapatkan jumlah saldo yang akan diubah"""
    if not await admin_check(update, context):
        return ConversationHandler.END
    
    try:
        amount = float(update.message.text.replace(',', '').strip())
        if amount <= 0:
            await update.message.reply_text("❌ Jumlah harus lebih dari 0. Silakan coba lagi:")
            return INPUT_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ Format jumlah tidak valid. Kirim hanya angka. Silakan coba lagi:")
        return INPUT_AMOUNT
    
    context.user_data['amount'] = amount
    
    user_data = context.user_data['target_user']
    action = context.user_data['balance_action']
    
    current_balance = user_data['current_balance']
    
    if action == "add_balance":
        new_balance = current_balance + amount
        action_text = "TAMBAH SALDO"
        emoji = "➕"
    else:
        if amount > current_balance:
            await update.message.reply_text(
                f"❌ Jumlah pengurangan ({amount:,.0f}) melebihi saldo user ({current_balance:,.0f}).\n"
                f"Silakan kirim jumlah yang valid:"
            )
            return INPUT_AMOUNT
        new_balance = current_balance - amount
        action_text = "KURANGI SALDO"
        emoji = "➖"
    
    # Konfirmasi perubahan
    keyboard = [
        [
            InlineKeyboardButton("✅ Konfirmasi", callback_data="confirm_balance"),
            InlineKeyboardButton("❌ Batal", callback_data="cancel_balance")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"💰 **KONFIRMASI {action_text}** {emoji}\n\n"
        f"👤 **User:** {user_data['full_name'] or user_data['username'] or user_data['telegram_id']}\n"
        f"🆔 **User ID:** `{user_data['telegram_id']}`\n"
        f"💰 **Saldo Saat Ini:** Rp {current_balance:,.0f}\n"
        f"💰 **Jumlah Perubahan:** Rp {amount:,.0f}\n"
        f"💰 **Saldo Baru:** Rp {new_balance:,.0f}\n\n"
        f"Apakah Anda yakin ingin melanjutkan?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return CONFIRM_BALANCE

async def confirm_balance_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mengkonfirmasi dan mengeksekusi perubahan saldo"""
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return ConversationHandler.END
    
    user_data = context.user_data['target_user']
    amount = context.user_data['amount']
    action = context.user_data['balance_action']
    
    telegram_id = user_data['telegram_id']
    current_balance = user_data['current_balance']
    
    # Eksekusi perubahan saldo
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if action == "add_balance":
        new_balance = current_balance + amount
        c.execute("UPDATE users SET saldo = ? WHERE telegram_id = ?", (new_balance, telegram_id))
        action_text = "ditambahkan"
        log_action = "ADD_BALANCE"
    else:
        new_balance = current_balance - amount
        c.execute("UPDATE users SET saldo = ? WHERE telegram_id = ?", (new_balance, telegram_id))
        action_text = "dikurangi"
        log_action = "SUBTRACT_BALANCE"
    
    conn.commit()
    conn.close()
    
    # Log admin action
    await log_admin_action(
        query.from_user.id,
        log_action,
        f"User: {telegram_id}, Amount: {amount}, Old: {current_balance}, New: {new_balance}"
    )
    
    # Kirim notifikasi ke user
    try:
        user_message = (
            f"💰 **SALDO ANDA TELAH DIUBAH**\n\n"
            f"📛 **Admin:** {query.from_user.first_name}\n"
            f"💰 **Jumlah {action_text}:** Rp {amount:,.0f}\n"
            f"💰 **Saldo Lama:** Rp {current_balance:,.0f}\n"
            f"💰 **Saldo Baru:** Rp {new_balance:,.0f}\n"
            f"🕒 **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        )
        await context.bot.send_message(
            chat_id=telegram_id,
            text=user_message,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Gagal mengirim notifikasi ke user {telegram_id}: {e}")
    
    # Update message admin
    keyboard = [
        [InlineKeyboardButton("💰 Kelola Saldo Lain", callback_data="admin_manage_balance")],
        [InlineKeyboardButton("👑 Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✅ **SALDO BERHASIL DIUBAH!**\n\n"
        f"👤 **User:** {user_data['full_name'] or user_data['username'] or telegram_id}\n"
        f"🆔 **User ID:** `{telegram_id}`\n"
        f"💰 **Jumlah {action_text}:** Rp {amount:,.0f}\n"
        f"💰 **Saldo Lama:** Rp {current_balance:,.0f}\n"
        f"💰 **Saldo Baru:** Rp {new_balance:,.0f}\n\n"
        f"✅ Notifikasi telah dikirim ke user.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def cancel_balance_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Membatalkan perubahan saldo"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text("❌ Perubahan saldo dibatalkan.")
    return ConversationHandler.END

async def manage_balance_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Membatalkan proses pengelolaan saldo"""
    await update.message.reply_text("❌ Proses kelola saldo dibatalkan.")
    return ConversationHandler.END

# ============================
# FITUR KELOLA USER - FIXED
# ============================

async def show_users_menu(query, context):
    keyboard = [
        [InlineKeyboardButton("📊 List Semua User", callback_data="list_all_users")],
        [InlineKeyboardButton("🔍 Cari User", callback_data="search_user")],
        [InlineKeyboardButton("👑 Jadikan Admin", callback_data="make_admin")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            "👥 **MENU KELOLA USER**\n\nPilih opsi yang diinginkan:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in show_users_menu: {e}")
        await query.message.reply_text(
            "👥 **MENU KELOLA USER**\n\nPilih opsi yang diinginkan:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def list_all_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan daftar semua user"""
    query = update.callback_query
    await query.answer()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT telegram_id, username, full_name, saldo, created_at FROM users ORDER BY created_at DESC LIMIT 50")
    users = c.fetchall()
    conn.close()
    
    if not users:
        await query.edit_message_text("📭 Tidak ada user terdaftar.")
        return
    
    message = "👥 **DAFTAR USER (50 TERBARU)**\n\n"
    for i, (telegram_id, username, full_name, saldo, created_at) in enumerate(users, 1):
        admin_status = "👑" if str(telegram_id) in config.ADMIN_TELEGRAM_IDS else "👤"
        message += f"{admin_status} **{i}. {full_name or username or 'N/A'}**\n"
        message += f"   📛 @{username or 'N/A'} | 🆔 `{telegram_id}`\n"
        message += f"   💰 Rp {saldo:,.0f} | 📅 {created_at[:10]}\n\n"
    
    # Tambahkan pagination jika perlu
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="list_all_users")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_users")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in list_all_users: {e}")
        await query.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def cek_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    username = args[0] if args else None
    if not username:
        await update.message.reply_text("❌ Format: `/cek_user <username>`", parse_mode='Markdown')
        return
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT saldo, telegram_id FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        await update.message.reply_text(f"❌ User tidak ditemukan: `{username}`", parse_mode='Markdown')
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
        await update.message.reply_text("❌ Format: `/jadikan_admin <telegram_id>`", parse_mode='Markdown')
        return
    
    # Cek apakah user ada
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username, full_name FROM users WHERE telegram_id=?", (telegram_id,))
    user = c.fetchone()
    conn.close()
    
    if not user:
        await update.message.reply_text(f"❌ User dengan ID `{telegram_id}` tidak ditemukan.", parse_mode='Markdown')
        return
    
    username, full_name = user
    
    if str(telegram_id) in config.ADMIN_TELEGRAM_IDS:
        await update.message.reply_text(f"❌ User `{telegram_id}` sudah menjadi admin.", parse_mode='Markdown')
        return
    
    config.ADMIN_TELEGRAM_IDS.append(str(telegram_id))
    
    await log_admin_action(update.message.from_user.id, "MAKE_ADMIN", f"User: {telegram_id}")
    
    await update.message.reply_text(
        f"✅ **Admin Berhasil Ditambahkan**\n\n"
        f"👤 **User:** {full_name or username or 'N/A'}\n"
        f"📛 **Username:** @{username or 'N/A'}\n"
        f"🆔 **Telegram ID:** `{telegram_id}`",
        parse_mode='Markdown'
    )

# ============================
# FITUR STATISTIK - FIXED
# ============================

async def show_stats_menu(query, context):
    try:
        stats = database.get_bot_statistics()
        
        await query.edit_message_text(
            f"📊 **STATISTIK SISTEM**\n\n"
            f"📦 **PRODUK:**\n"
            f"├ Total Produk: {stats['active_products']}\n"
            f"└ Tersedia: {stats['active_products']}\n\n"
            f"💳 **TOPUP:**\n"
            f"├ Total: {stats['pending_topups']}\n"
            f"├ Pending: {stats['pending_topups']}\n"
            f"└ Approved: 0\n\n"
            f"👥 **USER:**\n"
            f"├ Total User: {stats['total_users']}\n"
            f"└ Total Saldo: Rp {stats['total_revenue']:,.0f}\n\n"
            f"⏰ **Update:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in show_stats_menu: {e}")
        await query.edit_message_text("❌ Gagal memuat statistik.")

# ============================
# FITUR BROADCAST - FIXED
# ============================

async def broadcast_start(query, context):
    try:
        await query.edit_message_text(
            "📢 **BROADCAST PESAN**\n\n"
            "Kirim pesan yang ingin disampaikan ke semua user:\n"
            "(Gunakan /cancel untuk membatalkan)",
            parse_mode='Markdown'
        )
        return BROADCAST_MESSAGE
    except Exception as e:
        logger.error(f"Error in broadcast_start: {e}")
        await query.message.reply_text(
            "📢 **BROADCAST PESAN**\n\n"
            "Kirim pesan yang ingin disampaikan ke semua user:\n"
            "(Gunakan /cancel untuk membatalkan)",
            parse_mode='Markdown'
        )
        return BROADCAST_MESSAGE

async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update, context):
        return ConversationHandler.END
    
    message = update.message.text
    
    # Konfirmasi broadcast
    context.user_data['broadcast_message'] = message
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Ya, Broadcast", callback_data="confirm_broadcast"),
            InlineKeyboardButton("❌ Batal", callback_data="cancel_broadcast")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📢 **KONFIRMASI BROADCAST**\n\n"
        f"Pesan yang akan dikirim:\n\n"
        f"{message}\n\n"
        f"Apakah Anda yakin ingin mengirim broadcast ini ke semua user?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    message = context.user_data.get('broadcast_message')
    if not message:
        await query.edit_message_text("❌ Pesan broadcast tidak ditemukan.")
        return
    
    await query.edit_message_text("🔄 Mengirim broadcast ke semua user...")
    
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
        except Exception as e:
            logger.error(f"Gagal mengirim broadcast ke {user_id}: {e}")
            fail_count += 1
    
    await log_admin_action(query.from_user.id, "BROADCAST", f"Success: {success_count}, Failed: {fail_count}")
    
    await query.edit_message_text(
        f"✅ **Broadcast Selesai**\n\n"
        f"📊 **Statistik Pengiriman:**\n"
        f"├ ✅ Berhasil: {success_count}\n"
        f"├ ❌ Gagal: {fail_count}\n"
        f"└ 📊 Total: {success_count + fail_count}",
        parse_mode='Markdown'
    )

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text("❌ Broadcast dibatalkan.")

async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Proses broadcast dibatalkan.")
    return ConversationHandler.END

# ============================
# FITUR BACKUP DATABASE - FIXED
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
        await log_admin_action(query.from_user.id, "BACKUP_DATABASE", "Success")
    except Exception as e:
        await query.edit_message_text(f"❌ Gagal backup: {str(e)}")
        await log_admin_action(query.from_user.id, "BACKUP_DATABASE", f"Failed: {str(e)}")

# ============================
# FITUR SYSTEM HEALTH - FIXED
# ============================

async def system_health_from_query(query, context):
    try:
        # Check database connection
        try:
            async with aiosqlite.connect(DB_PATH) as conn:
                await conn.execute("SELECT 1")
            db_status = "✅ Connected"
        except Exception as e:
            db_status = f"❌ Error: {e}"
        
        # Check API status
        api_status = "❌ Not configured"
        if hasattr(config, 'API_KEY_PROVIDER') and config.API_KEY_PROVIDER:
            api_key = config.API_KEY_PROVIDER
            url = f"https://panel.khfy-store.com/api_v2/list_product?api_key={api_key}"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=10) as resp:
                        api_status = "✅ Connected" if resp.status == 200 else f"❌ Status: {resp.status}"
            except Exception as e:
                api_status = f"❌ Error: {e}"
        
        # Check disk space
        try:
            stat = shutil.disk_usage(".")
            free_gb = stat.free / (1024**3)
            disk_status = f"✅ {free_gb:.1f} GB free"
        except Exception as e:
            disk_status = f"❌ Error: {e}"
        
        # Get statistics
        stats = database.get_bot_statistics()
        
        await query.edit_message_text(
            f"🏥 **SYSTEM HEALTH CHECK**\n\n"
            f"📦 Database: {db_status}\n"
            f"🌐 API Provider: {api_status}\n"
            f"💾 Disk Space: {disk_status}\n"
            f"👥 Total Users: {stats['total_users']}\n"
            f"💰 Total Saldo: Rp {stats['total_revenue']:,.0f}\n"
            f"🕒 Check Time: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}",
            parse_mode='Markdown'
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Health check failed: {str(e)}")

# ============================
# FITUR CLEANUP DATA - FIXED
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
        
        await log_admin_action(query.from_user.id, "CLEANUP_DATA", f"Rejected: {rejected_deleted}, Logs: {logs_deleted}")
        
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
# LOGGING ADMIN ACTIONS - FIXED
# ============================

async def ensure_admin_logs_table():
    try:
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
            return True
    except Exception as e:
        logger.error(f"Error ensuring admin logs table: {e}")
        return False

async def log_admin_action(admin_id: int, action: str, details: str = ""):
    try:
        if not await ensure_admin_logs_table():
            return False
            
        async with aiosqlite.connect(DB_PATH) as conn:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await conn.execute(
                "INSERT INTO admin_logs (admin_id, action, details, created_at) VALUES (?, ?, ?, ?)",
                (admin_id, action, details, now)
            )
            await conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")
        return False

# ============================
# REGISTER HANDLERS & EXPORTS - FIXED
# ============================

admin_menu_handler = CommandHandler("admin", admin_menu)
admin_callback_query_handler = CallbackQueryHandler(admin_callback_handler, pattern=r'^admin_')

# Handler untuk fitur broadcast
broadcast_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(broadcast_start, pattern='^admin_broadcast$')],
    states={
        BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler)],
    },
    fallbacks=[CommandHandler('cancel', broadcast_cancel)],
    per_message=False
)

# Handler untuk konfirmasi broadcast
broadcast_confirm_handler = CallbackQueryHandler(confirm_broadcast, pattern='^confirm_broadcast$')
broadcast_cancel_handler = CallbackQueryHandler(cancel_broadcast, pattern='^cancel_broadcast$')

# Handler untuk fitur edit produk
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

# Handler untuk fitur kelola saldo
manage_balance_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(choose_balance_action, pattern='^(add_balance|subtract_balance)$')],
    states={
        CHOOSE_USER_BALANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_user_for_balance)],
        INPUT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount_for_balance)],
        CONFIRM_BALANCE: [CallbackQueryHandler(confirm_balance_change, pattern='^confirm_balance$')],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_balance_change, pattern='^cancel_balance$'),
        CommandHandler('cancel', manage_balance_cancel)
    ],
    per_message=False
)

# Handler untuk user management
user_management_handler = CallbackQueryHandler(list_all_users, pattern='^list_all_users$')

# Command handlers
cek_user_handler = CommandHandler("cek_user", cek_user)
jadikan_admin_handler = CommandHandler("jadikan_admin", jadikan_admin)
topup_list_handler = CommandHandler("topup_list", topup_list_interactive)
broadcast_handler = CommandHandler("broadcast", broadcast_start)

def get_admin_handlers():
    return [
        admin_menu_handler,
        admin_callback_query_handler,
        edit_produk_conv_handler,
        manage_balance_conv_handler,
        broadcast_conv_handler,
        broadcast_confirm_handler,
        broadcast_cancel_handler,
        user_management_handler,
        cek_user_handler,
        jadikan_admin_handler,
        topup_list_handler,
        broadcast_handler,
    ]
