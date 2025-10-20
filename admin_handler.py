#!/usr/bin/env python3
"""
Admin Handler - Full Feature Complete Version
Fitur lengkap untuk management bot Telegram
"""

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
import json
import asyncio
from typing import Dict, Any, List

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
CLEANUP_CONFIRM, USER_MANAGEMENT = range(9, 11)

# ============================
# UTILITY FUNCTIONS
# ============================

async def log_admin_action(user_id: int, action: str, details: str):
    """Log admin actions untuk audit trail"""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] ADMIN {user_id} - {action}: {details}"
        
        # Log ke file
        with open("admin_actions.log", "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
        
        # Log ke database jika diperlukan
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT,
                    details TEXT,
                    timestamp TEXT
                )
            """)
            await conn.execute(
                "INSERT INTO admin_logs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
                (user_id, action, details, timestamp)
            )
            await conn.commit()
            
        logger.info(f"Admin action logged: {user_id} - {action}")
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

def is_admin(user):
    """Validasi user admin"""
    if not user:
        return False
    return str(user.id) in config.ADMIN_TELEGRAM_IDS

def get_user_from_update(update):
    """Robust admin user extraction untuk berbagai jenis update"""
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
    """Middleware untuk verifikasi admin"""
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
    """Menu utama admin"""
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
            await update.callback_query.message.reply_text(
                "👑 **MENU ADMIN**\n\nSilakan pilih fitur:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

async def admin_menu_from_query(query, context):
    """Helper untuk kembali ke menu admin dari query"""
    class FakeUpdate:
        def __init__(self, callback_query):
            self.callback_query = callback_query
            self.message = None
    await admin_menu(FakeUpdate(query), context)

# ============================
# CALLBACK QUERY HANDLER - ROUTER UTAMA
# ============================

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main router untuk semua callback admin"""
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return
        
    data = query.data
    
    # Main menu routing
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
    
    # Topup management
    elif data.startswith('topup_detail:'):
        await topup_detail(update, context)
    elif data.startswith('approve_topup:'):
        await approve_topup(update, context)
    elif data.startswith('reject_topup:'):
        await reject_topup(update, context)
    
    # User management
    elif data.startswith('user_detail:'):
        await user_detail(update, context)
    elif data.startswith('make_admin:'):
        await make_admin(update, context)
    elif data.startswith('remove_admin:'):
        await remove_admin(update, context)
    
    # Navigation
    elif data == "admin_back":
        await admin_menu_from_query(query, context)
    elif data == "back_to_users":
        await show_users_menu(query, context)
    elif data == "back_to_topup":
        await topup_list_interactive(query, context)
    else:
        await query.message.reply_text("❌ Perintah tidak dikenali.")

# ============================
# FITUR UPDATE PRODUK
# ============================

async def ensure_products_table():
    """Memastikan tabel products ada"""
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
    """Update produk dari API provider"""
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

    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            # Start transaction
            await conn.execute("BEGIN TRANSACTION")
            
            # Mark semua produk sebagai inactive
            await conn.execute("UPDATE products SET status = 'inactive'")
            
            count = 0
            skipped = 0
            for prod in produk_list:
                code = str(prod.get("kode_produk", "")).strip()
                name = str(prod.get("nama_produk", "")).strip()
                price = float(prod.get("harga_final", 0))
                gangguan = int(prod.get("gangguan", 0))
                kosong = int(prod.get("kosong", 0))
                provider_code = str(prod.get("kode_provider", "")).strip()
                description = str(prod.get("deskripsi", "")).strip() or f"Produk {name}"
                
                # Skip jika data tidak valid
                if not code or not name or price <= 0 or gangguan == 1 or kosong == 1:
                    skipped += 1
                    continue
                
                # Kategorisasi produk
                category = "Umum"
                name_lower = name.lower()
                if "pulsa" in name_lower and "data" not in name_lower and "internet" not in name_lower:
                    category = "Pulsa"
                elif "data" in name_lower or "internet" in name_lower or "kuota" in name_lower:
                    category = "Internet"
                elif "listrik" in name_lower or "pln" in name_lower:
                    category = "Listrik"
                elif "game" in name_lower:
                    category = "Game"
                elif "emoney" in name_lower or "gopay" in name_lower or "dana" in name_lower or "ovo" in name_lower:
                    category = "E-Money"
                elif "akrab" in name_lower or "bonus" in name_lower:
                    category = "Paket Bonus"
                
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
            
    except Exception as e:
        logger.error(f"Error updating products: {e}")
        await msg_func(f"❌ Error saat update produk: {e}")
        return

    await log_admin_action(user_id, "UPDATE_PRODUCTS", f"Updated: {count} produk, Skipped: {skipped}")
    await msg_func(
        f"✅ **Update Produk Berhasil**\n\n"
        f"📊 **Statistik:**\n"
        f"├ Berhasil diupdate: {count} produk\n"
        f"├ Dilewati: {skipped} produk\n"
        f"⏰ **Update Terakhir:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
        parse_mode='Markdown'
    )

# ============================
# FITUR LIST PRODUK
# ============================

async def listproduk(update_or_query, context):
    """Menampilkan daftar produk"""
    if hasattr(update_or_query, "message") and update_or_query.message:
        msg_func = update_or_query.message.reply_text
    else:
        msg_func = update_or_query.edit_message_text

    if not await ensure_products_table():
        await msg_func("❌ Gagal mengakses database produk.")
        return

    try:
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
        categories = {}
        for code, name, price, category, status in rows:
            if category not in categories:
                categories[category] = []
            categories[category].append((code, name, price))
        
        msg = "📋 **DAFTAR PRODUK AKTIF**\n\n"
        for category, products in categories.items():
            msg += f"**{category.upper()}:**\n"
            for code, name, price in products[:10]:  # Max 10 per category untuk pesan yang tidak terlalu panjang
                msg += f"├ `{code}` | {name} | Rp {price:,.0f}\n"
            if len(products) > 10:
                msg += f"└ ... dan {len(products) - 10} produk lainnya\n"
            msg += "\n"
            
        msg += f"📊 Total: {len(rows)} produk aktif"
        
        await msg_func(msg, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error listing products: {e}")
        await msg_func("❌ Gagal mengambil daftar produk.")

# ============================
# FITUR EDIT PRODUK - CONVERSATION HANDLER
# ============================

async def edit_produk_start_from_query(query, context):
    """Memulai conversation edit produk"""
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
    """Handler untuk menu edit produk"""
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

        try:
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
            
        except Exception as e:
            logger.error(f"Error fetching products: {e}")
            await query.edit_message_text("❌ Gagal mengambil daftar produk.")
            return EDIT_MENU
        
    elif data == "admin_back":
        await admin_menu_from_query(query, context)
        return ConversationHandler.END
        
    elif data == "back_to_edit_menu":
        return await edit_produk_start_from_query(query, context)
        
    return EDIT_MENU

async def select_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memilih produk"""
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

        try:
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
            else:
                await query.edit_message_text("❌ Produk tidak ditemukan.")
                return EDIT_MENU
                
        except Exception as e:
            logger.error(f"Error fetching product: {e}")
            await query.edit_message_text("❌ Gagal mengambil data produk.")
            return EDIT_MENU
                
    await query.edit_message_text("❌ Terjadi kesalahan. Silakan coba lagi.")
    return EDIT_MENU

async def edit_harga_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk edit harga produk"""
    if not await admin_check(update, context):
        return ConversationHandler.END
        
    try:
        # Validasi input
        price_text = update.message.text.replace(',', '').replace('.', '').strip()
        new_price = float(price_text)
        
        if new_price <= 0:
            await update.message.reply_text("❌ Harga harus lebih dari 0. Silakan coba lagi:")
            return EDIT_HARGA
            
        if new_price > 100000000:  # Max 100 juta
            await update.message.reply_text("❌ Harga terlalu besar. Maksimal Rp 100.000.000. Silakan coba lagi:")
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

    try:
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
            [InlineKeyboardButton("🏠 Menu Admin", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **HARGA BERHASIL DIUPDATE!**\n\n"
            f"📦 **Produk:** {product_name}\n"
            f"📌 **Kode:** {product_code}\n"
            f"💰 **Harga Lama:** Rp {old_price:,.0f}\n"
            f"💰 **Harga Baru:** Rp {new_price:,.0f}\n\n"
            f"⏰ **Update:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error updating price: {e}")
        await update.message.reply_text("❌ Gagal mengupdate harga produk.")
        return ConversationHandler.END

async def edit_deskripsi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk edit deskripsi produk"""
    if not await admin_check(update, context):
        return ConversationHandler.END
        
    new_description = update.message.text.strip()
    
    if len(new_description) > 1000:
        await update.message.reply_text("❌ Deskripsi terlalu panjang. Maksimal 1000 karakter. Silakan coba lagi:")
        return EDIT_DESKRIPSI
        
    product_data = context.user_data.get('current_product')
    if not product_data:
        await update.message.reply_text("❌ Data produk tidak ditemukan. Silakan mulai ulang.")
        return ConversationHandler.END
        
    product_code = product_data['code']
    product_name = product_data['name']
    old_description = product_data.get('description', 'Tidak ada deskripsi')
    
    if not await ensure_products_table():
        await update.message.reply_text("❌ Gagal mengakses database produk.")
        return ConversationHandler.END

    try:
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
            [InlineKeyboardButton("🏠 Menu Admin", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **DESKRIPSI BERHASIL DIUPDATE!**\n\n"
            f"📦 **Produk:** {product_name}\n"
            f"📌 **Kode:** {product_code}\n"
            f"📄 **Deskripsi Baru:**\n{new_description}\n\n"
            f"⏰ **Update:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error updating description: {e}")
        await update.message.reply_text("❌ Gagal mengupdate deskripsi produk.")
        return ConversationHandler.END

async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation edit produk"""
    await update.message.reply_text("❌ Edit produk dibatalkan.")
    
    # Cleanup user data
    context.user_data.clear()
    
    return ConversationHandler.END

# ============================
# FITUR MANAJEMEN TOPUP
# ============================

async def topup_list_interactive(query, context):
    """Menampilkan daftar topup pending"""
    try:
        # Ambil data topup pending dari database
        topups = database.get_pending_topups()  # Asumsi function ini ada di module database
        
        if not topups:
            keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data="admin_topup")],
                       [InlineKeyboardButton("🏠 Menu Admin", callback_data="admin_back")]]
            await query.edit_message_text(
                "💳 **DAFTAR TOPUP PENDING**\n\n"
                "Tidak ada topup yang menunggu approval.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return
            
        keyboard = []
        for topup in topups[:10]:  # Limit 10 topup per halaman
            user_info = database.get_user_info(topup['user_id'])
            username = user_info.get('username', 'N/A') if user_info else 'N/A'
            amount = topup['amount']
            btn_text = f"@{username} - Rp {amount:,.0f}"
            if len(btn_text) > 30:
                btn_text = f"@{username[:15]}... - Rp {amount:,.0f}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"topup_detail:{topup['id']}")])
        
        # Navigation buttons
        keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="admin_topup")])
        keyboard.append([InlineKeyboardButton("🏠 Menu Admin", callback_data="admin_back")])
        
        await query.edit_message_text(
            f"💳 **DAFTAR TOPUP PENDING**\n\n"
            f"Total {len(topups)} topup menunggu approval.\n"
            f"Pilih topup untuk melihat detail:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error displaying topup list: {e}")
        await query.edit_message_text("❌ Gagal mengambil daftar topup.")

async def topup_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan detail topup"""
    query = update.callback_query
    await query.answer()
    
    try:
        topup_id = int(query.data.split(':')[1])
        
        # Ambil detail topup dari database
        topup = database.get_topup_by_id(topup_id)  # Asumsi function ini ada
        if not topup:
            await query.edit_message_text("❌ Data topup tidak ditemukan.")
            return
            
        user_info = database.get_user_info(topup['user_id'])
        username = user_info.get('username', 'Tidak ada') if user_info else 'Tidak ada'
        full_name = user_info.get('full_name', 'Tidak ada') if user_info else 'Tidak ada'
        
        status_text = "⏳ PENDING" if topup['status'] == 'pending' else topup['status']
        
        message = (
            f"💳 **DETAIL TOPUP**\n\n"
            f"👤 **User:** {full_name}\n"
            f"📱 **Username:** @{username}\n"
            f"🆔 **User ID:** {topup['user_id']}\n\n"
            f"💰 **Nominal:** Rp {topup['amount']:,.0f}\n"
            f"📊 **Status:** {status_text}\n"
            f"⏰ **Waktu:** {topup['created_at']}\n"
        )
        
        if topup.get('proof_url'):
            message += f"📎 **Bukti:** [Lihat Bukti]({topup['proof_url']})\n"
        
        keyboard = [
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_topup:{topup_id}"),
             InlineKeyboardButton("❌ Reject", callback_data=f"reject_topup:{topup_id}")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_topup")]
        ]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error displaying topup detail: {e}")
        await query.edit_message_text("❌ Gagal mengambil detail topup.")

async def approve_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approve topup"""
    query = update.callback_query
    await query.answer()
    
    try:
        topup_id = int(query.data.split(':')[1])
        
        # Approve topup di database
        success = database.approve_topup(topup_id, query.from_user.id)  # Asumsi function ini ada
        
        if success:
            await log_admin_action(query.from_user.id, "APPROVE_TOPUP", f"Topup ID: {topup_id}")
            
            keyboard = [[InlineKeyboardButton("⬅️ Kembali ke Daftar", callback_data="back_to_topup")]]
            await query.edit_message_text(
                "✅ **TOPUP BERHASIL DIAPPROVE!**\n\n"
                "Saldo user telah ditambahkan.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text("❌ Gagal approve topup.")
            
    except Exception as e:
        logger.error(f"Error approving topup: {e}")
        await query.edit_message_text("❌ Gagal approve topup.")

async def reject_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reject topup"""
    query = update.callback_query
    await query.answer()
    
    try:
        topup_id = int(query.data.split(':')[1])
        
        # Reject topup di database
        success = database.reject_topup(topup_id, query.from_user.id)  # Asumsi function ini ada
        
        if success:
            await log_admin_action(query.from_user.id, "REJECT_TOPUP", f"Topup ID: {topup_id}")
            
            keyboard = [[InlineKeyboardButton("⬅️ Kembali ke Daftar", callback_data="back_to_topup")]]
            await query.edit_message_text(
                "❌ **TOPUP DITOLAK!**\n\n"
                "Topup telah ditolak dan user akan diberitahu.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text("❌ Gagal menolak topup.")
            
    except Exception as e:
        logger.error(f"Error rejecting topup: {e}")
        await query.edit_message_text("❌ Gagal menolak topup.")

# ============================
# FITUR MANAJEMEN SALDO USER
# ============================

async def manage_balance_start(query, context):
    """Memulai manajemen saldo user"""
    keyboard = [
        [InlineKeyboardButton("➕ Tambah Saldo", callback_data="add_balance")],
        [InlineKeyboardButton("➖ Kurangi Saldo", callback_data="subtract_balance")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
    ]
    
    await query.edit_message_text(
        "💰 **KELOLA SALDO USER**\n\n"
        "Pilih aksi yang ingin dilakukan:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return MANAGE_BALANCE

async def manage_balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk manage balance"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data in ['add_balance', 'subtract_balance']:
        context.user_data['balance_action'] = data
        context.user_data['balance_type'] = 'tambah' if data == 'add_balance' else 'kurangi'
        
        # Ambil list user (contoh sederhana, batasi 20 user)
        users = database.get_recent_users(limit=20)  # Asumsi function ini ada
        
        if not users:
            await query.edit_message_text("❌ Tidak ada user yang ditemukan.")
            return MANAGE_BALANCE
            
        keyboard = []
        for user in users:
            btn_text = f"@{user['username']} - Rp {user['balance']:,.0f}" if user['username'] else f"User {user['user_id']} - Rp {user['balance']:,.0f}"
            if len(btn_text) > 30:
                btn_text = btn_text[:27] + "..."
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"select_user_balance:{user['user_id']}")])
        
        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="admin_manage_balance")])
        
        action_text = "menambah" if data == 'add_balance' else "mengurangi"
        await query.edit_message_text(
            f"👤 **PILIH USER UNTUK {action_text.upper()} SALDO**\n\n"
            f"Pilih user dari daftar di bawah:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return CHOOSE_USER_BALANCE
        
    elif data == "admin_back":
        await admin_menu_from_query(query, context)
        return ConversationHandler.END
        
    return MANAGE_BALANCE

async def select_user_balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memilih user"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('select_user_balance:'):
        user_id = query.data.split(':')[1]
        context.user_data['selected_user_id'] = user_id
        
        user_info = database.get_user_info(user_id)
        if not user_info:
            await query.edit_message_text("❌ User tidak ditemukan.")
            return MANAGE_BALANCE
            
        context.user_data['selected_user_info'] = user_info
        
        action_type = context.user_data.get('balance_type', 'tambah')
        await query.edit_message_text(
            f"💰 **{action_type.upper()} SALDO**\n\n"
            f"👤 **User:** {user_info.get('full_name', 'N/A')}\n"
            f"📱 **Username:** @{user_info.get('username', 'N/A')}\n"
            f"💳 **Saldo Saat Ini:** Rp {user_info.get('balance', 0):,.0f}\n\n"
            f"Silakan masukkan nominal yang ingin di{action_type} (hanya angka):",
            parse_mode='Markdown'
        )
        return INPUT_AMOUNT
        
    return CHOOSE_USER_BALANCE

async def input_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk input jumlah saldo"""
    if not await admin_check(update, context):
        return ConversationHandler.END
        
    try:
        amount_text = update.message.text.replace(',', '').replace('.', '').strip()
        amount = float(amount_text)
        
        if amount <= 0:
            await update.message.reply_text("❌ Nominal harus lebih dari 0. Silakan coba lagi:")
            return INPUT_AMOUNT
            
        if amount > 10000000:  # Max 10 juta
            await update.message.reply_text("❌ Nominal terlalu besar. Maksimal Rp 10.000.000. Silakan coba lagi:")
            return INPUT_AMOUNT
            
    except ValueError:
        await update.message.reply_text("❌ Format nominal tidak valid. Kirim hanya angka. Silakan coba lagi:")
        return INPUT_AMOUNT
        
    context.user_data['amount'] = amount
    
    user_info = context.user_data.get('selected_user_info', {})
    action_type = context.user_data.get('balance_type', 'tambah')
    current_balance = user_info.get('balance', 0)
    
    if action_type == 'tambah':
        new_balance = current_balance + amount
        action_text = "ditambahkan"
    else:
        new_balance = current_balance - amount
        if new_balance < 0:
            await update.message.reply_text("❌ Saldo user tidak cukup untuk dikurangi. Silakan masukkan nominal yang lebih kecil:")
            return INPUT_AMOUNT
        action_text = "dikurangi"
    
    keyboard = [
        [InlineKeyboardButton("✅ Konfirmasi", callback_data="confirm_balance")],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel_balance")]
    ]
    
    await update.message.reply_text(
        f"🔍 **KONFIRMASI {action_type.upper()} SALDO**\n\n"
        f"👤 **User:** {user_info.get('full_name', 'N/A')}\n"
        f"📱 **Username:** @{user_info.get('username', 'N/A')}\n\n"
        f"💰 **Saldo Saat Ini:** Rp {current_balance:,.0f}\n"
        f"📥 **Nominal {action_type.title()}:** Rp {amount:,.0f}\n"
        f"💳 **Saldo Baru:** Rp {new_balance:,.0f}\n\n"
        f"Apakah Anda yakin ingin {action_text} saldo?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return CONFIRM_BALANCE

async def confirm_balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk konfirmasi perubahan saldo"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_balance":
        user_id = context.user_data.get('selected_user_id')
        amount = context.user_data.get('amount', 0)
        action_type = context.user_data.get('balance_type', 'tambah')
        user_info = context.user_data.get('selected_user_info', {})
        
        try:
            if action_type == 'tambah':
                success = database.add_user_balance(user_id, amount)  # Asumsi function ini ada
                action_log = "ADD_BALANCE"
            else:
                success = database.subtract_user_balance(user_id, amount)  # Asumsi function ini ada
                action_log = "SUBTRACT_BALANCE"
            
            if success:
                await log_admin_action(query.from_user.id, action_log, 
                                     f"User: {user_id}, Amount: {amount}")
                
                keyboard = [
                    [InlineKeyboardButton("💰 Kelola Saldo Lain", callback_data="admin_manage_balance")],
                    [InlineKeyboardButton("🏠 Menu Admin", callback_data="admin_back")]
                ]
                
                action_text = "ditambahkan" if action_type == 'tambah' else "dikurangi"
                await query.edit_message_text(
                    f"✅ **SALDO BERHASIL DI{action_type.upper()}!**\n\n"
                    f"👤 **User:** {user_info.get('full_name', 'N/A')}\n"
                    f"💰 **Nominal:** Rp {amount:,.0f} {action_text}\n\n"
                    f"Saldo user telah berhasil diperbarui.",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ Gagal mengupdate saldo user.")
                
        except Exception as e:
            logger.error(f"Error updating balance: {e}")
            await query.edit_message_text("❌ Gagal mengupdate saldo user.")
            
    elif query.data == "cancel_balance":
        await query.edit_message_text("❌ Perubahan saldo dibatalkan.")
    
    # Cleanup user data
    context.user_data.clear()
    
    return ConversationHandler.END

async def cancel_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel manajemen saldo"""
    await update.message.reply_text("❌ Manajemen saldo dibatalkan.")
    
    # Cleanup user data
    context.user_data.clear()
    
    return ConversationHandler.END

# ============================
# FITUR MANAJEMEN USER
# ============================

async def show_users_menu(query, context):
    """Menampilkan menu manajemen user"""
    try:
        # Ambil statistik user
        stats = database.get_user_statistics()  # Asumsi function ini ada
        
        keyboard = [
            [InlineKeyboardButton("👥 List User", callback_data="list_users")],
            [InlineKeyboardButton("👑 List Admin", callback_data="list_admins")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_users")],
            [InlineKeyboardButton("🏠 Menu Admin", callback_data="admin_back")]
        ]
        
        await query.edit_message_text(
            f"👥 **MANAJEMEN USER**\n\n"
            f"📊 **Statistik User:**\n"
            f"├ Total User: {stats.get('total_users', 0)}\n"
            f"├ User Aktif: {stats.get('active_users', 0)}\n"
            f"├ Total Admin: {stats.get('total_admins', 0)}\n"
            f"└ Saldo Total: Rp {stats.get('total_balance', 0):,.0f}\n\n"
            f"Pilih opsi di bawah:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error showing users menu: {e}")
        await query.edit_message_text("❌ Gagal memuat menu user.")

async def user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan detail user"""
    query = update.callback_query
    await query.answer()
    
    try:
        user_id = query.data.split(':')[1]
        
        user_info = database.get_user_info(user_id)
        if not user_info:
            await query.edit_message_text("❌ User tidak ditemukan.")
            return
            
        is_admin = database.is_user_admin(user_id)  # Asumsi function ini ada
        
        status_text = "🟢 AKTIF" if user_info.get('is_active', True) else "🔴 NONAKTIF"
        admin_text = "✅ ADMIN" if is_admin else "❌ BUKAN ADMIN"
        
        message = (
            f"👤 **DETAIL USER**\n\n"
            f"🆔 **User ID:** {user_id}\n"
            f"👨‍💼 **Nama:** {user_info.get('full_name', 'Tidak ada')}\n"
            f"📱 **Username:** @{user_info.get('username', 'Tidak ada')}\n"
            f"💰 **Saldo:** Rp {user_info.get('balance', 0):,.0f}\n"
            f"📊 **Status:** {status_text}\n"
            f"👑 **Role:** {admin_text}\n"
            f"📅 **Bergabung:** {user_info.get('created_at', 'Tidak diketahui')}\n"
            f"🕒 **Aktif Terakhir:** {user_info.get('last_active', 'Tidak diketahui')}\n"
        )
        
        keyboard = []
        if not is_admin:
            keyboard.append([InlineKeyboardButton("👑 Jadikan Admin", callback_data=f"make_admin:{user_id}")])
        else:
            keyboard.append([InlineKeyboardButton("❌ Hapus Admin", callback_data=f"remove_admin:{user_id}")])
        
        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_users")])
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error showing user detail: {e}")
        await query.edit_message_text("❌ Gagal mengambil detail user.")

async def make_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jadikan user sebagai admin"""
    query = update.callback_query
    await query.answer()
    
    try:
        user_id = query.data.split(':')[1]
        
        success = database.make_user_admin(user_id)  # Asumsi function ini ada
        
        if success:
            await log_admin_action(query.from_user.id, "MAKE_ADMIN", f"User: {user_id}")
            
            # Update config
            if user_id not in config.ADMIN_TELEGRAM_IDS:
                config.ADMIN_TELEGRAM_IDS.append(user_id)
            
            keyboard = [[InlineKeyboardButton("⬅️ Kembali", callback_data=f"user_detail:{user_id}")]]
            await query.edit_message_text(
                "✅ **USER BERHASIL DIJADIKAN ADMIN!**\n\n"
                "User sekarang memiliki akses ke menu admin.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text("❌ Gagal menjadikan user sebagai admin.")
            
    except Exception as e:
        logger.error(f"Error making admin: {e}")
        await query.edit_message_text("❌ Gagal menjadikan user sebagai admin.")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hapus user dari admin"""
    query = update.callback_query
    await query.answer()
    
    try:
        user_id = query.data.split(':')[1]
        
        # Jangan biarkan menghapus diri sendiri
        if user_id == str(query.from_user.id):
            await query.answer("❌ Tidak bisa menghapus diri sendiri sebagai admin!", show_alert=True)
            return
            
        success = database.remove_user_admin(user_id)  # Asumsi function ini ada
        
        if success:
            await log_admin_action(query.from_user.id, "REMOVE_ADMIN", f"User: {user_id}")
            
            # Update config
            if user_id in config.ADMIN_TELEGRAM_IDS:
                config.ADMIN_TELEGRAM_IDS.remove(user_id)
            
            keyboard = [[InlineKeyboardButton("⬅️ Kembali", callback_data=f"user_detail:{user_id}")]]
            await query.edit_message_text(
                "❌ **ADMIN BERHASIL DIHAPUS!**\n\n"
                "User tidak lagi memiliki akses ke menu admin.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text("❌ Gagal menghapus user dari admin.")
            
    except Exception as e:
        logger.error(f"Error removing admin: {e}")
        await query.edit_message_text("❌ Gagal menghapus user dari admin.")

# ============================
# FITUR STATISTIK
# ============================

async def show_stats_menu(query, context):
    """Menampilkan menu statistik"""
    try:
        stats = database.get_bot_statistics()  # Asumsi function ini ada
        
        message = (
            f"📊 **STATISTIK BOT**\n\n"
            f"👥 **USER:**\n"
            f"├ Total User: {stats.get('total_users', 0)}\n"
            f"├ User Aktif: {stats.get('active_users', 0)}\n"
            f"└ User Baru (Hari Ini): {stats.get('new_users_today', 0)}\n\n"
            f"🛒 **PRODUK & ORDER:**\n"
            f"├ Produk Aktif: {stats.get('active_products', 0)}\n"
            f"├ Total Order: {stats.get('total_orders', 0)}\n"
            f"├ Order Hari Ini: {stats.get('orders_today', 0)}\n"
            f"└ Success Rate: {stats.get('success_rate', 0)}%\n\n"
            f"💰 **KEUANGAN:**\n"
            f"├ Total Revenue: Rp {stats.get('total_revenue', 0):,.0f}\n"
            f"├ Revenue Hari Ini: Rp {stats.get('revenue_today', 0):,.0f}\n"
            f"├ Total Topup: Rp {stats.get('total_topup', 0):,.0f}\n"
            f"└ Topup Pending: {stats.get('pending_topups', 0)}\n\n"
            f"🔄 **UPDATE TERAKHIR:**\n"
            f"└ {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_stats")],
            [InlineKeyboardButton("🏠 Menu Admin", callback_data="admin_back")]
        ]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error showing stats: {e}")
        await query.edit_message_text("❌ Gagal memuat statistik.")

# ============================
# FITUR BACKUP DATABASE
# ============================

async def backup_database_from_query(query, context):
    """Backup database"""
    try:
        await query.edit_message_text("💾 Membuat backup database...")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = "backups"
        backup_file = f"{backup_dir}/backup_{timestamp}.db"
        
        # Buat directory backups jika belum ada
        os.makedirs(backup_dir, exist_ok=True)
        
        # Copy database file
        shutil.copy2(DB_PATH, backup_file)
        
        # Juga backup sebagai SQL dump
        sql_file = f"{backup_dir}/backup_{timestamp}.sql"
        await create_sql_dump(sql_file)
        
        # Hitung size
        file_size = os.path.getsize(backup_file) / 1024  # KB
        
        await log_admin_action(query.from_user.id, "BACKUP_DATABASE", f"File: {backup_file}")
        
        keyboard = [
            [InlineKeyboardButton("🏠 Menu Admin", callback_data="admin_back")]
        ]
        
        await query.edit_message_text(
            f"✅ **BACKUP BERHASIL!**\n\n"
            f"📁 **File:** backup_{timestamp}.db\n"
            f"📊 **Size:** {file_size:.2f} KB\n"
            f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}\n\n"
            f"Backup disimpan di folder `backups/`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        await query.edit_message_text("❌ Gagal membuat backup database.")

async def create_sql_dump(sql_file):
    """Membuat SQL dump dari database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        with open(sql_file, 'w', encoding='utf-8') as f:
            for line in conn.iterdump():
                f.write(f'{line}\n')
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error creating SQL dump: {e}")
        return False

# ============================
# FITUR BROADCAST
# ============================

async def broadcast_start(query, context):
    """Memulai broadcast message"""
    await query.edit_message_text(
        "📢 **BROADCAST MESSAGE**\n\n"
        "Kirim pesan yang ingin di-broadcast ke semua user:\n\n"
        "⚠️ **Peringatan:** Pastikan pesan sudah benar sebelum dikirim!",
        parse_mode='Markdown'
    )
    return BROADCAST_MESSAGE

async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk broadcast message"""
    if not await admin_check(update, context):
        return ConversationHandler.END
        
    message_text = update.message.text
    user_id = update.message.from_user.id
    
    if not message_text or len(message_text.strip()) == 0:
        await update.message.reply_text("❌ Pesan tidak boleh kosong. Silakan kirim pesan yang valid:")
        return BROADCAST_MESSAGE
    
    # Konfirmasi broadcast
    context.user_data['broadcast_message'] = message_text
    
    keyboard = [
        [InlineKeyboardButton("✅ Ya, Broadcast", callback_data="confirm_broadcast")],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel_broadcast")]
    ]
    
    await update.message.reply_text(
        f"🔍 **KONFIRMASI BROADCAST**\n\n"
        f"**Pesan yang akan dikirim:**\n"
        f"{message_text}\n\n"
        f"**Estimasi:**\n"
        f"• Dikirim ke semua user aktif\n"
        f"• Proses mungkin memakan waktu beberapa menit\n\n"
        f"Apakah Anda yakin ingin melanjutkan?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Konfirmasi dan jalankan broadcast"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_broadcast":
        message_text = context.user_data.get('broadcast_message', '')
        
        if not message_text:
            await query.edit_message_text("❌ Pesan broadcast tidak ditemukan.")
            return
            
        await query.edit_message_text("📢 Mengirim broadcast ke semua user...\n\n⏰ Mohon tunggu...")
        
        try:
            # Ambil semua user aktif
            active_users = database.get_active_users()  # Asumsi function ini ada
            
            success_count = 0
            fail_count = 0
            
            for user in active_users:
                try:
                    await context.bot.send_message(
                        chat_id=user['user_id'],
                        text=message_text,
                        parse_mode='Markdown'
                    )
                    success_count += 1
                    
                    # Delay kecil untuk avoid rate limit
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.warning(f"Failed to send broadcast to {user['user_id']}: {e}")
                    fail_count += 1
            
            await log_admin_action(query.from_user.id, "BROADCAST", 
                                 f"Success: {success_count}, Failed: {fail_count}")
            
            keyboard = [[InlineKeyboardButton("🏠 Menu Admin", callback_data="admin_back")]]
            
            await query.edit_message_text(
                f"✅ **BROADCAST SELESAI!**\n\n"
                f"📊 **Statistik Pengiriman:**\n"
                f"├ Berhasil: {success_count} user\n"
                f"├ Gagal: {fail_count} user\n"
                f"└ Total: {success_count + fail_count} user\n\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error during broadcast: {e}")
            await query.edit_message_text("❌ Terjadi error saat broadcast.")
            
    elif query.data == "cancel_broadcast":
        await query.edit_message_text("❌ Broadcast dibatalkan.")
    
    # Cleanup
    context.user_data.clear()
    
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel broadcast"""
    await update.message.reply_text("❌ Broadcast dibatalkan.")
    
    # Cleanup
    context.user_data.clear()
    
    return ConversationHandler.END

# ============================
# FITUR SYSTEM HEALTH
# ============================

async def system_health_from_query(query, context):
    """Menampilkan system health"""
    try:
        # Ambil berbagai statistik sistem
        db_size = os.path.getsize(DB_PATH) / (1024 * 1024)  # MB
        
        # Hitung log size
        log_size = 0
        if os.path.exists('bot.log'):
            log_size = os.path.getsize('bot.log') / 1024  # KB
        
        # Ambil info dari database
        stats = database.get_bot_statistics()
        
        # Check API status (contoh sederhana)
        api_status = "✅ ONLINE"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://panel.khfy-store.com/", timeout=10) as resp:
                    if resp.status != 200:
                        api_status = "⚠️ DEGRADED"
        except:
            api_status = "❌ OFFLINE"
        
        message = (
            f"🏥 **SYSTEM HEALTH**\n\n"
            f"🖥️ **SERVER:**\n"
            f"├ Database Size: {db_size:.2f} MB\n"
            f"├ Log Size: {log_size:.2f} KB\n"
            f"├ API Provider: {api_status}\n"
            f"└ Bot Status: ✅ ONLINE\n\n"
            f"📊 **PERFORMANCE:**\n"
            f"├ Total Users: {stats.get('total_users', 0)}\n"
            f"├ Active Products: {stats.get('active_products', 0)}\n"
            f"├ Pending Topups: {stats.get('pending_topups', 0)}\n"
            f"└ Success Rate: {stats.get('success_rate', 0)}%\n\n"
            f"🛠️ **MAINTENANCE:**\n"
            f"├ Last Backup: {get_last_backup_time()}\n"
            f"├ Last Update: {stats.get('last_update', 'N/A')}\n"
            f"└ System Time: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_health")],
            [InlineKeyboardButton("💾 Backup Now", callback_data="admin_backup")],
            [InlineKeyboardButton("🏠 Menu Admin", callback_data="admin_back")]
        ]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error showing system health: {e}")
        await query.edit_message_text("❌ Gagal memuat system health.")

def get_last_backup_time():
    """Mendapatkan waktu backup terakhir"""
    try:
        backup_dir = "backups"
        if not os.path.exists(backup_dir):
            return "Belum ada backup"
            
        backups = [f for f in os.listdir(backup_dir) if f.endswith('.db')]
        if not backups:
            return "Belum ada backup"
            
        latest_backup = max(backups)
        return latest_backup.replace('backup_', '').replace('.db', '')
    except:
        return "Error"

# ============================
# FITUR CLEANUP DATA
# ============================

async def cleanup_data_from_query(query, context):
    """Memulai cleanup data"""
    keyboard = [
        [InlineKeyboardButton("🗑️ Hapus User Nonaktif", callback_data="cleanup_inactive_users")],
        [InlineKeyboardButton("📉 Hapus Log Lama", callback_data="cleanup_old_logs")],
        [InlineKeyboardButton("📦 Hapus Produk Inactive", callback_data="cleanup_inactive_products")],
        [InlineKeyboardButton("🔄 Refresh Stats", callback_data="admin_cleanup")],
        [InlineKeyboardButton("🏠 Menu Admin", callback_data="admin_back")]
    ]
    
    # Hitung statistik cleanup
    try:
        inactive_users = database.count_inactive_users()  # Asumsi function ini ada
        inactive_products = database.count_inactive_products()  # Asumsi function ini ada
        
        stats_text = (
            f"📊 **Data yang bisa dibersihkan:**\n"
            f"├ User Nonaktif: {inactive_users}\n"
            f"└ Produk Inactive: {inactive_products}\n\n"
        )
    except:
        stats_text = ""
    
    await query.edit_message_text(
        f"🧹 **CLEANUP DATA**\n\n{stats_text}"
        "Pilih jenis cleanup yang ingin dilakukan:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return CLEANUP_CONFIRM

async def cleanup_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk cleanup data"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cleanup_inactive_users":
        context.user_data['cleanup_type'] = 'inactive_users'
        await query.edit_message_text(
            "🗑️ **HAPUS USER NONAKTIF**\n\n"
            "Aksi ini akan menghapus user yang tidak aktif dalam 30 hari terakhir.\n\n"
            "Apakah Anda yakin ingin melanjutkan?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Ya, Hapus", callback_data="confirm_cleanup")],
                [InlineKeyboardButton("❌ Batal", callback_data="cancel_cleanup")]
            ]),
            parse_mode='Markdown'
        )
        
    elif data == "cleanup_inactive_products":
        context.user_data['cleanup_type'] = 'inactive_products'
        await query.edit_message_text(
            "📦 **HAPUS PRODUK INACTIVE**\n\n"
            "Aksi ini akan menghapus produk yang berstatus inactive.\n\n"
            "Apakah Anda yakin ingin melanjutkan?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Ya, Hapus", callback_data="confirm_cleanup")],
                [InlineKeyboardButton("❌ Batal", callback_data="cancel_cleanup")]
            ]),
            parse_mode='Markdown'
        )
        
    elif data == "cleanup_old_logs":
        context.user_data['cleanup_type'] = 'old_logs'
        await query.edit_message_text(
            "📉 **HAPUS LOG LAMA**\n\n"
            "Aksi ini akan menghapus log file yang lebih dari 30 hari.\n\n"
            "Apakah Anda yakin ingin melanjutkan?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Ya, Hapus", callback_data="confirm_cleanup")],
                [InlineKeyboardButton("❌ Batal", callback_data="cancel_cleanup")]
            ]),
            parse_mode='Markdown'
        )
        
    elif data == "admin_back":
        await admin_menu_from_query(query, context)
        return ConversationHandler.END
        
    return CLEANUP_CONFIRM

async def confirm_cleanup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Konfirmasi dan jalankan cleanup"""
    query = update.callback_query
    await query.answer()
    
    cleanup_type = context.user_data.get('cleanup_type')
    
    if not cleanup_type:
        await query.edit_message_text("❌ Jenis cleanup tidak valid.")
        return ConversationHandler.END
    
    try:
        deleted_count = 0
        
        if cleanup_type == 'inactive_users':
            deleted_count = database.delete_inactive_users()  # Asumsi function ini ada
            action_text = "user nonaktif"
            
        elif cleanup_type == 'inactive_products':
            deleted_count = database.delete_inactive_products()  # Asumsi function ini ada
            action_text = "produk inactive"
            
        elif cleanup_type == 'old_logs':
            deleted_count = await cleanup_old_logs()
            action_text = "log file"
        
        await log_admin_action(query.from_user.id, f"CLEANUP_{cleanup_type.upper()}", 
                             f"Deleted: {deleted_count} items")
        
        keyboard = [
            [InlineKeyboardButton("🧹 Cleanup Lain", callback_data="admin_cleanup")],
            [InlineKeyboardButton("🏠 Menu Admin", callback_data="admin_back")]
        ]
        
        await query.edit_message_text(
            f"✅ **CLEANUP BERHASIL!**\n\n"
            f"🗑️ **{deleted_count}** {action_text} telah dihapus.\n\n"
            f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        await query.edit_message_text("❌ Gagal melakukan cleanup.")
    
    # Cleanup
    context.user_data.clear()
    
    return ConversationHandler.END

async def cleanup_old_logs():
    """Cleanup log files yang lama"""
    try:
        deleted_count = 0
        log_dir = "."
        
        for filename in os.listdir(log_dir):
            if filename.endswith('.log'):
                filepath = os.path.join(log_dir, filename)
                # Hapus file log yang lebih dari 30 hari
                if os.path.getmtime(filepath) < (datetime.now().timestamp() - 30 * 24 * 60 * 60):
                    os.remove(filepath)
                    deleted_count += 1
        
        return deleted_count
    except Exception as e:
        logger.error(f"Error cleaning up old logs: {e}")
        return 0

async def cancel_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel cleanup"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text("❌ Cleanup dibatalkan.")
    
    # Cleanup
    context.user_data.clear()
    
    return ConversationHandler.END

# ============================
# CONVERSATION HANDLERS
# ============================

# Edit Produk Conversation Handler
edit_produk_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(edit_produk_start_from_query, pattern="^admin_edit_produk$")],
    states={
        EDIT_MENU: [CallbackQueryHandler(edit_produk_menu_handler, pattern="^(edit_harga|edit_deskripsi|admin_back|back_to_edit_menu)$")],
        CHOOSE_PRODUCT: [CallbackQueryHandler(select_product_handler, pattern="^select_product:")],
        EDIT_HARGA: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_harga_handler)],
        EDIT_DESKRIPSI: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_deskripsi_handler)],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_edit),
        CallbackQueryHandler(cancel_edit, pattern="^admin_back$")
    ],
    map_to_parent={
        ConversationHandler.END: ConversationHandler.END
    }
)

# Manage Balance Conversation Handler
manage_balance_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(manage_balance_start, pattern="^admin_manage_balance$")],
    states={
        MANAGE_BALANCE: [CallbackQueryHandler(manage_balance_handler, pattern="^(add_balance|subtract_balance|admin_back)$")],
        CHOOSE_USER_BALANCE: [CallbackQueryHandler(select_user_balance_handler, pattern="^select_user_balance:")],
        INPUT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_amount_handler)],
        CONFIRM_BALANCE: [CallbackQueryHandler(confirm_balance_handler, pattern="^(confirm_balance|cancel_balance)$")],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_balance),
        MessageHandler(filters.COMMAND, cancel_balance)
    ],
    map_to_parent={
        ConversationHandler.END: ConversationHandler.END
    }
)

# Broadcast Conversation Handler
broadcast_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(broadcast_start, pattern="^admin_broadcast$")],
    states={
        BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler)],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_broadcast),
        CallbackQueryHandler(confirm_broadcast, pattern="^(confirm_broadcast|cancel_broadcast)$")
    ],
    map_to_parent={
        ConversationHandler.END: ConversationHandler.END
    }
)

# Cleanup Conversation Handler
cleanup_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(cleanup_data_from_query, pattern="^admin_cleanup$")],
    states={
        CLEANUP_CONFIRM: [CallbackQueryHandler(cleanup_data_handler, pattern="^(cleanup_inactive_users|cleanup_inactive_products|cleanup_old_logs|admin_back)$")],
    },
    fallbacks=[
        CallbackQueryHandler(confirm_cleanup_handler, pattern="^confirm_cleanup$"),
        CallbackQueryHandler(cancel_cleanup, pattern="^cancel_cleanup$")
    ],
    map_to_parent={
        ConversationHandler.END: ConversationHandler.END
    }
)

# ============================
# COMMAND HANDLERS
# ============================

def get_admin_handlers():
    """Mengembalikan semua handler admin"""
    return [
        edit_produk_conv_handler,
        manage_balance_conv_handler,
        broadcast_conv_handler,
        cleanup_conv_handler,
        CallbackQueryHandler(admin_callback_handler, pattern="^admin_|^topup_|^user_|^make_|^remove_|^approve_|^reject_|^back_|^confirm_|^cancel_|^cleanup_")
    ]

# ============================
# EXPORT FUNCTIONS
# ============================

__all__ = [
    'admin_menu',
    'admin_callback_handler',
    'edit_produk_conv_handler',
    'manage_balance_conv_handler',
    'broadcast_conv_handler',
    'cleanup_conv_handler',
    'get_admin_handlers'
]

if __name__ == "__main__":
    print("✅ Admin Handler loaded successfully!")
    print("Available features:")
    print("- Product Management (Update, List, Edit)")
    print("- Topup Management (Approve/Reject)")
    print("- User Management (Balance, Admin rights)")
    print("- Statistics & Analytics")
    print("- Database Backup")
    print("- Broadcast Messages")
    print("- System Health Monitoring")
    print("- Data Cleanup")
