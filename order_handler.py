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
            reffid = custom_reffid or f"akrab_{uuid.uuid4().hex[:16]}"
            
            params = {
                "produk": product_code,
                "tujuan": target,
                "reff_id": reffid,
                "api_key": self.api_key
            }
            
            logger.info(f"Sending order to KhfyPay: {params}")
            
            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            result['reffid'] = reffid
            
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

# ==================== DATABASE COMPATIBILITY FIX ====================

def get_user_saldo(user_id):
    """Fixed compatibility function for user balance"""
    try:
        # Coba beberapa kemungkinan nama fungsi
        if hasattr(database, 'get_user_balance'):
            return database.get_user_balance(user_id)
        elif hasattr(database, 'get_user_saldo'):
            return database.get_user_saldo(user_id)
        else:
            # Fallback: cek langsung di database
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        return 0

def update_user_saldo(user_id, amount, note="", transaction_type="order"):
    """Fixed compatibility function for update balance"""
    try:
        # Determine transaction type based on amount
        if amount < 0:
            transaction_type = "order"
        else:
            transaction_type = "refund" if "refund" in note.lower() else "adjustment"
        
        # Coba beberapa kemungkinan nama fungsi
        if hasattr(database, 'update_user_balance'):
            return database.update_user_balance(user_id, amount, note, transaction_type)
        elif hasattr(database, 'update_user_saldo'):
            return database.update_user_saldo(user_id, amount, note, transaction_type)
        else:
            # Fallback: update langsung di database
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        logger.error(f"Error updating user saldo: {e}")
        return False

def save_order(user_id, product_name, product_code, customer_input, price, 
               status='pending', provider_order_id='', sn='', note='', saldo_awal=0):
    """Fixed compatibility function for save order"""
    try:
        if hasattr(database, 'save_order'):
            return database.save_order(
                user_id=user_id,
                product_name=product_name,
                product_code=product_code,
                customer_input=customer_input,
                price=price,
                status=status,
                provider_order_id=provider_order_id,
                sn=sn,
                note=note
            )
        else:
            # Fallback: simpan langsung ke database
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO orders (user_id, product_name, product_code, customer_input, 
                                  price, status, provider_order_id, sn, note, created_at, saldo_awal)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, product_name, product_code, customer_input, price, 
                  status, provider_order_id, sn, note, datetime.now(), saldo_awal))
            order_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return order_id
    except Exception as e:
        logger.error(f"Error saving order: {e}")
        return 0

def update_order_status(order_id, status, sn='', note=''):
    """Fixed compatibility function for update order status"""
    try:
        if hasattr(database, 'update_order_status'):
            return database.update_order_status(order_id, status, sn, note)
        else:
            # Fallback: update langsung di database
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE orders SET status = ?, sn = ?, note = ?, updated_at = ?
                WHERE id = ?
            ''', (status, sn, note, datetime.now(), order_id))
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        logger.error(f"Error updating order status: {e}")
        return False

# ==================== STOCK MANAGEMENT SYSTEM ====================

def sync_product_stock_from_provider():
    """Sinkronisasi stok produk dari provider KhfyPay"""
    try:
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            logger.error("API key tidak tersedia untuk sinkronisasi stok")
            return False
        
        khfy_api = KhfyPayAPI(api_key)
        provider_products = khfy_api.get_products()
        
        if not provider_products:
            logger.error("Gagal mendapatkan produk dari provider")
            return False
        
        updated_stock_count = 0
        
        if isinstance(provider_products, list):
            for provider_product in provider_products:
                if isinstance(provider_product, dict):
                    product_code = provider_product.get('code', '').strip()
                    product_status = provider_product.get('status', '').lower()
                    
                    if product_code:
                        # Tentukan stok berdasarkan status dari provider
                        if product_status == 'active':
                            new_stock = 100
                            gangguan = 0
                            kosong = 0
                        elif product_status == 'empty':
                            new_stock = 0
                            gangguan = 0
                            kosong = 1
                        elif product_status == 'problem':
                            new_stock = 0
                            gangguan = 1
                            kosong = 0
                        elif product_status == 'inactive':
                            new_stock = 0
                            gangguan = 0
                            kosong = 1
                        else:
                            new_stock = 0
                            gangguan = 0
                            kosong = 1
                        
                        # Update stok di database
                        try:
                            if hasattr(database, 'update_product'):
                                success = database.update_product(
                                    product_code,
                                    stock=new_stock,
                                    gangguan=gangguan,
                                    kosong=kosong
                                )
                            else:
                                # Fallback: update langsung di database
                                conn = sqlite3.connect('bot_database.db')
                                cursor = conn.cursor()
                                cursor.execute('''
                                    UPDATE products SET stock = ?, gangguan = ?, kosong = ?
                                    WHERE code = ?
                                ''', (new_stock, gangguan, kosong, product_code))
                                success = cursor.rowcount > 0
                                conn.commit()
                                conn.close()
                            
                            if success:
                                updated_stock_count += 1
                        except Exception as update_error:
                            logger.error(f"Error updating product {product_code}: {update_error}")
        
        logger.info(f"Berhasil update stok untuk {updated_stock_count} produk")
        return updated_stock_count > 0
        
    except Exception as e:
        logger.error(f"Error sync_product_stock_from_provider: {e}")
        return False

def get_product_stock_status(stock, gangguan, kosong):
    """Get stock status dengan tampilan yang informatif"""
    if kosong == 1:
        return "🔴 HABIS", 0
    elif gangguan == 1:
        return "🚧 GANGGUAN", 0
    elif stock > 20:
        return "🟢 TERSEDIA", stock
    elif stock > 10:
        return "🟢 TERSEDIA", stock
    elif stock > 5:
        return "🟡 SEDIKIT", stock
    elif stock > 0:
        return "🟡 MENIPIS", stock
    else:
        return "🔴 HABIS", 0

def update_product_stock_after_order(product_code, quantity=1):
    """Update stok produk setelah order berhasil"""
    try:
        # Get current product
        product = get_product_by_code_with_stock(product_code)
        if not product:
            logger.error(f"Product {product_code} not found for stock update")
            return False
        
        current_stock = product.get('stock', 0)
        new_stock = max(0, current_stock - quantity)
        
        # Update stock
        try:
            if hasattr(database, 'update_product'):
                success = database.update_product(product_code, stock=new_stock)
            else:
                # Fallback: update langsung di database
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE products SET stock = ? WHERE code = ?
                ''', (new_stock, product_code))
                success = cursor.rowcount > 0
                conn.commit()
                conn.close()
            
            if success:
                logger.info(f"Updated stock for {product_code}: {current_stock} -> {new_stock}")
            else:
                logger.error(f"Failed to update stock for {product_code}")
                
            return success
        except Exception as update_error:
            logger.error(f"Error updating stock in database: {update_error}")
            return False
    except Exception as e:
        logger.error(f"Error update_product_stock_after_order: {e}")
        return False

# ==================== REFUND SYSTEM ====================

def process_refund(order_id, user_id, amount, reason="Order gagal"):
    """Process refund untuk order yang gagal"""
    try:
        # Update saldo user
        update_success = update_user_saldo(user_id, amount, f"Refund: {reason}")
        
        if not update_success:
            logger.error(f"Failed to update balance for refund: user {user_id}, amount {amount}")
            return False
        
        # Update status order
        status_success = update_order_status(
            order_id, 
            'refunded', 
            note=f"Refund: {reason}"
        )
        
        if not status_success:
            logger.error(f"Failed to update order status for refund: order {order_id}")
            return False
        
        logger.info(f"Successfully refunded {amount} to user {user_id} for order {order_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error process_refund: {e}")
        return False

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
    try:
        phone = re.sub(r'\D', '', phone)
        
        if phone.startswith('0'):
            phone = '62' + phone[1:]
        elif phone.startswith('8'):
            phone = '62' + phone
        elif phone.startswith('+62'):
            phone = phone[1:]
        
        if len(phone) < 10 or len(phone) > 14:
            return None
        
        return phone
    except Exception as e:
        logger.error(f"Error validating phone number: {e}")
        return None

def validate_pulsa_target(phone, product_code):
    """Validate pulsa target"""
    try:
        phone = validate_phone_number(phone)
        if not phone:
            return None
        
        # Validasi berdasarkan operator
        if product_code.startswith('TS'):  # Telkomsel
            if not any(phone.startswith(prefix) for prefix in ['62852', '62853', '62811', '62812', '62813', '62821', '62822', '62823']):
                return None
        elif product_code.startswith('AX'):  # Axis
            if not any(phone.startswith(prefix) for prefix in ['62838', '62839', '62837']):
                return None
        elif product_code.startswith('XL'):  # XL
            if not any(phone.startswith(prefix) for prefix in ['62817', '62818', '62819', '62859']):
                return None
        elif product_code.startswith('IN'):  # Indosat
            if not any(phone.startswith(prefix) for prefix in ['62814', '62815', '62816', '62855', '62856', '62857', '62858']):
                return None
        elif product_code.startswith('SM'):  # Smartfren
            if not any(phone.startswith(prefix) for prefix in ['62888', '62889']):
                return None
        elif product_code.startswith('3'):  # Three
            if not any(phone.startswith(prefix) for prefix in ['62895', '62896', '62897', '62898', '62899']):
                return None
        
        return phone
    except Exception as e:
        logger.error(f"Error validating pulsa target: {e}")
        return None

# ==================== PRODUCT MANAGEMENT WITH STOCK DISPLAY ====================

def get_grouped_products_with_stock():
    """Get products grouped by category from database dengan tampilan stok"""
    try:
        # Sync stok terlebih dahulu sebelum menampilkan
        sync_product_stock_from_provider()
        
        # Get all active products
        try:
            if hasattr(database, 'get_products_by_category'):
                products_data = database.get_products_by_category(status='active')
            else:
                # Fallback: ambil langsung dari database
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute("SELECT code, name, price, category, description, stock, gangguan, kosong FROM products WHERE status = 'active'")
                products_data = [dict(zip(['code', 'name', 'price', 'category', 'description', 'stock', 'gangguan', 'kosong'], row)) 
                               for row in cursor.fetchall()]
                conn.close()
        except Exception as db_error:
            logger.error(f"Error getting products from database: {db_error}")
            products_data = []
        
        logger.info(f"Found {len(products_data)} active products in database with stock sync")
        
        groups = {}
        for product in products_data:
            group = product.get('category', 'Lainnya')
            
            # Additional grouping for specific product codes
            if product['code'].startswith("BPAL"):
                group = "BPAL (Bonus Akrab L)"
            elif product['code'].startswith("BPAXXL"):
                group = "BPAXXL (Bonus Akrab XXL)"
            elif product['code'].startswith("XLA"):
                group = "XLA (Umum)"
            elif "pulsa" in product['name'].lower():
                group = "Pulsa"
            elif "data" in product['name'].lower() or "internet" in product['name'].lower() or "kuota" in product['name'].lower():
                group = "Internet"
            elif "listrik" in product['name'].lower() or "pln" in product['name'].lower():
                group = "Listrik"
            elif "game" in product['name'].lower():
                group = "Game"
            elif "emoney" in product['name'].lower() or "gopay" in product['name'].lower() or "dana" in product['name'].lower():
                group = "E-Money"
            
            if group not in groups:
                groups[group] = []
            
            # Get stock status untuk tampilan
            stock_status, actual_stock = get_product_stock_status(
                product.get('stock', 0), 
                product.get('gangguan', 0), 
                product.get('kosong', 0)
            )
            
            groups[group].append({
                'code': product['code'],
                'name': product['name'],
                'price': product['price'],
                'category': product.get('category', ''),
                'description': product.get('description', ''),
                'stock': product.get('stock', 0),
                'gangguan': product.get('gangguan', 0),
                'kosong': product.get('kosong', 0),
                'stock_status': stock_status,
                'display_stock': actual_stock
            })
        
        # Sort groups alphabetically
        sorted_groups = {}
        for group in sorted(groups.keys()):
            sorted_groups[group] = groups[group]
            
        return sorted_groups
        
    except Exception as e:
        logger.error(f"Error getting grouped products with stock: {e}")
        return {}

def get_product_by_code_with_stock(product_code):
    """Get product details by code dengan info stok ter-update"""
    try:
        # Sync stok untuk produk ini
        sync_product_stock_from_provider()
        
        try:
            if hasattr(database, 'get_product'):
                product = database.get_product(product_code)
            else:
                # Fallback: ambil langsung dari database
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute("SELECT code, name, price, category, description, status, stock, gangguan, kosong FROM products WHERE code = ?", (product_code,))
                row = cursor.fetchone()
                conn.close()
                product = dict(zip(['code', 'name', 'price', 'category', 'description', 'status', 'stock', 'gangguan', 'kosong'], row)) if row else None
        except Exception as db_error:
            logger.error(f"Error getting product from database: {db_error}")
            product = None
        
        if product:
            stock_status, display_stock = get_product_stock_status(
                product.get('stock', 0), 
                product.get('gangguan', 0), 
                product.get('kosong', 0)
            )
            
            return {
                'code': product['code'],
                'name': product['name'],
                'price': product['price'],
                'category': product.get('category', ''),
                'description': product.get('description', ''),
                'status': product.get('status', ''),
                'gangguan': product.get('gangguan', 0),
                'kosong': product.get('kosong', 0),
                'stock': product.get('stock', 0),
                'stock_status': stock_status,
                'display_stock': display_stock
            }
        return None
    except Exception as e:
        logger.error(f"Error getting product by code with stock: {e}")
        return None

# ==================== ORDER FLOW HANDLERS WITH STOCK DISPLAY ====================

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main menu handler untuk order"""
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
    """Show product groups menu dengan info stok"""
    try:
        if hasattr(update, 'callback_query'):
            query = update.callback_query
            await query.answer()
        else:
            query = None
        
        logger.info("Loading product groups with stock info...")
        groups = get_grouped_products_with_stock()
        
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
        
        # Calculate total products and available stock
        total_products = sum(len(products) for products in groups.values())
        available_products = sum(
            1 for products in groups.values() 
            for product in products 
            if product['display_stock'] > 0 and product['gangguan'] == 0 and product['kosong'] == 0
        )
        
        keyboard = []
        for group_name in groups.keys():
            product_count = len(groups[group_name])
            available_count = sum(
                1 for product in groups[group_name] 
                if product['display_stock'] > 0 and product['gangguan'] == 0 and product['kosong'] == 0
            )
            
            # Tampilkan jumlah produk tersedia vs total
            status_emoji = "🟢" if available_count > 0 else "🔴"
            button_text = f"{status_emoji} {group_name} ({available_count}/{product_count})"
            
            keyboard.append([
                InlineKeyboardButton(button_text, callback_data=f"order_group_{group_name}")
            ])
        
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            f"📦 *PILIH KATEGORI PRODUK*\n\n"
            f"📊 *Statistik Ketersediaan:*\n"
            f"🟢 Tersedia: {available_products} produk\n"
            f"🔴 Total: {total_products} produk\n\n"
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
    """Show products in selected group dengan tampilan stok detail"""
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        group_name = data.replace('order_group_', '')
        
        groups = get_grouped_products_with_stock()
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
            # Tampilkan stok secara detail di button
            price_formatted = f"Rp {product['price']:,}"
            
            if product['kosong'] == 1:
                button_text = f"🔴 {product['name']} - {price_formatted} | HABIS"
            elif product['gangguan'] == 1:
                button_text = f"🚧 {product['name']} - {price_formatted} | GANGGUAN"
            elif product['display_stock'] > 10:
                button_text = f"🟢 {product['name']} - {price_formatted} | Stock: {product['display_stock']}+"
            elif product['display_stock'] > 5:
                button_text = f"🟢 {product['name']} - {price_formatted} | Stock: {product['display_stock']}"
            elif product['display_stock'] > 0:
                button_text = f"🟡 {product['name']} - {price_formatted} | Stock: {product['display_stock']}"
            else:
                button_text = f"🔴 {product['name']} - {price_formatted} | HABIS"
            
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
        
        # Hitung statistik untuk group ini
        total_in_group = len(products)
        available_in_group = sum(1 for p in products if p['display_stock'] > 0 and p['gangguan'] == 0 and p['kosong'] == 0)
        
        total_pages = (len(products) + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE
        page_info = f" (Halaman {page + 1}/{total_pages})" if total_pages > 1 else ""
        
        await safe_edit_message_text(
            update,
            f"📦 *PRODUK {group_name.upper()}*{page_info}\n\n"
            f"📊 *Ketersediaan:* {available_in_group}/{total_in_group} produk tersedia\n\n"
            f"🟢 Stock > 5 | 🟡 Stock 1-5 | 🔴 Habis | 🚧 Gangguan\n\n"
            f"Pilih produk:",
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
    """Handle product selection dengan info stok detail"""
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        product_code = data.replace('order_product_', '')
        
        # Ambil data produk dengan stok ter-update
        product = get_product_by_code_with_stock(product_code)
        
        if not product:
            await safe_edit_message_text(
                update,
                "❌ Produk tidak ditemukan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
            )
            return ConversationHandler.END
        
        # Check product availability dengan info stok detail
        if product['kosong'] == 1:
            await safe_edit_message_text(
                update,
                f"❌ *{product['name']}*\n\n"
                f"💰 Harga: Rp {product['price']:,}\n"
                f"📊 Status: 🔴 HABIS\n\n"
                f"Produk sedang kosong/tidak tersedia di provider.\n\n"
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
                f"💰 Harga: Rp {product['price']:,}\n"
                f"📊 Status: 🚧 GANGGUAN\n\n"
                f"Produk sedang mengalami gangguan di provider.\n\n"
                f"Silakan pilih produk lain atau coba lagi nanti.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"order_group_{product['category']}")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ]),
                parse_mode="Markdown"
            )
            return CHOOSING_PRODUCT
        
        if product['display_stock'] <= 0:
            await safe_edit_message_text(
                update,
                f"🔴 *{product['name']}*\n\n"
                f"💰 Harga: Rp {product['price']:,}\n"
                f"📊 Status: 🔴 HABIS\n\n"
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
        
        # Ask for target
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
            f"📊 Stok: {product['stock_status']} ({product['display_stock']} unit)\n"
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
        
        # Show confirmation dengan info stok
        user_id = str(update.effective_user.id)
        saldo = get_user_saldo(user_id)
        
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
            f"💰 *Harga:* Rp {product['price']:,}\n"
            f"📊 *Stok Tersedia:* {product['stock_status']} ({product['display_stock']} unit)\n\n"
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
    """Process order confirmation dengan update stok"""
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
        product_price = product_data['price']
        
        # === FITUR DARI PHP: DAPATKAN SALDO AWAL ===
        saldo_awal = get_user_saldo(user_id)
        
        if saldo_awal < product_price:
            await safe_edit_message_text(
                update,
                f"❌ Saldo tidak cukup!\n\n"
                f"💰 Saldo Anda: Rp {saldo_awal:,}\n"
                f"💳 Harga produk: Rp {product_price:,}\n"
                f"🔶 Kekurangan: Rp {product_price - saldo_awal:,}\n\n"
                f"Silakan top up saldo terlebih dahulu.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💸 Top Up Saldo", callback_data="topup_menu")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ])
            )
            return ConversationHandler.END
        
        # Final stock check sebelum order
        await safe_edit_message_text(
            update,
            f"🔍 *MEMERIKSA STOK TERAKHIR*...\n\n"
            f"📦 {product_data['name']}\n"
            f"📮 Tujuan: `{target}`\n"
            f"📊 Stok: {product_data['stock_status']}\n\n"
            f"Mohon tunggu...",
            parse_mode="Markdown"
        )
        
        # Sync stok terakhir untuk produk ini
        sync_product_stock_from_provider()
        updated_product = get_product_by_code_with_stock(product_data['code'])
        
        if not updated_product or updated_product.get('kosong') == 1 or updated_product.get('display_stock', 0) <= 0:
            await safe_edit_message_text(
                update,
                f"❌ *STOK SUDAH HABIS*\n\n"
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
        
        # === FITUR DARI PHP: BUAT REFF_ID UNIK ===
        reffid = f"akrab_{uuid.uuid4().hex[:16]}"
        
        # Deduct balance FIRST (sebelum ke provider)
        update_user_saldo(user_id, -product_price, "Pembelian produk")
        
        # Save order to database dengan saldo_awal
        order_id = save_order(
            user_id=user_id,
            product_name=product_data['name'],
            product_code=product_data['code'],
            customer_input=target,
            price=product_price,
            status='processing',
            provider_order_id=reffid,
            sn='',
            note='Sedang diproses ke provider',
            saldo_awal=saldo_awal  # === FITUR DARI PHP: SIMPAN SALDO AWAL ===
        )
        
        if not order_id:
            # Refund jika gagal save order
            update_user_saldo(user_id, product_price, "Refund: Gagal menyimpan order")
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
            f"💰 Rp {product_price:,}\n"
            f"📊 Stok: {updated_product['stock_status']}\n\n"
            f"Mohon tunggu...",
            parse_mode="Markdown"
        )
        
        # Kirim ke provider
        order_result = khfy_api.create_order(
            product_code=product_data['code'],
            target=target,
            custom_reffid=reffid
        )
        
        # Handle provider response
        if not order_result or order_result.get('status') == 'error':
            error_msg = order_result.get('message', 'Unknown error from provider') if order_result else 'Gagal terhubung ke provider'
            
            # REFUND: Order gagal di provider
            update_user_saldo(user_id, product_price, f"Refund: Provider error - {error_msg}")
            update_order_status(order_id, 'failed', note=f"Provider error: {error_msg}")
            
            await safe_edit_message_text(
                update,
                f"❌ *ORDER GAGAL DI PROVIDER*\n\n"
                f"📦 {product_data['name']}\n"
                f"📮 Tujuan: `{target}`\n"
                f"💰 Rp {product_price:,}\n\n"
                f"*Error:* {error_msg}\n\n"
                f"✅ *Saldo telah dikembalikan* ke akun Anda.",
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
        
        # === FITUR DARI PHP: STATUS MAPPING ===
        final_status = 'pending'
        if provider_status in ['success', 'SUKSES', 'SUCCESS']:
            final_status = 'completed'
            # Update stok setelah order berhasil
            update_product_stock_after_order(product_data['code'])
        elif provider_status in ['error', 'GAGAL', 'FAILED']:
            final_status = 'failed'
            # Auto refund untuk error yang langsung diketahui
            update_user_saldo(user_id, product_price, f"Refund: Provider error - {provider_message}")
        
        update_order_status(order_id, final_status, sn=sn_number, note=provider_message)
        
        # Prepare success message
        saldo_akhir = get_user_saldo(user_id)
        
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
            f"💰 *Saldo Awal:* Rp {saldo_awal:,}\n"  # === FITUR DARI PHP: TAMPILKAN SALDO AWAL ===
            f"💰 *Saldo Akhir:* Rp {saldo_akhir:,}\n"
        )
        
        if sn_number:
            success_message += f"🔢 *SN:* `{sn_number}`\n"
        
        if final_status == 'failed':
            success_message += f"\n✅ *Saldo telah dikembalikan*\n"
        
        success_message += f"⏰ *Waktu:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        if final_status == 'pending':
            success_message += "📝 Status order akan diperbarui otomatis via webhook.\n"
        
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
            update_user_saldo(user_id, product_price, f"Refund: System error - {str(e)}")
        except:
            pass
            
        await safe_edit_message_text(
            update,
            f"❌ Terjadi error tidak terduga:\n{str(e)}\n\n"
            f"Saldo telah dikembalikan ke akun Anda.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
        )
        return ConversationHandler.END

# ==================== WEBHOOK HANDLER ====================

def handle_webhook_callback(message):
    """Handle webhook callback dari KhfyPay"""
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
        product_code = groups.get('produk')
        
        # Determine final status
        is_success = False
        if status_code == '0' or 'sukses' in status_text:
            is_success = True
        elif status_code == '1' or 'gagal' in status_text or 'batal' in status_text:
            is_success = False
        
        # Cari order di database
        try:
            if hasattr(database, 'get_order_by_provider_id'):
                order = database.get_order_by_provider_id(reffid)
            else:
                # Fallback: cari langsung di database
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute("SELECT id, user_id, price FROM orders WHERE provider_order_id = ?", (reffid,))
                row = cursor.fetchone()
                conn.close()
                order = dict(zip(['id', 'user_id', 'price'], row)) if row else None
        except Exception as db_error:
            logger.error(f"Error finding order in database: {db_error}")
            order = None
        
        if not order:
            logger.warning(f"Order tidak ditemukan untuk reffid: {reffid}")
            return False
        
        order_id = order['id']
        user_id = order['user_id']
        price = order['price']
        
        if is_success:
            # Update jadi completed
            update_order_status(order_id, 'completed', note=f"Webhook: {message}")
            
            # Update stok untuk produk yang berhasil
            if product_code:
                update_product_stock_after_order(product_code)
            
            logger.info(f"Webhook: Order {order_id} completed")
            
        else:
            # REFUND otomatis untuk yang gagal
            update_order_status(order_id, 'failed', note=f"Webhook Gagal: {message}")
            
            # Refund saldo
            update_user_saldo(user_id, price, "Refund: Order gagal via webhook")
            
            logger.info(f"Webhook: Order {order_id} failed - refund processed")
        
        return True
        
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        return False

# ==================== PERIODIC TASKS ====================

async def periodic_stock_sync_task(context: ContextTypes.DEFAULT_TYPE):
    """Periodic task untuk sync stok dari provider"""
    try:
        logger.info("Running periodic stock sync task...")
        sync_product_stock_from_provider()
        logger.info("Periodic stock sync completed")
        
    except Exception as e:
        logger.error(f"Error in periodic_stock_sync_task: {e}")

# ==================== CANCEL HANDLERS ====================

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel order and return to product selection"""
    query = update.callback_query
    await query.answer("Order dibatalkan")
    
    if 'selected_product' in context.user_data:
        del context.user_data['selected_product']
    if 'order_target' in context.user_data:
        del context.user_data['order_target']
    
    return await show_products(update, context)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the entire order conversation"""
    query = update.callback_query
    await query.answer()
    
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
