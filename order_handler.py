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
        """Create new order in KhfyPay - IMPROVED seperti PHP"""
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
            
            # Improved response handling seperti PHP
            if result and isinstance(result, dict):
                status = result.get('status', '').upper()
                message = result.get('message', 'Order terkirim, menunggu update provider')
                
                # Mapping status seperti di PHP
                if status in ['SUKSES', 'SUCCESS']:
                    result['final_status'] = 'completed'
                elif status in ['GAGAL', 'FAILED']:
                    result['final_status'] = 'failed' 
                else:
                    result['final_status'] = 'pending'
                    
                result['status_api'] = status
                result['keterangan'] = message
            
            return result
            
        except requests.exceptions.Timeout:
            logger.error(f"Timeout creating order for {product_code}")
            return {"status": "error", "message": "Timeout - Silakan cek status manual", "final_status": "failed"}
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error creating order: {e}")
            return {"status": "error", "message": f"Network error: {str(e)}", "final_status": "failed"}
        except Exception as e:
            logger.error(f"Error creating KhfyPay order: {e}")
            return {"status": "error", "message": f"System error: {str(e)}", "final_status": "failed"}

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
    """Fixed compatibility function for save order - IMPROVED dengan saldo_awal"""
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
                                  price, status, provider_order_id, sn, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, product_name, product_code, customer_input, price, 
                  status, provider_order_id, sn, note, datetime.now()))
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

# ==================== PRODUCT VALIDATION - IMPROVED ====================

def get_product_by_code_direct(product_code):
    """Direct database product query - IMPROVED seperti PHP"""
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        # Coba tabel products
        cursor.execute("""
            SELECT code, name, price, category, description, stock, gangguan, kosong 
            FROM products WHERE code = ? LIMIT 1
        """, (product_code,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'code': row[0],
                'name': row[1],
                'price': row[2],
                'category': row[3],
                'description': row[4],
                'stock': row[5],
                'gangguan': row[6],
                'kosong': row[7]
            }
        return None
        
    except Exception as e:
        logger.error(f"Error in get_product_by_code_direct: {e}")
        return None

# ==================== ORDER PROCESSING - IMPROVED ====================

async def process_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process order confirmation dengan improvement dari PHP"""
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
        
        # STEP 1: DAPATKAN SALDO AWAL seperti di PHP
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
        
        # STEP 2: CHECK PRODUK TERAKHIR seperti di PHP
        await safe_edit_message_text(
            update,
            f"🔍 *MEMERIKSA KETERSEDIAAN PRODUK*...\n\n"
            f"📦 {product_data['name']}\n"
            f"📮 Tujuan: `{target}`\n\n"
            f"Mohon tunggu...",
            parse_mode="Markdown"
        )
        
        final_product_check = get_product_by_code_direct(product_data['code'])
        if not final_product_check:
            await safe_edit_message_text(
                update,
                f"❌ *PRODUK TIDAK TERSEDIA*\n\n"
                f"📦 {product_data['name']}\n\n"
                f"Produk tidak ditemukan atau sedang tidak aktif.\n"
                f"Silakan pilih produk lain.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"order_group_{product_data['category']}")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ]),
                parse_mode="Markdown"
            )
            return CHOOSING_PRODUCT
        
        if final_product_check.get('kosong') == 1:
            await safe_edit_message_text(
                update,
                f"❌ *PRODUK KOSONG*\n\n"
                f"📦 {product_data['name']}\n\n"
                f"Produk sedang kosong/tidak tersedia di provider.\n"
                f"Silakan pilih produk lain.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"order_group_{product_data['category']}")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ]),
                parse_mode="Markdown"
            )
            return CHOOSING_PRODUCT
        
        if final_product_check.get('gangguan') == 1:
            await safe_edit_message_text(
                update,
                f"🚧 *PRODUK GANGGUAN*\n\n"
                f"📦 {product_data['name']}\n\n"
                f"Produk sedang mengalami gangguan di provider.\n"
                f"Silakan pilih produk lain atau coba lagi nanti.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Produk", callback_data=f"order_group_{product_data['category']}")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ]),
                parse_mode="Markdown"
            )
            return CHOOSING_PRODUCT
        
        # STEP 3: POTONG SALDO seperti di PHP
        potong_saldo_success = update_user_saldo(user_id, -product_price, "Pembelian produk")
        if not potong_saldo_success:
            await safe_edit_message_text(
                update,
                "❌ Gagal memotong saldo. Silakan coba lagi.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
            )
            return ConversationHandler.END
        
        # STEP 4: KIRIM KE PROVIDER seperti di PHP
        await safe_edit_message_text(
            update,
            f"🔄 *MENGIRIM ORDER KE PROVIDER*...\n\n"
            f"📦 {product_data['name']}\n"
            f"📮 Tujuan: `{target}`\n"
            f"💰 Rp {product_price:,}\n\n"
            f"Mohon tunggu...",
            parse_mode="Markdown"
        )
        
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            # Refund saldo karena error sistem
            update_user_saldo(user_id, product_price, "Refund: API key tidak terkonfigurasi")
            await safe_edit_message_text(
                update,
                "❌ Error: API key tidak terkonfigurasi. Saldo telah dikembalikan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
            )
            return ConversationHandler.END
        
        khfy_api = KhfyPayAPI(api_key)
        
        # BUAT REFF_ID UNIK seperti di PHP
        reffid = f"akrab_{uuid.uuid4().hex[:16]}"
        
        # KIRIM KE API seperti di PHP
        order_result = khfy_api.create_order(
            product_code=product_data['code'],
            target=target,
            custom_reffid=reffid
        )
        
        # STEP 5: HANDLE RESPONSE seperti di PHP
        status_api = "PROSES"
        keterangan = "Order terkirim, menunggu update provider"
        final_status = "pending"
        
        if order_result and isinstance(order_result, dict):
            status_api = order_result.get('status_api', order_result.get('status', 'PROSES')).upper()
            keterangan = order_result.get('keterangan', order_result.get('message', keterangan))
            final_status = order_result.get('final_status', 'pending')
        
        # STEP 6: SIMPAN RIWAYAT seperti di PHP
        order_id = save_order(
            user_id=user_id,
            product_name=product_data['name'],
            product_code=product_data['code'],
            customer_input=target,
            price=product_price,
            status=final_status,
            provider_order_id=reffid,
            sn='',
            note=keterangan
        )
        
        if not order_id:
            # Refund saldo karena gagal save order
            update_user_saldo(user_id, product_price, "Refund: Gagal menyimpan order")
            await safe_edit_message_text(
                update,
                "❌ Gagal menyimpan order. Saldo telah dikembalikan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
            )
            return ConversationHandler.END
        
        # STEP 7: AUTO REFUND untuk yang langsung gagal seperti di PHP
        if final_status == 'failed':
            update_user_saldo(user_id, product_price, f"Refund: Order gagal - {keterangan}")
        
        # STEP 8: TAMPILKAN HASIL seperti di PHP
        saldo_akhir = get_user_saldo(user_id)
        
        # Tentukan status display seperti di PHP
        if status_api in ['SUKSES', 'SUCCESS']:
            status_display = "✅ SUKSES"
            status_emoji = "✅"
            color = "🟢"
        elif status_api in ['GAGAL', 'FAILED']:
            status_display = "❌ GAGAL"
            status_emoji = "❌"
            color = "🔴"
        else:
            status_display = "⏳ PROSES"
            status_emoji = "⏳"
            color = "🟡"
        
        success_message = (
            f"{status_emoji} *ORDER DIPROSES*\n\n"
            f"📦 *Produk:* {product_data['name']}\n"
            f"📮 *Tujuan:* `{target}`\n"
            f"💰 *Harga:* Rp {product_price:,}\n"
            f"🔗 *Ref ID:* `{reffid}`\n"
            f"📊 *Status:* {status_display} {color}\n"
            f"💬 *Pesan:* {keterangan}\n"
            f"💰 *Saldo Awal:* Rp {saldo_awal:,}\n"
            f"💰 *Saldo Akhir:* Rp {saldo_akhir:,}\n"
            f"⏰ *Waktu:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
        
        if final_status == 'failed':
            success_message += "✅ *Saldo telah dikembalikan* ke akun Anda.\n"
        
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
            update_user_saldo(user_id, product_price, f"Refund: Error sistem - {str(e)}")
        except:
            pass
            
        await safe_edit_message_text(
            update,
            f"❌ Terjadi error tidak terduga:\n{str(e)}\n\n"
            f"Saldo telah dikembalikan ke akun Anda.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
        )
        return ConversationHandler.END

# ==================== WEBHOOK HANDLER - IMPROVED ====================

def handle_webhook_callback(message):
    """Handle webhook callback dari KhfyPay - IMPROVED dengan pattern PHP"""
    try:
        # Regex pattern dari PHP yang sudah fix
        pattern = r'RC=(?P<reffid>[a-z0-9_.-]+)\s+TrxID=(?P<trxid>\d+)\s+(?P<produk>[A-Z0-9]+)\.(?P<tujuan>\d+)\s+(?P<status_text>[A-Za-z]+)[, ]*(?P<keterangan>.+?)Saldo[\s\S]*?result=(?P<status_code>\d+)'
        
        match = re.match(pattern, message, re.IGNORECASE)
        if not match:
            logger.error(f"Webhook format tidak dikenali: {message}")
            return False
        
        groups = match.groupdict()
        reffid = groups.get('reffid')
        status_text = groups.get('status_text', '').lower()
        status_code = groups.get('status_code')
        keterangan = groups.get('keterangan', '').strip()
        
        # Determine final status seperti di PHP
        if status_code == '0' or 'sukses' in status_text:
            final_status = 'completed'
        elif status_code == '1' or 'gagal' in status_text or 'batal' in status_text:
            final_status = 'failed'
        else:
            final_status = 'pending'
        
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
        
        if final_status == 'completed':
            # Update jadi completed
            update_order_status(order_id, final_status, note=f"Webhook: {keterangan}")
            logger.info(f"Webhook: Order {order_id} completed")
        else:
            # REFUND otomatis untuk yang gagal
            update_order_status(order_id, final_status, note=f"Webhook Gagal: {keterangan}")
            update_user_saldo(user_id, price, f"Refund: Order gagal via webhook - {keterangan}")
            logger.info(f"Webhook: Order {order_id} failed - refund processed")
        
        return True
        
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        return False

# ==================== FUNGSI YANG TETAP SAMA ====================

# Semua fungsi lainnya TETAP SAMA seperti code ORI Anda:

def sync_product_stock_from_provider():
    """Sinkronisasi stok produk dari provider KhfyPay"""
    # ... (tetap sama seperti code ORI)

def get_product_stock_status(stock, gangguan, kosong):
    """Get stock status dengan tampilan yang informatif"""
    # ... (tetap sama seperti code ORI)

def update_product_stock_after_order(product_code, quantity=1):
    """Update stok produk setelah order berhasil"""
    # ... (tetap sama seperti code ORI)

def process_refund(order_id, user_id, amount, reason="Order gagal"):
    """Process refund untuk order yang gagal"""
    # ... (tetap sama seperti code ORI)

async def safe_edit_message_text(update, text, *args, **kwargs):
    """Safely edit message text with error handling"""
    # ... (tetap sama seperti code ORI)

async def safe_reply_message(update, text, *args, **kwargs):
    """Safely reply to message with error handling"""
    # ... (tetap sama seperti code ORI)

def validate_phone_number(phone):
    """Validate phone number format"""
    # ... (tetap sama seperti code ORI)

def validate_pulsa_target(phone, product_code):
    """Validate pulsa target"""
    # ... (tetap sama seperti code ORI)

def get_grouped_products_with_stock():
    """Get products grouped by category from database dengan tampilan stok"""
    # ... (tetap sama seperti code ORI)

def get_product_by_code_with_stock(product_code):
    """Get product details by code dengan info stok ter-update"""
    # ... (tetap sama seperti code ORI)

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main menu handler untuk order"""
    # ... (tetap sama seperti code ORI)

async def show_group_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show product groups menu dengan info stok"""
    # ... (tetap sama seperti code ORI)

async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show products in selected group dengan tampilan stok detail"""
    # ... (tetap sama seperti code ORI)

async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product pagination"""
    # ... (tetap sama seperti code ORI)

async def back_to_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kembali ke menu grup produk"""
    # ... (tetap sama seperti code ORI)

async def select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product selection dengan info stok detail"""
    # ... (tetap sama seperti code ORI)

async def receive_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and validate target input"""
    # ... (tetap sama seperti code ORI)

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel order and return to product selection"""
    # ... (tetap sama seperti code ORI)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the entire order conversation"""
    # ... (tetap sama seperti code ORI)

def get_conversation_handler():
    """Get order conversation handler untuk didaftarkan di main.py"""
    # ... (tetap sama seperti code ORI)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the order handler"""
    # ... (tetap sama seperti code ORI)

async def periodic_stock_sync_task(context: ContextTypes.DEFAULT_TYPE):
    """Periodic task untuk sync stok dari provider"""
    # ... (tetap sama seperti code ORI)
