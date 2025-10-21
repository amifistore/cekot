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
            [InlineKeyboardButton("💸 Top Up Saldo", callback_data="topup_start")],
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
                    [InlineKeyboardButton("💸 Top Up Saldo", callback_data="topup_start")],
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
            await query.answer("🔄 Membuka menu topup...")
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
    """Show user's order history - FIXED VERSION"""
    query = update.callback_query
    await query.answer()
    
    try:
        user_id = str(query.from_user.id)
        
        # Get last 10 orders from database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT id, product_name, customer_input, price, status, created_at, sn
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
                order_id, product_name, target, price, status, created_at, sn = order
                status_emoji = {
                    'completed': '✅',
                    'pending': '⏳', 
                    'failed': '❌',
                    'processing': '🔄',
                    'refunded': '💸',
                    'partial': '⚠️'
                }.get(status, '❓')
                
                # Format timestamp
                if ' ' in str(created_at):
                    order_time = str(created_at).split(' ')[1][:5]
                    order_date = str(created_at).split(' ')[0]
                else:
                    order_time = str(created_at)[:5]
                    order_date = str(created_at)
                
                # Display SN if available
                sn_display = f"\n🔢 SN: `{sn}`" if sn else ""
                
                msg += (
                    f"{status_emoji} *{product_name}*\n"
                    f"📮 Tujuan: `{target}`\n"
                    f"💰 Rp {price:,}{sn_display}\n"
                    f"📅 {order_date} {order_time} | {status.upper()}\n"
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

async def show_products_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show products in selected group"""
    query = update.callback_query
    await query.answer()
    
    group_name_encoded = query.data.replace('group_', '')
    
    try:
        groups = get_grouped_products()
        group_name = None
        
        # Find the actual group name
        for gname in groups.keys():
            clean_gname = re.sub(r'[^a-zA-Z0-9_]', '', gname.replace(' ', '_'))
            if clean_gname == group_name_encoded:
                group_name = gname
                break
        
        if not group_name or group_name not in groups:
            await safe_edit_message_text(
                query,
                "❌ Kategori produk tidak ditemukan.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📦 Kategori Lain", callback_data="menu_order")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ])
            )
            return MENU
        
        products = groups[group_name]
        context.user_data['current_group'] = group_name
        context.user_data['current_products'] = products
        
        # Create product buttons
        keyboard = []
        for product in products:
            # Product status indicator
            if product.get('gangguan') == 1:
                status_emoji = "🚧"
            elif product.get('kosong') == 1:
                status_emoji = "🔴"
            elif product.get('stock', 0) > 10:
                status_emoji = "🟢"
            elif product.get('stock', 0) > 0:
                status_emoji = "🟡"
            else:
                status_emoji = "🔴"
            
            button_text = f"{status_emoji} {product['name']} - Rp {product['price']:,}"
            callback_data = f"product_{product['code']}"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Add navigation buttons
        keyboard.append([InlineKeyboardButton("🔙 Kembali ke Kategori", callback_data="menu_order")])
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            f"📦 **PRODUK {group_name.upper()}**\n\n"
            f"🟢 Tersedia | 🟡 Sedikit | 🔴 Habis/Kosong | 🚧 Gangguan\n\n"
            f"Silakan pilih produk:"
        )
        
        await safe_edit_message_text(
            query,
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return CHOOSING_PRODUCT
        
    except Exception as e:
        logger.error(f"Error in show_products_in_group: {e}")
        await safe_edit_message_text(
            query,
            "❌ Terjadi error saat memuat produk. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Kembali ke Kategori", callback_data="menu_order")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
            ])
        )
        return MENU

async def select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product selection"""
    query = update.callback_query
    await query.answer()
    
    product_code = query.data.replace('product_', '')
    
    try:
        products = context.user_data.get('current_products', [])
        selected_product = None
        
        for product in products:
            if product['code'] == product_code:
                selected_product = product
                break
        
        if not selected_product:
            await safe_edit_message_text(
                query,
                "❌ Produk tidak ditemukan.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"group_{context.user_data.get('current_group', '').replace(' ', '_')}")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ])
            )
            return MENU
        
        # Store selected product in context
        context.user_data['selected_product'] = selected_product
        
        # Check product status
        status_msg = ""
        if selected_product.get('gangguan') == 1:
            status_msg = "🚧 **Produk sedang gangguan** - Mungkin terjadi delay"
        elif selected_product.get('kosong') == 1:
            status_msg = "🔴 **Produk kosong** - Tidak bisa dipesan sementara"
        elif selected_product.get('stock', 0) <= 0:
            status_msg = "🔴 **Stok habis** - Tidak bisa dipesan sementara"
        else:
            status_msg = "🟢 **Produk tersedia** - Bisa dipesan"
        
        message_text = (
            f"📦 **{selected_product['name']}**\n\n"
            f"💰 Harga: Rp {selected_product['price']:,}\n"
            f"📝 Deskripsi: {selected_product.get('description', 'Tidak ada deskripsi')}\n"
            f"📊 Status: {status_msg}\n\n"
            f"Silakan masukkan nomor tujuan:\n"
            f"• Contoh: 081234567890\n"
            f"• Pastikan nomor benar\n\n"
            f"❌ Ketik /cancel untuk membatalkan"
        )
        
        await safe_edit_message_text(
            query,
            message_text,
            parse_mode='Markdown'
        )
        
        return ENTER_TUJUAN
        
    except Exception as e:
        logger.error(f"Error in select_product: {e}")
        await safe_edit_message_text(
            query,
            "❌ Terjadi error saat memilih produk. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"group_{context.user_data.get('current_group', '').replace(' ', '_')}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
            ])
        )
        return MENU

async def enter_tujuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process target number input"""
    try:
        target = update.message.text.strip()
        
        # Basic validation
        if not target:
            await update.message.reply_text(
                "❌ Nomor tujuan tidak boleh kosong. Silakan masukkan nomor:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Menu", callback_data="menu_main")]
                ])
            )
            return ENTER_TUJUAN
        
        # Simple phone number validation (basic check)
        if not re.match(r'^[0-9+]{10,15}$', target.replace(' ', '').replace('-', '')):
            await update.message.reply_text(
                "❌ Format nomor tidak valid. Silakan masukkan nomor yang benar:\n"
                "Contoh: 081234567890 atau +6281234567890",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Menu", callback_data="menu_main")]
                ])
            )
            return ENTER_TUJUAN
        
        # Store target in context
        context.user_data['target'] = target
        
        # Get selected product
        product = context.user_data.get('selected_product', {})
        
        # Check user balance
        user_id = str(update.message.from_user.id)
        saldo = database.get_user_saldo(user_id)
        
        if saldo < product.get('price', 0):
            await update.message.reply_text(
                f"❌ Saldo tidak mencukupi!\n\n"
                f"💰 Saldo Anda: Rp {saldo:,}\n"
                f"💳 Harga produk: Rp {product.get('price', 0):,}\n"
                f"📊 Kekurangan: Rp {product.get('price', 0) - saldo:,}\n\n"
                f"Silakan top up saldo terlebih dahulu.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💸 Top Up Saldo", callback_data="topup_start")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ])
            )
            return MENU
        
        # Show confirmation
        status_info = ""
        if product.get('gangguan') == 1:
            status_info = "🚧 **PERINGATAN:** Produk sedang gangguan, mungkin terjadi delay"
        elif product.get('kosong') == 1 or product.get('stock', 0) <= 0:
            status_info = "🔴 **PERINGATAN:** Produk kosong/habis, mungkin gagal"
        else:
            status_info = "🟢 Produk tersedia"
        
        message_text = (
            f"✅ **KONFIRMASI ORDER**\n\n"
            f"📦 Produk: {product['name']}\n"
            f"💰 Harga: Rp {product['price']:,}\n"
            f"📮 Tujuan: `{target}`\n"
            f"💳 Saldo: Rp {saldo:,}\n"
            f"💰 Sisa: Rp {saldo - product['price']:,}\n\n"
            f"{status_info}\n\n"
            f"Apakah Anda yakin ingin melanjutkan?"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Ya, Lanjutkan", callback_data="confirm_order")],
            [InlineKeyboardButton("❌ Batalkan", callback_data="cancel_order")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return CONFIRM_ORDER
        
    except Exception as e:
        logger.error(f"Error in enter_tujuan: {e}")
        await update.message.reply_text(
            "❌ Terjadi error. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
            ])
        )
        return MENU

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle order confirmation"""
    query = update.callback_query
    await query.answer()
    
    try:
        user_id = str(query.from_user.id)
        product = context.user_data.get('selected_product', {})
        target = context.user_data.get('target', '')
        
        if not product or not target:
            await safe_edit_message_text(
                query,
                "❌ Data order tidak lengkap. Silakan ulangi dari awal.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ])
            )
            return MENU
        
        # Check balance again
        saldo = database.get_user_saldo(user_id)
        if saldo < product.get('price', 0):
            await safe_edit_message_text(
                query,
                f"❌ Saldo tidak mencukupi!\n\n"
                f"Silakan top up saldo terlebih dahulu.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💸 Top Up Saldo", callback_data="topup_start")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ])
            )
            return MENU
        
        # Show processing message
        await safe_edit_message_text(
            query,
            "🔄 **Memproses order Anda...**\n\n"
            "Mohon tunggu sebentar...",
            parse_mode='Markdown'
        )
        
        return await process_order(update, context)
        
    except Exception as e:
        logger.error(f"Error in confirm_order: {e}")
        await safe_edit_message_text(
            query,
            "❌ Terjadi error saat konfirmasi order. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
            ])
        )
        return MENU

async def process_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the actual order - FIXED VERSION tanpa kolom cost & profit"""
    try:
        user_id = str(update.callback_query.from_user.id)
        product = context.user_data.get('selected_product', {})
        target = context.user_data.get('target', '')
        
        # Create order in database - menggunakan database module
        order_id = database.create_order(
            user_id=user_id,
            product_code=product['code'],
            customer_input=target
        )
        
        if order_id:
            logger.info(f"Order created successfully: ID {order_id}")
            
            # Simulate API call to provider
            await asyncio.sleep(2)
            
            # Simulate successful order with random SN
            import random
            sn_number = random.randint(100000, 999999)
            sn = f"SN{sn_number}"
            
            # Update order status to completed dengan SN
            success = database.update_order_status(
                order_id=order_id, 
                status='completed', 
                sn=sn,
                note="Order berhasil diproses"
            )
            
            if success:
                # Get updated balance
                new_saldo = database.get_user_saldo(user_id)
                
                # Log transaction
                database.add_system_log(
                    level='INFO',
                    module='ORDER',
                    message=f"Order completed: {order_id} - {product['name']} to {target}",
                    user_id=user_id
                )
                
                # Send success message
                success_text = (
                    f"✅ **ORDER BERHASIL!**\n\n"
                    f"📦 Produk: {product['name']}\n"
                    f"📮 Tujuan: `{target}`\n"
                    f"💰 Harga: Rp {product['price']:,}\n"
                    f"📋 Order ID: `{order_id}`\n"
                    f"🔢 SN: `{sn}`\n"
                    f"💳 Sisa Saldo: Rp {new_saldo:,}\n\n"
                    f"Terima kasih telah berbelanja! 🛍️"
                )
                
                await update.callback_query.message.reply_text(
                    success_text,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🛒 Beli Lagi", callback_data="menu_order")],
                        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                    ])
                )
            else:
                # If update status failed, set to failed
                database.update_order_status(order_id, 'failed', note="Gagal update status order")
                await update.callback_query.message.reply_text(
                    "❌ Gagal memproses order. Silakan hubungi admin.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                    ])
                )
            
        else:
            logger.error(f"Failed to create order for user {user_id}")
            await update.callback_query.message.reply_text(
                "❌ Gagal membuat order. Silakan coba lagi.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ])
            )
        
        # Clear context
        context.user_data.clear()
        return MENU
        
    except Exception as e:
        logger.error(f"Error in process_order: {e}")
        
        # Try to log the error
        try:
            user_id = str(update.callback_query.from_user.id)
            database.add_system_log(
                level='ERROR',
                module='ORDER',
                message=f"Order processing failed: {str(e)}",
                user_id=user_id
            )
        except:
            pass
            
        await update.callback_query.message.reply_text(
            "❌ Terjadi error saat memproses order. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
            ])
        )
        return MENU

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle order cancellation"""
    query = update.callback_query
    await query.answer()
    
    # Clear context
    context.user_data.clear()
    
    await safe_edit_message_text(
        query,
        "❌ **Order dibatalkan**\n\nKembali ke menu utama.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
        ])
    )
    
    return MENU

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the entire conversation"""
    context.user_data.clear()
    
    await update.message.reply_text(
        "❌ **Dibatalkan**\n\nKembali ke menu utama.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
        ])
    )
    
    return ConversationHandler.END

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
                CallbackQueryHandler(show_products_in_group, pattern="^group_"),
                CallbackQueryHandler(show_group_menu, pattern="^menu_order$"),
                CallbackQueryHandler(menu_main, pattern="^menu_main$"),
            ],
            CHOOSING_PRODUCT: [
                CallbackQueryHandler(select_product, pattern="^product_"),
                CallbackQueryHandler(show_group_menu, pattern="^menu_order$"),
                CallbackQueryHandler(menu_main, pattern="^menu_main$"),
            ],
            ENTER_TUJUAN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_tujuan),
                CommandHandler("cancel", cancel_conversation),
            ],
            CONFIRM_ORDER: [
                CallbackQueryHandler(confirm_order, pattern="^confirm_order$"),
                CallbackQueryHandler(cancel_order, pattern="^cancel_order$"),
                CallbackQueryHandler(menu_main, pattern="^menu_main$"),
            ],
            ORDER_PROCESSING: [
                CallbackQueryHandler(process_order, pattern="^process_order$"),
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            CallbackQueryHandler(menu_main, pattern="^menu_main$"),
            CallbackQueryHandler(cancel_order, pattern="^cancel_order$"),
        ],
        allow_reentry=True
    )

# Export the conversation handler
order_conv_handler = get_conversation_handler()
