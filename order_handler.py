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

# ==================== KHFYPAY API INTEGRATION - IMPROVED ====================

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
            
            # IMPROVED: Handle response seperti di PHP
            status_api = "PROSES"
            keterangan = "Order terkirim, menunggu update provider"
            
            if result and isinstance(result, dict):
                status_api = strtoupper(result.get('status', 'PROSES'))
                keterangan = result.get('msg', keterangan)
            
            result['reffid'] = reffid
            result['status_api'] = status_api
            result['keterangan'] = keterangan
            
            return result
            
        except requests.exceptions.Timeout:
            logger.error(f"Timeout creating order for {product_code}")
            return {"status": "error", "message": "Timeout - Silakan cek status manual", "status_api": "GAGAL"}
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error creating order: {e}")
            return {"status": "error", "message": f"Network error: {str(e)}", "status_api": "GAGAL"}
        except Exception as e:
            logger.error(f"Error creating KhfyPay order: {e}")
            return {"status": "error", "message": f"System error: {str(e)}", "status_api": "GAGAL"}
    
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

# ==================== DATABASE COMPATIBILITY - IMPROVED ====================

def strtoupper(text):
    """PHP strtoupper equivalent"""
    return text.upper() if text else ""

def get_user_saldo(user_id):
    """Fixed compatibility function for user balance - IMPROVED"""
    try:
        # Coba beberapa kemungkinan nama fungsi
        if hasattr(database, 'get_user_balance'):
            return database.get_user_balance(user_id)
        elif hasattr(database, 'get_user_saldo'):
            return database.get_user_saldo(user_id)
        else:
            # FALLBACK: Direct database query seperti di PHP
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            
            # Coba tabel users dengan struktur seperti PHP
            cursor.execute("SELECT balance FROM users WHERE user_id = ? OR username = ?", (user_id, user_id))
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        return 0

def update_user_saldo(user_id, amount, note="", transaction_type="order"):
    """Fixed compatibility function for update balance - IMPROVED"""
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
            # FALLBACK: Direct database update seperti di PHP
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ? OR username = ?", 
                         (amount, user_id, user_id))
            success = cursor.rowcount > 0
            conn.commit()
            conn.close()
            return success
    except Exception as e:
        logger.error(f"Error updating user saldo: {e}")
        return False

def save_order(user_id, product_name, product_code, customer_input, price, 
               status='pending', provider_order_id='', sn='', note='', saldo_awal=0):
    """Fixed compatibility function for save order - IMPROVED seperti PHP"""
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
                note=note,
                saldo_awal=saldo_awal
            )
        else:
            # FALLBACK: Direct database insert seperti di PHP
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            
            # Cek struktur tabel (riwayat_pembelian seperti di PHP atau orders)
            try:
                # Coba tabel riwayat_pembelian seperti PHP
                cursor.execute('''
                    INSERT INTO riwayat_pembelian 
                    (username, kode_produk, nama_produk, tujuan, harga, saldo_awal, reff_id, status_api, keterangan, waktu) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, product_code, product_name, customer_input, price, 
                      saldo_awal, provider_order_id, status, note, datetime.now()))
            except sqlite3.OperationalError:
                # Fallback ke tabel orders
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
    """Fixed compatibility function for update order status - IMPROVED"""
    try:
        if hasattr(database, 'update_order_status'):
            return database.update_order_status(order_id, status, sn, note)
        else:
            # FALLBACK: Direct database update
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            
            # Cek struktur tabel
            try:
                # Coba update riwayat_pembelian seperti PHP
                cursor.execute('''
                    UPDATE riwayat_pembelian SET status_api = ?, keterangan = ?, waktu = ?
                    WHERE id = ?
                ''', (status, note, datetime.now(), order_id))
            except sqlite3.OperationalError:
                # Fallback ke tabel orders
                cursor.execute('''
                    UPDATE orders SET status = ?, sn = ?, note = ?, updated_at = ?
                    WHERE id = ?
                ''', (status, sn, note, datetime.now(), order_id))
            
            success = cursor.rowcount > 0
            conn.commit()
            conn.close()
            return success
    except Exception as e:
        logger.error(f"Error updating order status: {e}")
        return False

def get_product_by_code_direct(product_code):
    """Direct database product query - IMPROVED seperti PHP"""
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        # Coba tabel akrabv3 seperti di PHP
        try:
            cursor.execute("""
                SELECT kode_produk, nama_produk, harga_final, kategori, deskripsi, kosong, gangguan 
                FROM akrabv3 WHERE kode_produk = ? AND kosong = 0 AND gangguan = 0 LIMIT 1
            """, (product_code,))
        except sqlite3.OperationalError:
            # Fallback ke tabel products
            cursor.execute("""
                SELECT code, name, price, category, description, kosong, gangguan, stock 
                FROM products WHERE code = ? AND (kosong = 0 OR kosong IS NULL) AND (gangguan = 0 OR gangguan IS NULL) LIMIT 1
            """, (product_code,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # Handle both table structures
            if len(row) >= 7:  # akrabv3 structure
                return {
                    'code': row[0],
                    'name': row[1],
                    'price': row[2],
                    'category': row[3],
                    'description': row[4],
                    'kosong': row[5],
                    'gangguan': row[6],
                    'stock': 100  # Default stock untuk produk aktif
                }
            else:  # products structure
                return {
                    'code': row[0],
                    'name': row[1],
                    'price': row[2],
                    'category': row[3],
                    'description': row[4],
                    'kosong': row[5] or 0,
                    'gangguan': row[6] or 0,
                    'stock': row[7] if len(row) > 7 else 100
                }
        return None
        
    except Exception as e:
        logger.error(f"Error in get_product_by_code_direct: {e}")
        return None

# ==================== TRANSACTION HANDLING - NEW LIKE PHP ====================

def begin_transaction():
    """Begin database transaction seperti di PHP"""
    try:
        conn = sqlite3.connect('bot_database.db')
        conn.execute("BEGIN TRANSACTION")
        return conn
    except Exception as e:
        logger.error(f"Error beginning transaction: {e}")
        return None

def commit_transaction(conn):
    """Commit transaction seperti di PHP"""
    try:
        if conn:
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        logger.error(f"Error committing transaction: {e}")
        return False

def rollback_transaction(conn):
    """Rollback transaction seperti di PHP"""
    try:
        if conn:
            conn.rollback()
            conn.close()
            return True
    except Exception as e:
        logger.error(f"Error rolling back transaction: {e}")
        return False

# ==================== ORDER PROCESSING - IMPROVED LIKE PHP ====================

async def process_order_improved(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """PROSES ORDER YANG DISEMPURNAKAN seperti kode PHP"""
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
    
    # Initialize transaction seperti di PHP
    db_conn = begin_transaction()
    if not db_conn:
        await safe_edit_message_text(
            update,
            "❌ Error sistem database. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
        )
        return ConversationHandler.END
    
    try:
        user_id = str(query.from_user.id)
        product_price = product_data['price']
        product_code = product_data['code']
        
        # STEP 1: DAPATKAN SALDO AWAL seperti di PHP
        saldo_awal = get_user_saldo(user_id)
        
        if saldo_awal < product_price:
            rollback_transaction(db_conn)
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
        
        final_product_check = get_product_by_code_direct(product_code)
        if not final_product_check:
            rollback_transaction(db_conn)
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
            rollback_transaction(db_conn)
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
            rollback_transaction(db_conn)
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
            rollback_transaction(db_conn)
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
            rollback_transaction(db_conn)
            # Refund saldo karena error sistem
            update_user_saldo(user_id, product_price, "Refund: API key tidak terkonfigurasi")
            commit_transaction(db_conn)
            
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
            product_code=product_code,
            target=target,
            custom_reffid=reffid
        )
        
        # STEP 5: HANDLE RESPONSE seperti di PHP
        status_api = "PROSES"
        keterangan = "Order terkirim, menunggu update provider"
        
        if order_result and isinstance(order_result, dict):
            status_api = strtoupper(order_result.get('status_api', order_result.get('status', 'PROSES')))
            keterangan = order_result.get('keterangan', order_result.get('message', keterangan))
        
        # STEP 6: SIMPAN RIWAYAT seperti di PHP
        order_id = save_order(
            user_id=user_id,
            product_name=product_data['name'],
            product_code=product_code,
            customer_input=target,
            price=product_price,
            status='processing',  # Default status
            provider_order_id=reffid,
            sn='',
            note=keterangan,
            saldo_awal=saldo_awal  # RECORD SALDO AWAL seperti di PHP
        )
        
        if not order_id:
            rollback_transaction(db_conn)
            # Refund saldo karena gagal save order
            update_user_saldo(user_id, product_price, "Refund: Gagal menyimpan order")
            
            await safe_edit_message_text(
                update,
                "❌ Gagal menyimpan order. Saldo telah dikembalikan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
            )
            return ConversationHandler.END
        
        # STEP 7: UPDATE STATUS BERDASARKAN RESPONSE seperti di PHP
        final_status = 'pending'
        if status_api == 'SUKSES' or status_api == 'SUCCESS':
            final_status = 'completed'
        elif status_api == 'GAGAL' or status_api == 'FAILED':
            final_status = 'failed'
            # AUTO REFUND untuk yang langsung gagal
            update_user_saldo(user_id, product_price, f"Refund: Order gagal - {keterangan}")
        
        update_order_status(order_id, final_status, note=keterangan)
        
        # STEP 8: COMMIT TRANSACTION seperti di PHP
        if not commit_transaction(db_conn):
            await safe_edit_message_text(
                update,
                "❌ Error commit transaction. Silakan cek status order.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
            )
            return ConversationHandler.END
        
        # STEP 9: TAMPILKAN HASIL seperti di PHP
        saldo_akhir = get_user_saldo(user_id)
        
        # Tentukan redirect status seperti di PHP
        if status_api == 'SUKSES' or status_api == 'SUCCESS':
            status_display = "✅ SUKSES"
            status_emoji = "✅"
            color = "🟢"
        elif status_api == 'GAGAL' or status_api == 'FAILED':
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
        
        # SAFETY ROLLBACK seperti di PHP
        rollback_transaction(db_conn)
        
        # Safety refund jika error tidak terduga
        try:
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

# ==================== REPLACE THE OLD process_order FUNCTION ====================

# Ganti function process_order yang lama dengan yang baru
async def process_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alias untuk process_order_improved"""
    return await process_order_improved(update, context)

# ==================== WEBHOOK HANDLER - IMPROVED ====================

def handle_webhook_callback(message):
    """Handle webhook callback dari KhfyPay - IMPROVED"""
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
        product_code = groups.get('produk')
        keterangan = groups.get('keterangan', '').strip()
        
        # Determine final status seperti di PHP
        is_success = False
        if status_code == '0' or 'sukses' in status_text:
            is_success = True
            final_status = 'completed'
        elif status_code == '1' or 'gagal' in status_text or 'batal' in status_text:
            is_success = False
            final_status = 'failed'
        else:
            final_status = 'pending'
        
        # Cari order di database
        try:
            order = get_order_by_reffid_direct(reffid)
        except Exception as db_error:
            logger.error(f"Error finding order in database: {db_error}")
            order = None
        
        if not order:
            logger.warning(f"Order tidak ditemukan untuk reffid: {reffid}")
            return False
        
        order_id = order['id']
        user_id = order['user_id']
        price = order['price']
        
        # Begin transaction untuk webhook processing
        db_conn = begin_transaction()
        
        try:
            if is_success:
                # Update jadi completed
                update_order_status(order_id, final_status, note=f"Webhook: {keterangan}")
                logger.info(f"Webhook: Order {order_id} completed")
            else:
                # REFUND otomatis untuk yang gagal
                update_order_status(order_id, final_status, note=f"Webhook Gagal: {keterangan}")
                update_user_saldo(user_id, price, f"Refund: Order gagal via webhook - {keterangan}")
                logger.info(f"Webhook: Order {order_id} failed - refund processed")
            
            # Commit transaction
            if db_conn:
                commit_transaction(db_conn)
            
            return True
            
        except Exception as e:
            if db_conn:
                rollback_transaction(db_conn)
            logger.error(f"Error in webhook transaction: {e}")
            return False
        
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        return False

def get_order_by_reffid_direct(reffid):
    """Direct database query untuk cari order by reffid"""
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        # Coba berbagai kemungkinan tabel dan kolom
        try:
            # Coba tabel riwayat_pembelian seperti PHP
            cursor.execute("SELECT id, username, harga FROM riwayat_pembelian WHERE reff_id = ?", (reffid,))
        except sqlite3.OperationalError:
            # Coba tabel orders
            cursor.execute("SELECT id, user_id, price FROM orders WHERE provider_order_id = ?", (reffid,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            if len(row) >= 3:
                return {
                    'id': row[0],
                    'user_id': row[1],
                    'price': row[2]
                }
        return None
        
    except Exception as e:
        logger.error(f"Error in get_order_by_reffid_direct: {e}")
        return None

# ==================== KEEP EXISTING FUNCTIONS (tidak diubah) ====================

# Fungsi-fungsi berikut TETAP sama seperti sebelumnya:
# - sync_product_stock_from_provider()
# - get_product_stock_status()
# - update_product_stock_after_order()
# - process_refund()
# - safe_edit_message_text()
# - safe_reply_message()
# - validate_phone_number()
# - validate_pulsa_target()
# - get_grouped_products_with_stock()
# - get_product_by_code_with_stock()
# - menu_handler()
# - show_group_menu()
# - show_products()
# - handle_pagination()
# - back_to_groups()
# - select_product()
# - receive_target()
# - cancel_order()
# - cancel_conversation()
# - get_conversation_handler()
# - error_handler()
# - periodic_stock_sync_task()

# ... (semua fungsi lainnya tetap sama seperti code awal Anda)

# ==================== UPDATE CONVERSATION HANDLER ====================

# Pastikan conversation handler menggunakan function yang sudah diimprove
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
                CallbackQueryHandler(process_order, pattern="^order_confirm$"),  # NOW USING IMPROVED VERSION
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
