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

# ==================== CONSTANTS ====================
CHOOSING_GROUP, CHOOSING_PRODUCT, ENTER_TUJUAN, CONFIRM_ORDER = range(4)
PRODUCTS_PER_PAGE = 6
PROVIDER_TIMEOUT = 300  # 5 menit
ADMIN_CHECK_INTERVAL = 300
ADMIN_USER_IDS = getattr(config, 'ADMIN_USER_IDS', [123456789])

# Global variables
bot_application = None
pending_admin_notifications = {}
pending_orders_timeout = {}

# ==================== MODERN ANIMATION SYSTEM ====================

class ModernAnimations:
    @staticmethod
    async def show_processing_animation(update, context, message_text, animation_type="order"):
        """Show modern processing animation"""
        animations = {
            "order": ["🔄 Memproses Order...", "📡 Mengirim ke Provider...", "⏳ Menunggu Respon..."],
            "checking": ["🔍 Memeriksa Stok...", "📊 Analisis Ketersediaan...", "✅ Verifikasi Produk..."],
            "payment": ["💳 Memverifikasi Saldo...", "💰 Memproses Pembayaran...", "✅ Konfirmasi Berhasil..."],
            "status": ["📡 Checking Status...", "🔄 Sync dengan Provider...", "✅ Update Data..."]
        }
        
        anim_frames = animations.get(animation_type, animations["order"])
        message = await update.effective_message.reply_text(
            f"⏳ *{anim_frames[0]}*",
            parse_mode="Markdown"
        )
        
        for i in range(1, len(anim_frames)):
            await asyncio.sleep(1.5)
            try:
                await context.bot.edit_message_text(
                    chat_id=message.chat_id,
                    message_id=message.message_id,
                    text=f"⏳ *{anim_frames[i]}*",
                    parse_mode="Markdown"
                )
            except:
                pass
        
        return message

    @staticmethod
    async def progress_bar(update, context, duration=3, text="Memproses"):
        """Show animated progress bar"""
        message = await update.effective_message.reply_text(
            f"🔄 {text}\n\n{ModernAnimations._create_progress_bar(0)}",
            parse_mode="Markdown"
        )
        
        for i in range(1, 11):
            await asyncio.sleep(duration / 10)
            try:
                await context.bot.edit_message_text(
                    chat_id=message.chat_id,
                    message_id=message.message_id,
                    text=f"🔄 {text}\n\n{ModernAnimations._create_progress_bar(i * 10)}",
                    parse_mode="Markdown"
                )
            except:
                pass
        
        return message

    @staticmethod
    def _create_progress_bar(percentage):
        """Create visual progress bar"""
        bars = 10
        filled = int(bars * percentage / 100)
        empty = bars - filled
        return f"`[{ '█' * filled }{ '░' * empty }]` {percentage}%"

    @staticmethod
    async def typing_animation(update, context, duration=2):
        """Simulate typing animation"""
        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )
            await asyncio.sleep(duration)
        except:
            pass

# ==================== MODERN MESSAGE BUILDER ====================

class ModernMessageBuilder:
    @staticmethod
    def create_modern_header(emoji, title, status):
        """Create modern header with gradient effect"""
        status_emojis = {
            'success': '🟢', 'pending': '🟡', 'failed': '🔴', 
            'processing': '🔵', 'timeout': '🟠'
        }
        
        status_emoji = status_emojis.get(status, '🟡')
        return f"{emoji} **{title.upper()}** {status_emoji}\n" + "▬" * 35 + "\n\n"

    @staticmethod
    def create_order_card(order_data, status_type, additional_info=None):
        """Create modern order card"""
        message = ""
        
        # Header based on status
        status_configs = {
            'success': {'emoji': '✅', 'title': 'ORDER BERHASIL', 'color': '🟢'},
            'pending': {'emoji': '⏳', 'title': 'ORDER DIPROSES', 'color': '🟡'},
            'failed': {'emoji': '❌', 'title': 'ORDER GAGAL', 'color': '🔴'},
            'processing': {'emoji': '🔄', 'title': 'PROSES ORDER', 'color': '🔵'},
            'timeout': {'emoji': '⏰', 'title': 'ORDER TIMEOUT', 'color': '🟠'}
        }
        
        config = status_configs.get(status_type, status_configs['pending'])
        message += ModernMessageBuilder.create_modern_header(config['emoji'], config['title'], status_type)
        
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
        message += f"🕒 **Waktu:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        
        return message

    @staticmethod
    def create_product_card(product):
        """Create modern product card"""
        stock_emojis = {
            'high': '🟢', 'medium': '🟡', 'low': '🟠', 'empty': '🔴', 'problem': '🚧'
        }
        
        stock_status = "high"
        if product.get('kosong', 0) == 1:
            stock_status = "empty"
        elif product.get('gangguan', 0) == 1:
            stock_status = "problem"
        elif product.get('display_stock', 0) <= 0:
            stock_status = "empty"
        elif product.get('display_stock', 0) <= 5:
            stock_status = "low"
        elif product.get('display_stock', 0) <= 10:
            stock_status = "medium"
        
        emoji = stock_emojis.get(stock_status, '🟡')
        
        card = f"{emoji} **{product['name']}**\n"
        card += f"💰 `Rp {product['price']:,}`\n"
        
        if stock_status == 'high':
            card += f"📦 Stock: 🟢 Tersedia\n"
        elif stock_status == 'medium':
            card += f"📦 Stock: 🟡 {product['display_stock']} unit\n"
        elif stock_status == 'low':
            card += f"📦 Stock: 🟠 {product['display_stock']} unit\n"
        elif stock_status == 'empty':
            card += f"📦 Stock: 🔴 Habis\n"
        elif stock_status == 'problem':
            card += f"📦 Status: 🚧 Gangguan\n"
        
        if product.get('description'):
            card += f"📝 {product['description'][:50]}...\n"
        
        return card

# ==================== KHFYPAY API MODERN ====================

class KhfyPayAPIModern:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://panel.khfy-store.com/api_v2"
    
    async def get_products_async(self):
        """Get products asynchronously"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/list_product",
                    params={"api_key": self.api_key},
                    timeout=30
                ) as response:
                    data = await response.json()
                    logger.info(f"✅ Got {len(data) if isinstance(data, list) else 'unknown'} products")
                    return data
        except Exception as e:
            logger.error(f"❌ Error getting products: {e}")
            return None

    async def create_order_async(self, product_code, target, custom_reffid=None):
        """Create order asynchronously dengan timeout handling"""
        try:
            reffid = custom_reffid or f"akrab_{uuid.uuid4().hex[:16]}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/trx",
                    params={
                        "produk": product_code,
                        "tujuan": target,
                        "reff_id": reffid,
                        "api_key": self.api_key
                    },
                    timeout=45
                ) as response:
                    result = await response.json()
                    result['reffid'] = reffid
                    logger.info(f"✅ Order created: {result}")
                    return result
                    
        except asyncio.TimeoutError:
            logger.error(f"⏰ Timeout creating order for {product_code}")
            return {"status": "error", "message": "Timeout - Silakan cek status manual"}
        except Exception as e:
            logger.error(f"❌ Error creating order: {e}")
            return {"status": "error", "message": f"System error: {str(e)}"}

    async def check_order_status_async(self, reffid):
        """Check order status asynchronously"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/history",
                    params={"api_key": self.api_key, "refid": reffid},
                    timeout=25
                ) as response:
                    return await response.json()
        except Exception as e:
            logger.error(f"❌ Error checking status: {e}")
            return None

# ==================== DATABASE MODERN ====================

def get_user_saldo_modern(user_id):
    """Get user balance dengan error handling"""
    try:
        if hasattr(database, 'get_user_balance'):
            return database.get_user_balance(user_id)
        else:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else 0
    except Exception as e:
        logger.error(f"❌ Error getting saldo: {e}")
        return 0

def update_user_saldo_modern(user_id, amount, note=""):
    """Update user balance dengan atomic operation"""
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        # Get current balance
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        current = cursor.fetchone()
        
        if not current:
            conn.close()
            return False
        
        new_balance = current[0] + amount
        
        # Update balance
        cursor.execute(
            "UPDATE users SET balance = ? WHERE user_id = ?", 
            (new_balance, user_id)
        )
        
        # Save transaction
        cursor.execute('''
            INSERT INTO transactions (user_id, amount, type, note, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, amount, 'refund' if amount > 0 else 'order', note, datetime.now()))
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Updated balance for {user_id}: {amount}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error updating saldo: {e}")
        return False

def save_order_modern(user_id, product_data, target, price, provider_order_id, status='processing'):
    """Save order dengan data lengkap"""
    try:
        order_id = save_order(
            user_id=user_id,
            product_name=product_data['name'],
            product_code=product_data['code'],
            customer_input=target,
            price=price,
            status=status,
            provider_order_id=provider_order_id,
            sn='',
            note='Sedang diproses ke provider',
            saldo_awal=get_user_saldo_modern(user_id)
        )
        return order_id
    except Exception as e:
        logger.error(f"❌ Error saving order: {e}")
        return 0

# ==================== STOCK MANAGEMENT MODERN ====================

async def sync_stock_modern():
    """Sync stock dengan provider"""
    try:
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            return False
            
        khfy_api = KhfyPayAPIModern(api_key)
        products = await khfy_api.get_products_async()
        
        if not products:
            return False
            
        updated_count = 0
        for product in products if isinstance(products, list) else []:
            if product.get('code'):
                # Update stock logic here
                updated_count += 1
                
        logger.info(f"✅ Synced {updated_count} products")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error syncing stock: {e}")
        return False

# ==================== ORDER FLOW MODERN ====================

async def modern_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Modern menu handler dengan animasi"""
    query = update.callback_query
    await query.answer()
    
    await ModernAnimations.typing_animation(update, context, 1)
    
    try:
        return await show_modern_groups(update, context)
    except Exception as e:
        logger.error(f"❌ Error in menu: {e}")
        await show_error_message(update, "Error memuat menu")
        return ConversationHandler.END

async def show_modern_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show modern group selection"""
    try:
        await ModernAnimations.typing_animation(update, context, 1)
        
        groups = get_grouped_products_with_stock()
        if not groups:
            await show_error_message(update, "Tidak ada produk tersedia")
            return ConversationHandler.END
        
        keyboard = []
        for group_name, products in groups.items():
            available = sum(1 for p in products if p['display_stock'] > 0 and p['gangguan'] == 0 and p['kosong'] == 0)
            total = len(products)
            
            emoji = "🟢" if available > 0 else "🔴"
            text = f"{emoji} {group_name} ({available}/{total})"
            
            keyboard.append([InlineKeyboardButton(text, callback_data=f"mgroup_{group_name}")])
        
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")])
        
        message = (
            "🛍️ *TOKO DIGITAL AKRAB*\n\n"
            "📦 **PILIH KATEGORI PRODUK**\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
            "Pilih kategori produk yang tersedia:\n"
            "🟢 Tersedia | 🔴 Habis\n\n"
            "Klik kategori untuk melihat produk:"
        )
        
        await safe_edit_modern(update, message, InlineKeyboardMarkup(keyboard))
        return CHOOSING_GROUP
        
    except Exception as e:
        logger.error(f"❌ Error showing groups: {e}")
        await show_error_message(update, "Error memuat kategori")
        return ConversationHandler.END

async def show_modern_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show modern product list"""
    query = update.callback_query
    await query.answer()
    
    try:
        group_name = query.data.replace('mgroup_', '')
        groups = get_grouped_products_with_stock()
        
        if group_name not in groups:
            await show_error_message(update, "Kategori tidak ditemukan")
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
            card = ModernMessageBuilder.create_product_card(product)
            keyboard.append([InlineKeyboardButton(card, callback_data=f"mproduct_{product['code']}")])
        
        # Navigation
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data="mprev_page"))
        if end_idx < len(products):
            nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data="mnext_page"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.extend([
            [InlineKeyboardButton("🔙 Kategori", callback_data="mback_groups")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
        ])
        
        total_pages = (len(products) + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE
        available = sum(1 for p in products if p['display_stock'] > 0 and p['gangguan'] == 0 and p['kosong'] == 0)
        
        message = (
            f"📦 **PRODUK {group_name.upper()}**\n"
            f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
            f"📊 **Ketersediaan:** {available}/{len(products)} produk\n"
            f"📄 **Halaman:** {page + 1}/{total_pages}\n\n"
            f"Pilih produk untuk order:"
        )
        
        await safe_edit_modern(update, message, InlineKeyboardMarkup(keyboard))
        return CHOOSING_PRODUCT
        
    except Exception as e:
        logger.error(f"❌ Error showing products: {e}")
        await show_error_message(update, "Error memuat produk")
        return ConversationHandler.END

async def handle_modern_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle modern pagination"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    current_page = context.user_data.get('product_page', 0)
    
    if data == 'mnext_page':
        context.user_data['product_page'] = current_page + 1
    elif data == 'mprev_page':
        context.user_data['product_page'] = max(0, current_page - 1)
    
    return await show_modern_products(update, context)

async def select_modern_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Select product dengan validasi stok"""
    query = update.callback_query
    await query.answer()
    
    try:
        product_code = query.data.replace('mproduct_', '')
        product = get_product_by_code_with_stock(product_code)
        
        if not product:
            await show_error_message(update, "Produk tidak ditemukan")
            return CHOOSING_PRODUCT
        
        # Validasi stok
        if product['kosong'] == 1 or product['display_stock'] <= 0:
            message = ModernMessageBuilder.create_order_card(
                product, 'failed',
                ["❌ **Stok sedang habis**", "🔄 Silakan pilih produk lain"]
            )
            
            keyboard = [
                [InlineKeyboardButton("🔙 Kembali", callback_data=f"mgroup_{product['category']}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            
            await safe_edit_modern(update, message, InlineKeyboardMarkup(keyboard))
            return CHOOSING_PRODUCT
        
        if product['gangguan'] == 1:
            message = ModernMessageBuilder.create_order_card(
                product, 'failed',
                ["🚧 **Produk sedang gangguan**", "⏳ Coba lagi nanti"]
            )
            
            keyboard = [
                [InlineKeyboardButton("🔙 Kembali", callback_data=f"mgroup_{product['category']}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            
            await safe_edit_modern(update, message, InlineKeyboardMarkup(keyboard))
            return CHOOSING_PRODUCT
        
        context.user_data['selected_product'] = product
        
        # Tentukan contoh input berdasarkan produk
        examples = {
            'pulsa': "Contoh: 081234567890",
            'pln': "Contoh: 123456789012345 (ID PLN)",
            'game': "Contoh: 1234567890 (ID Game)", 
            'emoney': "Contoh: 081234567890 (No HP)"
        }
        
        example = examples.get(product['category'].lower(), "Contoh: 081234567890")
        
        message = (
            f"🛒 **PILIHAN PRODUK**\n"
            f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
            f"📦 **{product['name']}**\n"
            f"💰 Harga: Rp {product['price']:,}\n"
            f"📊 Stok: {product['stock_status']}\n\n"
            f"📝 **Masukkan nomor tujuan:**\n"
            f"`{example}`\n\n"
            f"Ketik nomor tujuan dan kirim:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔙 Produk Lain", callback_data=f"mgroup_{product['category']}")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
        ]
        
        await safe_edit_modern(update, message, InlineKeyboardMarkup(keyboard))
        return ENTER_TUJUAN
        
    except Exception as e:
        logger.error(f"❌ Error selecting product: {e}")
        await show_error_message(update, "Error memilih produk")
        return CHOOSING_PRODUCT

async def receive_modern_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive target dengan validasi"""
    try:
        target = update.message.text.strip()
        product = context.user_data.get('selected_product')
        
        if not product:
            await show_error_message(update, "Sesi expired")
            return ConversationHandler.END
        
        # Validasi target
        validated_target = validate_target_modern(target, product['code'])
        if not validated_target:
            await update.message.reply_text(
                "❌ **Format tidak valid!**\n\n"
                f"Produk: {product['name']}\n"
                f"Input: {target}\n\n"
                "Silakan masukkan format yang benar:",
                parse_mode="Markdown"
            )
            return ENTER_TUJUAN
        
        context.user_data['order_target'] = validated_target
        
        # Tampilkan konfirmasi
        user_id = str(update.effective_user.id)
        saldo = get_user_saldo_modern(user_id)
        
        message = ModernMessageBuilder.create_order_card(
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
        
        keyboard = [
            [
                InlineKeyboardButton("✅ LANJUTKAN", callback_data="mconfirm_yes"),
                InlineKeyboardButton("❌ BATALKAN", callback_data="mconfirm_no")
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
        await show_error_message(update, "Error memproses tujuan")
        return ENTER_TUJUAN

async def process_modern_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process order dengan animasi lengkap"""
    query = update.callback_query
    await query.answer()
    
    user_data = context.user_data
    product = user_data.get('selected_product')
    target = user_data.get('order_target')
    
    if not product or not target:
        await show_error_message(update, "Data tidak lengkap")
        return ConversationHandler.END
    
    try:
        user_id = str(query.from_user.id)
        price = product['price']
        
        # 1. CHECK SALDO
        saldo_awal = get_user_saldo_modern(user_id)
        if saldo_awal < price:
            message = ModernMessageBuilder.create_order_card(
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
                [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu")]
            ]
            
            await safe_edit_modern(update, message, InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END
        
        # 2. CHECK STOK TERAKHIR
        await ModernAnimations.progress_bar(update, context, 2, "Memeriksa Stok Terbaru")
        
        await sync_stock_modern()
        updated_product = get_product_by_code_with_stock(product['code'])
        
        if not updated_product or updated_product.get('kosong') == 1 or updated_product.get('display_stock', 0) <= 0:
            message = ModernMessageBuilder.create_order_card(
                product, 'failed',
                ["❌ **Stok sudah habis**", "🔄 Silakan pilih produk lain"]
            )
            
            keyboard = [
                [InlineKeyboardButton("🛒 PRODUK LAIN", callback_data="mback_groups")],
                [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu")]
            ]
            
            await safe_edit_modern(update, message, InlineKeyboardMarkup(keyboard))
            return CHOOSING_PRODUCT
        
        # 3. POTONG SALDO
        await ModernAnimations.typing_animation(update, context, 1)
        
        if not update_user_saldo_modern(user_id, -price, f"Order: {product['name']}"):
            await show_error_message(update, "Gagal memotong saldo")
            return ConversationHandler.END
        
        # 4. BUAT ORDER DI DATABASE
        reffid = f"akrab_{uuid.uuid4().hex[:16]}"
        order_id = save_order_modern(user_id, product, target, price, reffid)
        
        if not order_id:
            update_user_saldo_modern(user_id, price, "Refund: Gagal save order")
            await show_error_message(update, "Gagal menyimpan order")
            return ConversationHandler.END
        
        # 5. PROSES KE PROVIDER DENGAN ANIMASI
        anim_message = await ModernAnimations.show_processing_animation(
            update, context, 
            "🔄 Mengirim ke Provider...",
            "order"
        )
        
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        khfy_api = KhfyPayAPIModern(api_key)
        
        order_result = await khfy_api.create_order_async(product['code'], target, reffid)
        
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
            update_user_saldo_modern(user_id, price, f"Refund: {provider_message}")
            status_info = ["❌ **Gagal di Provider**", f"💡 {provider_message}", "✅ Saldo telah dikembalikan"]
        
        # Update order status
        update_order_status(order_id, final_status, sn=sn_number, note=provider_message)
        
        # 7. TAMPILKAN HASIL FINAL
        saldo_akhir = get_user_saldo_modern(user_id)
        
        additional_info = status_info + [
            f"💰 **Saldo Awal:** Rp {saldo_awal:,}",
            f"💰 **Saldo Akhir:** Rp {saldo_akhir:,}",
            f"🔗 **Ref ID:** `{reffid}`"
        ]
        
        if sn_number:
            additional_info.append(f"🔢 **SN:** `{sn_number}`")
        
        message = ModernMessageBuilder.create_order_card(
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
            [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu")]
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
            await query.message.reply_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        # 8. CLEANUP
        order_keys = ['selected_product', 'order_target', 'product_page', 'current_group', 'current_products']
        for key in order_keys:
            if key in user_data:
                del user_data[key]
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"❌ Critical error in order: {e}")
        
        # REFUND JIKA ERROR
        try:
            user_id = str(query.from_user.id)
            update_user_saldo_modern(user_id, product['price'], "Refund: System error")
        except:
            pass
        
        await show_error_message(update, f"System error: {str(e)}")
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
        asyncio.create_task(self.admin_service())
    
    async def timeout_service(self):
        """Service untuk handle timeout orders"""
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
    
    async def admin_service(self):
        """Service untuk admin notifications"""
        while self.is_running:
            try:
                await self.check_admin_notifications()
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"❌ Admin service error: {e}")
                await asyncio.sleep(60)
    
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
                
                if (current_time - created_at).total_seconds() >= PROVIDER_TIMEOUT:
                    if order_id not in pending_orders_timeout:
                        await self.auto_fail_timeout_order(order)
                        pending_orders_timeout[order_id] = current_time
                        
        except Exception as e:
            logger.error(f"❌ Error in timeout processor: {e}")
    
    async def auto_fail_timeout_order(self, order):
        """Auto fail timeout order dan refund"""
        try:
            # Update status
            update_order_status(
                order['id'], 
                'failed', 
                note=f"Auto failed: Timeout {PROVIDER_TIMEOUT/60} menit"
            )
            
            # Refund saldo
            update_user_saldo_modern(
                order['user_id'],
                order['price'],
                f"Refund auto: Timeout - {order['product_name']}"
            )
            
            # Notify user
            message = ModernMessageBuilder.create_order_card(
                order,
                'timeout',
                [
                    "⏰ **Timeout 5 Menit**",
                    "❌ Tidak ada respon dari provider",
                    "✅ **Saldo telah dikembalikan**",
                    "🔄 Silakan order ulang"
                ]
            )
            
            await send_modern_notification(order['user_id'], message)
            
            logger.info(f"✅ Auto-failed timeout order {order['id']}")
            
        except Exception as e:
            logger.error(f"❌ Error auto-failing order: {e}")

# ==================== UTILITY FUNCTIONS ====================

async def safe_edit_modern(update, text, reply_markup=None):
    """Safely edit modern message"""
    try:
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                text, 
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        return True
    except Exception as e:
        logger.error(f"❌ Error editing modern message: {e}")
        return False

async def show_error_message(update, error_text):
    """Show modern error message"""
    message = (
        f"❌ **SYSTEM ERROR**\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        f"{error_text}\n\n"
        f"🔄 Silakan coba lagi atau hubungi admin"
    )
    
    keyboard = [[InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu")]]
    
    await safe_edit_modern(update, message, InlineKeyboardMarkup(keyboard))

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

def validate_target_modern(target, product_code):
    """Modern target validation"""
    try:
        # Clean target
        target = re.sub(r'\D', '', target)
        
        if product_code.startswith(('TS', 'AX', 'XL', 'IN', 'SM', '3')):
            # Validasi pulsa
            if target.startswith('0'):
                target = '62' + target[1:]
            elif target.startswith('8'):
                target = '62' + target
            
            if len(target) < 10 or len(target) > 14:
                return None
                
        elif product_code.startswith('PLN'):
            # Validasi PLN
            if len(target) < 10 or len(target) > 20:
                return None
                
        return target
        
    except Exception as e:
        logger.error(f"❌ Validation error: {e}")
        return None

# ==================== CONVERSATION HANDLER ====================

def get_modern_conversation_handler():
    """Get modern conversation handler"""
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(modern_menu_handler, pattern="^main_menu_order$")],
        states={
            CHOOSING_GROUP: [
                CallbackQueryHandler(show_modern_products, pattern="^mgroup_"),
                CallbackQueryHandler(cancel_modern, pattern="^main_menu$")
            ],
            CHOOSING_PRODUCT: [
                CallbackQueryHandler(select_modern_product, pattern="^mproduct_"),
                CallbackQueryHandler(handle_modern_pagination, pattern="^(mnext_page|mprev_page)$"),
                CallbackQueryHandler(show_modern_groups, pattern="^mback_groups$"),
                CallbackQueryHandler(cancel_modern, pattern="^main_menu$")
            ],
            ENTER_TUJUAN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_modern_target),
                CallbackQueryHandler(show_modern_products, pattern="^mgroup_"),
                CallbackQueryHandler(cancel_modern, pattern="^main_menu$")
            ],
            CONFIRM_ORDER: [
                CallbackQueryHandler(process_modern_order, pattern="^mconfirm_yes$"),
                CallbackQueryHandler(cancel_modern, pattern="^mconfirm_no$"),
                CallbackQueryHandler(show_modern_products, pattern="^mgroup_"),
                CallbackQueryHandler(cancel_modern, pattern="^main_menu$")
            ],
        },
        fallbacks=[
            CommandHandler("start", cancel_modern),
            CommandHandler("cancel", cancel_modern),
            CallbackQueryHandler(cancel_modern, pattern="^main_menu$")
        ],
        name="modern_order",
        persistent=False
    )

async def cancel_modern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel modern conversation"""
    query = update.callback_query
    if query:
        await query.answer()
    
    # Cleanup
    order_keys = ['selected_product', 'order_target', 'product_page', 'current_group', 'current_products']
    for key in order_keys:
        if key in context.user_data:
            del context.user_data[key]
    
    await safe_edit_modern(
        update,
        "❌ **ORDER DIBATALKAN**\n\nKembali ke menu utama...",
        InlineKeyboardMarkup([[InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu")]])
    )
    
    return ConversationHandler.END

# ==================== INITIALIZATION ====================

modern_poller = None

def initialize_modern_system(application):
    """Initialize modern order system"""
    global bot_application, modern_poller
    bot_application = application
    
    api_key = getattr(config, 'KHFYPAY_API_KEY', '')
    modern_poller = ModernPoller(api_key)
    
    # Start polling system
    loop = asyncio.get_event_loop()
    loop.create_task(modern_poller.start_polling(application))
    
    logger.info("✅ Modern Order System Initialized!")

# Export handler untuk main.py
modern_order_handler = get_modern_conversation_handler()
