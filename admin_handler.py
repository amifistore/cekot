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

EDIT_PRODUK_MENU, EDIT_PRODUK_PILIH, EDIT_HARGA, EDIT_DESKRIPSI = range(4)

def is_admin(user):
    if not user:
        return False
    return str(user.id) in config.ADMIN_TELEGRAM_IDS

async def ensure_products_table():
    """Ensure products table exists with stock column (fix bug)"""
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
                stock INTEGER DEFAULT 0,
                updated_at TEXT
            )
        """)
        # Emergency fix: add stock column if missing
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
# FITUR EDIT PRODUK (ASLI)
# ============================

async def edit_produk_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update, context):
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("✏️ Edit Harga Produk", callback_data="edit_harga")],
        [InlineKeyboardButton("📝 Edit Deskripsi Produk", callback_data="edit_deskripsi")],
        [InlineKeyboardButton("⬅️ Kembali ke Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🛠️ **MENU EDIT PRODUK**\n\n"
        "Pilih jenis edit yang ingin dilakukan:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return EDIT_PRODUK_MENU

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
            return EDIT_PRODUK_MENU

        keyboard = []
        for code, name, price in products:
            btn_text = f"{name} - Rp {price:,.0f}"
            if len(btn_text) > 50:
                btn_text = f"{name[:30]}... - Rp {price:,.0f}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"select_product:{code}")])
        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_edit_menu")])
        edit_type_text = "harga" if data == "edit_harga" else "deskripsi"
        await query.edit_message_text(
            f"📦 **PILIH PRODUK UNTUK EDIT {edit_type_text.upper()}**\n\n"
            f"Pilih produk dari daftar di bawah:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return EDIT_PRODUK_PILIH

    elif data == "admin_back":
        await query.edit_message_text("❌ Proses edit dibatalkan.")
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
    return EDIT_PRODUK_MENU

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
    return EDIT_PRODUK_MENU

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

    await log_admin_action(update.message.from_user.id, "EDIT_DESKRIPSI_SUCCESS", 
                          f"Product: {product_code}")

    keyboard = [
        [InlineKeyboardButton("✏️ Edit Produk Lain", callback_data="back_to_edit_menu")],
        [InlineKeyboardButton("❌ Selesai", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    new_desc_preview = new_description[:100] + "..." if len(new_description) > 100 else new_description
    old_desc_preview = old_description[:100] + "..." if len(old_description) > 100 else old_description

    await update.message.reply_text(
        f"✅ **DESKRIPSI BERHASIL DIUPDATE!**\n\n"
        f"📦 **Produk:** {product_name}\n"
        f"📌 **Kode:** {product_code}\n\n"
        f"📄 **Deskripsi Lama:**\n{old_desc_preview}\n\n"
        f"📄 **Deskripsi Baru:**\n{new_desc_preview}\n\n"
        f"⏰ **Update:** {now}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return EDIT_PRODUK_MENU

async def edit_produk_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Proses edit produk dibatalkan.")
    return ConversationHandler.END

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
    return EDIT_PRODUK_MENU

# ============================
# REGISTER HANDLERS & EXPORTS
# ============================

edit_produk_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('edit_produk', edit_produk_start)],
    states={
        EDIT_PRODUK_MENU: [
            CallbackQueryHandler(edit_produk_menu_handler, pattern='^(edit_harga|edit_deskripsi|admin_back|back_to_edit_menu)$')
        ],
        EDIT_PRODUK_PILIH: [
            CallbackQueryHandler(select_product_handler, pattern='^select_product:')
        ],
        EDIT_HARGA: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, edit_harga_handler)
        ],
        EDIT_DESKRIPSI: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, edit_deskripsi_handler)
        ],
    },
    fallbacks=[CommandHandler('cancel', edit_produk_cancel)],
    per_message=False
)

# Export handler
def get_admin_handlers():
    return [edit_produk_conv_handler]
