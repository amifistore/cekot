import logging
import uuid
import requests
import aiohttp
import asyncio
import sqlite3
import re
import json
import traceback
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CommandHandler,
    Application
)
import database
import config
import telegram

logger = logging.getLogger(__name__)

# States untuk order conversation
CHOOSING_GROUP, CHOOSING_PRODUCT, ENTER_TUJUAN, CONFIRM_ORDER = range(4)
PRODUCTS_PER_PAGE = 8

# Global variables
bot_application = None
pending_admin_notifications = {}
pending_orders_timeout = {}

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
            
            data = response.json()
            logger.info(f"✅ Got {len(data) if isinstance(data, list) else 'unknown'} products from provider")
            return data
        except Exception as e:
            logger.error(f"❌ Error getting KhfyPay products: {e}")
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
            
            logger.info(f"🔄 Sending order to KhfyPay: {params}")
            
            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            result['reffid'] = reffid
            
            logger.info(f"✅ Order created with response: {result}")
            return result
            
        except requests.exceptions.Timeout:
            logger.error(f"❌ Timeout creating order for {product_code}")
            return {"status": "error", "message": "Timeout - Silakan cek status manual"}
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Network error creating order: {e}")
            return {"status": "error", "message": f"Network error: {str(e)}"}
        except Exception as e:
            logger.error(f"❌ Error creating KhfyPay order: {e}")
            return {"status": "error", "message": f"System error: {str(e)}"}
    
    def check_order_status(self, reffid):
        """Check order status by reffid dengan error handling lengkap"""
        try:
            url = f"{self.base_url}/history"
            params = {
                "api_key": self.api_key,
                "refid": reffid
            }
            
            logger.info(f"🔍 Checking status for reffid: {reffid}")
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"📊 Status check response: {result}")
            return result
            
        except requests.exceptions.Timeout:
            logger.error(f"⏰ Timeout checking status for {reffid}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"🌐 Network error checking status: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error checking KhfyPay order status: {e}")
            return None

# ==================== MODERN ANIMATION SYSTEM ====================

class ModernAnimations:
    @staticmethod
    async def show_processing(update, context, message_text, duration=2):
        """Show modern processing animation"""
        try:
            message = await update.effective_message.reply_text(
                f"⏳ *{message_text}*",
                parse_mode="Markdown"
            )
            
            frames = ["🔄 Memproses...", "📡 Mengirim...", "⏳ Menunggu..."]
            for frame in frames:
                await asyncio.sleep(duration / len(frames))
                try:
                    await context.bot.edit_message_text(
                        chat_id=message.chat_id,
                        message_id=message.message_id,
                        text=f"⏳ *{frame}*",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            
            return message
        except Exception as e:
            logger.error(f"❌ Animation error: {e}")
            return None

    @staticmethod
    async def typing_effect(update, context, duration=1):
        """Simulate typing effect"""
        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )
            await asyncio.sleep(duration)
        except:
            pass

    @staticmethod
    def create_progress_bar(percentage, length=10):
        """Create visual progress bar"""
        filled = int(length * percentage / 100)
        empty = length - filled
        return f"`[{ '█' * filled }{ '░' * empty }]` {percentage}%"

# ==================== MODERN MESSAGE BUILDER ====================

class ModernMessageBuilder:
    @staticmethod
    def create_header(emoji, title, status):
        """Create modern header"""
        status_emojis = {'success': '🟢', 'pending': '🟡', 'failed': '🔴', 'processing': '🔵'}
        status_emoji = status_emojis.get(status, '🟡')
        return f"{emoji} **{title}** {status_emoji}\n" + "▬" * 35 + "\n\n"

    @staticmethod
    def create_order_message(order_data, status_type, additional_info=None):
        """Create modern order message"""
        status_configs = {
            'success': {'emoji': '✅', 'title': 'ORDER BERHASIL', 'color': '🟢'},
            'pending': {'emoji': '⏳', 'title': 'ORDER DIPROSES', 'color': '🟡'},
            'failed': {'emoji': '❌', 'title': 'ORDER GAGAL', 'color': '🔴'},
            'processing': {'emoji': '🔄', 'title': 'PROSES ORDER', 'color': '🔵'}
        }
        
        config = status_configs.get(status_type, status_configs['pending'])
        message = ModernMessageBuilder.create_header(config['emoji'], config['title'], status_type)
        
        # Order details
        details = [
            f"📦 **Produk:** {order_data.get('product_name', 'N/A')}",
            f"📮 **Tujuan:** `{order_data.get('customer_input', 'N/A')}`",
            f"💰 **Harga:** Rp {order_data.get('price', 0):,}",
            f"🔗 **Ref ID:** `{order_data.get('provider_order_id', 'N/A')}`"
        ]
        
        message += "\n".join(details) + "\n\n"
        
        # Additional info
        if additional_info:
            for info in additional_info:
                message += f"• {info}\n"
            message += "\n"
        
        # Footer
        message += "─" * 25 + "\n"
        message += f"🕒 **Waktu:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        
        return message

# ==================== DATABASE COMPATIBILITY FIX ====================

def get_user_saldo(user_id):
    """Fixed compatibility function for user balance"""
    try:
        if hasattr(database, 'get_user_balance'):
            return database.get_user_balance(user_id)
        elif hasattr(database, 'get_user_saldo'):
            return database.get_user_saldo(user_id)
        else:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else 0
    except Exception as e:
        logger.error(f"❌ Error getting user saldo: {e}")
        return 0

def update_user_saldo(user_id, amount, note="", transaction_type="order"):
    """Fixed compatibility function for update balance"""
    try:
        if amount < 0:
            transaction_type = "order"
        else:
            transaction_type = "refund" if "refund" in note.lower() else "adjustment"
        
        if hasattr(database, 'update_user_balance'):
            return database.update_user_balance(user_id, amount, note, transaction_type)
        elif hasattr(database, 'update_user_saldo'):
            return database.update_user_saldo(user_id, amount, note, transaction_type)
        else:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        logger.error(f"❌ Error updating user saldo: {e}")
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
        logger.error(f"❌ Error saving order: {e}")
        return 0

def update_order_status(order_id, status, sn='', note=''):
    """Fixed compatibility function for update order status"""
    try:
        if hasattr(database, 'update_order_status'):
            return database.update_order_status(order_id, status, sn, note)
        else:
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
        logger.error(f"❌ Error updating order status: {e}")
        return False

def get_pending_orders():
    """Get all pending orders"""
    try:
        if hasattr(database, 'get_pending_orders'):
            return database.get_pending_orders()
        else:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_id, product_code, provider_order_id, created_at, price, product_name, customer_input, status
                FROM orders WHERE status IN ('processing', 'pending')
            ''')
            rows = cursor.fetchall()
            conn.close()
            return [dict(zip([
                'id', 'user_id', 'product_code', 'provider_order_id', 'created_at', 'price', 'product_name', 'customer_input', 'status'
            ], row)) for row in rows]
    except Exception as e:
        logger.error(f"❌ Error getting pending orders: {e}")
        return []

# ==================== STOCK MANAGEMENT SYSTEM ====================

def sync_product_stock_from_provider():
    """Sinkronisasi stok produk dari provider KhfyPay"""
    try:
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            logger.error("❌ API key tidak tersedia untuk sinkronisasi stok")
            return False
        
        khfy_api = KhfyPayAPI(api_key)
        provider_products = khfy_api.get_products()
        
        if not provider_products:
            logger.error("❌ Gagal mendapatkan produk dari provider")
            return False
        
        updated_stock_count = 0
        
        if isinstance(provider_products, list):
            for provider_product in provider_products:
                if isinstance(provider_product, dict):
                    product_code = provider_product.get('code', '').strip()
                    product_status = provider_product.get('status', '').lower()
                    
                    if product_code:
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
                        
                        try:
                            if hasattr(database, 'update_product'):
                                success = database.update_product(
                                    product_code,
                                    stock=new_stock,
                                    gangguan=gangguan,
                                    kosong=kosong
                                )
                            else:
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
                            logger.error(f"❌ Error updating product {product_code}: {update_error}")
        
        logger.info(f"✅ Berhasil update stok untuk {updated_stock_count} produk")
        return updated_stock_count > 0
        
    except Exception as e:
        logger.error(f"❌ Error sync_product_stock_from_provider: {e}")
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
        product = get_product_by_code_with_stock(product_code)
        if not product:
            logger.error(f"❌ Product {product_code} not found for stock update")
            return False
        
        current_stock = product.get('stock', 0)
        new_stock = max(0, current_stock - quantity)
        
        try:
            if hasattr(database, 'update_product'):
                success = database.update_product(product_code, stock=new_stock)
            else:
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE products SET stock = ? WHERE code = ?
                ''', (new_stock, product_code))
                success = cursor.rowcount > 0
                conn.commit()
                conn.close()
            
            if success:
                logger.info(f"✅ Updated stock for {product_code}: {current_stock} -> {new_stock}")
            else:
                logger.error(f"❌ Failed to update stock for {product_code}")
                
            return success
        except Exception as update_error:
            logger.error(f"❌ Error updating stock in database: {update_error}")
            return False
    except Exception as e:
        logger.error(f"❌ Error update_product_stock_after_order: {e}")
        return False

# ==================== PRODUCT MANAGEMENT ====================

def get_grouped_products_with_stock():
    """Get products grouped by category dari database dengan tampilan stok"""
    try:
        sync_product_stock_from_provider()
        
        try:
            if hasattr(database, 'get_products_by_category'):
                products_data = database.get_products_by_category(status='active')
            else:
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute("SELECT code, name, price, category, description, stock, gangguan, kosong FROM products WHERE status = 'active'")
                products_data = [dict(zip(['code', 'name', 'price', 'category', 'description', 'stock', 'gangguan', 'kosong'], row)) 
                               for row in cursor.fetchall()]
                conn.close()
        except Exception as db_error:
            logger.error(f"❌ Error getting products from database: {db_error}")
            products_data = []
        
        logger.info(f"✅ Found {len(products_data)} active products in database")
        
        groups = {}
        for product in products_data:
            group = product.get('category', 'Lainnya')
            
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
        
        sorted_groups = {}
        for group in sorted(groups.keys()):
            sorted_groups[group] = groups[group]
            
        return sorted_groups
        
    except Exception as e:
        logger.error(f"❌ Error getting grouped products with stock: {e}")
        return {}

def get_product_by_code_with_stock(product_code):
    """Get product details by code dengan info stok ter-update"""
    try:
        sync_product_stock_from_provider()
        
        try:
            if hasattr(database, 'get_product'):
                product = database.get_product(product_code)
            else:
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute("SELECT code, name, price, category, description, status, stock, gangguan, kosong FROM products WHERE code = ?", (product_code,))
                row = cursor.fetchone()
                conn.close()
                product = dict(zip(['code', 'name', 'price', 'category', 'description', 'status', 'stock', 'gangguan', 'kosong'], row)) if row else None
        except Exception as db_error:
            logger.error(f"❌ Error getting product from database: {db_error}")
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
        logger.error(f"❌ Error getting product by code with stock: {e}")
        return None

# ==================== MODERN ORDER FLOW HANDLERS ====================

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Modern menu handler untuk order"""
    query = update.callback_query
    await query.answer()
    
    await ModernAnimations.typing_effect(update, context, 1)
    
    try:
        return await show_modern_group_menu(update, context)
    except Exception as e:
        logger.error(f"❌ Error in modern menu_handler: {e}")
        await show_modern_error(update, "Error memuat menu order")
        return ConversationHandler.END

async def show_modern_group_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show modern product groups menu"""
    try:
        await ModernAnimations.typing_effect(update, context, 1)
        
        groups = get_grouped_products_with_stock()
        
        if not groups:
            await show_modern_error(update, "Tidak ada produk yang tersedia")
            return ConversationHandler.END
        
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
            
            status_emoji = "🟢" if available_count > 0 else "🔴"
            button_text = f"{status_emoji} {group_name} ({available_count}/{product_count})"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"morder_group_{group_name}")])
        
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")])
        
        message = (
            f"🛍️ *TOKO DIGITAL AKRAB*\n\n"
            f"📦 **PILIH KATEGORI PRODUK**\n"
            f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
            f"📊 **Statistik Ketersediaan:**\n"
            f"🟢 Tersedia: {available_products} produk\n"
            f"📋 Total: {total_products} produk\n\n"
            f"Pilih kategori:"
        )
        
        await safe_edit_modern_message(
            update,
            message,
            InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        return CHOOSING_GROUP
        
    except Exception as e:
        logger.error(f"❌ Error in show_modern_group_menu: {e}")
        await show_modern_error(update, "Error memuat kategori")
        return ConversationHandler.END

async def show_modern_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show modern products list"""
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        group_name = data.replace('morder_group_', '')
        
        groups = get_grouped_products_with_stock()
        if group_name not in groups:
            await show_modern_error(update, "Kategori tidak ditemukan")
            return ConversationHandler.END
        
        products = groups[group_name]
        context.user_data['current_group'] = group_name
        context.user_data['current_products'] = products
        
        page = context.user_data.get('product_page', 0)
        start_idx = page * PRODUCTS_PER_PAGE
        end_idx = start_idx + PRODUCTS_PER_PAGE
        page_products = products[start_idx:end_idx]
        
        keyboard = []
        for product in page_products:
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
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"morder_product_{product['code']}")])
        
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ Sebelumnya", callback_data="morder_prev_page"))
        
        if end_idx < len(products):
            nav_buttons.append(InlineKeyboardButton("Selanjutnya ▶️", callback_data="morder_next_page"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("🔙 Kembali ke Kategori", callback_data="morder_back_to_groups")])
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")])
        
        total_in_group = len(products)
        available_in_group = sum(1 for p in products if p['display_stock'] > 0 and p['gangguan'] == 0 and p['kosong'] == 0)
        total_pages = (len(products) + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE
        page_info = f" (Halaman {page + 1}/{total_pages})" if total_pages > 1 else ""
        
        message = (
            f"📦 **PRODUK {group_name.upper()}**{page_info}\n"
            f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
            f"📊 **Ketersediaan:** {available_in_group}/{total_in_group} produk tersedia\n\n"
            f"🟢 Stock > 5 | 🟡 Stock 1-5 | 🔴 Habis | 🚧 Gangguan\n\n"
            f"Pilih produk:"
        )
        
        await safe_edit_modern_message(
            update,
            message,
            InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        return CHOOSING_PRODUCT
        
    except Exception as e:
        logger.error(f"❌ Error in show_modern_products: {e}")
        await show_modern_error(update, "Error memuat produk")
        return ConversationHandler.END

async def handle_modern_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle modern pagination"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    current_page = context.user_data.get('product_page', 0)
    
    if data == 'morder_next_page':
        context.user_data['product_page'] = current_page + 1
    elif data == 'morder_prev_page':
        context.user_data['product_page'] = max(0, current_page - 1)
    
    return await show_modern_products(update, context)

async def back_to_modern_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kembali ke modern group menu"""
    query = update.callback_query
    await query.answer()
    
    if 'product_page' in context.user_data:
        del context.user_data['product_page']
    
    return await show_modern_group_menu(update, context)

async def select_modern_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle modern product selection"""
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        product_code = data.replace('morder_product_', '')
        
        product = get_product_by_code_with_stock(product_code)
        
        if not product:
            await show_modern_error(update, "Produk tidak ditemukan")
            return CHOOSING_PRODUCT
        
        # Validasi stok
        if product['kosong'] == 1:
            message = ModernMessageBuilder.create_order_message(
                product, 'failed',
                ["❌ **Stok sedang habis**", "🔄 Silakan pilih produk lain"]
            )
            
            keyboard = [
                [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"morder_group_{product['category']}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ]
            
            await safe_edit_modern_message(update, message, InlineKeyboardMarkup(keyboard))
            return CHOOSING_PRODUCT
        
        if product['gangguan'] == 1:
            message = ModernMessageBuilder.create_order_message(
                product, 'failed',
                ["🚧 **Produk sedang gangguan**", "⏳ Coba lagi nanti"]
            )
            
            keyboard = [
                [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"morder_group_{product['category']}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ]
            
            await safe_edit_modern_message(update, message, InlineKeyboardMarkup(keyboard))
            return CHOOSING_PRODUCT
        
        if product['display_stock'] <= 0:
            message = ModernMessageBuilder.create_order_message(
                product, 'failed',
                ["🔴 **Stok produk habis**", "🔄 Silakan pilih produk lain"]
            )
            
            keyboard = [
                [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"morder_group_{product['category']}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ]
            
            await safe_edit_modern_message(update, message, InlineKeyboardMarkup(keyboard))
            return CHOOSING_PRODUCT
        
        context.user_data['selected_product'] = product
        
        target_example = "Contoh: 081234567890"
        if product['code'].startswith('PLN'):
            target_example = "Contoh: 123456789012345 (ID Pelanggan PLN)"
        elif product['code'].startswith('VOUCHER'):
            target_example = "Contoh: 1234567890 (ID Game)"
        
        message = (
            f"🛒 **PILIHAN PRODUK**\n"
            f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
            f"📦 **{product['name']}**\n"
            f"💰 Harga: Rp {product['price']:,}\n"
            f"📊 Stok: {product['stock_status']} ({product['display_stock']} unit)\n"
            f"📝 {product['description'] or 'Tidak ada deskripsi'}\n\n"
            f"📮 **Masukkan nomor tujuan:**\n"
            f"`{target_example}`\n\n"
            f"Ketik nomor tujuan dan kirim:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"morder_group_{product['category']}")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
        ]
        
        await safe_edit_modern_message(
            update,
            message,
            InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        return ENTER_TUJUAN
        
    except Exception as e:
        logger.error(f"❌ Error in select_modern_product: {e}")
        await show_modern_error(update, "Error memilih produk")
        return CHOOSING_PRODUCT

async def receive_modern_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive modern target input"""
    try:
        target = update.message.text.strip()
        product = context.user_data.get('selected_product')
        
        if not product:
            await show_modern_error(update, "Sesi telah berakhir")
            return ConversationHandler.END
        
        validated_target = None
        if product['code'].startswith(('TS', 'AX', 'XL', 'IN', 'SM', '3')):
            validated_target = validate_pulsa_target(target, product['code'])
        elif product['code'].startswith('PLN'):
            validated_target = re.sub(r'\D', '', target)
            if len(validated_target) < 10 or len(validated_target) > 20:
                validated_target = None
        else:
            validated_target = target.strip()
        
        if not validated_target:
            await update.message.reply_text(
                "❌ **Format tujuan tidak valid!**\n\n"
                f"Produk: {product['name']}\n"
                f"Tujuan: {target}\n\n"
                f"Silakan masukkan format yang benar:",
                parse_mode="Markdown"
            )
            return ENTER_TUJUAN
        
        context.user_data['order_target'] = validated_target
        
        user_id = str(update.effective_user.id)
        saldo = get_user_saldo(user_id)
        
        keyboard = [
            [
                InlineKeyboardButton("✅ KONFIRMASI ORDER", callback_data="morder_confirm"),
                InlineKeyboardButton("❌ BATALKAN", callback_data="morder_cancel")
            ]
        ]
        
        message = ModernMessageBuilder.create_order_message(
            {
                'product_name': product['name'],
                'customer_input': validated_target,
                'price': product['price'],
                'provider_order_id': 'Akan digenerate'
            },
            'processing',
            [
                f"💰 **Saldo Anda:** Rp {saldo:,}",
                f"🔰 **Sisa Saldo:** Rp {saldo - product['price']:,}",
                f"📦 **Stok:** {product['stock_status']}"
            ]
        )
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        return CONFIRM_ORDER
        
    except Exception as e:
        logger.error(f"❌ Error in receive_modern_target: {e}")
        await show_modern_error(update, "Error memproses tujuan")
        return ENTER_TUJUAN

async def process_modern_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process modern order dengan animasi lengkap"""
    query = update.callback_query
    await query.answer()
    
    user_data = context.user_data
    product = user_data.get('selected_product')
    target = user_data.get('order_target')
    
    if not product or not target:
        await show_modern_error(update, "Data order tidak lengkap")
        return ConversationHandler.END
    
    try:
        user_id = str(query.from_user.id)
        price = product['price']
        
        # 1. CHECK SALDO
        saldo_awal = get_user_saldo(user_id)
        if saldo_awal < price:
            message = ModernMessageBuilder.create_order_message(
                {
                    'product_name': product['name'],
                    'customer_input': target,
                    'price': price,
                    'provider_order_id': 'N/A'
                },
                'failed',
                [
                    f"💰 **Saldo:** Rp {saldo_awal:,}",
                    f"💳 **Dibutuhkan:** Rp {price:,}",
                    f"🔶 **Kurang:** Rp {price - saldo_awal:,}",
                    "💸 **Silakan top up saldo terlebih dahulu**"
                ]
            )
            
            keyboard = [
                [InlineKeyboardButton("💸 TOP UP", callback_data="topup_menu")],
                [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]
            ]
            
            await safe_edit_modern_message(update, message, InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END
        
        # 2. CHECK STOK TERAKHIR DENGAN ANIMASI
        anim_message = await ModernAnimations.show_processing(
            update, context, 
            "Memeriksa Stok Terbaru...", 2
        )
        
        sync_product_stock_from_provider()
        updated_product = get_product_by_code_with_stock(product['code'])
        
        if not updated_product or updated_product.get('kosong') == 1 or updated_product.get('display_stock', 0) <= 0:
            message = ModernMessageBuilder.create_order_message(
                product, 'failed',
                ["❌ **Stok sudah habis**", "🔄 Silakan pilih produk lain"]
            )
            
            keyboard = [
                [InlineKeyboardButton("🛒 PRODUK LAIN", callback_data="morder_back_to_groups")],
                [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]
            ]
            
            try:
                await context.bot.edit_message_text(
                    chat_id=anim_message.chat_id,
                    message_id=anim_message.message_id,
                    text=message,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            except:
                await safe_edit_modern_message(update, message, InlineKeyboardMarkup(keyboard))
            
            return CHOOSING_PRODUCT
        
        # 3. POTONG SALDO
        await ModernAnimations.typing_effect(update, context, 1)
        
        if not update_user_saldo(user_id, -price, f"Order: {product['name']}"):
            await show_modern_error(update, "Gagal memotong saldo")
            return ConversationHandler.END
        
        # 4. BUAT ORDER DI DATABASE
        reffid = f"akrab_{uuid.uuid4().hex[:16]}"
        order_id = save_order(
            user_id=user_id,
            product_name=product['name'],
            product_code=product['code'],
            customer_input=target,
            price=price,
            status='processing',
            provider_order_id=reffid,
            sn='',
            note='Sedang diproses ke provider',
            saldo_awal=saldo_awal
        )
        
        if not order_id:
            update_user_saldo(user_id, price, "Refund: Gagal save order")
            await show_modern_error(update, "Gagal menyimpan order")
            return ConversationHandler.END
        
        # 5. PROSES KE PROVIDER DENGAN ANIMASI
        try:
            await context.bot.edit_message_text(
                chat_id=anim_message.chat_id,
                message_id=anim_message.message_id,
                text="🔄 **MENGIRIM KE PROVIDER...**\n\nMohon tunggu sebentar...",
                parse_mode="Markdown"
            )
        except:
            pass
        
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        khfy_api = KhfyPayAPI(api_key)
        
        order_result = khfy_api.create_order(product['code'], target, reffid)
        
        # 6. PROCESS RESULT
        provider_status = order_result.get('status', '').lower() if order_result else 'error'
        provider_message = order_result.get('message', 'Timeout') if order_result else 'Gagal terhubung'
        sn_number = order_result.get('sn', '')
        
        # Determine final status
        if any(s in provider_status for s in ['sukses', 'success', 'berhasil']):
            final_status = 'completed'
            update_product_stock_after_order(product['code'])
            status_info = ["✅ **Pembelian Berhasil**", f"📦 Stok produk diperbarui"]
        elif any(s in provider_status for s in ['pending', 'proses', 'processing']):
            final_status = 'pending'
            status_info = ["⏳ **Menunggu Konfirmasi**", "📡 Polling system aktif"]
        else:
            final_status = 'failed'
            update_user_saldo(user_id, price, f"Refund: {provider_message}")
            status_info = ["❌ **Gagal di Provider**", f"💡 {provider_message}", "✅ Saldo telah dikembalikan"]
        
        # Update order status
        update_order_status(order_id, final_status, sn=sn_number, note=provider_message)
        
        # 7. TAMPILKAN HASIL FINAL
        saldo_akhir = get_user_saldo(user_id)
        
        additional_info = status_info + [
            f"💰 **Saldo Awal:** Rp {saldo_awal:,}",
            f"💰 **Saldo Akhir:** Rp {saldo_akhir:,}",
            f"🔗 **Ref ID:** `{reffid}`"
        ]
        
        if sn_number:
            additional_info.append(f"🔢 **SN:** `{sn_number}`")
        
        message = ModernMessageBuilder.create_order_message(
            {
                'product_name': product['name'],
                'customer_input': target,
                'price': price,
                'provider_order_id': reffid
            },
            final_status,
            additional_info
        )
        
        keyboard = [
            [InlineKeyboardButton("🛒 BELI LAGI", callback_data="main_menu_order")],
            [InlineKeyboardButton("📋 RIWAYAT", callback_data="main_menu_history")],
            [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]
        ]
        
        try:
            await context.bot.edit_message_text(
                chat_id=anim_message.chat_id,
                message_id=anim_message.message_id,
                text=message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        except:
            await safe_edit_modern_message(update, message, InlineKeyboardMarkup(keyboard))
        
        # 8. CLEANUP
        order_keys = ['selected_product', 'order_target', 'product_page', 'current_group', 'current_products']
        for key in order_keys:
            if key in user_data:
                del user_data[key]
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"❌ Critical error in modern order: {e}")
        
        # REFUND JIKA ERROR
        try:
            user_id = str(query.from_user.id)
            update_user_saldo(user_id, product['price'], "Refund: System error")
        except:
            pass
        
        await show_modern_error(update, f"System error: {str(e)}")
        return ConversationHandler.END

# ==================== POLLING SYSTEM MODERN ====================

class ModernPoller:
    def __init__(self, api_key, poll_interval=60):
        self.api_key = api_key
        self.poll_interval = poll_interval
        self.is_running = False
        self.application = None
    
    async def start_polling(self, application):
        """Start modern polling system"""
        self.application = application
        self.is_running = True
        
        logger.info("🚀 Starting Modern Polling System...")
        
        # Start all services
        asyncio.create_task(self.timeout_service())
        asyncio.create_task(self.polling_service())
    
    async def timeout_service(self):
        """Service untuk handle timeout orders (5 menit)"""
        while self.is_running:
            try:
                await self.process_timeout_orders()
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"❌ Timeout service error: {e}")
                await asyncio.sleep(30)
    
    async def polling_service(self):
        """Service untuk check order status"""
        while self.is_running:
            try:
                await self.check_pending_orders()
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"❌ Polling service error: {e}")
                await asyncio.sleep(30)
    
    async def process_timeout_orders(self):
        """Process orders that timeout after 5 minutes"""
        try:
            pending_orders = get_pending_orders()
            current_time = datetime.now()
            
            for order in pending_orders:
                order_id = order['id']
                created_at = order['created_at']
                
                if isinstance(created_at, str):
                    created_at = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                
                time_diff = (current_time - created_at).total_seconds()
                
                # Jika sudah lebih dari 5 menit, auto failed dan refund
                if time_diff >= 300 and order_id not in pending_orders_timeout:
                    await self.auto_fail_timeout_order(order)
                    pending_orders_timeout[order_id] = current_time
                    
        except Exception as e:
            logger.error(f"❌ Error in process_timeout_orders: {e}")
    
    async def auto_fail_timeout_order(self, order):
        """Auto fail timeout order dan refund"""
        try:
            order_id = order['id']
            user_id = order['user_id']
            
            logger.info(f"⏰ Auto-failing timeout order {order_id}")
            
            # Update status order
            update_order_status(
                order_id, 
                'failed', 
                note=f"Auto failed: Timeout 5 menit tanpa respon provider"
            )
            
            # Refund saldo user
            refund_success = update_user_saldo(
                user_id, 
                order['price'], 
                f"Refund auto: Order timeout - {order['product_name']}"
            )
            
            # Notify user
            message = ModernMessageBuilder.create_order_message(
                order,
                'failed',
                [
                    "⏰ **Timeout 5 Menit**",
                    "❌ Tidak ada respon dari provider",
                    "✅ **Saldo telah dikembalikan**",
                    "🔄 Silakan order ulang"
                ]
            )
            
            await send_modern_notification(order['user_id'], message)
            
            logger.info(f"✅ Auto-failed timeout order {order_id}")
            
        except Exception as e:
            logger.error(f"❌ Error auto-failing order: {e}")
    
    async def check_pending_orders(self):
        """Check all pending orders"""
        try:
            pending_orders = get_pending_orders()
            
            if not pending_orders:
                return
            
            logger.info(f"🔍 Checking {len(pending_orders)} pending orders...")
            
            api_key = getattr(config, 'KHFYPAY_API_KEY', '')
            if not api_key:
                return
            
            khfy_api = KhfyPayAPI(api_key)
            
            for order in pending_orders:
                await self.check_order_status(order, khfy_api)
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error(f"❌ Error in check_pending_orders: {e}")
    
    async def check_order_status(self, order, khfy_api):
        """Check status of a single order"""
        try:
            reffid = order['provider_order_id']
            order_id = order['id']
            
            status_result = khfy_api.check_order_status(reffid)
            
            if not status_result:
                return
            
            await self.process_status_result(order, status_result)
                
        except Exception as e:
            logger.error(f"❌ Error checking order {order.get('id', 'unknown')}: {e}")
    
    async def process_status_result(self, order, status_result):
        """Process the status result from API"""
        try:
            order_id = order['id']
            user_id = order['user_id']
            current_status = order['status']
            
            # Handle berbagai format response
            provider_status = None
            message = ""
            sn = ""
            
            if isinstance(status_result, dict):
                if status_result.get('data'):
                    data = status_result['data']
                    if isinstance(data, dict):
                        provider_status = data.get('status') or data.get('Status')
                        message = data.get('message') or data.get('Message') or data.get('keterangan', '')
                        sn = data.get('sn') or data.get('SN') or data.get('serial', '')
                    else:
                        provider_status = str(data).lower()
                        message = str(data)
                else:
                    provider_status = status_result.get('status') or status_result.get('Status')
                    message = status_result.get('message') or status_result.get('Message') or status_result.get('keterangan', '')
                    sn = status_result.get('sn') or status_result.get('SN')
            
            if not provider_status:
                return
            
            provider_status = str(provider_status).lower().strip()
            
            # Process status
            if any(s in provider_status for s in ['sukses', 'success', 'berhasil']):
                if current_status != 'completed':
                    update_order_status(order_id, 'completed', sn=sn, note=f"Polling: {message}")
                    update_product_stock_after_order(order['product_code'])
                    
                    success_message = ModernMessageBuilder.create_order_message(
                        order,
                        'success',
                        [f"✅ **Order berhasil** via polling", f"💬 {message}"]
                    )
                    
                    await send_modern_notification(user_id, success_message)
            
            elif any(s in provider_status for s in ['gagal', 'failed', 'error', 'batal']):
                if current_status != 'failed':
                    update_order_status(order_id, 'failed', note=f"Polling Gagal: {message}")
                    update_user_saldo(user_id, order['price'], f"Refund: Order gagal - {message}")
                    
                    failed_message = ModernMessageBuilder.create_order_message(
                        order,
                        'failed',
                        [f"❌ **Order gagal** via polling", f"💬 {message}", "✅ **Saldo telah dikembalikan**"]
                    )
                    
                    await send_modern_notification(user_id, failed_message)
            
        except Exception as e:
            logger.error(f"❌ Error processing status: {e}")

# ==================== UTILITY FUNCTIONS ====================

async def safe_edit_modern_message(update, text, reply_markup=None, parse_mode="Markdown"):
    """Safely edit modern message"""
    try:
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                text, 
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        return True
    except Exception as e:
        logger.error(f"❌ Error editing modern message: {e}")
        return False

async def show_modern_error(update, error_text):
    """Show modern error message"""
    message = (
        f"❌ **SYSTEM ERROR**\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        f"{error_text}\n\n"
        f"🔄 Silakan coba lagi atau hubungi admin"
    )
    
    keyboard = [[InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]]
    
    await safe_edit_modern_message(update, message, InlineKeyboardMarkup(keyboard))

async def send_modern_notification(user_id, message):
    """Send modern notification"""
    try:
        if bot_application:
            await bot_application.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="Markdown"
            )
            return True
    except Exception as e:
        logger.error(f"❌ Failed to send notification: {e}")
    return False

def validate_pulsa_target(phone, product_code):
    """Validate pulsa target"""
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
        logger.error(f"❌ Error validating pulsa target: {e}")
        return None

# ==================== CANCEL HANDLERS ====================

async def cancel_modern_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel modern order"""
    query = update.callback_query
    await query.answer("Order dibatalkan")
    
    if 'selected_product' in context.user_data:
        del context.user_data['selected_product']
    if 'order_target' in context.user_data:
        del context.user_data['order_target']
    
    return await show_modern_products(update, context)

async def cancel_modern_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the entire modern order conversation"""
    query = update.callback_query
    if query:
        await query.answer()
    
    order_keys = ['selected_product', 'order_target', 'product_page', 'current_group', 'current_products']
    for key in order_keys:
        if key in context.user_data:
            del context.user_data[key]
    
    await safe_edit_modern_message(
        update,
        "❌ **ORDER DIBATALKAN**\n\nKembali ke menu utama...",
        InlineKeyboardMarkup([[InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]])
    )
    
    return ConversationHandler.END

# ==================== CONVERSATION HANDLER SETUP ====================

def get_modern_conversation_handler():
    """Get modern conversation handler untuk didaftarkan di main.py"""
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler, pattern="^main_menu_order$")],
        states={
            CHOOSING_GROUP: [
                CallbackQueryHandler(show_modern_products, pattern="^morder_group_"),
                CallbackQueryHandler(cancel_modern_conversation, pattern="^main_menu_main$")
            ],
            CHOOSING_PRODUCT: [
                CallbackQueryHandler(select_modern_product, pattern="^morder_product_"),
                CallbackQueryHandler(handle_modern_pagination, pattern="^(morder_next_page|morder_prev_page)$"),
                CallbackQueryHandler(back_to_modern_groups, pattern="^morder_back_to_groups$"),
                CallbackQueryHandler(cancel_modern_conversation, pattern="^main_menu_main$")
            ],
            ENTER_TUJUAN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_modern_target),
                CallbackQueryHandler(show_modern_products, pattern="^morder_group_"),
                CallbackQueryHandler(cancel_modern_conversation, pattern="^main_menu_main$")
            ],
            CONFIRM_ORDER: [
                CallbackQueryHandler(process_modern_order, pattern="^morder_confirm$"),
                CallbackQueryHandler(cancel_modern_order, pattern="^morder_cancel$"),
                CallbackQueryHandler(show_modern_products, pattern="^morder_group_"),
                CallbackQueryHandler(cancel_modern_conversation, pattern="^main_menu_main$")
            ],
        },
        fallbacks=[
            CommandHandler("start", cancel_modern_conversation),
            CommandHandler("cancel", cancel_modern_conversation),
            CallbackQueryHandler(cancel_modern_conversation, pattern="^main_menu_main$")
        ],
        name="modern_order_conversation",
        persistent=False
    )

# ==================== INITIALIZATION FUNCTION ====================

modern_poller = None

def initialize_modern_order_system(application):
    """Initialize the complete modern order system dengan polling system"""
    global bot_application, modern_poller
    bot_application = application
    
    api_key = getattr(config, 'KHFYPAY_API_KEY', '')
    modern_poller = ModernPoller(api_key)
    
    # Start polling system
    loop = asyncio.get_event_loop()
    loop.create_task(modern_poller.start_polling(application))
    
    logger.info("✅ Modern Order System Initialized with Polling System!")

# Export handler untuk main.py
modern_order_handler = get_modern_conversation_handler()
