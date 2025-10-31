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

# ==================== OPERATOR DETECTION SYSTEM ====================

def detect_operator(phone):
    """Deteksi operator berdasarkan prefix nomor"""
    try:
        # Bersihkan nomor
        phone = re.sub(r'\D', '', phone)
        
        # Konversi format
        if phone.startswith('0'):
            phone = '62' + phone[1:]
        elif phone.startswith('8'):
            phone = '62' + phone
        elif phone.startswith('+62'):
            phone = phone[1:]
        
        # XL Axiata prefixes
        xl_prefixes = ['62817', '62818', '62819', '62859', '62878', '62877', '62876']
        
        # Axis prefixes (sebenarnya sama dengan XL karena merger)
        axis_prefixes = ['62838', '62839', '62837', '62888']
        
        # Other operators
        telkomsel_prefixes = ['62852', '62853', '62811', '62812', '62813', '62821', '62822', '62823']
        indosat_prefixes = ['62814', '62815', '62816', '62855', '62856', '62857', '62858']
        three_prefixes = ['62895', '62896', '62897', '62898', '62899']
        smartfren_prefixes = ['62888', '62889']
        
        # Check XL first
        for prefix in xl_prefixes:
            if phone.startswith(prefix):
                return "XL"
        
        # Check Axis
        for prefix in axis_prefixes:
            if phone.startswith(prefix):
                return "AXIS"
        
        # Check other operators
        for prefix in telkomsel_prefixes:
            if phone.startswith(prefix):
                return "TELKOMSEL"
        
        for prefix in indosat_prefixes:
            if phone.startswith(prefix):
                return "INDOSAT"
        
        for prefix in three_prefixes:
            if phone.startswith(prefix):
                return "THREE"
        
        for prefix in smartfren_prefixes:
            if phone.startswith(prefix):
                return "SMARTFREN"
        
        return "UNKNOWN"
        
    except Exception as e:
        logger.error(f"❌ Error detecting operator: {e}")
        return "UNKNOWN"

def get_operator_from_product_code(product_code):
    """Get operator dari kode produk"""
    try:
        product_code_upper = product_code.upper()
        
        if any(prefix in product_code_upper for prefix in ['XL', 'XLA']):
            return "XL"
        elif any(prefix in product_code_upper for prefix in ['AX', 'AXIS']):
            return "AXIS"
        elif any(prefix in product_code_upper for prefix in ['TS', 'TELKOMSEL']):
            return "TELKOMSEL"
        elif any(prefix in product_code_upper for prefix in ['IN', 'INDOSAT', 'IM']):
            return "INDOSAT"
        elif any(prefix in product_code_upper for prefix in ['SM', 'SMARTFREN', 'SF']):
            return "SMARTFREN"
        elif any(prefix in product_code_upper for prefix in ['3', 'THREE']):
            return "THREE"
        else:
            return None  # Untuk produk non-pulsa
            
    except Exception as e:
        logger.error(f"❌ Error getting operator from product code: {e}")
        return None

def validate_phone_number_modern(phone, product_code=None):
    """Validasi nomor telepon dengan deteksi otomatis operator"""
    try:
        original_phone = phone
        phone = re.sub(r'\D', '', phone)
        
        if not phone:
            return None, "Nomor tidak valid - hanya mengandung angka"
        
        # Validasi panjang dasar
        if len(phone) < 10:
            return None, "Nomor terlalu pendek (minimal 10 digit)"
        if len(phone) > 14:
            return None, "Nomor terlalu panjang (maksimal 14 digit)"
        
        # Konversi format ke 62
        if phone.startswith('0'):
            phone = '62' + phone[1:]
        elif phone.startswith('8'):
            phone = '62' + phone
        elif phone.startswith('+62'):
            phone = phone[1:]
        
        # Pastikan sekarang format 62
        if not phone.startswith('62'):
            return None, "Format nomor tidak valid (harus diawali 0, 62, atau +62)"
        
        # Deteksi operator
        operator = detect_operator(phone)
        
        # Jika product_code diberikan, validasi kecocokan
        if product_code:
            expected_operator = get_operator_from_product_code(product_code)
            if expected_operator:
                if operator == "UNKNOWN":
                    return None, f"Operator tidak dikenali. Pastikan nomor sesuai dengan produk {expected_operator}"
                elif operator != expected_operator:
                    return None, f"Nomor {operator} tidak cocok dengan produk {expected_operator}. Harus menggunakan nomor {expected_operator}"
        
        return phone, operator
        
    except Exception as e:
        logger.error(f"❌ Error validating phone: {e}")
        return None, "Error sistem dalam validasi nomor"

def validate_target_modern(target, product_code):
    """Validasi target dengan deteksi operator otomatis"""
    try:
        # Untuk produk non-pulsa (PLN, dll)
        if product_code.startswith('PLN'):
            target = re.sub(r'\D', '', target)
            if len(target) < 10 or len(target) > 20:
                return None, "ID Pelanggan PLN harus 10-20 digit"
            return target, "PLN"
        
        elif product_code.startswith('VOUCHER'):
            target = target.strip()
            if len(target) < 5:
                return None, "ID Game terlalu pendek (minimal 5 karakter)"
            return target, "GAME"
        
        elif product_code.startswith('LISTRIK'):
            target = re.sub(r'\D', '', target)
            if len(target) < 10 or len(target) > 20:
                return None, "ID Pelanggan Listrik harus 10-20 digit"
            return target, "LISTRIK"
        
        # Untuk produk pulsa - gunakan validasi modern
        elif product_code.startswith(('TS', 'AX', 'XL', 'IN', 'SM', '3')):
            return validate_phone_number_modern(target, product_code)
        
        # Default untuk produk lain
        else:
            target = target.strip()
            if len(target) < 3:
                return None, "Input terlalu pendek (minimal 3 karakter)"
            return target, "OTHER"
        
    except Exception as e:
        logger.error(f"❌ Error in validate_target_modern: {e}")
        return None, "Error validasi input"

# ==================== KHFYPAY API REAL-TIME INTEGRATION ====================

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

    def check_order_status_detailed(self, reffid):
        """Check order status dengan parsing detail untuk berbagai format response"""
        try:
            result = self.check_order_status(reffid)
            if not result:
                return None, "Tidak ada response dari provider"
            
            # Parse berbagai format response KhfyPay
            status = None
            message = ""
            sn = ""
            
            # Format 1: { "data": { "status": "...", "message": "...", "sn": "..." } }
            if isinstance(result, dict) and result.get('data'):
                data = result['data']
                if isinstance(data, dict):
                    status = data.get('status') or data.get('Status')
                    message = data.get('message') or data.get('Message') or data.get('keterangan', '')
                    sn = data.get('sn') or data.get('SN') or data.get('serial', '')
                else:
                    # Data bukan dict, mungkin string langsung
                    status = str(data).lower()
                    message = str(data)
            
            # Format 2: { "status": "...", "message": "...", "sn": "..." }
            elif isinstance(result, dict):
                status = result.get('status') or result.get('Status')
                message = result.get('message') or result.get('Message') or result.get('keterangan', '')
                sn = result.get('sn') or result.get('SN') or result.get('serial', '')
            
            # Format 3: Array response
            elif isinstance(result, list) and len(result) > 0:
                first_item = result[0]
                if isinstance(first_item, dict):
                    status = first_item.get('status') or first_item.get('Status')
                    message = first_item.get('message') or first_item.get('Message') or first_item.get('keterangan', '')
                    sn = first_item.get('sn') or first_item.get('SN') or first_item.get('serial', '')
            
            # Format tidak dikenali
            else:
                message = f"Format response tidak dikenali: {result}"
            
            return status, message, sn
            
        except Exception as e:
            logger.error(f"❌ Error parsing order status: {e}")
            return None, f"Error parsing: {str(e)}", ""

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
        status_emojis = {'success': '🟢', 'pending': '🟡', 'failed': '🔴', 'processing': '🔵', 'timeout': '🟠'}
        status_emoji = status_emojis.get(status, '🟡')
        return f"{emoji} **{title}** {status_emoji}\n" + "▬" * 35 + "\n\n"

    @staticmethod
    def create_order_message(order_data, status_type, additional_info=None):
        """Create modern order message"""
        status_configs = {
            'success': {'emoji': '✅', 'title': 'ORDER BERHASIL', 'color': '🟢'},
            'pending': {'emoji': '⏳', 'title': 'ORDER DIPROSES', 'color': '🟡'},
            'failed': {'emoji': '❌', 'title': 'ORDER GAGAL', 'color': '🔴'},
            'processing': {'emoji': '🔄', 'title': 'PROSES ORDER', 'color': '🔵'},
            'timeout': {'emoji': '⏰', 'title': 'ORDER TIMEOUT', 'color': '🟠'}
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

def update_user_saldo_modern(user_id, amount, note=""):
    """Update user balance dengan error handling - FIXED VERSION"""
    try:
        # Coba function database yang ada
        if hasattr(database, 'update_user_balance'):
            try:
                return database.update_user_balance(user_id, amount, note)
            except TypeError:
                # Coba tanpa note parameter
                return database.update_user_balance(user_id, amount)
        elif hasattr(database, 'update_user_saldo'):
            try:
                return database.update_user_saldo(user_id, amount, note)
            except TypeError:
                # Coba tanpa note parameter
                return database.update_user_saldo(user_id, amount)
        else:
            # Fallback ke SQL langsung
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            
            # Get current balance
            cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            
            if not result:
                conn.close()
                return False
            
            current_balance = result[0]
            new_balance = current_balance + amount
            
            # Update balance
            cursor.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?", 
                (new_balance, user_id)
            )
            
            # Save transaction
            transaction_type = "refund" if amount > 0 else "order"
            
            cursor.execute('''
                INSERT INTO transactions (user_id, amount, type, note, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, amount, transaction_type, note, datetime.now()))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Updated balance for {user_id}: {amount} (New: {new_balance})")
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

def get_order_by_id(order_id):
    """Get order by ID"""
    try:
        if hasattr(database, 'get_order_by_id'):
            return database.get_order_by_id(order_id)
        else:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_id, product_name, product_code, customer_input, price, 
                       status, provider_order_id, sn, note, created_at 
                FROM orders WHERE id = ?
            ''', (order_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return dict(zip([
                    'id', 'user_id', 'product_name', 'product_code', 'customer_input', 
                    'price', 'status', 'provider_order_id', 'sn', 'note', 'created_at'
                ], row))
            return None
    except Exception as e:
        logger.error(f"❌ Error getting order by ID: {e}")
        return None

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

# ==================== REAL-TIME STATUS POLLING SYSTEM ====================

class RealTimePoller:
    def __init__(self, api_key, poll_interval=30):  # Poll lebih sering untuk real-time
        self.api_key = api_key
        self.poll_interval = poll_interval
        self.is_running = False
        self.application = None
        self.khfy_api = KhfyPayAPI(api_key)
    
    async def start_polling(self, application):
        """Start real-time polling system"""
        self.application = application
        self.is_running = True
        
        logger.info("🚀 Starting REAL-TIME Polling System...")
        
        # Start all services
        asyncio.create_task(self.real_time_status_service())
        asyncio.create_task(self.timeout_service())
    
    async def real_time_status_service(self):
        """Service untuk real-time status checking"""
        while self.is_running:
            try:
                await self.check_all_pending_orders_real_time()
                await asyncio.sleep(self.poll_interval)  # Check setiap 30 detik
            except Exception as e:
                logger.error(f"❌ Real-time service error: {e}")
                await asyncio.sleep(30)
    
    async def timeout_service(self):
        """Service untuk handle timeout orders (3 menit)"""
        while self.is_running:
            try:
                await self.process_timeout_orders()
                await asyncio.sleep(20)  # Check timeout setiap 20 detik
            except Exception as e:
                logger.error(f"❌ Timeout service error: {e}")
                await asyncio.sleep(20)
    
    async def check_all_pending_orders_real_time(self):
        """Check semua pending orders dengan real-time update"""
        try:
            pending_orders = get_pending_orders()
            
            if not pending_orders:
                return
            
            logger.info(f"🔍 REAL-TIME Checking {len(pending_orders)} pending orders...")
            
            for order in pending_orders:
                await self.check_single_order_real_time(order)
                await asyncio.sleep(1)  # Jeda 1 detik antar request
            
        except Exception as e:
            logger.error(f"❌ Error in real-time order checking: {e}")
    
    async def check_single_order_real_time(self, order):
        """Check single order dengan real-time update ke user"""
        try:
            reffid = order['provider_order_id']
            order_id = order['id']
            user_id = order['user_id']
            
            # Skip order yang terlalu baru (kurang dari 30 detik)
            created_at = order['created_at']
            if isinstance(created_at, str):
                created_at = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
            
            if (datetime.now() - created_at).total_seconds() < 30:
                return
            
            # Check status dengan parsing detail
            status, message, sn = self.khfy_api.check_order_status_detailed(reffid)
            
            if not status:
                logger.warning(f"⚠️ No status for order {order_id}")
                return
            
            status = str(status).lower().strip()
            current_status = order['status']
            
            # Process status real-time
            new_status = None
            refund_amount = 0
            
            if any(s in status for s in ['sukses', 'success', 'berhasil', 'completed']):
                if current_status != 'completed':
                    new_status = 'completed'
                    update_product_stock_after_order(order['product_code'])
                    logger.info(f"✅ REAL-TIME: Order {order_id} completed")
            
            elif any(s in status for s in ['gagal', 'failed', 'error', 'batal']):
                if current_status != 'failed':
                    new_status = 'failed'
                    refund_amount = order['price']
                    logger.info(f"❌ REAL-TIME: Order {order_id} failed")
            
            elif any(s in status for s in ['pending', 'proses', 'processing', 'waiting']):
                if current_status != 'pending':
                    new_status = 'pending'
                    logger.info(f"⏳ REAL-TIME: Order {order_id} still pending")
            
            # Update status jika ada perubahan
            if new_status:
                # Update database
                update_order_status(order_id, new_status, sn=sn, note=f"Real-time: {message}")
                
                # Refund jika gagal
                if refund_amount > 0:
                    update_user_saldo_modern(user_id, refund_amount, f"Refund: Order failed - {message}")
                
                # Notify user
                await self.send_real_time_notification(user_id, order, new_status, message, sn)
                
        except Exception as e:
            logger.error(f"❌ Error in real-time order check {order.get('id', 'unknown')}: {e}")
    
    async def send_real_time_notification(self, user_id, order, new_status, message, sn):
        """Send real-time notification to user"""
        try:
            status_configs = {
                'completed': {'emoji': '✅', 'title': 'ORDER BERHASIL', 'color': '🟢'},
                'failed': {'emoji': '❌', 'title': 'ORDER GAGAL', 'color': '🔴'},
                'pending': {'emoji': '⏳', 'title': 'ORDER DIPROSES', 'color': '🟡'}
            }
            
            config = status_configs.get(new_status, status_configs['pending'])
            
            notification_text = (
                f"{config['emoji']} **{config['title']}** {config['color']}\n"
                f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
                f"📦 **Produk:** {order['product_name']}\n"
                f"📮 **Tujuan:** `{order['customer_input']}`\n"
                f"💰 **Harga:** Rp {order['price']:,}\n"
                f"🔗 **Ref ID:** `{order['provider_order_id']}`\n"
            )
            
            if sn:
                notification_text += f"🔢 **SN:** `{sn}`\n"
            
            notification_text += f"💬 **Pesan:** {message}\n\n"
            
            if new_status == 'failed':
                notification_text += "✅ **Saldo telah dikembalikan otomatis**\n\n"
            
            notification_text += f"🕒 **Update:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
            
            keyboard = [
                [InlineKeyboardButton("🛒 BELI LAGI", callback_data="main_menu_order")],
                [InlineKeyboardButton("📋 RIWAYAT", callback_data="main_menu_history")],
                [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]
            ]
            
            await bot_application.bot.send_message(
                chat_id=user_id,
                text=notification_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            
            logger.info(f"📢 Real-time notification sent for order {order['id']}")
            
        except Exception as e:
            logger.error(f"❌ Error sending real-time notification: {e}")
    
    async def process_timeout_orders(self):
        """Process orders that timeout after 3 menit (lebih cepat)"""
        try:
            pending_orders = get_pending_orders()
            current_time = datetime.now()
            
            for order in pending_orders:
                order_id = order['id']
                created_at = order['created_at']
                
                if isinstance(created_at, str):
                    created_at = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                
                time_diff = (current_time - created_at).total_seconds()
                
                # Jika sudah lebih dari 3 menit, auto failed dan refund
                if time_diff >= 180 and order_id not in pending_orders_timeout:
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
                note=f"Auto failed: Timeout 3 menit tanpa respon provider"
            )
            
            # Refund saldo user
            refund_success = update_user_saldo_modern(
                user_id, 
                order['price'], 
                f"Refund: Order timeout - {order['product_name']}"
            )
            
            # Notify user
            message = ModernMessageBuilder.create_order_message(
                order,
                'failed',
                [
                    "⏰ **Timeout 3 Menit**",
                    "❌ Tidak ada respon dari provider",
                    "✅ **Saldo telah dikembalikan**",
                    "🔄 Silakan order ulang"
                ]
            )
            
            await send_modern_notification(user_id, message)
            
            logger.info(f"✅ Auto-failed timeout order {order_id}")
            
        except Exception as e:
            logger.error(f"❌ Error auto-failing order: {e}")

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
    """Show modern products list dengan info operator"""
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
            # Dapatkan info operator
            operator = get_operator_from_product_code(product['code'])
            operator_text = f" | {operator}" if operator else ""
            
            price_formatted = f"Rp {product['price']:,}"
            
            if product['kosong'] == 1:
                button_text = f"🔴 {product['name']} - {price_formatted}{operator_text} | HABIS"
            elif product['gangguan'] == 1:
                button_text = f"🚧 {product['name']} - {price_formatted}{operator_text} | GANGGUAN"
            elif product['display_stock'] > 10:
                button_text = f"🟢 {product['name']} - {price_formatted}{operator_text} | Stock: {product['display_stock']}+"
            elif product['display_stock'] > 5:
                button_text = f"🟢 {product['name']} - {price_formatted}{operator_text} | Stock: {product['display_stock']}"
            elif product['display_stock'] > 0:
                button_text = f"🟡 {product['name']} - {price_formatted}{operator_text} | Stock: {product['display_stock']}"
            else:
                button_text = f"🔴 {product['name']} - {price_formatted}{operator_text} | HABIS"
            
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
        return CHOOSING_PRODUCT

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
    """Select product dengan info operator yang jelas"""
    query = update.callback_query
    await query.answer()
    
    try:
        product_code = query.data.replace('morder_product_', '')
        product = get_product_by_code_with_stock(product_code)
        
        if not product:
            await show_modern_error(update, "Produk tidak ditemukan")
            return CHOOSING_PRODUCT
        
        # Validasi stok
        if product['kosong'] == 1 or product['display_stock'] <= 0:
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
        
        context.user_data['selected_product'] = product
        
        # Tentukan contoh input berdasarkan operator
        operator = get_operator_from_product_code(product['code'])
        examples = {
            'XL': "Contoh: 0817xxxxxxx, 0818xxxxxxx, 0819xxxxxxx",
            'AXIS': "Contoh: 0838xxxxxxx, 0839xxxxxxx", 
            'TELKOMSEL': "Contoh: 0812xxxxxxx, 0813xxxxxxx, 0821xxxxxxx",
            'INDOSAT': "Contoh: 0814xxxxxxx, 0815xxxxxxx, 0816xxxxxxx",
            'SMARTFREN': "Contoh: 0888xxxxxxx, 0889xxxxxxx",
            'THREE': "Contoh: 0895xxxxxxx, 0896xxxxxxx, 0897xxxxxxx",
            'PLN': "Contoh: 123456789012345 (ID Pelanggan PLN)",
            'GAME': "Contoh: 1234567890 (ID Game)",
            'OTHER': "Contoh: Sesuai kebutuhan produk"
        }
        
        example = examples.get(operator, "Contoh: 081234567890")
        operator_text = f"**Operator:** {operator}\n" if operator else ""
        
        message = (
            f"🛒 **PILIHAN PRODUK**\n"
            f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
            f"📦 **{product['name']}**\n"
            f"💰 Harga: Rp {product['price']:,}\n"
            f"📊 Stok: {product['stock_status']}\n"
            f"{operator_text}"
            f"📝 **Masukkan nomor tujuan:**\n"
            f"`{example}`\n\n"
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
        logger.error(f"❌ Error selecting product: {e}")
        await show_modern_error(update, "Error memilih produk")
        return CHOOSING_PRODUCT

async def receive_modern_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive target dengan validasi dan deteksi operator otomatis"""
    try:
        target = update.message.text.strip()
        product = context.user_data.get('selected_product')
        
        if not product:
            await show_modern_error(update, "Sesi telah berakhir")
            return ConversationHandler.END
        
        # Validasi target dengan deteksi operator
        validated_target, operator_info = validate_target_modern(target, product['code'])
        
        if not validated_target:
            # Tampilkan pesan error yang informatif
            error_message = f"❌ **FORMAT TIDAK VALID!**\n\n"
            error_message += f"📦 **Produk:** {product['name']}\n"
            error_message += f"📮 **Input:** `{target}`\n\n"
            error_message += f"**Error:** {operator_info}\n\n"
            
            # Berikan contoh berdasarkan produk
            expected_operator = get_operator_from_product_code(product['code'])
            if expected_operator:
                error_message += f"**Produk ini untuk operator:** {expected_operator}\n\n"
                error_message += "**Contoh format yang benar:**\n"
                if expected_operator == "XL":
                    error_message += "• 0817xxxxxxx\n• 0818xxxxxxx\n• 0819xxxxxxx\n"
                elif expected_operator == "AXIS":
                    error_message += "• 0838xxxxxxx\n• 0839xxxxxxx\n"
                elif expected_operator == "TELKOMSEL":
                    error_message += "• 0812xxxxxxx\n• 0813xxxxxxx\n• 0821xxxxxxx\n"
                elif expected_operator == "INDOSAT":
                    error_message += "• 0814xxxxxxx\n• 0815xxxxxxx\n• 0816xxxxxxx\n"
                else:
                    error_message += "• 081234567890\n• 81234567890\n• +6281234567890\n"
            
            await update.message.reply_text(
                error_message,
                parse_mode="Markdown"
            )
            return ENTER_TUJUAN
        
        context.user_data['order_target'] = validated_target
        context.user_data['detected_operator'] = operator_info
        
        # Tampilkan konfirmasi dengan info operator
        user_id = str(update.effective_user.id)
        saldo = get_user_saldo(user_id)
        
        operator_message = f"📡 **Operator Terdeteksi:** {operator_info}"
        
        message = ModernMessageBuilder.create_order_message(
            {
                'product_name': product['name'],
                'customer_input': validated_target,
                'price': product['price'],
                'provider_order_id': 'Akan digenerate'
            },
            'processing',
            [
                operator_message,
                f"💰 **Saldo Anda:** Rp {saldo:,}",
                f"🔰 **Sisa Saldo:** Rp {saldo - product['price']:,}",
                f"📦 **Stok:** {product['stock_status']}"
            ]
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ LANJUTKAN ORDER", callback_data="morder_confirm"),
                InlineKeyboardButton("❌ BATALKAN", callback_data="morder_cancel")
            ]
        ]
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        return CONFIRM_ORDER
        
    except Exception as e:
        logger.error(f"❌ Error receiving target: {e}")
        await show_modern_error(update, "Error memproses tujuan")
        return ENTER_TUJUAN

async def process_modern_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process modern order dengan real-time status tracking"""
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
        
        if not update_user_saldo_modern(user_id, -price, f"Order: {product['name']}"):
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
            note='Sedang diproses ke provider - REAL-TIME TRACKING',
            saldo_awal=saldo_awal
        )
        
        if not order_id:
            update_user_saldo_modern(user_id, price, "Refund: Gagal save order")
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
        
        # 6. PROCESS RESULT DENGAN REAL-TIME PARSING
        provider_status = None
        provider_message = "Menunggu konfirmasi provider"
        sn_number = ""
        
        if order_result:
            # Parse response dengan method baru
            status, message, sn = khfy_api.check_order_status_detailed(reffid)
            if status:
                provider_status = status
                provider_message = message
                sn_number = sn
        
        # Determine final status berdasarkan real-time response
        final_status = 'pending'  # Default pending untuk real-time tracking
        status_info = ["⏳ **Menunggu Konfirmasi Provider**", "📡 **Real-time tracking aktif**"]
        
        if provider_status and any(s in provider_status for s in ['sukses', 'success', 'berhasil']):
            final_status = 'completed'
            update_product_stock_after_order(product['code'])
            status_info = ["✅ **Pembelian Berhasil**", f"📦 Stok produk diperbarui"]
        elif provider_status and any(s in provider_status for s in ['gagal', 'failed', 'error']):
            final_status = 'failed'
            update_user_saldo_modern(user_id, price, f"Refund: {provider_message}")
            status_info = ["❌ **Gagal di Provider**", f"💡 {provider_message}", "✅ Saldo telah dikembalikan"]
        
        # Update order status
        update_order_status(order_id, final_status, sn=sn_number, note=provider_message)
        
        # 7. TAMPILKAN HASIL FINAL
        saldo_akhir = get_user_saldo(user_id)
        
        additional_info = status_info + [
            f"💰 **Saldo Awal:** Rp {saldo_awal:,}",
            f"💰 **Saldo Akhir:** Rp {saldo_akhir:,}",
            f"🔗 **Ref ID:** `{reffid}`",
            f"🔄 **Status:** Real-time tracking aktif"
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
            [InlineKeyboardButton("🔄 CEK STATUS", callback_data=f"check_status_{order_id}")],
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
            update_user_saldo_modern(user_id, product['price'], "Refund: System error")
        except:
            pass
        
        await show_modern_error(update, f"System error: {str(e)}")
        return ConversationHandler.END

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

real_time_poller = None

def initialize_modern_order_system(application):
    """Initialize the complete modern order system dengan REAL-TIME polling"""
    global bot_application, real_time_poller
    bot_application = application
    
    api_key = getattr(config, 'KHFYPAY_API_KEY', '')
    real_time_poller = RealTimePoller(api_key, poll_interval=30)  # 30 detik untuk real-time
    
    # Start polling system
    loop = asyncio.get_event_loop()
    loop.create_task(real_time_poller.start_polling(application))
    
    logger.info("✅ REAL-TIME Order System Initialized with Auto Operator Detection!")

# Export handler untuk main.py
modern_order_handler = get_modern_conversation_handler()
