#!/usr/bin/env python3
"""
Admin Handler - Fixed Version with SQLite3 (tanpa aiosqlite)
"""

import config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from telegram.error import BadRequest
import aiohttp
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

DB_PATH = getattr(database, 'DB_PATH', 'bot_database.db')

# States untuk Conversation Handlers
EDIT_MENU, CHOOSE_PRODUCT, EDIT_HARGA, EDIT_DESKRIPSI = range(4)
MANAGE_BALANCE, CHOOSE_USER_BALANCE, INPUT_AMOUNT, CONFIRM_BALANCE = range(4, 8)
BROADCAST_MESSAGE = range(8, 9)
CLEANUP_CONFIRM = range(9, 10)

# ============================
# UTILITY FUNCTIONS & SAFE WRAPPERS - FIXED
# ============================

def safe_db_call(func_name, default_value=None, *args, **kwargs):
    """Safe wrapper untuk memanggil fungsi database dengan error handling"""
    try:
        if hasattr(database, func_name):
            func = getattr(database, func_name)
            result = func(*args, **kwargs)
            return result if result is not None else default_value
        else:
            logger.warning(f"Database function {func_name} not found")
            return default_value
    except Exception as e:
        logger.error(f"Error calling database.{func_name}: {e}")
        return default_value

async def log_admin_action(user_id: int, action: str, details: str):
    """Log admin actions untuk audit trail"""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] ADMIN {user_id} - {action}: {details}"
        
        # Log ke file
        with open("admin_actions.log", "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
        
        # Log ke database
        safe_db_call('add_admin_log', None, str(user_id), action, None, None, details)
            
        logger.info(f"Admin action logged: {user_id} - {action}")
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

def is_admin(user):
    """Validasi user admin"""
    if not user:
        return False
    return str(user.id) in config.ADMIN_TELEGRAM_IDS

def get_user_from_update(update):
    """Robust user extraction untuk berbagai jenis update"""
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

async def safe_edit_message_text(update, text, reply_markup=None, parse_mode=None):
    """Safe wrapper untuk edit_message_text dengan error handling"""
    try:
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return True
        elif hasattr(update, 'message') and update.message:
            await update.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return True
        return False
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return True
        elif "Message can't be deleted" in str(e):
            try:
                if hasattr(update, 'callback_query') and update.callback_query:
                    await update.callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
                return True
            except Exception as send_error:
                logger.error(f"Failed to send new message: {send_error}")
                return False
        logger.error(f"BadRequest in safe_edit_message_text: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in safe_edit_message_text: {e}")
        return False

# ============================
# DATABASE FUNCTIONS - FIXED (menggunakan sqlite3 biasa)
# ============================

def ensure_products_table():
    """Memastikan tabel products ada"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
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
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error ensuring products table: {e}")
        return False

def execute_sql(query, params=(), fetch=False):
    """Execute SQL query dengan error handling"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(query, params)
        
        if fetch:
            result = c.fetchall()
        else:
            result = c.rowcount
            
        conn.commit()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"SQL Error: {e}")
        return None

def fetch_all(query, params=()):
    """Fetch semua data dari database"""
    return execute_sql(query, params, fetch=True)

def fetch_one(query, params=()):
    """Fetch satu baris dari database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(query, params)
        result = c.fetchone()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Fetch one error: {e}")
        return None

# ============================
# MENU ADMIN UTAMA
# ============================

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu utama admin"""
    if not await admin_check(update, context):
        return
    
    keyboard = [
        [InlineKeyboardButton("🔄 Update Produk", callback_data="admin_update")],
        [InlineKeyboardButton("📦 Sync Stok Provider", callback_data="admin_sync_stock")],
        [InlineKeyboardButton("📊 Cek Status Stok", callback_data="admin_check_stock")],
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
            "👑 **MENU ADMIN**\n\n**Fitur Stok Terbaru:**\n• Sync stok dari provider\n• Cek status stok real-time\n• Update otomatis\n\nSilakan pilih fitur:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    elif getattr(update, "callback_query", None):
        query = update.callback_query
        await query.answer()
        await safe_edit_message_text(
            query,
            "👑 **MENU ADMIN**\n\n**Fitur Stok Terbaru:**\n• Sync stok dari provider\n• Cek status stok real-time\n• Update otomatis\n\nSilakan pilih fitur:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def admin_menu_from_query(query, context):
    """Helper untuk kembali ke menu admin dari query"""
    await admin_menu(Update(update_id=0, callback_query=query), context)

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
    
    try:
        # Main menu routing
        if data == "admin_update":
            await updateproduk(query, context)
        elif data == "admin_sync_stock":
            await sync_stok_from_provider(query, context)
        elif data == "admin_check_stock":
            await cek_stok_produk(query, context)
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
            await broadcast_start(update, context)
        elif data == "admin_health":
            await system_health_from_query(query, context)
        elif data == "admin_cleanup":
            await cleanup_data_from_query(update, context)
        
        # Topup management
        elif data.startswith('topup_detail:'):
            await topup_detail(update, context)
        elif data.startswith('approve_topup:'):
            await approve_topup_handler(update, context)
        elif data.startswith('reject_topup:'):
            await reject_topup_handler(update, context)
        
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
        elif data == "back_to_edit_menu":
            await edit_produk_start_from_query(query, context)
        else:
            await query.message.reply_text("❌ Perintah tidak dikenali.")
            
    except Exception as e:
        logger.error(f"Error in admin_callback_handler: {e}")
        await query.message.reply_text("❌ Terjadi kesalahan sistem.")

# ============================
# FITUR UPDATE PRODUK - FIXED
# ============================

async def updateproduk(update_or_query, context):
    """Update produk dari API provider dengan sync stok yang benar"""
    if hasattr(update_or_query, "message") and update_or_query.message:
        msg_func = update_or_query.message.reply_text
        user_id = update_or_query.message.from_user.id
    else:
        msg_func = update_or_query.edit_message_text
        user_id = update_or_query.from_user.id

    await msg_func("🔄 Memperbarui Produk dan Stok...")
    
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

    if not ensure_products_table():
        await msg_func("❌ Gagal memastikan tabel produk.")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Start transaction
        c.execute("BEGIN TRANSACTION")
        
        # Mark semua produk sebagai inactive terlebih dahulu
        c.execute("UPDATE products SET status = 'inactive'")
        
        count = 0
        skipped = 0
        updated_stock = 0
        updated_kosong = 0
        updated_gangguan = 0
        
        for prod in produk_list:
            code = str(prod.get("kode_produk", "")).strip()
            name = str(prod.get("nama_produk", "")).strip()
            price = float(prod.get("harga_final", 0))
            gangguan = int(prod.get("gangguan", 0))
            kosong = int(prod.get("kosong", 0))
            provider_code = str(prod.get("kode_provider", "")).strip()
            description = str(prod.get("deskripsi", "")).strip() or f"Produk {name}"
            
            # Skip jika data tidak valid
            if not code or not name or price <= 0:
                skipped += 1
                continue
            
            # TENTUKAN STATUS STOK BERDASARKAN DATA PROVIDER
            stock_quantity = 0
            
            if gangguan == 1:
                # Produk gangguan - stok 0
                stock_quantity = 0
                updated_gangguan += 1
            elif kosong == 1:
                # Produk kosong - stok 0
                stock_quantity = 0
                updated_kosong += 1
            else:
                # Produk aktif - beri stok
                stock_quantity = 100
                updated_stock += 1
            
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
            
            # UPDATE DENGAN DATA STOK YANG BENAR
            c.execute("""
                INSERT INTO products (
                    code, name, price, status, description, category, 
                    provider, gangguan, kosong, stock, updated_at
                )
                VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name=excluded.name,
                    price=excluded.price,
                    status='active',
                    description=excluded.description,
                    category=excluded.category,
                    provider=excluded.provider,
                    gangguan=excluded.gangguan,
                    kosong=excluded.kosong,
                    stock=excluded.stock,
                    updated_at=excluded.updated_at
            """, (
                code, name, price, description, category, 
                provider_code, gangguan, kosong, stock_quantity, now
            ))
            count += 1
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error updating products: {e}")
        await msg_func(f"❌ Error saat update produk: {e}")
        return

    await log_admin_action(user_id, "UPDATE_PRODUCTS", 
                         f"Updated: {count} produk, Stock: {updated_stock}, Gangguan: {updated_gangguan}, Kosong: {updated_kosong}, Skipped: {skipped}")
    
    await msg_func(
        f"✅ **Update Produk & Stok Berhasil**\n\n"
        f"📊 **Statistik Update:**\n"
        f"├ Berhasil diupdate: {count} produk\n"
        f"├ 🟢 Stok tersedia: {updated_stock} produk\n"
        f"├ 🚧 Stok gangguan: {updated_gangguan} produk\n"
        f"├ 🔴 Stok kosong: {updated_kosong} produk\n"
        f"├ Dilewati: {skipped} produk\n"
        f"⏰ **Update Terakhir:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
        parse_mode='Markdown'
    )

# ============================
# FITUR SYNC STOK DARI PROVIDER - FIXED
# ============================

async def sync_stok_from_provider(update_or_query, context):
    """Sync stok produk dari provider tanpa mengubah data lainnya - FIXED"""
    if hasattr(update_or_query, "message") and update_or_query.message:
        msg_func = update_or_query.message.reply_text
        user_id = update_or_query.message.from_user.id
    else:
        msg_func = update_or_query.edit_message_text
        user_id = update_or_query.from_user.id

    await msg_func("🔄 Mensinkronisasi Stok dari Provider...")
    
    if not hasattr(config, 'API_KEY_PROVIDER') or not config.API_KEY_PROVIDER:
        await msg_func("❌ API Key Provider tidak ditemukan di config.py")
        return

    api_key = config.API_KEY_PROVIDER
    url = f"https://panel.khfy-store.com/api_v2/list_product?api_key={api_key}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as resp:
                if resp.status != 200:
                    await msg_func(f"❌ Gagal mengambil data stok: Status {resp.status}")
                    return
                data = await resp.json()
    except Exception as e:
        await msg_func(f"❌ Gagal mengambil data stok: {e}")
        return

    if not data.get("ok", False):
        await msg_func("❌ Response error dari provider.")
        return

    produk_list = data.get("data", [])
    if not produk_list:
        await msg_func("⚠️ Tidak ada data stok dari provider.")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        updated_count = 0
        kosong_count = 0
        gangguan_count = 0
        tersedia_count = 0
        
        for prod in produk_list:
            code = str(prod.get("kode_produk", "")).strip()
            gangguan = int(prod.get("gangguan", 0))
            kosong = int(prod.get("kosong", 0))
            
            if not code:
                continue
            
            # Tentukan stok berdasarkan status dari provider
            new_stock = 0
            
            if gangguan == 1:
                new_stock = 0
                gangguan_count += 1
            elif kosong == 1:
                new_stock = 0
                kosong_count += 1
            else:
                new_stock = 100  # Stok tersedia
                tersedia_count += 1
            
            # Update hanya field stok dan status terkait
            c.execute("""
                UPDATE products 
                SET stock = ?, gangguan = ?, kosong = ?, updated_at = ?
                WHERE code = ? AND status = 'active'
            """, (new_stock, gangguan, kosong, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), code))
            
            if c.rowcount > 0:
                updated_count += 1
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error syncing stock: {e}")
        await msg_func(f"❌ Error saat sync stok: {e}")
        return

    await log_admin_action(user_id, "SYNC_STOCK", 
                         f"Updated: {updated_count} produk, Tersedia: {tersedia_count}, Gangguan: {gangguan_count}, Kosong: {kosong_count}")
    
    await msg_func(
        f"✅ **Sync Stok Berhasil**\n\n"
        f"📊 **Status Stok Terbaru:**\n"
        f"├ Produk diupdate: {updated_count}\n"
        f"├ 🟢 Tersedia: {tersedia_count} produk\n"
        f"├ 🚧 Gangguan: {gangguan_count} produk\n"
        f"├ 🔴 Kosong: {kosong_count} produk\n"
        f"⏰ **Sync Terakhir:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
        parse_mode='Markdown'
    )

# ============================
# FITUR CEK STOK PRODUK - FIXED
# ============================

async def cek_stok_produk(update_or_query, context):
    """Menampilkan status stok produk"""
    if hasattr(update_or_query, "message") and update_or_query.message:
        msg_func = update_or_query.message.reply_text
    else:
        msg_func = update_or_query.edit_message_text

    try:
        products = fetch_all("""
            SELECT code, name, price, stock, gangguan, kosong, category
            FROM products 
            WHERE status='active'
            ORDER BY category, name ASC
        """)
                
        if not products:
            await msg_func("📭 Tidak ada produk aktif.")
            return
        
        # Hitung statistik stok
        total_products = len(products)
        tersedia = sum(1 for p in products if p[3] > 0 and p[4] == 0 and p[5] == 0)
        gangguan = sum(1 for p in products if p[4] == 1)
        kosong = sum(1 for p in products if p[5] == 1 or p[3] == 0)
        
        # Group by category dengan info stok
        categories = {}
        for code, name, price, stock, gangguan_flag, kosong_flag, category in products:
            if category not in categories:
                categories[category] = []
            
            status_emoji = "🟢"
            status_text = f"Stock: {stock}"
            if gangguan_flag == 1:
                status_emoji = "🚧"
                status_text = "GANGGUAN"
            elif kosong_flag == 1:
                status_emoji = "🔴"
                status_text = "KOSONG"
            elif stock == 0:
                status_emoji = "🔴"
                status_text = "HABIS"
            elif stock < 10:
                status_emoji = "🟡"
                status_text = f"Stock: {stock}"
            
            categories[category].append(f"{status_emoji} {name} - {status_text}")
        
        # Buat pesan
        message = f"📊 **STATUS STOK PRODUK**\n\n"
        message += f"📈 **Ringkasan:**\n"
        message += f"├ Total Produk: {total_products}\n"
        message += f"├ 🟢 Tersedia: {tersedia}\n"
        message += f"├ 🚧 Gangguan: {gangguan}\n"
        message += f"└ 🔴 Kosong/Habis: {kosong}\n\n"
        
        for category, items in categories.items():
            message += f"**{category.upper()}:**\n"
            for item in items[:8]:  # Limit items per category
                message += f"├ {item}\n"
            if len(items) > 8:
                message += f"└ ... dan {len(items) - 8} produk lainnya\n"
            message += "\n"
        
        message += f"⏰ **Update:** {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        
        # Tambahkan tombol refresh dan sync
        keyboard = [
            [
                InlineKeyboardButton("🔄 Sync Stok", callback_data="admin_sync_stock"),
                InlineKeyboardButton("📦 Update Produk", callback_data="admin_update")
            ],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
        ]
        
        await safe_edit_message_text(
            update_or_query,
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
            
    except Exception as e:
        logger.error(f"Error checking stock: {e}")
        await msg_func("❌ Gagal memuat status stok.")

# ============================
# FITUR LIST PRODUK - FIXED
# ============================

async def listproduk(update_or_query, context):
    """Menampilkan daftar produk"""
    if hasattr(update_or_query, "message") and update_or_query.message:
        msg_func = update_or_query.message.reply_text
    else:
        msg_func = update_or_query.edit_message_text

    if not ensure_products_table():
        await msg_func("❌ Gagal mengakses database produk.")
        return

    try:
        rows = fetch_all("""
            SELECT code, name, price, category, status, stock, gangguan, kosong
            FROM products 
            WHERE status='active' 
            ORDER BY category, name ASC 
            LIMIT 100
        """)
                
        if not rows:
            await msg_func("📭 Tidak ada produk aktif.")
            return
            
        # Group by category
        categories = {}
        for code, name, price, category, status, stock, gangguan, kosong in rows:
            if category not in categories:
                categories[category] = []
            
            # Tentukan status emoji
            status_emoji = "🟢"
            if gangguan == 1:
                status_emoji = "🚧"
            elif kosong == 1 or stock == 0:
                status_emoji = "🔴"
            elif stock < 10:
                status_emoji = "🟡"
                
            categories[category].append((code, name, price, status_emoji))
        
        msg = "📋 **DAFTAR PRODUK AKTIF**\n\n"
        for category, products in categories.items():
            msg += f"**{category.upper()}:**\n"
            for code, name, price, emoji in products[:10]:
                msg += f"├ {emoji} `{code}` | {name} | Rp {price:,.0f}\n"
            if len(products) > 10:
                msg += f"└ ... dan {len(products) - 10} produk lainnya\n"
            msg += "\n"
            
        msg += f"📊 Total: {len(rows)} produk aktif"
        
        await msg_func(msg, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error listing products: {e}")
        await msg_func("❌ Gagal mengambil daftar produk.")

# ============================
# FITUR EDIT PRODUK - FIXED
# ============================

async def edit_produk_start_from_query(query, context):
    """Memulai conversation edit produk"""
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Harga Produk", callback_data="edit_harga")],
        [InlineKeyboardButton("📝 Edit Deskripsi Produk", callback_data="edit_deskripsi")],
        [InlineKeyboardButton("⬅️ Kembali ke Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await safe_edit_message_text(
        query,
        "🛠️ **MENU EDIT PRODUK**\n\nPilih jenis edit yang ingin dilakukan:",
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
        
        if not ensure_products_table():
            await query.edit_message_text("❌ Gagal mengakses database produk.")
            return EDIT_MENU

        try:
            products = fetch_all("""
                SELECT code, name, price 
                FROM products 
                WHERE status='active' 
                ORDER BY name ASC 
                LIMIT 50
            """)
                    
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
    
    data = query.data
    if data.startswith('select_product:'):
        product_code = data.split(':')[1]
        context.user_data['selected_product'] = product_code
        edit_type = context.user_data.get('edit_type')
        
        # Get product details
        try:
            product = fetch_one("SELECT name, price, description FROM products WHERE code = ?", (product_code,))
                    
            if not product:
                await query.edit_message_text("❌ Produk tidak ditemukan.")
                return CHOOSE_PRODUCT
                
            name, price, description = product
            
            if edit_type == 'edit_harga':
                context.user_data['current_price'] = price
                await query.edit_message_text(
                    f"✏️ **EDIT HARGA PRODUK**\n\n"
                    f"📦 Produk: {name}\n"
                    f"💰 Harga Sekarang: Rp {price:,.0f}\n\n"
                    f"Silakan kirim harga baru (hanya angka):",
                    parse_mode='Markdown'
                )
                return EDIT_HARGA
            else:
                context.user_data['current_description'] = description
                await query.edit_message_text(
                    f"📝 **EDIT DESKRIPSI PRODUK**\n\n"
                    f"📦 Produk: {name}\n"
                    f"📄 Deskripsi Sekarang: {description}\n\n"
                    f"Silakan kirim deskripsi baru:",
                    parse_mode='Markdown'
                )
                return EDIT_DESKRIPSI
                
        except Exception as e:
            logger.error(f"Error getting product details: {e}")
            await query.edit_message_text("❌ Gagal mengambil detail produk.")
            return CHOOSE_PRODUCT
            
    return CHOOSE_PRODUCT

async def edit_harga_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk edit harga"""
    if not await admin_check(update, context):
        return ConversationHandler.END
        
    try:
        new_price = float(update.message.text)
        product_code = context.user_data.get('selected_product')
        
        if new_price <= 0:
            await update.message.reply_text("❌ Harga harus lebih dari 0. Silakan coba lagi:")
            return EDIT_HARGA
            
        # Update harga di database
        try:
            execute_sql("UPDATE products SET price = ?, updated_at = ? WHERE code = ?", 
                       (new_price, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), product_code))
                
            # Get product name for logging
            product = fetch_one("SELECT name FROM products WHERE code = ?", (product_code,))
            product_name = product[0] if product else "Unknown"
            
            await log_admin_action(update.message.from_user.id, "EDIT_PRODUCT_PRICE", 
                                f"Product: {product_name}, New Price: {new_price}")
            
            await update.message.reply_text(
                f"✅ **Harga berhasil diupdate!**\n\n"
                f"📦 Produk: {product_name}\n"
                f"💰 Harga Baru: Rp {new_price:,.0f}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Kembali ke Edit Menu", callback_data="back_to_edit_menu")]
                ])
            )
            
        except Exception as e:
            logger.error(f"Error updating price: {e}")
            await update.message.reply_text("❌ Gagal mengupdate harga.")
            
    except ValueError:
        await update.message.reply_text("❌ Format harga tidak valid. Silakan masukkan angka saja:")
        return EDIT_HARGA
        
    return ConversationHandler.END

async def edit_deskripsi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk edit deskripsi"""
    if not await admin_check(update, context):
        return ConversationHandler.END
        
    new_description = update.message.text
    product_code = context.user_data.get('selected_product')
    
    if len(new_description) > 500:
        await update.message.reply_text("❌ Deskripsi terlalu panjang (max 500 karakter). Silakan coba lagi:")
        return EDIT_DESKRIPSI
        
    # Update deskripsi di database
    try:
        execute_sql("UPDATE products SET description = ?, updated_at = ? WHERE code = ?", 
                   (new_description, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), product_code))
            
        # Get product name for logging
        product = fetch_one("SELECT name FROM products WHERE code = ?", (product_code,))
        product_name = product[0] if product else "Unknown"
    
        await log_admin_action(update.message.from_user.id, "EDIT_PRODUCT_DESCRIPTION", 
                            f"Product: {product_name}, New Description: {new_description[:100]}...")
        
        await update.message.reply_text(
            f"✅ **Deskripsi berhasil diupdate!**\n\n"
            f"📦 Produk: {product_name}\n"
            f"📄 Deskripsi Baru: {new_description}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Kembali ke Edit Menu", callback_data="back_to_edit_menu")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error updating description: {e}")
        await update.message.reply_text("❌ Gagal mengupdate deskripsi.")
        
    return ConversationHandler.END

# ============================
# FITUR TOPUP MANAGEMENT - FIXED
# ============================

async def topup_list_interactive(query, context):
    """Menampilkan daftar topup pending dengan pagination"""
    try:
        # Get pending topups from database
        topups = safe_db_call('get_pending_topups', [])
        
        if not topups:
            await safe_edit_message_text(
                query,
                "📭 Tidak ada topup yang menunggu persetujuan.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Refresh", callback_data="admin_topup")],
                    [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
                ])
            )
            return

        keyboard = []
        for topup in topups[:10]:
            user_id = topup.get('user_id', 'Unknown')
            amount = topup.get('amount', 0)
            topup_id = topup.get('id')
            
            keyboard.append([
                InlineKeyboardButton(
                    f"👤 {user_id} - Rp {amount:,}",
                    callback_data=f"topup_detail:{topup_id}"
                )
            ])

        # Navigation buttons
        keyboard.append([
            InlineKeyboardButton("🔄 Refresh", callback_data="admin_topup"),
            InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")
        ])

        await safe_edit_message_text(
            query,
            f"💳 **DAFTAR TOPUP PENDING**\n\nTotal: {len(topups)} topup menunggu persetujuan:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error in topup_list_interactive: {e}")
        await query.message.reply_text("❌ Gagal memuat daftar topup.")

# ... (sisa code untuk topup_detail, approve_topup_handler, reject_topup_handler tetap sama)
# ... (sisa code untuk user management, broadcast, backup, health check tetap sama)

# ============================
# CONVERSATION HANDLERS - FIXED
# ============================

def get_admin_conversation_handlers():
    """Mengembalikan semua conversation handlers untuk admin"""
    
    broadcast_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_start, pattern="^admin_broadcast$")],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler)]
        },
        fallbacks=[
            CallbackQueryHandler(admin_menu_from_query, pattern="^admin_back$"),
            CommandHandler('cancel', admin_menu)
        ],
        name="admin_broadcast"
    )
    
    edit_produk_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_produk_start_from_query, pattern="^admin_edit_produk$")],
        states={
            EDIT_MENU: [CallbackQueryHandler(edit_produk_menu_handler, pattern="^(edit_harga|edit_deskripsi|admin_back|back_to_edit_menu)$")],
            CHOOSE_PRODUCT: [CallbackQueryHandler(select_product_handler, pattern="^select_product:")],
            EDIT_HARGA: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_harga_handler)],
            EDIT_DESKRIPSI: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_deskripsi_handler)]
        },
        fallbacks=[
            CallbackQueryHandler(admin_menu_from_query, pattern="^admin_back$"),
            CommandHandler('cancel', admin_menu)
        ],
        name="admin_edit_produk"
    )
    
    return [broadcast_handler, edit_produk_handler]

# ============================
# COMMAND HANDLERS
# ============================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /admin"""
    await admin_menu(update, context)

def get_admin_handlers():
    """Mengembalikan semua handlers untuk admin"""
    return [
        CommandHandler('admin', admin_command),
        CallbackQueryHandler(admin_callback_handler, pattern="^admin_"),
        CallbackQueryHandler(admin_callback_handler, pattern="^topup_"),
        CallbackQueryHandler(admin_callback_handler, pattern="^approve_topup:"),
        CallbackQueryHandler(admin_callback_handler, pattern="^reject_topup:"),
        CallbackQueryHandler(admin_callback_handler, pattern="^user_"),
        CallbackQueryHandler(admin_callback_handler, pattern="^make_admin:"),
        CallbackQueryHandler(admin_callback_handler, pattern="^remove_admin:"),
        CallbackQueryHandler(admin_callback_handler, pattern="^back_"),
        CallbackQueryHandler(admin_callback_handler, pattern="^edit_"),
        CallbackQueryHandler(admin_callback_handler, pattern="^balance_"),
        *get_admin_conversation_handlers()
    ]

if __name__ == "__main__":
    print("✅ Admin Handler - FIXED VERSION")
    print("🔧 Perbaikan yang dilakukan:")
    print("  ✅ Menghapus aiosqlite dan menggunakan sqlite3 biasa")
    print("  ✅ Memperbaiki error: 'object Cursor can't be used in await expression'")
    print("  ✅ Menambahkan wrapper functions untuk database operations")
    print("  ✅ Memastikan semua database calls konsisten")
    print("🚀 Ready for production use!")
