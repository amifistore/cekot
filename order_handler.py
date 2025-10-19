import logging
import uuid
import requests
import aiohttp
import asyncio
import sqlite3
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CommandHandler
)
import database
import config
import telegram

logger = logging.getLogger(__name__)

# States
MENU, CHOOSING_GROUP, CHOOSING_PRODUCT, ENTER_TUJUAN, CONFIRM_ORDER, ORDER_PROCESSING = range(6)
PRODUCTS_PER_PAGE = 8

# Database path
DB_PATH = getattr(database, 'DB_PATH', 'bot_database.db')

async def safe_edit_message_text(callback_query, *args, **kwargs):
    """Safely edit message text with error handling"""
    try:
        await callback_query.edit_message_text(*args, **kwargs)
        return True
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e):
            return True
        elif "Message can't be deleted" in str(e):
            try:
                await callback_query.message.reply_text(*args, **kwargs)
                return True
            except Exception as send_error:
                logger.error(f"Failed to send new message: {send_error}")
                return False
        logger.error(f"Error editing message: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in safe_edit_message_text: {e}")
        return False

async def safe_reply_message(update, *args, **kwargs):
    """Safely reply to message with error handling"""
    try:
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(*args, **kwargs)
            return True
        elif hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.reply_text(*args, **kwargs)
            return True
        return False
    except Exception as e:
        logger.error(f"Error replying to message: {e}")
        return False

def get_grouped_products():
    """Get products grouped by category from database - TAMPILKAN SEMUA PRODUK"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT code, name, price, category, description, status, gangguan, kosong, stock
            FROM products 
            WHERE status='active'
            ORDER BY category, name ASC
        """)
        products = c.fetchall()
        conn.close()

        logger.info(f"Found {len(products)} active products in database (including out-of-stock)")
        
        groups = {}
        for code, name, price, category, description, status, gangguan, kosong, stock in products:
            # Use category from database, fallback to code-based grouping
            group = category or "Lainnya"
            
            # Additional grouping for specific product codes
            if code.startswith("BPAL"):
                group = "BPAL (Bonus Akrab L)"
            elif code.startswith("BPAXXL"):
                group = "BPAXXL (Bonus Akrab XXL)"
            elif code.startswith("XLA"):
                group = "XLA (Umum)"
            elif "pulsa" in name.lower():
                group = "Pulsa"
            elif "data" in name.lower() or "internet" in name.lower() or "kuota" in name.lower():
                group = "Internet"
            elif "listrik" in name.lower() or "pln" in name.lower():
                group = "Listrik"
            elif "game" in name.lower():
                group = "Game"
            elif "emoney" in name.lower() or "gopay" in name.lower() or "dana" in name.lower():
                group = "E-Money"
            
            if group not in groups:
                groups[group] = []
            
            groups[group].append({
                'code': code,
                'name': name,
                'price': price,
                'category': category,
                'description': description,
                'stock': stock,
                'gangguan': gangguan,
                'kosong': kosong
            })
        
        # Sort groups alphabetically
        sorted_groups = {}
        for group in sorted(groups.keys()):
            sorted_groups[group] = groups[group]
            
        return sorted_groups
        
    except Exception as e:
        logger.error(f"Error getting grouped products from database: {e}")
        return {}

async def menu_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show main menu"""
    try:
        user = getattr(update, 'effective_user', None)
        if user is None and hasattr(update, "callback_query"):
            user = getattr(update.callback_query, "from_user", None)
        
        if not user:
            await safe_reply_message(update, "❌ Error: Tidak dapat mengidentifikasi pengguna.")
            return MENU
        
        saldo = 0
        try:
            user_id = str(user.id)
            database.get_or_create_user(user_id, user.username or "", user.full_name or "")
            saldo = database.get_user_saldo(user_id)
        except Exception as e:
            logger.error(f"Error getting user saldo: {e}")
            saldo = 0
        
        keyboard = [
            [InlineKeyboardButton("🛒 Beli Produk", callback_data="menu_order")],
            [InlineKeyboardButton("💳 Cek Saldo", callback_data="menu_saldo")],
            [InlineKeyboardButton("💸 Top Up Saldo", callback_data="topup_start")],  # DIUBAH: menu_topup -> topup_start
            [InlineKeyboardButton("📊 Cek Stok", callback_data="menu_stock")],
            [InlineKeyboardButton("📋 Riwayat Order", callback_data="menu_history")],
            [InlineKeyboardButton("📞 Bantuan", callback_data="menu_help")]
        ]
        
        # Check if user is admin
        admin_ids = getattr(config, 'ADMIN_TELEGRAM_IDS', [])
        if user and str(user.id) in admin_ids:
            keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="menu_admin")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = (
            f"🤖 *Selamat Datang!*\n\n"
            f"Halo, *{user.full_name or user.username or 'User'}*!\n"
            f"💰 Saldo Anda: *Rp {saldo:,.0f}*\n\n"
            f"Pilih menu di bawah:"
        )
        
        if hasattr(update, "callback_query") and update.callback_query:
            await safe_edit_message_text(update.callback_query, text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await safe_reply_message(update, text, reply_markup=reply_markup, parse_mode="Markdown")
            
        return MENU
        
    except Exception as e:
        logger.error(f"Error in menu_main: {e}")
        await safe_reply_message(update, "❌ Terjadi error. Silakan coba lagi.")
        return MENU

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main menu handler - DIUBAH: Hapus penanganan menu_topup"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    logger.info(f"Menu callback received: {data}")
    
    try:
        if data == "menu_order":
            return await show_group_menu(update, context)
        elif data == "menu_saldo":
            user_id = str(query.from_user.id)
            saldo = database.get_user_saldo(user_id)
            await safe_edit_message_text(
                query,
                f"💳 *SALDO ANDA*\n\nSaldo: *Rp {saldo:,.0f}*\n\nGunakan menu Top Up untuk menambah saldo.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💸 Top Up Saldo", callback_data="topup_start")],  # DIUBAH: menu_topup -> topup_start
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ]),
                parse_mode="Markdown"
            )
            return MENU
        elif data == "menu_help":
            await safe_edit_message_text(
                query,
                "📞 *BANTUAN*\n\n"
                "Jika mengalami masalah, hubungi admin.\n\n"
                "**Cara Order:**\n"
                "1. Pilih *Beli Produk*\n"
                "2. Pilih kategori produk\n" 
                "3. Pilih produk yang diinginkan\n"
                "4. Masukkan nomor tujuan\n"
                "5. Konfirmasi order\n\n"
                "**Fitur Lain:**\n"
                "• Top Up Saldo\n"
                "• Cek Stok Produk\n"
                "• Riwayat Transaksi\n"
                "• Bantuan Admin",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛒 Beli Produk", callback_data="menu_order")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ]),
                parse_mode="Markdown"
            )
            return MENU
        # DIHAPUS: Penanganan menu_topup - biarkan topup_handler yang menanganinya
        elif data == "menu_stock":
            await show_stock_menu(update, context)
            return MENU
        elif data == "menu_history":
            await show_order_history(update, context)
            return MENU
        elif data == "menu_admin":
            admin_ids = getattr(config, 'ADMIN_TELEGRAM_IDS', [])
            if str(query.from_user.id) in admin_ids:
                try:
                    from admin_handler import admin_menu
                    await admin_menu(update, context)
                    return ConversationHandler.END
                except Exception as e:
                    logger.error(f"Error loading admin panel: {e}")
                    await safe_edit_message_text(
                        query,
                        "❌ Error memuat panel admin. Silakan gunakan command /admin",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
                    )
                    return MENU
            else:
                await query.answer("❌ Anda bukan admin!", show_alert=True)
                return MENU
        elif data == "menu_main":
            return await menu_main(update, context)
        else:
            await query.answer("❌ Menu tidak dikenal!")
            return MENU
            
    except Exception as e:
        logger.error(f"Error in menu_handler: {e}")
        await safe_edit_message_text(
            query,
            "❌ Terjadi error. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return MENU

async def show_stock_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show stock menu"""
    query = update.callback_query
    await query.answer()
    
    try:
        await get_stock_from_database(update, context)
    except Exception as e:
        logger.error(f"Error showing stock menu: {e}")
        await safe_edit_message_text(
            query,
            "❌ Gagal mengambil data stok. Silakan coba lagi nanti.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh Stok", callback_data="menu_stock")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
            ])
        )

async def get_stock_from_database(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get stock information from database"""
    query = update.callback_query
    
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT code, name, price, category, stock, gangguan, kosong
            FROM products 
            WHERE status='active' 
            ORDER BY category, name ASC
            LIMIT 50
        """)
        products = c.fetchall()
        conn.close()

        if not products:
            msg = "📭 Tidak ada produk aktif di database.\n\nℹ️ Admin dapat mengupdate produk melalui menu admin."
        else:
            msg = "📊 **STOK PRODUK DARI DATABASE**\n\n"
            current_category = ""
            
            for code, name, price, category, stock, gangguan, kosong in products:
                if category != current_category:
                    msg += f"\n**{category.upper()}:**\n"
                    current_category = category
                
                # Status indicators
                if gangguan == 1:
                    status_emoji = "🚧"
                    status_text = "Gangguan"
                elif kosong == 1:
                    status_emoji = "🔴"
                    status_text = "Kosong"
                elif stock > 10:
                    status_emoji = "🟢"
                    status_text = f"Tersedia ({stock})"
                elif stock > 0:
                    status_emoji = "🟡"
                    status_text = f"Sedikit ({stock})"
                else:
                    status_emoji = "🔴"
                    status_text = "Habis"
                
                msg += f"{status_emoji} {name} - Rp {price:,.0f} - *{status_text}*\n"
            
            msg += f"\n📊 Total {len(products)} produk aktif"
            msg += f"\n\n🟢 Tersedia | 🟡 Sedikit | 🔴 Habis/Kosong | 🚧 Gangguan"

    except Exception as e:
        logger.error(f"Error getting stock from database: {e}")
        msg = f"❌ Gagal mengambil data stok dari database: {str(e)}"

    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Stok", callback_data="menu_stock")],
        [InlineKeyboardButton("🛒 Beli Produk", callback_data="menu_order")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await safe_edit_message_text(query, msg, parse_mode='Markdown', reply_markup=reply_markup)

async def show_order_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's order history"""
    query = update.callback_query
    await query.answer()
    
    try:
        user_id = str(query.from_user.id)
        
        # Get last 10 orders from database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT order_id, product_name, target, price, status, created_at 
            FROM orders 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 10
        """, (user_id,))
        orders = c.fetchall()
        conn.close()

        if not orders:
            msg = "📋 *RIWAYAT ORDER*\n\nAnda belum memiliki riwayat order."
        else:
            msg = "📋 *RIWAYAT ORDER TERAKHIR*\n\n"
            for order in orders:
                order_id, product_name, target, price, status, created_at = order
                status_emoji = {
                    'success': '✅',
                    'pending': '⏳', 
                    'failed': '❌',
                    'processing': '🔄'
                }.get(status, '❓')
                
                # Format timestamp
                order_time = created_at.split(' ')[1][:5] if ' ' in created_at else created_at
                
                msg += (
                    f"{status_emoji} *{product_name}*\n"
                    f"📮 Tujuan: `{target}`\n"
                    f"💰 Rp {price:,}\n"
                    f"🕒 {order_time} | {status.upper()}\n"
                    f"────────────────────\n"
                )
            
            msg += f"\n📊 Total: {len(orders)} order terakhir"
        
        keyboard = [
            [InlineKeyboardButton("🛒 Beli Lagi", callback_data="menu_order")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await safe_edit_message_text(query, msg, parse_mode='Markdown', reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error showing order history: {e}")
        await safe_edit_message_text(
            query,
            "❌ Gagal memuat riwayat order. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )

async def show_group_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show product groups menu from database - SEMUA PRODUK DITAMPILKAN"""
    try:
        query = update.callback_query
        await query.answer()
        
        logger.info("Loading product groups from database...")
        groups = get_grouped_products()
        
        if not groups:
            logger.warning("No products found in database")
            await safe_edit_message_text(
                query,
                "❌ Tidak ada produk yang tersedia saat ini.\n\n"
                "ℹ️ Silakan hubungi admin untuk mengupdate produk.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Coba Lagi", callback_data="menu_order")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ])
            )
            return MENU
        
        # Calculate total products
        total_products = sum(len(group_products) for group_products in groups.values())
        logger.info(f"Showing {len(groups)} groups with {total_products} products")
        
        # Create keyboard with better formatting
        keyboard = []
        for group, group_products in groups.items():
            # Count products by status
            total_in_group = len(group_products)
            available_in_group = sum(1 for p in group_products if p.get('stock', 0) > 0 and p.get('gangguan', 0) == 0 and p.get('kosong', 0) == 0)
            gangguan_in_group = sum(1 for p in group_products if p.get('gangguan', 0) == 1)
            kosong_in_group = sum(1 for p in group_products if p.get('kosong', 0) == 1)
            
            # Create button text with emoji based on availability
            if gangguan_in_group > 0:
                button_text = f"🚧 {group}"
            elif kosong_in_group == total_in_group:
                button_text = f"🔴 {group}"
            elif available_in_group == total_in_group:
                button_text = f"🟢 {group}"
            elif available_in_group > 0:
                button_text = f"🟡 {group}"
            else:
                button_text = f"🔴 {group}"
            
            # Add product count
            button_text += f" ({len(group_products)})"
            
            # Clean group name for callback data
            clean_group = re.sub(r'[^a-zA-Z0-9_]', '', group.replace(' ', '_'))
            callback_data = f"group_{clean_group}"[:64]
                
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Add navigation buttons
        keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="menu_order")])
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Create safe message text
        message_text = (
            "📦 PILIH KATEGORI PRODUK\n\n"
            f"📊 Ditemukan {total_products} produk dalam {len(groups)} kategori\n\n"
            "🟢 Semua tersedia | 🟡 Sebagian tersedia | 🔴 Habis/Kosong | 🚧 Gangguan\n\n"
            "ℹ️ Produk dengan stok kosong tetap bisa dipesan untuk testing\n\n"
            "Silakan pilih kategori produk:"
        )
        
        logger.info(f"Sending group menu with {len(keyboard)} buttons")
        
        await safe_edit_message_text(
            query,
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return CHOOSING_GROUP
        
    except Exception as e:
        logger.error(f"Error in show_group_menu: {e}")
        await safe_edit_message_text(
            query,
            "❌ Terjadi error saat memuat kategori produk. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Coba Lagi", callback_data="menu_order")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
            ])
        )
        return MENU

# ... (fungsi-fungsi lainnya tetap sama, tidak perlu diubah)
# [Kode selanjutnya tetap sama seperti sebelumnya]

def get_conversation_handler():
    """Return the order conversation handler"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(menu_main, pattern="^menu_main$"),
            CallbackQueryHandler(menu_handler, pattern="^menu_"),
            CommandHandler("order", menu_main),
            CommandHandler("start", menu_main)
        ],
        states={
            MENU: [
                CallbackQueryHandler(menu_handler, pattern="^menu_"),
                CallbackQueryHandler(show_group_menu, pattern="^menu_order$"),
            ],
            CHOOSING_GROUP: [
                CallbackQueryHandler(show_group_menu, pattern="^menu_order$"),
                # ... (state handlers lainnya)
            ],
            # ... (states lainnya)
        },
        fallbacks=[
            CommandHandler("cancel", menu_main),
            CallbackQueryHandler(menu_main, pattern="^menu_main$")
        ],
        allow_reentry=True
    )
