import logging
import uuid
import requests
import aiohttp
import asyncio
import sqlite3
import re
from datetime import datetime, timedelta
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

# States untuk order conversation
CHOOSING_GROUP, CHOOSING_PRODUCT, ENTER_TUJUAN, CONFIRM_ORDER = range(4)
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
            
            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            result['reffid'] = reffid  # Tambahkan reffid ke result
            
            return result
        except requests.exceptions.Timeout:
            logger.error(f"Timeout creating order for {product_code}")
            return {"status": "error", "message": "Timeout - Silakan cek status manual"}
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error creating order: {e}")
            return {"status": "error", "message": f"Network error: {str(e)}"}
        except Exception as e:
            logger.error(f"Error creating KhfyPay order: {e}")
            return {"status": "error", "message": f"System error: {str(e)}"}
    
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

    def check_stock_akrab(self):
        """Check stock akrab XL Axis"""
        try:
            url = "https://panel.khfy-store.com/api_v3/cek_stock_akrab"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error checking stock akrab: {e}")
            return None

# ==================== STOCK SYNCHRONIZATION SYSTEM ====================

def sync_products_with_provider():
    """Sinkronisasi produk database dengan provider KhfyPay"""
    try:
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            logger.error("API key tidak tersedia untuk sinkronisasi produk")
            return False
        
        khfy_api = KhfyPayAPI(api_key)
        provider_products = khfy_api.get_products()
        
        if not provider_products:
            logger.error("Gagal mendapatkan produk dari provider")
            return False
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Reset status stock untuk produk aktif
        c.execute("UPDATE products SET stock = 0, gangguan = 0, kosong = 0 WHERE status = 'active'")
        
        updated_count = 0
        if isinstance(provider_products, list):
            for provider_product in provider_products:
                if isinstance(provider_product, dict):
                    product_code = provider_product.get('code', '').strip()
                    product_name = provider_product.get('name', '').strip()
                    price = provider_product.get('price', 0)
                    status = provider_product.get('status', 'active')
                    
                    if product_code:
                        # Cek apakah produk sudah ada di database
                        c.execute("SELECT code, name, price FROM products WHERE code = ?", (product_code,))
                        existing = c.fetchone()
                        
                        if existing:
                            # Update produk existing
                            c.execute("""
                                UPDATE products 
                                SET name = ?, price = ?, status = ?, stock = 100, 
                                    gangguan = 0, kosong = 0, last_sync = ?
                                WHERE code = ?
                            """, (product_name, price, status, datetime.now(), product_code))
                        else:
                            # Insert produk baru
                            # Tentukan kategori berdasarkan kode produk
                            category = "Umum"
                            if product_code.startswith("BPAL"):
                                category = "BPAL (Bonus Akrab L)"
                            elif product_code.startswith("BPAXXL"):
                                category = "BPAXXL (Bonus Akrab XXL)"
                            elif product_code.startswith("XLA"):
                                category = "XLA (Umum)"
                            elif "pulsa" in product_name.lower():
                                category = "Pulsa"
                            elif any(keyword in product_name.lower() for keyword in ['data', 'internet', 'kuota']):
                                category = "Internet"
                            elif "listrik" in product_name.lower() or "pln" in product_name.lower():
                                category = "Listrik"
                            elif "game" in product_name.lower():
                                category = "Game"
                            elif any(keyword in product_name.lower() for keyword in ['emoney', 'gopay', 'dana', 'ovo']):
                                category = "E-Money"
                            
                            c.execute("""
                                INSERT INTO products 
                                (code, name, price, category, description, status, stock, gangguan, kosong, last_sync)
                                VALUES (?, ?, ?, ?, ?, ?, 100, 0, 0, ?)
                            """, (product_code, product_name, price, category, '', status, datetime.now()))
                        
                        updated_count += 1
        
        conn.commit()
        conn.close()
        
        logger.info(f"Berhasil sinkronisasi {updated_count} produk dengan provider")
        return True
        
    except Exception as e:
        logger.error(f"Error sync_products_with_provider: {e}")
        return False

def get_grouped_products_with_sync():
    """Get products dengan auto-sync jika diperlukan"""
    try:
        # Cek kapan terakhir sync
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT MAX(last_sync) FROM products WHERE last_sync IS NOT NULL")
        last_sync = c.fetchone()[0]
        conn.close()
        
        # Sync jika lebih dari 1 jam yang lalu atau belum pernah sync
        should_sync = False
        if not last_sync:
            should_sync = True
        else:
            last_sync_time = datetime.fromisoformat(last_sync) if isinstance(last_sync, str) else last_sync
            if datetime.now() - last_sync_time > timedelta(hours=1):
                should_sync = True
        
        if should_sync:
            logger.info("Auto-syncing products with provider...")
            sync_products_with_provider()
        
        # Kembali ke fungsi original
        return get_grouped_products()
        
    except Exception as e:
        logger.error(f"Error in get_grouped_products_with_sync: {e}")
        return get_grouped_products()

# ==================== REFUND SYSTEM ====================

def process_refund(order_id, user_id, amount, reason="Order gagal"):
    """Process refund untuk order yang gagal"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Update saldo user
        c.execute("UPDATE users SET saldo = saldo + ? WHERE user_id = ?", (amount, user_id))
        
        # Update status order
        c.execute("""
            UPDATE orders 
            SET status = 'refunded', note = ?, updated_at = ?
            WHERE id = ?
        """, (f"Refund: {reason}", datetime.now(), order_id))
        
        # Log refund transaction
        c.execute("""
            INSERT INTO transactions 
            (user_id, type, amount, description, created_at)
            VALUES (?, 'refund', ?, ?, ?)
        """, (user_id, amount, f"Refund order #{order_id}: {reason}", datetime.now()))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Successfully refunded {amount} to user {user_id} for order {order_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error process_refund: {e}")
        return False

def auto_refund_failed_orders():
    """Otomatis refund order yang gagal dan belum di-refund"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Cari order yang failed tapi belum di-refund
        c.execute("""
            SELECT id, user_id, price, product_name, provider_order_id 
            FROM orders 
            WHERE status = 'failed' AND note NOT LIKE '%Refund%'
            LIMIT 50
        """)
        
        failed_orders = c.fetchall()
        
        refunded_count = 0
        for order_id, user_id, price, product_name, provider_order_id in failed_orders:
            try:
                # Process refund
                if process_refund(order_id, user_id, price, f"Auto-refund: {product_name}"):
                    refunded_count += 1
                    logger.info(f"Auto-refunded order {order_id} for user {user_id}")
            except Exception as e:
                logger.error(f"Error auto-refunding order {order_id}: {e}")
                continue
        
        conn.close()
        logger.info(f"Auto-refund completed: {refunded_count} orders refunded")
        return refunded_count
        
    except Exception as e:
        logger.error(f"Error auto_refund_failed_orders: {e}")
        return 0

# ==================== TRANSACTION HISTORY SYNC ====================

def sync_order_status_from_provider():
    """Sinkronisasi status order pending dengan provider"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Ambil order yang masih pending (lebih dari 5 menit)
        cutoff_time = datetime.now() - timedelta(minutes=5)
        c.execute("""
            SELECT id, provider_order_id, user_id, price, product_name, product_code
            FROM orders 
            WHERE status IN ('pending', 'processing') AND created_at < ?
            LIMIT 50
        """, (cutoff_time,))
        
        pending_orders = c.fetchall()
        conn.close()
        
        if not pending_orders:
            return 0
        
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            return 0
        
        khfy_api = KhfyPayAPI(api_key)
        synced_count = 0
        
        for order_id, provider_order_id, user_id, price, product_name, product_code in pending_orders:
            try:
                status_data = khfy_api.check_order_status(provider_order_id)
                
                if status_data and isinstance(status_data, dict):
                    status = status_data.get('status', '').lower()
                    message = status_data.get('message', '')
                    sn = status_data.get('sn', '')
                    
                    if status == 'success':
                        # Update order jadi completed
                        database.update_order_status(order_id, 'completed')
                        if sn:
                            conn = sqlite3.connect(DB_PATH)
                            c = conn.cursor()
                            c.execute("UPDATE orders SET sn = ? WHERE id = ?", (sn, order_id))
                            conn.commit()
                            conn.close()
                        logger.info(f"Order {order_id} synced as COMPLETED")
                        
                    elif status == 'error' or 'gagal' in message.lower():
                        # Update status dan refund
                        database.update_order_status(order_id, 'failed')
                        process_refund(order_id, user_id, price, f"Provider gagal: {message}")
                        logger.info(f"Order {order_id} synced as FAILED - refund processed")
                    
                    synced_count += 1
                    
            except Exception as e:
                logger.error(f"Error syncing order {order_id}: {e}")
                continue
        
        logger.info(f"Successfully synced {synced_count} orders from provider")
        return synced_count
        
    except Exception as e:
        logger.error(f"Error sync_order_status_from_provider: {e}")
        return 0

# ==================== UTILITY FUNCTIONS ====================

async def safe_edit_message_text(update, text, *args, **kwargs):
    """Safely edit message text with error handling"""
    try:
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(text, *args, **kwargs)
            return True
        elif hasattr(update, 'message') and update.message:
            await update.message.reply_text(text, *args, **kwargs)
            return True
        return False
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e):
            return True
        elif "Message can't be deleted" in str(e):
            try:
                if hasattr(update, 'callback_query') and update.callback_query:
                    await update.callback_query.message.reply_text(text, *args, **kwargs)
                return True
            except Exception as send_error:
                logger.error(f"Failed to send new message: {send_error}")
                return False
        logger.error(f"Error editing message: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in safe_edit_message_text: {e}")
        return False

async def safe_reply_message(update, text, *args, **kwargs):
    """Safely reply to message with error handling"""
    try:
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(text, *args, **kwargs)
            return True
        elif hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.reply_text(text, *args, **kwargs)
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

# ==================== PRODUCT MANAGEMENT (SESUAI DATABASE ORI) ====================

def get_grouped_products():
    """Get products grouped by category from database - SAMA SEPERTI CODE ORI"""
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
            
            # Additional grouping for specific product codes - SAMA SEPERTI CODE ORI
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

def get_product_by_code(product_code):
    """Get product details by code - SAMA SEPERTI CODE ORI"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT code, name, price, category, description, status, gangguan, kosong, stock
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
                'stock': product[8]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting product by code: {e}")
        return None

# ==================== ORDER FLOW HANDLERS ====================

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main menu handler untuk order - dipanggil dari main.py"""
    query = update.callback_query
    await query.answer()
    
    try:
        return await show_group_menu(update, context)
    except Exception as e:
        logger.error(f"Error in order menu_handler: {e}")
        await safe_edit_message_text(
            update,
            "❌ Error memuat menu order. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ])
        )
        return ConversationHandler.END

async def show_group_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show product groups menu from database - SAMA SEPERTI CODE ORI"""
    try:
        if hasattr(update, 'callback_query'):
            query = update.callback_query
            await query.answer()
        else:
            query = None
        
        logger.info("Loading product groups from database...")
        groups = get_grouped_products_with_sync()  # Pakai yang dengan sync
        
        if not groups:
            logger.warning("No products found in database")
            await safe_edit_message_text(
                update,
                "❌ Tidak ada produk yang tersedia saat ini.\n\n"
                "ℹ️ Silakan hubungi admin untuk mengupdate produk.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Coba Lagi", callback_data="main_menu_order")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ])
            )
            return ConversationHandler.END
        
        # Calculate total products
        total_products = sum(len(products) for products in groups.values())
        
        keyboard = []
        for group_name in groups.keys():
            product_count = len(groups[group_name])
            keyboard.append([
                InlineKeyboardButton(
                    f"{group_name} ({product_count})", 
                    callback_data=f"order_group_{group_name}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            f"📦 *PILIH KATEGORI PRODUK*\n\n"
            f"Total {total_products} produk aktif tersedia\n\n"
            f"Pilih kategori:"
        )
        
        if query:
            await safe_edit_message_text(
                update,
                message_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        else:
            await safe_reply_message(
                update,
                message_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        
        return CHOOSING_GROUP
        
    except Exception as e:
        logger.error(f"Error in show_group_menu: {e}")
        await safe_reply_message(update, "❌ Error memuat kategori produk. Silakan coba lagi.")
        return ConversationHandler.END

async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show products in selected group - SAMA SEPERTI CODE ORI"""
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        group_name = data.replace('order_group_', '')
        
        groups = get_grouped_products_with_sync()  # Pakai yang dengan sync
        if group_name not in groups:
            await safe_edit_message_text(
                update,
                "❌ Kategori tidak ditemukan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
            )
            return ConversationHandler.END
        
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
            # Add status indicator - SAMA SEPERTI CODE ORI
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
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"order_product_{product['code']}")])
        
        # Add navigation buttons
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data="order_prev_page"))
        
        if end_idx < len(products):
            nav_buttons.append(InlineKeyboardButton("Selanjutnya ➡️", callback_data="order_next_page"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("🔙 Kembali ke Kategori", callback_data="order_back_to_groups")])
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        total_pages = (len(products) + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE
        page_info = f" (Halaman {page + 1}/{total_pages})" if total_pages > 1 else ""
        
        await safe_edit_message_text(
            update,
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
            update,
            "❌ Error memuat produk. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
        )
        return ConversationHandler.END

async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product pagination"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    current_page = context.user_data.get('product_page', 0)
    
    if data == 'order_next_page':
        context.user_data['product_page'] = current_page + 1
    elif data == 'order_prev_page':
        context.user_data['product_page'] = max(0, current_page - 1)
    
    return await show_products(update, context)

async def back_to_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kembali ke menu grup produk"""
    query = update.callback_query
    await query.answer()
    
    # Clear pagination state
    if 'product_page' in context.user_data:
        del context.user_data['product_page']
    
    return await show_group_menu(update, context)

async def select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product selection - SAMA SEPERTI CODE ORI"""
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        product_code = data.replace('order_product_', '')
        
        # Sync terakhir untuk pastikan stok update
        sync_products_with_provider()
        product = get_product_by_code(product_code)
        
        if not product:
            await safe_edit_message_text(
                update,
                "❌ Produk tidak ditemukan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
            )
            return ConversationHandler.END
        
        # Check product availability - SAMA SEPERTI CODE ORI
        if product['kosong'] == 1:
            await safe_edit_message_text(
                update,
                f"❌ *{product['name']}*\n\n"
                f"Produk sedang kosong/tidak tersedia.\n\n"
                f"Silakan pilih produk lain.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"order_group_{product['category']}")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ]),
                parse_mode="Markdown"
            )
            return CHOOSING_PRODUCT
        
        if product['gangguan'] == 1:
            await safe_edit_message_text(
                update,
                f"🚧 *{product['name']}*\n\n"
                f"Produk sedang mengalami gangguan.\n\n"
                f"Silakan pilih produk lain atau coba lagi nanti.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"order_group_{product['category']}")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ]),
                parse_mode="Markdown"
            )
            return CHOOSING_PRODUCT
        
        if product['stock'] <= 0:
            await safe_edit_message_text(
                update,
                f"🔴 *{product['name']}*\n\n"
                f"Stok produk habis.\n\n"
                f"Silakan pilih produk lain.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"order_group_{product['category']}")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ]),
                parse_mode="Markdown"
            )
            return CHOOSING_PRODUCT
        
        # Store selected product
        context.user_data['selected_product'] = product
        
        # Ask for target - SAMA SEPERTI CODE ORI
        target_example = "Contoh: 081234567890"
        if product['code'].startswith('PLN'):
            target_example = "Contoh: 123456789012345 (ID Pelanggan PLN)"
        elif product['code'].startswith('VOUCHER'):
            target_example = "Contoh: 1234567890 (ID Game)"
        
        await safe_edit_message_text(
            update,
            f"🛒 *PILIHAN PRODUK*\n\n"
            f"📦 {product['name']}\n"
            f"💰 Harga: Rp {product['price']:,}\n"
            f"📝 {product['description'] or 'Tidak ada deskripsi'}\n\n"
            f"📮 *Masukkan nomor tujuan:*\n"
            f"{target_example}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"order_group_{product['category']}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ]),
            parse_mode="Markdown"
        )
        
        return ENTER_TUJUAN
        
    except Exception as e:
        logger.error(f"Error in select_product: {e}")
        await safe_edit_message_text(
            update,
            "❌ Error memilih produk. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
        )
        return ConversationHandler.END

async def receive_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and validate target input"""
    try:
        target = update.message.text.strip()
        product = context.user_data.get('selected_product')
        
        if not product:
            await safe_reply_message(update, "❌ Sesi telah berakhir. Silakan mulai ulang dari menu.")
            return ConversationHandler.END
        
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
        user_id = str(update.effective_user.id)
        saldo = database.get_user_saldo(user_id)
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Konfirmasi Order", callback_data="order_confirm"),
                InlineKeyboardButton("❌ Batalkan", callback_data="order_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await safe_reply_message(
            update,
            f"📋 *KONFIRMASI ORDER*\n\n"
            f"📦 *Produk:* {product['name']}\n"
            f"📮 *Tujuan:* `{validated_target}`\n"
            f"💰 *Harga:* Rp {product['price']:,}\n\n"
            f"💰 *Saldo Anda:* Rp {saldo:,}\n\n"
            f"Apakah Anda yakin ingin melanjutkan?",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        return CONFIRM_ORDER
        
    except Exception as e:
        logger.error(f"Error in receive_target: {e}")
        await safe_reply_message(update, "❌ Error memproses tujuan. Silakan coba lagi.")
        return ConversationHandler.END

async def process_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process order confirmation dengan refund handling"""
    query = update.callback_query
    await query.answer()
    
    user_data = context.user_data
    product_data = user_data.get('selected_product')
    target = user_data.get('order_target')
    
    if not product_data or not target:
        await safe_edit_message_text(
            update,
            "❌ Data order tidak lengkap. Silakan ulangi dari awal.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
        )
        return ConversationHandler.END
    
    try:
        user_id = str(query.from_user.id)
        username = query.from_user.username or ""
        full_name = query.from_user.full_name or ""
        
        # Get user balance
        saldo = database.get_user_saldo(user_id)
        product_price = product_data['price']
        
        if saldo < product_price:
            await safe_edit_message_text(
                update,
                f"❌ Saldo tidak cukup!\n\n"
                f"💰 Saldo Anda: Rp {saldo:,}\n"
                f"💳 Harga produk: Rp {product_price:,}\n"
                f"🔶 Kekurangan: Rp {product_price - saldo:,}\n\n"
                f"Silakan top up saldo terlebih dahulu.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💸 Top Up Saldo", callback_data="topup_menu")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ])
            )
            return ConversationHandler.END
        
        # Initialize KhfyPay API
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            await safe_edit_message_text(
                update,
                "❌ Error: API key tidak terkonfigurasi.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
            )
            return ConversationHandler.END
        
        khfy_api = KhfyPayAPI(api_key)
        
        # Generate unique reffid
        reffid = str(uuid.uuid4())
        
        # Final stock check sebelum order
        await safe_edit_message_text(
            update,
            f"🔍 *MEMERIKSA KETERSEDIAAN TERAKHIR*...\n\n"
            f"📦 {product_data['name']}\n"
            f"📮 Tujuan: `{target}`\n\n"
            f"Mohon tunggu...",
            parse_mode="Markdown"
        )
        
        # Quick sync untuk produk ini
        sync_products_with_provider()
        updated_product = get_product_by_code(product_data['code'])
        
        if not updated_product or updated_product.get('kosong') == 1 or updated_product.get('stock', 0) <= 0:
            await safe_edit_message_text(
                update,
                f"❌ *PRODUK SUDAH TIDAK TERSEDIA*\n\n"
                f"📦 {product_data['name']}\n\n"
                f"Stok produk sedang habis atau tidak tersedia di provider.\n"
                f"Silakan pilih produk lain.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"order_group_{product_data['category']}")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ]),
                parse_mode="Markdown"
            )
            return CHOOSING_PRODUCT
        
        # Deduct balance FIRST (sebelum ke provider)
        new_saldo = database.update_user_saldo(user_id, -product_price)
        
        # Save order to database dengan status 'processing'
        order_id = database.save_order(
            user_id=user_id,
            product_name=product_data['name'],
            product_code=product_data['code'],
            customer_input=target,
            price=product_price,
            status='processing',  # Status processing (sedang diproses ke provider)
            provider_order_id=reffid,
            sn='',
            note='Sedang diproses ke provider'
        )
        
        if not order_id:
            # Refund jika gagal save order
            database.update_user_saldo(user_id, product_price)
            await safe_edit_message_text(
                update,
                "❌ Gagal menyimpan order. Saldo telah dikembalikan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
            )
            return ConversationHandler.END
        
        # Create order in provider system
        await safe_edit_message_text(
            update,
            f"🔄 *MEMPROSES ORDER KE PROVIDER*...\n\n"
            f"📦 {product_data['name']}\n"
            f"📮 Tujuan: `{target}`\n"
            f"💰 Rp {product_price:,}\n\n"
            f"Mohon tunggu...",
            parse_mode="Markdown"
        )
        
        # Sekarang kirim ke provider
        order_result = khfy_api.create_order(
            product_code=product_data['code'],
            target=target,
            custom_reffid=reffid
        )
        
        # Handle provider response
        if not order_result or order_result.get('status') == 'error':
            error_msg = order_result.get('message', 'Unknown error from provider') if order_result else 'Gagal terhubung ke provider'
            
            # REFUND: Order gagal di provider
            database.update_user_saldo(user_id, product_price)
            database.update_order_status(order_id, 'failed')
            process_refund(order_id, user_id, product_price, f"Provider error: {error_msg}")
            
            await safe_edit_message_text(
                update,
                f"❌ *ORDER GAGAL DI PROVIDER*\n\n"
                f"📦 {product_data['name']}\n"
                f"📮 Tujuan: `{target}`\n"
                f"💰 Rp {product_price:,}\n\n"
                f"*Error:* {error_msg}\n\n"
                f"✅ *Saldo telah dikembalikan* ke akun Anda.\n"
                f"💰 Saldo: Rp {new_saldo + product_price:,}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛒 Coba Lagi", callback_data="main_menu_order")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ]),
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
        # Update order dengan data dari provider
        provider_status = order_result.get('status', '')
        provider_message = order_result.get('message', '')
        sn_number = order_result.get('sn', '')
        
        final_status = 'pending'
        if provider_status == 'success':
            final_status = 'completed'
        elif provider_status == 'error':
            final_status = 'failed'
            # Auto refund untuk error yang langsung diketahui
            database.update_user_saldo(user_id, product_price)
            process_refund(order_id, user_id, product_price, f"Provider error: {provider_message}")
        
        database.update_order_status(order_id, final_status)
        
        # Update SN jika ada
        if sn_number:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE orders SET sn = ? WHERE id = ?", (sn_number, order_id))
            conn.commit()
            conn.close()
        
        # Prepare success message
        status_info = {
            'completed': ('✅', 'SUKSES', '🟢'),
            'pending': ('⏳', 'PENDING', '🟡'), 
            'failed': ('❌', 'GAGAL', '🔴')
        }
        
        emoji, status_text, color = status_info.get(final_status, ('⏳', 'PENDING', '🟡'))
        
        success_message = (
            f"{emoji} *ORDER BERHASIL DIBUAT*\n\n"
            f"📦 *Produk:* {product_data['name']}\n"
            f"📮 *Tujuan:* `{target}`\n"
            f"💰 *Harga:* Rp {product_price:,}\n"
            f"🔗 *Ref ID:* `{reffid}`\n"
            f"📊 *Status:* {status_text} {color}\n"
            f"💬 *Pesan:* {provider_message}\n"
        )
        
        if sn_number:
            success_message += f"🔢 *SN:* `{sn_number}`\n"
        
        if final_status == 'failed':
            success_message += f"\n💰 *Saldo Dikembalikan:* Rp {product_price:,}\n"
            current_balance = new_saldo + product_price
        else:
            current_balance = new_saldo
        
        success_message += (
            f"💰 *Saldo Akhir:* Rp {current_balance:,}\n"
            f"⏰ *Waktu:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
        
        if final_status == 'pending':
            success_message += "📝 Status order akan diperbarui otomatis via webhook.\n"
            success_message += "⏳ Jika status masih pending > 10 menit, silakan cek manual.\n"
        
        keyboard = [
            [InlineKeyboardButton("🛒 Beli Lagi", callback_data="main_menu_order")],
            [InlineKeyboardButton("📋 Riwayat Order", callback_data="main_menu_history")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await safe_edit_message_text(
            update,
            success_message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        # Clean up user data
        order_keys = ['selected_product', 'order_target', 'product_page', 'current_group', 'current_products']
        for key in order_keys:
            if key in user_data:
                del user_data[key]
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error processing order: {e}")
        
        # Safety refund jika error tidak terduga
        try:
            user_id = str(query.from_user.id)
            database.update_user_saldo(user_id, product_price)
        except:
            pass
            
        await safe_edit_message_text(
            update,
            f"❌ Terjadi error tidak terduga:\n{str(e)}\n\n"
            f"Saldo telah dikembalikan ke akun Anda.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
        )
        return ConversationHandler.END

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

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the entire order conversation"""
    query = update.callback_query
    await query.answer()
    
    # Clear all order-related user data
    order_keys = ['selected_product', 'order_target', 'product_page', 'current_group', 'current_products']
    for key in order_keys:
        if key in context.user_data:
            del context.user_data[key]
    
    await safe_edit_message_text(
        update,
        "❌ Order dibatalkan.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
        ])
    )
    
    return ConversationHandler.END

# ==================== WEBHOOK HANDLER ====================

def handle_webhook_callback(message):
    """Handle webhook callback dari KhfyPay dengan refund automation"""
    try:
        # Regex pattern dari dokumentasi KhfyPay
        pattern = r'RC=(?P<reffid>[a-f0-9-]+)\s+TrxID=(?P<trxid>\d+)\s+(?P<produk>[A-Z0-9]+)\.(?P<tujuan>\d+)\s+(?P<status_text>[A-Za-z]+)\s*(?P<keterangan>.+?)(?:\s+Saldo[\s\S]*?)?(?:\bresult=(?P<status_code>\d+))?\s*>?$'
        
        match = re.match(pattern, message, re.IGNORECASE)
        if not match:
            logger.error(f"Webhook format tidak dikenali: {message}")
            return False
        
        groups = match.groupdict()
        reffid = groups.get('reffid')
        status_text = groups.get('status_text', '').lower()
        status_code = groups.get('status_code')
        
        # Determine final status
        is_success = False
        if status_code == '0' or 'sukses' in status_text:
            is_success = True
        elif status_code == '1' or 'gagal' in status_text or 'batal' in status_text:
            is_success = False
        
        # Cari order di database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT id, user_id, price, status 
            FROM orders 
            WHERE provider_order_id = ? AND status IN ('processing', 'pending')
        """, (reffid,))
        
        order = c.fetchone()
        if not order:
            logger.warning(f"Order tidak ditemukan untuk reffid: {reffid}")
            conn.close()
            return False
        
        order_id, user_id, price, current_status = order
        
        if is_success:
            # Update jadi completed
            c.execute("""
                UPDATE orders 
                SET status = 'completed', note = ?, updated_at = ?
                WHERE id = ?
            """, (f"Webhook: {message}", datetime.now(), order_id))
            logger.info(f"Webhook: Order {order_id} completed")
            
        else:
            # REFUND otomatis untuk yang gagal
            c.execute("""
                UPDATE orders 
                SET status = 'failed', note = ?, updated_at = ?
                WHERE id = ?
            """, (f"Webhook Gagal: {message}", datetime.now(), order_id))
            
            # Refund saldo
            c.execute("UPDATE users SET saldo = saldo + ? WHERE user_id = ?", (price, user_id))
            
            # Log refund
            c.execute("""
                INSERT INTO transactions 
                (user_id, type, amount, description, created_at)
                VALUES (?, 'refund', ?, ?, ?)
            """, (user_id, price, f"Auto-refund order gagal via webhook: {message}", datetime.now()))
            
            logger.info(f"Webhook: Order {order_id} failed - refund processed")
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        return False

# ==================== PERIODIC TASKS ====================

async def periodic_sync_task(context: ContextTypes.DEFAULT_TYPE):
    """Periodic task untuk sync status order dan auto-refund"""
    try:
        logger.info("Running periodic sync task...")
        
        # Sync order status dari provider
        synced_orders = sync_order_status_from_provider()
        
        # Auto refund order yang failed
        refunded_orders = auto_refund_failed_orders()
        
        # Sync products setiap 6 jam
        current_hour = datetime.now().hour
        if current_hour % 6 == 0:  # Setiap 6 jam
            sync_products_with_provider()
        
        logger.info(f"Periodic sync completed: {synced_orders} orders synced, {refunded_orders} orders refunded")
        
    except Exception as e:
        logger.error(f"Error in periodic_sync_task: {e}")

# ==================== CONVERSATION HANDLER SETUP ====================

def get_conversation_handler():
    """Get order conversation handler untuk didaftarkan di main.py"""
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler, pattern="^main_menu_order$")],
        states={
            CHOOSING_GROUP: [
                CallbackQueryHandler(show_products, pattern="^order_group_"),
                CallbackQueryHandler(cancel_conversation, pattern="^main_menu_main$")
            ],
            CHOOSING_PRODUCT: [
                CallbackQueryHandler(select_product, pattern="^order_product_"),
                CallbackQueryHandler(handle_pagination, pattern="^(order_next_page|order_prev_page)$"),
                CallbackQueryHandler(back_to_groups, pattern="^order_back_to_groups$"),
                CallbackQueryHandler(cancel_conversation, pattern="^main_menu_main$")
            ],
            ENTER_TUJUAN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_target),
                CallbackQueryHandler(show_products, pattern="^order_group_"),
                CallbackQueryHandler(cancel_conversation, pattern="^main_menu_main$")
            ],
            CONFIRM_ORDER: [
                CallbackQueryHandler(process_order, pattern="^order_confirm$"),
                CallbackQueryHandler(cancel_order, pattern="^order_cancel$"),
                CallbackQueryHandler(show_products, pattern="^order_group_"),
                CallbackQueryHandler(cancel_conversation, pattern="^main_menu_main$")
            ],
        },
        fallbacks=[
            CommandHandler("start", cancel_conversation),
            CommandHandler("cancel", cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern="^main_menu_main$")
        ],
        name="order_conversation",
        persistent=False
    )

# ==================== ERROR HANDLER ====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the order handler"""
    logger.error(f"Exception while handling an update in order handler: {context.error}", exc_info=context.error)
    
    try:
        await safe_reply_message(
            update,
            "❌ Terjadi error yang tidak terduga dalam proses order. Silakan coba lagi atau hubungi admin.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
        )
    except Exception as e:
        logger.error(f"Error in order error handler: {e}")
    
    return ConversationHandler.END

# ==================== MANUAL SYNC COMMANDS ====================

async def manual_sync_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual sync products command"""
    try:
        await safe_reply_message(update, "🔄 Mensinkronisasi produk dengan provider...")
        
        if sync_products_with_provider():
            await safe_reply_message(update, "✅ Sinkronisasi produk berhasil!")
        else:
            await safe_reply_message(update, "❌ Gagal sinkronisasi produk.")
            
    except Exception as e:
        logger.error(f"Error in manual_sync_products: {e}")
        await safe_reply_message(update, "❌ Error saat sinkronisasi produk.")

async def manual_sync_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual sync orders command"""
    try:
        await safe_reply_message(update, "🔄 Mensinkronisasi status order...")
        
        synced_count = sync_order_status_from_provider()
        await safe_reply_message(update, f"✅ Berhasil sinkronisasi {synced_count} order.")
            
    except Exception as e:
        logger.error(f"Error in manual_sync_orders: {e}")
        await safe_reply_message(update, "❌ Error saat sinkronisasi order.")
