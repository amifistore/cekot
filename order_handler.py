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
            [InlineKeyboardButton("💸 Top Up Saldo", callback_data="menu_topup")],
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
    """Main menu handler"""
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
                    [InlineKeyboardButton("💸 Top Up Saldo", callback_data="menu_topup")], 
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
        elif data == "menu_topup":
            try:
                from topup_handler import topup_start
                await topup_start(update, context)
                return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error loading topup: {e}")
                await safe_edit_message_text(
                    query,
                    "❌ Error memulai topup. Silakan gunakan command /topup",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
                )
                return MENU
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
        
        # Use plain text to avoid Markdown issues
        await query.edit_message_text(
            message_text,
            reply_markup=reply_markup
        )
        
        # Store groups in context for later use
        context.user_data["groups"] = groups
        context.user_data["group_mapping"] = {f"group_{re.sub(r'[^a-zA-Z0-9_]', '', k.replace(' ', '_'))}"[:64]: k for k in groups.keys()}
        
        logger.info("Successfully displayed group menu")
        return CHOOSING_GROUP
        
    except Exception as e:
        logger.error(f"Error in show_group_menu: {e}")
        await safe_edit_message_text(
            update.callback_query,
            "❌ Error memuat daftar produk dari database. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return MENU

def get_products_keyboard_group(products, page=0):
    """Create paginated products keyboard - SEMUA PRODUK DITAMPILKAN"""
    total_pages = (len(products) - 1) // PRODUCTS_PER_PAGE + 1
    start = page * PRODUCTS_PER_PAGE
    end = start + PRODUCTS_PER_PAGE
    page_products = products[start:end]
    
    keyboard = []
    for prod in page_products:
        # Truncate long product names
        display_name = prod['name']
        if len(display_name) > 30:
            display_name = display_name[:27] + "..."
        
        # Add status indicator
        stock = prod.get('stock', 0)
        gangguan = prod.get('gangguan', 0)
        kosong = prod.get('kosong', 0)
        
        if gangguan == 1:
            status_emoji = "🚧"
        elif kosong == 1:
            status_emoji = "🔴"
        elif stock > 10:
            status_emoji = "🟢"
        elif stock > 0:
            status_emoji = "🟡"
        else:
            status_emoji = "🔴"
            
        btn_text = f"{status_emoji} {display_name} - Rp {prod['price']:,.0f}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"prod_{prod['code']}")])
    
    # Navigation buttons
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data=f"page_{page-1}"))
    if page < total_pages - 1:
        navigation.append(InlineKeyboardButton("Selanjutnya ➡️", callback_data=f"page_{page+1}"))
    
    if navigation:
        keyboard.append(navigation)
    
    keyboard.append([InlineKeyboardButton("⬅️ Kembali ke Kategori", callback_data="back_to_categories")])
    keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")])
    
    return InlineKeyboardMarkup(keyboard), total_pages

async def choose_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle group selection"""
    query = update.callback_query
    await query.answer()
    
    try:
        callback_data = query.data
        group_mapping = context.user_data.get("group_mapping", {})
        
        # Get the original group name from mapping
        group_name = group_mapping.get(callback_data)
        if not group_name:
            # Fallback: try to extract from callback data
            group_name = callback_data.replace("group_", "").replace('_', ' ')
        
        groups = context.user_data.get("groups", {})
        products = groups.get(group_name, [])
        
        logger.info(f"User selected group: {group_name} with {len(products)} products")
        
        if not products:
            await safe_edit_message_text(
                query,
                f"❌ Tidak ada produk di kategori {group_name}.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali ke Kategori", callback_data="back_to_categories")]])
            )
            return CHOOSING_GROUP
        
        context.user_data["current_group"] = group_name
        context.user_data["product_list"] = products
        context.user_data["product_page"] = 0
        
        return await show_product_in_group(query, context, page=0)
        
    except Exception as e:
        logger.error(f"Error in choose_group: {e}")
        await safe_edit_message_text(
            query,
            "❌ Error memuat produk. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return MENU

async def show_product_in_group(query, context, page=0):
    """Show products in selected group - SEMUA PRODUK DITAMPILKAN"""
    try:
        products = context.user_data.get("product_list", [])
        group_name = context.user_data.get("current_group", "")
        
        if not products:
            await safe_edit_message_text(
                query,
                f"❌ Tidak ada produk di kategori {group_name}.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali ke Kategori", callback_data="back_to_categories")]])
            )
            return CHOOSING_GROUP
        
        reply_markup, total_pages = get_products_keyboard_group(products, page)
        
        # Count products by status
        total_products = len(products)
        available_products = sum(1 for p in products if p.get('stock', 0) > 0 and p.get('gangguan', 0) == 0 and p.get('kosong', 0) == 0)
        gangguan_products = sum(1 for p in products if p.get('gangguan', 0) == 1)
        kosong_products = sum(1 for p in products if p.get('kosong', 0) == 1)
        
        message_text = (
            f"🛒 PILIH PRODUK - {group_name}\n\n"
            f"📄 Halaman {page+1} dari {total_pages}\n"
            f"📊 Status: {available_products} tersedia, {gangguan_products} gangguan, {kosong_products} kosong\n\n"
            f"🟢 Tersedia | 🟡 Sedikit | 🔴 Habis/Kosong | 🚧 Gangguan\n\n"
            f"ℹ️ Semua produk bisa dipesan untuk testing response provider\n\n"
            f"Silakan pilih produk:"
        )
        
        await safe_edit_message_text(
            query,
            message_text,
            reply_markup=reply_markup
        )
        
        context.user_data["product_page"] = page
        return CHOOSING_PRODUCT
        
    except Exception as e:
        logger.error(f"Error in show_product_in_group: {e}")
        await safe_edit_message_text(
            query,
            "❌ Error menampilkan produk. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return MENU

async def choose_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product selection - BOLEH PILIH PRODUK STOK KOSONG"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    try:
        # Handle pagination
        if data.startswith("page_"):
            page = int(data.replace("page_", ""))
            return await show_product_in_group(query, context, page)
        
        # Handle back to categories
        elif data == "back_to_categories":
            return await show_group_menu(update, context)
        
        # Handle product selection
        elif data.startswith("prod_"):
            product_code = data.replace("prod_", "")
            products = context.user_data.get("product_list", [])
            
            # Find the selected product
            selected_product = None
            for product in products:
                if product['code'] == product_code:
                    selected_product = product
                    break
            
            if not selected_product:
                await query.answer("❌ Produk tidak ditemukan!", show_alert=True)
                return CHOOSING_PRODUCT
            
            # Get product status
            stock = selected_product.get('stock', 0)
            gangguan = selected_product.get('gangguan', 0)
            kosong = selected_product.get('kosong', 0)
            
            # Store selected product in context
            context.user_data['selected_product'] = selected_product
            
            # Show product details and ask for destination
            product_info = (
                f"🛒 PRODUK DIPILIH\n\n"
                f"📦 Nama: {selected_product['name']}\n"
                f"🏷️ Kode: {selected_product['code']}\n"
                f"💰 Harga: Rp {selected_product['price']:,.0f}\n"
            )
            
            # Add status information
            if gangguan == 1:
                product_info += f"🚧 Status: GANGGUAN - Produk sedang mengalami gangguan\n"
            elif kosong == 1:
                product_info += f"🔴 Status: KOSONG - Stok produk habis\n"
            elif stock > 0:
                product_info += f"📊 Stok: {stock} pcs\n"
            else:
                product_info += f"🔴 Status: STOK HABIS\n"
            
            # Show warning for out-of-stock products but allow ordering
            if gangguan == 1 or kosong == 1 or stock <= 0:
                product_info += f"⚠️ PERINGATAN: Produk ini sedang tidak tersedia\n"
                product_info += f"✅ Tetapi bisa dipesan untuk testing response provider\n\n"
            else:
                product_info += f"\n"
            
            if selected_product.get('description'):
                product_info += f"📝 Deskripsi: {selected_product['description']}\n"
            
            product_info += f"\n📮 Masukkan nomor tujuan atau ID:\n"
            
            # Provide examples based on product type
            if any(x in selected_product['name'].lower() for x in ['pulsa', 'data', 'internet', 'telkomsel', 'xl', 'axis', 'tri', 'indosat', 'smartfren']):
                product_info += "Contoh: 081234567890"
                context.user_data['input_type'] = 'phone'
            elif any(x in selected_product['name'].lower() for x in ['listrik', 'pln']):
                product_info += "Contoh: 1234567890123456 (ID PLN 16/20 digit)"
                context.user_data['input_type'] = 'pln'
            elif any(x in selected_product['name'].lower() for x in ['game', 'voucher']):
                product_info += "Contoh: 123456789 (ID Game/User ID)"
                context.user_data['input_type'] = 'game'
            else:
                product_info += "Contoh: 081234567890 atau 123456789"
                context.user_data['input_type'] = 'general'
            
            await safe_edit_message_text(
                query,
                product_info,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Kembali ke Produk", callback_data=f"back_to_products_{context.user_data.get('product_page', 0)}")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ])
            )
            
            return ENTER_TUJUAN
        
        else:
            await query.answer("❌ Perintah tidak dikenali!")
            return CHOOSING_PRODUCT
            
    except Exception as e:
        logger.error(f"Error in choose_product: {e}")
        await safe_edit_message_text(
            query,
            "❌ Error memilih produk. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return MENU

async def back_to_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back to products list"""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data.startswith("back_to_products_"):
            page = int(query.data.replace("back_to_products_", ""))
            return await show_product_in_group(query, context, page)
        else:
            return await show_product_in_group(query, context, 0)
    except Exception as e:
        logger.error(f"Error in back_to_products: {e}")
        return await show_group_menu(update, context)

async def enter_tujuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle destination input - FIXED: Handle both message and callback query"""
    try:
        # Check if this is a message (text input) or callback query
        if update.message:
            tujuan = update.message.text.strip()
            user_message = update.message
        elif update.callback_query:
            await update.callback_query.answer()
            return ENTER_TUJUAN
        else:
            await safe_reply_message(update, "❌ Format input tidak valid.")
            return ENTER_TUJUAN
        
        logger.info(f"ENTER_TUJUAN: User input received: {tujuan}")
        
        # Basic validation
        if not tujuan:
            await safe_reply_message(update, "❌ Nomor tujuan tidak boleh kosong. Silakan masukkan kembali:")
            return ENTER_TUJUAN
        
        # Validate based on input type
        input_type = context.user_data.get('input_type', 'general')
        is_valid = True
        error_msg = ""
        
        if input_type == 'phone':
            # Validate phone number
            clean_phone = re.sub(r'[^0-9]', '', tujuan)
            if len(clean_phone) < 10 or len(clean_phone) > 14:
                is_valid = False
                error_msg = "❌ Format nomor telepon tidak valid. Harus 10-14 digit angka."
            else:
                context.user_data['tujuan'] = clean_phone
                
        elif input_type == 'pln':
            # Validate PLN ID
            clean_pln = re.sub(r'[^0-9]', '', tujuan)
            if len(clean_pln) not in [16, 20]:
                is_valid = False
                error_msg = "❌ ID PLN harus 16 atau 20 digit angka."
            else:
                context.user_data['tujuan'] = clean_pln
                
        elif input_type == 'game':
            # Validate game ID (basic)
            if len(tujuan) < 3:
                is_valid = False
                error_msg = "❌ ID Game terlalu pendek. Minimal 3 karakter."
            else:
                context.user_data['tujuan'] = tujuan
        
        else:
            context.user_data['tujuan'] = tujuan
        
        if not is_valid:
            await safe_reply_message(update, error_msg)
            return ENTER_TUJUAN
        
        # Proceed to confirmation
        logger.info(f"ENTER_TUJUAN: Valid input received, proceeding to confirmation")
        return await show_confirmation(update, context)
        
    except Exception as e:
        logger.error(f"Error in enter_tujuan: {e}")
        await safe_reply_message(update, "❌ Error memproses tujuan. Silakan coba lagi.")
        return ENTER_TUJUAN

async def show_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show order confirmation"""
    try:
        selected_product = context.user_data.get('selected_product')
        tujuan = context.user_data.get('tujuan')
        
        if not selected_product or not tujuan:
            await safe_reply_message(update, "❌ Data order tidak lengkap. Silakan mulai kembali.")
            return await cancel_order(update, context)
        
        # Get user saldo
        user_id = str(update.effective_user.id)
        saldo = database.get_user_saldo(user_id)
        product_price = selected_product['price']
        
        # Get product status
        stock = selected_product.get('stock', 0)
        gangguan = selected_product.get('gangguan', 0)
        kosong = selected_product.get('kosong', 0)
        
        confirmation_text = (
            f"✅ KONFIRMASI ORDER\n\n"
            f"📦 Produk: {selected_product['name']}\n"
            f"🏷️ Kode: {selected_product['code']}\n"
            f"📮 Tujuan: {tujuan}\n"
            f"💰 Harga: Rp {product_price:,.0f}\n"
            f"💳 Saldo Anda: Rp {saldo:,.0f}\n\n"
        )
        
        # Add status warning if product is unavailable
        if gangguan == 1:
            confirmation_text += f"🚧 PERINGATAN: Produk sedang GANGGUAN\n"
        elif kosong == 1:
            confirmation_text += f"🔴 PERINGATAN: Produk KOSONG\n"
        elif stock <= 0:
            confirmation_text += f"🔴 PERINGATAN: Stok produk HABIS\n"
        
        if gangguan == 1 or kosong == 1 or stock <= 0:
            confirmation_text += f"⚠️ Order akan diproses untuk testing response provider\n\n"
        
        if saldo < product_price:
            confirmation_text += f"❌ Saldo tidak cukup!\nSilakan top up saldo terlebih dahulu."
            keyboard = [
                [InlineKeyboardButton("💸 Top Up Saldo", callback_data="menu_topup")],
                [InlineKeyboardButton("❌ Batalkan", callback_data="cancel_order")]
            ]
        else:
            confirmation_text += f"Apakah Anda yakin ingin melanjutkan order?"
            keyboard = [
                [
                    InlineKeyboardButton("✅ Ya, Order Sekarang", callback_data="confirm_order"),
                    InlineKeyboardButton("❌ Batalkan", callback_data="cancel_order")
                ]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(confirmation_text, reply_markup=reply_markup)
        else:
            await safe_edit_message_text(update.callback_query, confirmation_text, reply_markup=reply_markup)
        
        return CONFIRM_ORDER
        
    except Exception as e:
        logger.error(f"Error in show_confirmation: {e}")
        await safe_reply_message(update, "❌ Error menampilkan konfirmasi. Silakan coba lagi.")
        return await cancel_order(update, context)

async def process_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the order - BOLEH PROSES PRODUK STOK KOSONG"""
    query = update.callback_query
    await query.answer()
    
    try:
        user_id = str(query.from_user.id)
        selected_product = context.user_data.get('selected_product')
        tujuan = context.user_data.get('tujuan')
        
        if not selected_product or not tujuan:
            await safe_edit_message_text(query, "❌ Data order tidak lengkap. Silakan mulai kembali.")
            return await cancel_order(update, context)
        
        # Check balance
        user_saldo = database.get_user_saldo(user_id)
        product_price = selected_product['price']
        
        if user_saldo < product_price:
            await safe_edit_message_text(
                query,
                f"❌ Saldo tidak cukup!\n\n"
                f"💳 Saldo Anda: Rp {user_saldo:,.0f}\n"
                f"💰 Dibutuhkan: Rp {product_price:,.0f}\n\n"
                f"Silakan top up saldo terlebih dahulu.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💸 Top Up Saldo", callback_data="menu_topup")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ])
            )
            return ConversationHandler.END
        
        # Generate order ID
        order_id = str(uuid.uuid4())[:8].upper()
        
        # Create order in database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO orders (order_id, user_id, product_code, product_name, target, price, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_id,
            user_id,
            selected_product['code'],
            selected_product['name'],
            tujuan,
            product_price,
            'processing',
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        conn.commit()
        conn.close()
        
        # Deduct balance
        new_saldo = database.deduct_saldo(user_id, product_price)
        
        if new_saldo is None:
            # Refund order if deduction failed
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE orders SET status = 'failed' WHERE order_id = ?", (order_id,))
            conn.commit()
            conn.close()
            
            await safe_edit_message_text(
                query,
                "❌ Gagal memotong saldo. Order dibatalkan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
            return ConversationHandler.END
        
        # Get product status for message
        stock = selected_product.get('stock', 0)
        gangguan = selected_product.get('gangguan', 0)
        kosong = selected_product.get('kosong', 0)
        
        # Show processing message
        processing_text = (
            f"🔄 ORDER DALAM PROSES\n\n"
            f"📦 Produk: {selected_product['name']}\n"
            f"📮 Tujuan: {tujuan}\n"
            f"💰 Harga: Rp {product_price:,.0f}\n"
            f"📋 Order ID: {order_id}\n"
        )
        
        # Add status information
        if gangguan == 1:
            processing_text += f"🚧 Status: GANGGUAN\n"
        elif kosong == 1:
            processing_text += f"🔴 Status: KOSONG\n"
        elif stock <= 0:
            processing_text += f"🔴 Status: STOK HABIS\n"
        
        processing_text += f"\n⏳ Sedang memproses order Anda..."
        
        await safe_edit_message_text(
            query,
            processing_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh Status", callback_data=f"check_status_{order_id}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
            ])
        )
        
        # Call provider API
        try:
            api_key = getattr(config, 'API_KEY_PROVIDER', '')
            payload = {
                "produk": selected_product['code'],
                "tujuan": tujuan,
                "reff_id": order_id,
                "api_key": api_key
            }
            
            response = requests.get("https://panel.khfy-store.com/api_v2/trx", params=payload, timeout=30)
            api_response = response.json() if response.status_code == 200 else None
            
            if api_response and api_response.get('status') in ['SUKSES', 'SUCCESS']:
                # Update order status to success
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("UPDATE orders SET status = 'success' WHERE order_id = ?", (order_id,))
                
                # Update product stock only if it's positive
                if stock > 0:
                    c.execute("UPDATE products SET stock = stock - 1 WHERE code = ?", (selected_product['code'],))
                conn.commit()
                conn.close()
                
                success_text = (
                    f"✅ ORDER BERHASIL\n\n"
                    f"📦 Produk: {selected_product['name']}\n"
                    f"📮 Tujuan: {tujuan}\n"
                    f"💰 Harga: Rp {product_price:,.0f}\n"
                    f"📋 Order ID: {order_id}\n"
                    f"💳 Sisa Saldo: Rp {new_saldo:,.0f}\n\n"
                    f"Terima kasih telah berbelanja! 🎉"
                )
                
                await safe_edit_message_text(
                    query,
                    success_text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🛒 Beli Lagi", callback_data="menu_order")],
                        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                    ])
                )
                
            else:
                # Refund user and update order status
                database.increment_user_saldo(user_id, product_price)
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("UPDATE orders SET status = 'failed' WHERE order_id = ?", (order_id,))
                conn.commit()
                conn.close()
                
                error_msg = api_response.get('msg', 'Unknown error') if api_response else 'Provider tidak merespon'
                
                failed_text = (
                    f"❌ ORDER GAGAL\n\n"
                    f"📦 Produk: {selected_product['name']}\n"
                    f"📮 Tujuan: {tujuan}\n"
                    f"💰 Harga: Rp {product_price:,.0f}\n"
                    f"📋 Order ID: {order_id}\n"
                    f"💳 Saldo telah dikembalikan: Rp {new_saldo + product_price:,.0f}\n\n"
                    f"Error: {error_msg}"
                )
                
                await safe_edit_message_text(
                    query,
                    failed_text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Coba Lagi", callback_data="menu_order")],
                        [InlineKeyboardButton("📞 Bantuan", callback_data="menu_help")],
                        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                    ])
                )
        
        except Exception as api_error:
            logger.error(f"API Error: {api_error}")
            # Refund user and mark as failed
            database.increment_user_saldo(user_id, product_price)
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE orders SET status = 'failed' WHERE order_id = ?", (order_id,))
            conn.commit()
            conn.close()
            
            await safe_edit_message_text(
                query,
                f"❌ ERROR SISTEM\n\nOrder gagal diproses karena error sistem.\nSaldo telah dikembalikan.\n\nOrder ID: {order_id}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 Bantuan", callback_data="menu_help")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ])
            )
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in process_order: {e}")
        await safe_edit_message_text(
            query,
            "❌ Error memproses order. Silakan hubungi admin.\n\nSaldo akan dikembalikan jika terpotong.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return ConversationHandler.END

async def check_order_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check specific order status"""
    query = update.callback_query
    await query.answer()
    
    try:
        order_id = query.data.replace("check_status_", "")
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT order_id, user_id, product_code, product_name, target, price, status, created_at FROM orders WHERE order_id = ?", (order_id,))
        order = c.fetchone()
        conn.close()

        if not order:
            await safe_edit_message_text(
                query,
                f"❌ Order ID {order_id} tidak ditemukan."
            )
            return ConversationHandler.END
        
        order_id, user_id, product_code, product_name, target, price, status, created_at = order
        
        status_info = {
            'success': ('✅ BERHASIL', 'Order telah berhasil diproses'),
            'failed': ('❌ GAGAL', 'Order gagal diproses, saldo telah dikembalikan'),
            'processing': ('🔄 PROSES', 'Order sedang dalam proses'),
            'pending': ('⏳ MENUNGGU', 'Order menunggu diproses')
        }
        
        status_text, status_desc = status_info.get(status, ('❓ UNKNOWN', 'Status tidak diketahui'))
        
        status_msg = (
            f"📋 STATUS ORDER\n\n"
            f"🆔 Order ID: {order_id}\n"
            f"📦 Produk: {product_name}\n"
            f"📮 Tujuan: {target}\n"
            f"💰 Harga: Rp {price:,.0f}\n"
            f"🕒 Waktu: {created_at}\n\n"
            f"Status: {status_text}\n"
            f"{status_desc}"
        )
        
        keyboard = [[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]
        
        if status in ['processing', 'pending']:
            keyboard.insert(0, [InlineKeyboardButton("🔄 Refresh Status", callback_data=f"check_status_{order_id}")])
        
        await safe_edit_message_text(
            query,
            status_msg,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error checking order status: {e}")
        await safe_edit_message_text(
            query,
            "❌ Gagal memeriksa status order.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel order and return to main menu"""
    try:
        # Clear user data
        context.user_data.clear()
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await safe_edit_message_text(
                update.callback_query,
                "❌ Order dibatalkan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
        else:
            await safe_reply_message(
                update,
                "❌ Order dibatalkan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in cancel_order: {e}")
        return ConversationHandler.END

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start order process from command"""
    return await menu_main(update, context)

# Conversation handler - FIXED VERSION
def get_conversation_handler():
    """Return the conversation handler for orders - FIXED VERSION"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(menu_handler, pattern="^menu_"),
            CommandHandler('start', start_order),
            CommandHandler('order', start_order)
        ],
        states={
            MENU: [
                CallbackQueryHandler(menu_handler, pattern="^menu_")
            ],
            CHOOSING_GROUP: [
                CallbackQueryHandler(choose_group, pattern="^group_"),
                CallbackQueryHandler(menu_handler, pattern="^menu_")
            ],
            CHOOSING_PRODUCT: [
                CallbackQueryHandler(choose_product, pattern="^page_|^back_to_categories|^prod_"),
                CallbackQueryHandler(back_to_products, pattern="^back_to_products_"),
                CallbackQueryHandler(menu_handler, pattern="^menu_")
            ],
            ENTER_TUJUAN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_tujuan),
                CallbackQueryHandler(back_to_products, pattern="^back_to_products_"),
                CallbackQueryHandler(menu_handler, pattern="^menu_")
            ],
            CONFIRM_ORDER: [
                CallbackQueryHandler(process_order, pattern="^confirm_order$"),
                CallbackQueryHandler(cancel_order, pattern="^cancel_order$"),
                CallbackQueryHandler(menu_handler, pattern="^menu_")
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel_order),
            CommandHandler('start', menu_main),
            CommandHandler('menu', menu_main),
            CallbackQueryHandler(menu_handler, pattern="^menu_"),
            CallbackQueryHandler(cancel_order, pattern="^cancel_order$")
        ],
        allow_reentry=True,
        name="order_conversation"
    )

# Additional handlers for specific patterns
def get_additional_handlers():
    return [
        CallbackQueryHandler(check_order_status, pattern="^check_status_"),
        CallbackQueryHandler(back_to_products, pattern="^back_to_products_")
    ]
