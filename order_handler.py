import logging
import uuid
import requests
import aiohttp
import asyncio
import sqlite3
import re
import time
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

# ==================== KHFYPAY API INTEGRATION ====================

class KhfyPayAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://panel.khfy-store.com/api_v2"
    
    def get_products(self):
        """Get list products from KhfyPay"""
        try:
            url = f"{self.base_url}/list_product"
            params = {"api_key": self.api_key}
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            return response.json()
        except Exception as e:
            logger.error(f"Error getting KhfyPay products: {e}")
            return None
    
    def create_order(self, product_code, target, custom_reffid=None):
        """Create new order in KhfyPay"""
        try:
            url = f"{self.base_url}/trx"
            reffid = custom_reffid or str(uuid.uuid4())
            
            params = {
                "produk": product_code,
                "tujuan": target,
                "reff_id": reffid,
                "api_key": self.api_key
            }
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            result['reffid'] = reffid  # Tambahkan reffid ke result
            
            return result
        except Exception as e:
            logger.error(f"Error creating KhfyPay order: {e}")
            return None
    
    def check_order_status(self, reffid):
        """Check order status by reffid"""
        try:
            url = f"{self.base_url}/history"
            params = {
                "api_key": self.api_key,
                "refid": reffid
            }
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            return response.json()
        except Exception as e:
            logger.error(f"Error checking KhfyPay order status: {e}")
            return None

# ==================== WEBHOOK STATUS SYNC FUNCTIONS ====================

def update_order_status_from_webhook(reffid, status, keterangan=None, sn=None):
    """Update order status based on webhook data"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Map webhook status to internal status
        status_mapping = {
            'SUKSES': 'completed',
            'GAGAL': 'failed',
            'PENDING': 'pending',
            'PROSES': 'processing',
            'REFUND': 'refunded'
        }
        
        internal_status = status_mapping.get(status.upper(), status.lower())
        
        # Update order status
        update_query = """
            UPDATE orders 
            SET status = ?, updated_at = ?, note = COALESCE(?, note)
            WHERE provider_order_id = ?
        """
        update_params = [internal_status, datetime.now(), keterangan, reffid]
        
        if sn:
            update_query = """
                UPDATE orders 
                SET status = ?, updated_at = ?, note = COALESCE(?, note), sn = ?
                WHERE provider_order_id = ?
            """
            update_params = [internal_status, datetime.now(), keterangan, sn, reffid]
        
        c.execute(update_query, update_params)
        
        # If order failed and needs refund, process refund
        if internal_status == 'failed':
            c.execute("""
                SELECT user_id, price FROM orders 
                WHERE provider_order_id = ? AND status_refund = 0
            """, (reffid,))
            order_data = c.fetchone()
            
            if order_data:
                user_id, price = order_data
                # Refund user balance
                c.execute("""
                    UPDATE users SET saldo = saldo + ? 
                    WHERE user_id = ?
                """, (price, user_id))
                # Mark as refunded
                c.execute("""
                    UPDATE orders SET status_refund = 1 
                    WHERE provider_order_id = ?
                """, (reffid,))
                logger.info(f"Refund processed for order {reffid}: user {user_id} amount {price}")
        
        conn.commit()
        conn.close()
        
        logger.info(f"Order status updated: {reffid} -> {internal_status}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating order status from webhook: {e}")
        return False

def get_order_by_reffid(reffid):
    """Get order details by reffid"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT id, user_id, product_name, customer_input, price, status, 
                   provider_order_id, created_at, sn, note
            FROM orders 
            WHERE provider_order_id = ?
        """, (reffid,))
        order = c.fetchone()
        conn.close()
        return order
    except Exception as e:
        logger.error(f"Error getting order by reffid: {e}")
        return None

async def notify_user_order_update(context, user_id, order_data):
    """Notify user about order status update"""
    try:
        order_id, _, product_name, target, price, status, provider_id, created_at, sn, note = order_data
        
        status_emoji = {
            'completed': '✅',
            'pending': '⏳', 
            'failed': '❌',
            'processing': '🔄',
            'refunded': '💸',
            'partial': '⚠️'
        }.get(status, '❓')
        
        message = (
            f"{status_emoji} *UPDATE STATUS ORDER*\n\n"
            f"📦 *Produk:* {product_name}\n"
            f"📮 *Tujuan:* `{target}`\n"
            f"💰 *Harga:* Rp {price:,}\n"
            f"🆔 *Ref ID:* `{provider_id}`\n"
            f"📊 *Status:* {status.upper()}\n"
        )
        
        if sn:
            message += f"🔢 *SN:* `{sn}`\n"
        if note:
            message += f"📝 *Keterangan:* {note}\n"
        
        message += f"\n⏰ *Update:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await context.bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error notifying user about order update: {e}")

# ==================== UTILITY FUNCTIONS ====================

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

def validate_phone_number(phone):
    """Validate phone number format"""
    # Remove non-digit characters
    phone = re.sub(r'\D', '', phone)
    
    # Check if it's a valid Indonesian phone number
    if phone.startswith('0'):
        phone = '62' + phone[1:]
    elif phone.startswith('8'):
        phone = '62' + phone
    elif phone.startswith('+62'):
        phone = phone[1:]
    
    # Validate length
    if len(phone) < 10 or len(phone) > 14:
        return None
    
    return phone

def validate_pulsa_target(phone, product_code):
    """Validate pulsa target"""
    phone = validate_phone_number(phone)
    if not phone:
        return None
    
    # Additional validation for specific products
    if product_code.startswith('TS'):
        # Telkomsel validation
        if not phone.startswith('62852') and not phone.startswith('62853') and not phone.startswith('62811') and not phone.startswith('62812') and not phone.startswith('62813') and not phone.startswith('62821') and not phone.startswith('62822') and not phone.startswith('62823'):
            return None
    elif product_code.startswith('AX'):
        # AXIS validation
        if not phone.startswith('62838') and not phone.startswith('62839') and not phone.startswith('62837'):
            return None
    elif product_code.startswith('XL'):
        # XL validation
        if not phone.startswith('62817') and not phone.startswith('62818') and not phone.startswith('62819') and not phone.startswith('62859'):
            return None
    elif product_code.startswith('IN'):
        # Indosat validation
        if not phone.startswith('62814') and not phone.startswith('62815') and not phone.startswith('62816') and not phone.startswith('62855') and not phone.startswith('62856') and not phone.startswith('62857') and not phone.startswith('62858'):
            return None
    elif product_code.startswith('SM'):
        # Smartfren validation
        if not phone.startswith('62888') and not phone.startswith('62889'):
            return None
    elif product_code.startswith('3'):
        # Three validation
        if not phone.startswith('62895') and not phone.startswith('62896') and not phone.startswith('62897') and not phone.startswith('62898') and not phone.startswith('62899'):
            return None
    
    return phone

# ==================== PRODUCT MANAGEMENT ====================

def get_grouped_products():
    """Get products grouped by category from database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT code, name, price, category, description, status, gangguan, kosong, stock, minimal, maksimal
            FROM products 
            WHERE status='active'
            ORDER BY category, name ASC
        """)
        products = c.fetchall()
        conn.close()

        logger.info(f"Found {len(products)} active products in database")
        
        groups = {}
        for code, name, price, category, description, status, gangguan, kosong, stock, minimal, maksimal in products:
            # Use category from database
            group = category or "Lainnya"
            
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
                'kosong': kosong,
                'minimal': minimal,
                'maksimal': maksimal
            })
        
        # Sort groups alphabetically
        sorted_groups = {}
        for group in sorted(groups.keys()):
            sorted_groups[group] = groups[group]
            
        return sorted_groups
        
    except Exception as e:
        logger.error(f"Error getting grouped products from database: {e}")
        return {}

def get_product_by_code(product_code):
    """Get product details by code"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT code, name, price, category, description, status, gangguan, kosong, stock, minimal, maksimal
            FROM products 
            WHERE code = ? AND status = 'active'
        """, (product_code,))
        product = c.fetchone()
        conn.close()
        
        if product:
            return {
                'code': product[0],
                'name': product[1],
                'price': product[2],
                'category': product[3],
                'description': product[4],
                'status': product[5],
                'gangguan': product[6],
                'kosong': product[7],
                'stock': product[8],
                'minimal': product[9],
                'maksimal': product[10]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting product by code: {e}")
        return None

# ==================== MAIN MENU & NAVIGATION ====================

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

# ==================== STOCK & HISTORY ====================

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
            SELECT id, product_name, customer_input, price, status, created_at, sn, provider_order_id
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
                order_id, product_name, target, price, status, created_at, sn, provider_id = order
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
                # Display provider ID if available
                provider_display = f"\n🔗 Ref ID: `{provider_id}`" if provider_id else ""
                
                msg += (
                    f"{status_emoji} *{product_name}*\n"
                    f"📮 Tujuan: `{target}`\n"
                    f"💰 Rp {price:,}{sn_display}{provider_display}\n"
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

# ==================== ORDER FLOW ====================

async def show_group_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show product groups menu from database"""
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
        total_products = sum(len(products) for products in groups.values())
        
        keyboard = []
        for group_name in groups.keys():
            product_count = len(groups[group_name])
            keyboard.append([
                InlineKeyboardButton(
                    f"{group_name} ({product_count})", 
                    callback_data=f"group_{group_name}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await safe_edit_message_text(
            query,
            f"📦 *PILIH KATEGORI PRODUK*\n\n"
            f"Total {total_products} produk aktif tersedia\n\n"
            f"Pilih kategori:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        return CHOOSING_GROUP
        
    except Exception as e:
        logger.error(f"Error in show_group_menu: {e}")
        await safe_reply_message(update, "❌ Error memuat kategori produk. Silakan coba lagi.")
        return MENU

async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show products in selected group"""
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        group_name = data.replace('group_', '')
        
        groups = get_grouped_products()
        if group_name not in groups:
            await safe_edit_message_text(
                query,
                "❌ Kategori tidak ditemukan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
            return MENU
        
        products = groups[group_name]
        context.user_data['current_group'] = group_name
        context.user_data['current_products'] = products
        
        # Create pagination if needed
        page = context.user_data.get('product_page', 0)
        start_idx = page * PRODUCTS_PER_PAGE
        end_idx = start_idx + PRODUCTS_PER_PAGE
        page_products = products[start_idx:end_idx]
        
        keyboard = []
        for product in page_products:
            # Add status indicator
            if product['gangguan'] == 1:
                status_emoji = "🚧"
            elif product['kosong'] == 1:
                status_emoji = "🔴"
            elif product['stock'] > 10:
                status_emoji = "🟢"
            elif product['stock'] > 0:
                status_emoji = "🟡"
            else:
                status_emoji = "🔴"
            
            button_text = f"{status_emoji} {product['name']} - Rp {product['price']:,}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"product_{product['code']}")])
        
        # Add navigation buttons
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data="prev_page"))
        
        if end_idx < len(products):
            nav_buttons.append(InlineKeyboardButton("Selanjutnya ➡️", callback_data="next_page"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("🔙 Kembali ke Kategori", callback_data="back_to_groups")])
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        total_pages = (len(products) + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE
        page_info = f" (Halaman {page + 1}/{total_pages})" if total_pages > 1 else ""
        
        await safe_edit_message_text(
            query,
            f"📦 *PRODUK {group_name.upper()}*{page_info}\n\n"
            f"Pilih produk yang ingin dibeli:\n\n"
            f"🟢 Tersedia | 🟡 Sedikit | 🔴 Habis | 🚧 Gangguan",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        return CHOOSING_PRODUCT
        
    except Exception as e:
        logger.error(f"Error in show_products: {e}")
        await safe_edit_message_text(
            query,
            "❌ Error memuat produk. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return MENU

async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product pagination"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    current_page = context.user_data.get('product_page', 0)
    
    if data == 'next_page':
        context.user_data['product_page'] = current_page + 1
    elif data == 'prev_page':
        context.user_data['product_page'] = max(0, current_page - 1)
    
    return await show_products(update, context)

async def select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product selection"""
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        product_code = data.replace('product_', '')
        
        product = get_product_by_code(product_code)
        if not product:
            await safe_edit_message_text(
                query,
                "❌ Produk tidak ditemukan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
            return MENU
        
        # Check product availability
        if product['kosong'] == 1:
            await safe_edit_message_text(
                query,
                f"❌ *{product['name']}*\n\n"
                f"Produk sedang kosong/tidak tersedia.\n\n"
                f"Silakan pilih produk lain.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"group_{product['category']}")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ]),
                parse_mode="Markdown"
            )
            return CHOOSING_PRODUCT
        
        if product['gangguan'] == 1:
            await safe_edit_message_text(
                query,
                f"🚧 *{product['name']}*\n\n"
                f"Produk sedang mengalami gangguan.\n\n"
                f"Silakan pilih produk lain atau coba lagi nanti.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"group_{product['category']}")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ]),
                parse_mode="Markdown"
            )
            return CHOOSING_PRODUCT
        
        if product['stock'] <= 0:
            await safe_edit_message_text(
                query,
                f"🔴 *{product['name']}*\n\n"
                f"Stok produk habis.\n\n"
                f"Silakan pilih produk lain.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"group_{product['category']}")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ]),
                parse_mode="Markdown"
            )
            return CHOOSING_PRODUCT
        
        # Store selected product
        context.user_data['selected_product'] = product
        
        # Ask for target
        target_example = "Contoh: 081234567890"
        if product['code'].startswith('PLN'):
            target_example = "Contoh: 123456789012345 (ID Pelanggan PLN)"
        elif product['code'].startswith('VOUCHER'):
            target_example = "Contoh: 1234567890 (ID Game)"
        
        await safe_edit_message_text(
            query,
            f"🛒 *PILIHAN PRODUK*\n\n"
            f"📦 {product['name']}\n"
            f"💰 Harga: Rp {product['price']:,}\n"
            f"📝 {product['description'] or 'Tidak ada deskripsi'}\n\n"
            f"📮 *Masukkan nomor tujuan:*\n"
            f"{target_example}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"group_{product['category']}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
            ]),
            parse_mode="Markdown"
        )
        
        return ENTER_TUJUAN
        
    except Exception as e:
        logger.error(f"Error in select_product: {e}")
        await safe_edit_message_text(
            query,
            "❌ Error memilih produk. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return MENU

async def receive_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and validate target input"""
    try:
        target = update.message.text.strip()
        product = context.user_data.get('selected_product')
        
        if not product:
            await safe_reply_message(update, "❌ Sesi telah berakhir. Silakan mulai ulang dari menu.")
            return MENU
        
        # Validate target based on product type
        validated_target = None
        if product['code'].startswith(('TS', 'AX', 'XL', 'IN', 'SM', '3')):  # Pulsa/Data
            validated_target = validate_pulsa_target(target, product['code'])
        elif product['code'].startswith('PLN'):  # PLN
            validated_target = re.sub(r'\D', '', target)
            if len(validated_target) < 10 or len(validated_target) > 20:
                validated_target = None
        else:  # Other products
            validated_target = target.strip()
        
        if not validated_target:
            await safe_reply_message(
                update,
                f"❌ Format tujuan tidak valid!\n\n"
                f"Produk: {product['name']}\n"
                f"Tujuan: {target}\n\n"
                f"Silakan masukkan format yang benar."
            )
            return ENTER_TUJUAN
        
        # Store validated target
        context.user_data['order_target'] = validated_target
        
        # Show confirmation
        keyboard = [
            [
                InlineKeyboardButton("✅ Konfirmasi Order", callback_data="confirm_order"),
                InlineKeyboardButton("❌ Batalkan", callback_data="cancel_order")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await safe_reply_message(
            update,
            f"📋 *KONFIRMASI ORDER*\n\n"
            f"📦 *Produk:* {product['name']}\n"
            f"📮 *Tujuan:* `{validated_target}`\n"
            f"💰 *Harga:* Rp {product['price']:,}\n\n"
            f"💰 *Saldo Anda:* Rp {database.get_user_saldo(str(update.effective_user.id)):,}\n\n"
            f"Apakah Anda yakin ingin melanjutkan?",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        return CONFIRM_ORDER
        
    except Exception as e:
        logger.error(f"Error in receive_target: {e}")
        await safe_reply_message(update, "❌ Error memproses tujuan. Silakan coba lagi.")
        return MENU

async def process_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process order with webhook synchronization"""
    query = update.callback_query
    await query.answer()
    
    user_data = context.user_data
    product_data = user_data.get('selected_product')
    target = user_data.get('order_target')
    
    if not product_data or not target:
        await safe_edit_message_text(
            query,
            "❌ Data order tidak lengkap. Silakan ulangi dari awal.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return MENU
    
    try:
        user_id = str(query.from_user.id)
        username = query.from_user.username or ""
        full_name = query.from_user.full_name or ""
        
        # Get user balance
        saldo = database.get_user_saldo(user_id)
        product_price = product_data['price']
        
        if saldo < product_price:
            await safe_edit_message_text(
                query,
                f"❌ Saldo tidak cukup!\n\n"
                f"💰 Saldo Anda: Rp {saldo:,}\n"
                f"💳 Harga produk: Rp {product_price:,}\n"
                f"🔶 Kekurangan: Rp {product_price - saldo:,}\n\n"
                f"Silakan top up saldo terlebih dahulu.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💸 Top Up Saldo", callback_data="topup_start")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ])
            )
            return MENU
        
        # Initialize KhfyPay API
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            await safe_edit_message_text(
                query,
                "❌ Error: API key tidak terkonfigurasi.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
            return MENU
        
        khfy_api = KhfyPayAPI(api_key)
        
        # Generate unique reffid
        reffid = str(uuid.uuid4())
        
        # Create order in provider system
        await safe_edit_message_text(
            query,
            f"🔄 *MEMPROSES ORDER*...\n\n"
            f"📦 {product_data['name']}\n"
            f"📮 Tujuan: `{target}`\n"
            f"💰 Rp {product_price:,}\n\n"
            f"Mohon tunggu...",
            parse_mode="Markdown"
        )
        
        order_result = khfy_api.create_order(
            product_code=product_data['code'],
            target=target,
            custom_reffid=reffid
        )
        
        if not order_result:
            await safe_edit_message_text(
                query,
                "❌ Gagal membuat order di sistem provider. Silakan coba lagi.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
            return MENU
        
        # Check order result
        if order_result.get('status') == 'error':
            error_msg = order_result.get('message', 'Unknown error')
            await safe_edit_message_text(
                query,
                f"❌ Gagal membuat order:\n{error_msg}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
            return MENU
        
        # Deduct balance and save order to database
        new_saldo = database.update_user_saldo(user_id, -product_price)
        
        # Save order to database
        order_id = database.save_order(
            user_id=user_id,
            product_name=product_data['name'],
            product_code=product_data['code'],
            customer_input=target,
            price=product_price,
            status='pending',  # Initial status, will be updated by webhook
            provider_order_id=reffid,
            sn=order_result.get('sn'),  # Serial number if available
            note=order_result.get('message', 'Order created')
        )
        
        if not order_id:
            # Refund if failed to save order
            database.update_user_saldo(user_id, product_price)
            await safe_edit_message_text(
                query,
                "❌ Gagal menyimpan order. Saldo telah dikembalikan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
            return MENU
        
        # Prepare success message
        status_emoji = "⏳"
        status_text = "PENDING"
        provider_message = order_result.get('message', 'Order diproses')
        
        if order_result.get('status') == 'success':
            status_emoji = "✅"
            status_text = "SUKSES"
            # Update status immediately if success
            database.update_order_status(order_id, 'completed')
        
        success_message = (
            f"{status_emoji} *ORDER BERHASIL DIBUAT*\n\n"
            f"📦 *Produk:* {product_data['name']}\n"
            f"📮 *Tujuan:* `{target}`\n"
            f"💰 *Harga:* Rp {product_price:,}\n"
            f"🔗 *Ref ID:* `{reffid}`\n"
            f"📊 *Status:* {status_text}\n"
            f"💬 *Pesan:* {provider_message}\n"
        )
        
        if order_result.get('sn'):
            success_message += f"🔢 *SN:* `{order_result.get('sn')}`\n"
        
        success_message += (
            f"\n💰 *Saldo Baru:* Rp {new_saldo:,}\n"
            f"⏰ *Waktu:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"📝 Status order akan diperbarui otomatis via webhook."
        )
        
        keyboard = [
            [InlineKeyboardButton("🛒 Beli Lagi", callback_data="menu_order")],
            [InlineKeyboardButton("📋 Riwayat Order", callback_data="menu_history")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await safe_edit_message_text(
            query,
            success_message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        # Clean up user data
        if 'selected_product' in user_data:
            del user_data['selected_product']
        if 'order_target' in user_data:
            del user_data['order_target']
        if 'product_page' in user_data:
            del user_data['product_page']
        if 'current_group' in user_data:
            del user_data['current_group']
        if 'current_products' in user_data:
            del user_data['current_products']
        
        return MENU
        
    except Exception as e:
        logger.error(f"Error processing order: {e}")
        await safe_edit_message_text(
            query,
            f"❌ Terjadi error saat memproses order:\n{str(e)}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return MENU

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel order and return to product selection"""
    query = update.callback_query
    await query.answer("Order dibatalkan")
    
    # Clear user data
    if 'selected_product' in context.user_data:
        del context.user_data['selected_product']
    if 'order_target' in context.user_data:
        del context.user_data['order_target']
    
    return await show_products(update, context)

# ==================== CONVERSATION HANDLER SETUP ====================

def get_order_conversation_handler():
    """Get order conversation handler"""
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler, pattern="^menu_order$")],
        states={
            CHOOSING_GROUP: [
                CallbackQueryHandler(show_products, pattern="^group_"),
                CallbackQueryHandler(menu_main, pattern="^menu_main$")
            ],
            CHOOSING_PRODUCT: [
                CallbackQueryHandler(select_product, pattern="^product_"),
                CallbackQueryHandler(handle_pagination, pattern="^(next_page|prev_page)$"),
                CallbackQueryHandler(show_group_menu, pattern="^back_to_groups$"),
                CallbackQueryHandler(menu_main, pattern="^menu_main$")
            ],
            ENTER_TUJUAN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_target),
                CallbackQueryHandler(show_products, pattern="^group_"),
                CallbackQueryHandler(menu_main, pattern="^menu_main$")
            ],
            CONFIRM_ORDER: [
                CallbackQueryHandler(process_order, pattern="^confirm_order$"),
                CallbackQueryHandler(cancel_order, pattern="^cancel_order$"),
                CallbackQueryHandler(show_products, pattern="^group_"),
                CallbackQueryHandler(menu_main, pattern="^menu_main$")
            ],
        },
        fallbacks=[
            CommandHandler("start", menu_main),
            CommandHandler("cancel", menu_main),
            CallbackQueryHandler(menu_main, pattern="^menu_main$")
        ],
        map_to_parent={
            MENU: MENU,
        }
    )

# ==================== ERROR HANDLER ====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the order handler"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    try:
        if update and update.callback_query:
            await safe_edit_message_text(
                update.callback_query,
                "❌ Terjadi error yang tidak terduga. Silakan coba lagi atau hubungi admin.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
        elif update and update.message:
            await safe_reply_message(
                update,
                "❌ Terjadi error yang tidak terduga. Silakan coba lagi atau hubungi admin.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")
    
    return MENU
