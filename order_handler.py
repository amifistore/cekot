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
    """Show product groups menu from database"""
    try:
        if hasattr(update, 'callback_query'):
            query = update.callback_query
            await query.answer()
        else:
            query = None
        
        logger.info("Loading product groups from database...")
        groups = get_grouped_products()
        
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
    """Show products in selected group"""
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        group_name = data.replace('order_group_', '')
        
        groups = get_grouped_products()
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
    """Handle product selection"""
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        product_code = data.replace('order_product_', '')
        
        product = get_product_by_code(product_code)
        if not product:
            await safe_edit_message_text(
                update,
                "❌ Produk tidak ditemukan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
            )
            return ConversationHandler.END
        
        # Check product availability
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
    """Process order confirmation"""
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
        
        # Create order in provider system
        await safe_edit_message_text(
            update,
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
                update,
                "❌ Gagal membuat order di sistem provider. Silakan coba lagi.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
            )
            return ConversationHandler.END
        
        # Check order result
        if order_result.get('status') == 'error':
            error_msg = order_result.get('message', 'Unknown error')
            await safe_edit_message_text(
                update,
                f"❌ Gagal membuat order:\n{error_msg}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
            )
            return ConversationHandler.END
        
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
                update,
                "❌ Gagal menyimpan order. Saldo telah dikembalikan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]])
            )
            return ConversationHandler.END
        
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
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error processing order: {e}")
        await safe_edit_message_text(
            update,
            f"❌ Terjadi error saat memproses order:\n{str(e)}",
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
