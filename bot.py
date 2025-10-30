#!/usr/bin/env python3
"""
🤖 Telegram Bot - MODERN VERSION dengan KhfyPay Integration
🎨 Modern UI & Enhanced User Experience  
⚡ Full Features - Ready for Production
🛡️  Conflict Protection & Auto Recovery
"""

import logging
import sys
import os
import asyncio
import traceback
import signal
import time
from typing import Dict, Any
from datetime import datetime

# Telegram Imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    MessageHandler,
    ConversationHandler,
    PicklePersistence
)

# Custom Module Imports
import config
import database

# ==================== SINGLETON PATTERN UNTUK MENCEGAH MULTIPLE INSTANCE ====================
class BotSingleton:
    _instance = None
    _pid_file = 'bot.pid'
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._application = None
    
    def is_already_running(self):
        """Check if bot is already running"""
        try:
            if os.path.exists(self._pid_file):
                with open(self._pid_file, 'r') as f:
                    old_pid = int(f.read().strip())
                    # Check if process is still running
                    try:
                        os.kill(old_pid, 0)  # This will throw an error if process doesn't exist
                        return True
                    except OSError:
                        # Process doesn't exist, remove stale PID file
                        os.remove(self._pid_file)
                        return False
            return False
        except Exception as e:
            print(f"⚠️ Error checking running status: {e}")
            return False
    
    def create_pid_file(self):
        """Create PID file"""
        try:
            with open(self._pid_file, 'w') as f:
                f.write(str(os.getpid()))
            return True
        except Exception as e:
            print(f"❌ Error creating PID file: {e}")
            return False
    
    def remove_pid_file(self):
        """Remove PID file"""
        try:
            if os.path.exists(self._pid_file):
                os.remove(self._pid_file)
            return True
        except Exception as e:
            print(f"⚠️ Error removing PID file: {e}")
            return False

# ==================== IMPORTS DENGAN ERROR HANDLING ====================
print("🔄 Loading handlers...")

# Admin Handler
try:
    from admin_handler import (
        admin_menu,
        admin_callback_handler,
        get_admin_handlers
    )
    ADMIN_AVAILABLE = True
    print("✅ Admin handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing admin_handler: {e}")
    ADMIN_AVAILABLE = False
    
    async def admin_menu(update, context):
        await send_modern_message(update, "❌ Admin features sedang dalam perbaikan.", "main_menu_main")
    
    async def admin_callback_handler(update, context):
        await update.callback_query.answer("❌ Admin features sedang dalam perbaikan.", show_alert=True)
    
    def get_admin_handlers():
        return []

# Stok Handler
try:
    from stok_handler import stock_akrab_callback, stock_command
    STOK_AVAILABLE = True
    print("✅ Stok handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing stok_handler: {e}")
    STOK_AVAILABLE = False
    
    async def stock_akrab_callback(update, context):
        await send_modern_message(update, "❌ Fitur stok sedang dalam perbaikan.", "main_menu_main")
    
    async def stock_command(update, context):
        await send_modern_message(update, "❌ Fitur stok sedang dalam perbaikan.", "main_menu_main")

# Order Handler
try:
    from order_handler import (
        get_conversation_handler as get_order_conversation_handler,
        menu_handler as order_menu_handler,
        initialize_order_system
    )
    ORDER_AVAILABLE = True
    print("✅ Order handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing order_handler: {e}")
    ORDER_AVAILABLE = False
    
    def get_order_conversation_handler():
        return None
    
    async def order_menu_handler(update, context):
        await send_modern_message(update, "❌ Fitur order sedang dalam perbaikan.", "main_menu_main")
    
    def initialize_order_system(app, webhook_port=5000):
        print("⚠️ Order system initialization skipped")

# Topup Handler
try:
    from topup_handler import (
        get_topup_conversation_handler,
        show_topup_menu,
        get_topup_handlers,
        topup_command
    )
    TOPUP_AVAILABLE = True
    print("✅ Topup handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing topup_handler: {e}")
    TOPUP_AVAILABLE = False
    
    async def show_topup_menu(update, context): 
        await send_modern_message(update, "❌ Fitur topup sedang dalam perbaikan.", "main_menu_main")
    
    def get_topup_conversation_handler():
        return None
    
    def get_topup_handlers():
        return []
    
    async def topup_command(update, context):
        await show_topup_menu(update, context)

# ==================== KHFYPAY INTEGRATION IMPORTS ====================
try:
    from webhook_handler import set_bot_application, start_webhook_server
    from auto_status_checker import start_auto_status_checker
    KHFYPAY_AVAILABLE = True
    print("✅ KhfyPay integration loaded successfully")
except Exception as e:
    print(f"⚠️ KhfyPay integration not available: {e}")
    KHFYPAY_AVAILABLE = False
    
    def set_bot_application(app):
        pass
    
    def start_webhook_server():
        pass
    
    def start_auto_status_checker(app, check_interval=120):
        pass

# ==================== MODERN UI FUNCTIONS ====================
async def send_modern_message(update, text, callback_data=None, title=None, image_emoji="✨"):
    """Send modern formatted message dengan design yang lebih menarik"""
    try:
        if title:
            formatted_text = f"{image_emoji} **{title}**\n\n{text}"
        else:
            formatted_text = f"{image_emoji} {text}"
        
        if callback_data:
            keyboard = [[
                InlineKeyboardButton("🏠 Kembali ke Menu", callback_data=callback_data)
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
        else:
            reply_markup = None
        
        if hasattr(update, 'callback_query') and update.callback_query:
            try:
                await update.callback_query.edit_message_text(
                    formatted_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except Exception:
                await update.callback_query.message.reply_text(
                    formatted_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        elif hasattr(update, 'message') and update.message:
            await update.message.reply_text(
                formatted_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error in send_modern_message: {e}")

def create_modern_keyboard(buttons, back_button=True):
    """Create modern keyboard layout dengan design yang lebih baik"""
    keyboard = []
    
    # Add main buttons
    for button_row in buttons:
        keyboard.append(button_row)
    
    # Add back button if needed
    if back_button:
        keyboard.append([InlineKeyboardButton("🔙 Kembali", callback_data="main_menu_main")])
    
    return InlineKeyboardMarkup(keyboard)

# ==================== RIWAYAT TRANSAKSI HANDLER ====================
async def show_history_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu riwayat transaksi yang modern"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    keyboard = [
        [InlineKeyboardButton("📋 Riwayat Order", callback_data="history_orders")],
        [InlineKeyboardButton("💰 Riwayat Topup", callback_data="history_topups")],
        [InlineKeyboardButton("📊 Semua Transaksi", callback_data="history_all")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📊 **RIWAYAT TRANSAKSI**\n\n"
        "Pilih jenis riwayat yang ingin dilihat:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_order_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan riwayat order user dengan data REAL-TIME"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    
    try:
        # Get user orders
        orders = database.get_user_orders(user_id, limit=10)
        
        if not orders:
            await send_modern_message(
                update,
                "Anda belum memiliki riwayat order.\n\n"
                "Silakan melakukan order terlebih dahulu untuk melihat riwayat.",
                "history_menu",
                "📋 Riwayat Order Kosong"
            )
            return
        
        # Format orders for display dengan status terbaru
        orders_text = ""
        total_spent = 0
        completed_orders = 0
        
        for i, order in enumerate(orders[:8], 1):
            status_emoji = {
                'completed': '✅',
                'pending': '⏳', 
                'processing': '🔄',
                'failed': '❌',
                'refunded': '💰',
                'cancelled': '🚫'
            }.get(order['status'], '📦')
            
            # Format date
            try:
                if isinstance(order['created_at'], str):
                    order_date = datetime.strptime(order['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m %H:%M')
                else:
                    order_date = order['created_at'].strftime('%d/%m %H:%M')
            except:
                order_date = "N/A"
            
            orders_text += (
                f"{status_emoji} **Order #{order['id']}**\n"
                f"📦 {order['product_name']}\n"
                f"💳 Rp {order['price']:,}\n"
                f"⏰ {order_date} | {order['status'].upper()}\n"
            )
            
            if order.get('sn'):
                orders_text += f"🔢 SN: `{order['sn']}`\n"
            
            orders_text += "━━━━━━━━━━━━━━━━━━━━\n"
            
            if order['status'] == 'completed':
                completed_orders += 1
                total_spent += order['price']
        
        # Summary dengan real-time data
        success_rate = (completed_orders / len(orders) * 100) if orders else 0
        
        summary = (
            f"\n📈 **STATISTIK REAL-TIME**\n"
            f"• Total Order: {len(orders)}\n"
            f"• Berhasil: {completed_orders}\n"
            f"• Success Rate: {success_rate:.1f}%\n"
            f"• Total Pengeluaran: Rp {total_spent:,}\n"
        )
        
        if len(orders) > 8:
            summary += f"• Dan {len(orders) - 8} order lainnya..."
        
        full_text = f"📋 **RIWAYAT ORDER REAL-TIME**\n\n{orders_text}{summary}"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Data", callback_data="history_orders")],
            [InlineKeyboardButton("📊 Riwayat Lain", callback_data="history_menu")],
            [InlineKeyboardButton("🛒 Order Lagi", callback_data="main_menu_order")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            full_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error showing order history: {e}")
        await send_modern_message(
            update,
            "Terjadi error saat memuat riwayat order.\nSilakan coba lagi beberapa saat.",
            "history_menu",
            "❌ Error"
        )

async def show_topup_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan riwayat topup user"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    
    try:
        # Get user transactions (topups)
        transactions = database.get_user_transactions(user_id, limit=10)
        
        if not transactions:
            await send_modern_message(
                update,
                "Anda belum memiliki riwayat topup.\n\n"
                "Silakan melakukan topup terlebih dahulu untuk melihat riwayat.",
                "history_menu",
                "💰 Riwayat Topup Kosong"
            )
            return
        
        # Format transactions for display
        transactions_text = ""
        total_topup = 0
        
        for i, transaction in enumerate(transactions[:8], 1):
            status_emoji = '✅' if transaction.get('status') == 'completed' else '⏳'
            
            transactions_text += (
                f"{status_emoji} **Topup #{transaction.get('id', 'N/A')}**\n"
                f"💳 Rp {transaction.get('amount', 0):,}\n"
                f"⏰ {transaction.get('created_at', 'N/A')}\n"
                f"📊 {transaction.get('status', 'pending').upper()}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
            )
            
            if transaction.get('status') == 'completed':
                total_topup += transaction.get('amount', 0)
        
        summary = (
            f"\n📈 **STATISTIK TOPUP**\n"
            f"• Total Topup: {len(transactions)}\n"
            f"• Total Nominal: Rp {total_topup:,}\n"
        )
        
        full_text = f"💰 **RIWAYAT TOPUP**\n\n{transactions_text}{summary}"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="history_topups")],
            [InlineKeyboardButton("📊 Riwayat Lain", callback_data="history_menu")],
            [InlineKeyboardButton("💸 Topup Lagi", callback_data="topup_menu")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            full_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error showing topup history: {e}")
        await send_modern_message(
            update,
            "Terjadi error saat memuat riwayat topup.\nSilakan coba lagi beberapa saat.",
            "history_menu",
            "❌ Error"
        )

async def show_all_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan semua riwayat transaksi"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    
    try:
        # Get user orders for combined history
        orders = database.get_user_orders(user_id, limit=15)
        
        if not orders:
            await send_modern_message(
                update,
                "Anda belum memiliki riwayat transaksi.\n\n"
                "Silakan melakukan order atau topup terlebih dahulu.",
                "history_menu",
                "📊 Riwayat Kosong"
            )
            return
        
        # Format combined history
        history_text = ""
        total_orders = len(orders)
        completed_orders = 0
        total_spent = 0
        
        for order in orders[:10]:
            status_emoji = {
                'completed': '✅',
                'pending': '⏳', 
                'processing': '🔄',
                'failed': '❌',
                'refunded': '💰'
            }.get(order['status'], '📦')
            
            try:
                if isinstance(order['created_at'], str):
                    order_date = datetime.strptime(order['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m %H:%M')
                else:
                    order_date = order['created_at'].strftime('%d/%m %H:%M')
            except:
                order_date = order['created_at']
            
            history_text += (
                f"{status_emoji} **{order['product_name']}**\n"
                f"💳 Rp {order['price']:,} | {order_date}\n"
                f"📊 {order['status'].upper()}\n"
            )
            
            if order.get('sn'):
                history_text += f"🔢 SN: `{order['sn']}`\n"
            
            history_text += "━━━━━━━━━━━━━━━━━━━━\n"
            
            if order['status'] == 'completed':
                completed_orders += 1
                total_spent += order['price']
        
        # Statistics
        success_rate = (completed_orders / total_orders * 100) if total_orders > 0 else 0
        
        summary = (
            f"\n📈 **STATISTIK AKUN**\n"
            f"• Total Transaksi: {total_orders}\n"
            f"• Berhasil: {completed_orders}\n"
            f"• Tingkat Kesuksesan: {success_rate:.1f}%\n"
            f"• Total Pengeluaran: Rp {total_spent:,}\n"
        )
        
        if len(orders) > 10:
            summary += f"• Dan {len(orders) - 10} transaksi lainnya..."
        
        full_text = f"📊 **SEMUA RIWAYAT TRANSAKSI**\n\n{history_text}{summary}"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="history_all")],
            [InlineKeyboardButton("📋 Riwayat Order", callback_data="history_orders")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            full_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error showing all history: {e}")
        await send_modern_message(
            update,
            "Terjadi error saat memuat riwayat transaksi.\nSilakan coba lagi beberapa saat.",
            "history_menu",
            "❌ Error"
        )

# ==================== LOGGING SETUP ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ==================== GLOBAL VARIABLES ====================
BOT_TOKEN = config.BOT_TOKEN
ADMIN_IDS = getattr(config, 'ADMIN_TELEGRAM_IDS', [])

# ==================== BASIC COMMAND HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start - Menu utama modern"""
    try:
        user = update.message.from_user
        logger.info(f"User {user.id} started the bot")
        
        # Get or create user in database
        saldo = 0
        try:
            user_data = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(str(user.id))
        except Exception as e:
            logger.error(f"Error getting user saldo: {e}")
            saldo = 0
        
        # Modern main menu keyboard
        keyboard = [
            [InlineKeyboardButton("🛒 Beli Produk", callback_data="main_menu_order")],
            [InlineKeyboardButton("💳 Top Up Saldo", callback_data="topup_menu")],
            [InlineKeyboardButton("📊 Riwayat Transaksi", callback_data="history_menu")],
            [InlineKeyboardButton("📦 Cek Stok", callback_data="main_menu_stock")],
            [InlineKeyboardButton("ℹ️ Bantuan", callback_data="main_menu_help")]
        ]
        
        # Add admin button if user is admin
        if str(user.id) in ADMIN_IDS:
            keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="main_menu_admin")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = (
            f"🎉 **Selamat Datang di Store Bot!**\n\n"
            f"👋 Halo **{user.full_name}**\n"
            f"💰 **Saldo Anda:** `Rp {saldo:,.0f}`\n\n"
            f"*Apa yang ingin Anda lakukan hari ini?*"
        )
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text(
            "❌ Maaf, terjadi kesalahan sistem.\nSilakan coba lagi dalam beberapa saat.",
            parse_mode='Markdown'
        )

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main menu handler untuk semua callback"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    logger.info(f"Main menu callback: {data} from user {user.id}")
    
    try:
        if data == "main_menu_main":
            await show_main_menu(update, context)
        elif data == "main_menu_saldo":
            await show_saldo_menu(update, context)
        elif data == "main_menu_help":
            await show_help_menu(update, context)
        elif data == "main_menu_stock":
            await stock_akrab_callback(update, context)
        elif data == "main_menu_admin":
            if str(user.id) in ADMIN_IDS:
                await admin_menu(update, context)
            else:
                await query.answer("❌ Anda bukan admin!", show_alert=True)
        elif data == "main_menu_order":
            await order_menu_handler(update, context)
        elif data == "topup_menu":
            await show_topup_menu(update, context)
        elif data == "history_menu":
            await show_history_menu(update, context)
        elif data == "history_orders":
            await show_order_history(update, context)
        elif data == "history_topups":
            await show_topup_history(update, context)
        elif data == "history_all":
            await show_all_history(update, context)
        else:
            await query.answer("❌ Menu tidak dikenali", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error in main_menu_handler for {data}: {e}")
        await send_modern_message(update, "Terjadi error. Silakan coba lagi.", "main_menu_main", "❌ Error")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu utama modern"""
    query = update.callback_query
    user = query.from_user
    
    saldo = 0
    try:
        saldo = database.get_user_saldo(str(user.id))
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        saldo = 0
    
    # Modern keyboard layout
    keyboard = [
        [InlineKeyboardButton("🛒 Beli Produk", callback_data="main_menu_order")],
        [InlineKeyboardButton("💳 Top Up Saldo", callback_data="topup_menu")],
        [InlineKeyboardButton("📊 Riwayat Transaksi", callback_data="history_menu")],
        [InlineKeyboardButton("📦 Cek Stok", callback_data="main_menu_stock")],
        [InlineKeyboardButton("ℹ️ Bantuan", callback_data="main_menu_help")]
    ]
    
    if str(user.id) in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="main_menu_admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    menu_text = (
        f"🏠 **Menu Utama**\n\n"
        f"👤 **User:** {user.full_name}\n"
        f"💰 **Saldo:** `Rp {saldo:,.0f}`\n\n"
        f"*Pilih menu di bawah untuk melanjutkan:*"
    )
    
    try:
        await query.edit_message_text(
            menu_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}")
        await query.message.reply_text(
            menu_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def show_saldo_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu saldo modern"""
    query = update.callback_query
    user = query.from_user
    
    saldo = 0
    try:
        saldo = database.get_user_saldo(str(user.id))
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        saldo = 0
    
    keyboard = [
        [InlineKeyboardButton("💸 Top Up Sekarang", callback_data="topup_menu")],
        [InlineKeyboardButton("📊 Riwayat", callback_data="history_menu")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    saldo_text = (
        f"💰 **Informasi Saldo**\n\n"
        f"💳 **Saldo Tersedia:** `Rp {saldo:,.0f}`\n\n"
        f"*Gunakan saldo untuk membeli produk digital.*\n"
        f"*Top up saldo jika saldo tidak mencukupi.*"
    )
    
    try:
        await query.edit_message_text(
            saldo_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}")
        await query.message.reply_text(
            saldo_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def show_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu bantuan modern"""
    query = update.callback_query
    
    help_text = (
        "❓ **Pusat Bantuan**\n\n"
        
        "🛒 **Cara Order:**\n"
        "1. Pilih → `Beli Produk`\n"
        "2. Pilih kategori produk\n" 
        "3. Pilih produk yang diinginkan\n"
        "4. Masukkan nomor tujuan\n"
        "5. Konfirmasi & bayar dengan saldo\n\n"
        
        "💳 **Cara Top Up:**\n"
        "1. Pilih → `Top Up Saldo`\n"
        "2. Masukkan nominal\n"
        "3. Pilih metode pembayaran\n"
        "4. Ikuti instruksi pembayaran\n"
        "5. Tunggu konfirmasi admin\n\n"
        
        "📊 **Fitur Lainnya:**\n"
        "• `Riwayat Transaksi` - Lihat history order & topup\n"
        "• `Cek Stok` - Lihat ketersediaan produk\n"
        "• `Admin Panel` - Untuk administrator\n\n"
        
        "🔧 **Butuh Bantuan?**\n"
        "Hubungi Admin untuk bantuan lebih lanjut."
    )
    
    keyboard = [
        [InlineKeyboardButton("🛒 Mulai Order", callback_data="main_menu_order")],
        [InlineKeyboardButton("💳 Top Up Saldo", callback_data="topup_menu")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            help_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}")
        await query.message.reply_text(
            help_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

# ==================== COMMAND HANDLERS ====================
async def saldo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /saldo"""
    await show_saldo_menu(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /help"""
    await show_help_menu(update, context)

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /history"""
    await show_history_menu(update, context)

async def stock_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /stock"""
    await stock_command(update, context)

async def order_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /order"""
    await order_menu_handler(update, context)

async def topup_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /topup"""
    if TOPUP_AVAILABLE:
        await topup_command(update, context)
    else:
        await send_modern_message(update, "Fitur topup sedang dalam perbaikan.", "main_menu_main", "❌ Peringatan")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /admin"""
    if str(update.message.from_user.id) in ADMIN_IDS:
        await admin_menu(update, context)
    else:
        await send_modern_message(update, "Anda bukan administrator!", "main_menu_main", "❌ Akses Ditolak")

# ==================== ADMIN COMMAND HANDLERS ====================
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /broadcast"""
    if str(update.message.from_user.id) in ADMIN_IDS:
        if ADMIN_AVAILABLE:
            await admin_callback_handler(update, context)
        else:
            await send_modern_message(update, "Fitur admin sedang dalam perbaikan.", "main_menu_main")
    else:
        await send_modern_message(update, "Anda bukan administrator!", "main_menu_main")

async def topup_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /topup_list"""
    if str(update.message.from_user.id) in ADMIN_IDS:
        if ADMIN_AVAILABLE:
            query = type('Query', (), {
                'data': 'admin_topup',
                'from_user': update.message.from_user,
                'message': update.message,
                'answer': lambda: None,
            })()
            fake_update = type('Update', (), {'callback_query': query})()
            await admin_callback_handler(fake_update, context)
        else:
            await send_modern_message(update, "Fitur admin sedang dalam perbaikan.", "main_menu_main")
    else:
        await send_modern_message(update, "Anda bukan administrator!", "main_menu_main")

async def cek_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /cek_user"""
    if str(update.message.from_user.id) in ADMIN_IDS:
        if ADMIN_AVAILABLE:
            query = type('Query', (), {
                'data': 'admin_users',
                'from_user': update.message.from_user,
                'message': update.message,
                'answer': lambda: None,
            })()
            fake_update = type('Update', (), {'callback_query': query})()
            await admin_callback_handler(fake_update, context)
        else:
            await send_modern_message(update, "Fitur admin sedang dalam perbaikan.", "main_menu_main")
    else:
        await send_modern_message(update, "Anda bukan administrator!", "main_menu_main")

# ==================== UTILITY HANDLERS ====================
async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk pesan yang tidak dikenal"""
    await send_modern_message(
        update,
        "Saya tidak mengerti perintah tersebut.\n\n"
        "Gunakan /start untuk membuka menu utama atau /help untuk bantuan.",
        "main_menu_main",
        "🤔 Perintah Tidak Dikenali"
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler untuk menangani semua error"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
    
    if isinstance(update, Update):
        await send_modern_message(
            update,
            "Terjadi kesalahan sistem. Silakan coba lagi dalam beberapa saat.\n\n"
            "Jika error berlanjut, hubungi admin.",
            "main_menu_main",
            "❌ System Error"
        )

async def post_init(application: Application):
    """Function yang dijalankan setelah bot berhasil initialized"""
    logger.info("🤖 Bot has been initialized successfully!")
    
    try:
        # SET KHFYPAY BOT APPLICATION
        if KHFYPAY_AVAILABLE:
            set_bot_application(application)
            logger.info("✅ KhfyPay bot application set")
        
        # START KHFYPAY WEBHOOK SERVER IN BACKGROUND
        if KHFYPAY_AVAILABLE:
            import threading
            webhook_thread = threading.Thread(
                target=start_webhook_server, 
                daemon=True
            )
            webhook_thread.start()
            logger.info("✅ KhfyPay Webhook server started in background")
        
        # START KHFYPAY AUTO STATUS CHECKER
        if KHFYPAY_AVAILABLE:
            start_auto_status_checker(application, check_interval=120)
            logger.info("✅ KhfyPay Auto Status Checker started")
        
        # INITIALIZE ORDER SYSTEM WITH POLLING
        if ORDER_AVAILABLE:
            initialize_order_system(application)
            logger.info("✅ Order system with polling initialized")
        
        bot = await application.bot.get_me()
        
        try:
            total_users = database.get_total_users()
            total_products = database.get_total_products()
            pending_topups = database.get_pending_topups_count()
        except:
            total_users = 0
            total_products = 0
            pending_topups = 0
        
        status_info = (
            f"🎉 **Bot Started Successfully!**\n\n"
            f"📊 **System Status:**\n"
            f"• Database: ✅\n"
            f"• KhfyPay Integration: {'✅' if KHFYPAY_AVAILABLE else '❌'}\n"
            f"• Topup: {'✅' if TOPUP_AVAILABLE else '❌'}\n"
            f"• Order: {'✅' if ORDER_AVAILABLE else '❌'}\n"
            f"• Admin: {'✅' if ADMIN_AVAILABLE else '❌'}\n"
            f"• Stok: {'✅' if STOK_AVAILABLE else '❌'}\n\n"
            f"📈 **Statistics:**\n"
            f"• Total Users: `{total_users}`\n"
            f"• Total Products: `{total_products}`\n"
            f"• Pending Topups: `{pending_topups}`\n\n"
            f"🤖 **Bot Information:**\n"
            f"• Name: @{bot.username}\n"
            f"• ID: `{bot.id}`\n"
            f"• Start Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )
        
        print("=" * 60)
        print("🤖 BOT STARTED SUCCESSFULLY WITH ALL FEATURES!")
        print("=" * 60)
        print(status_info)
        print("=" * 60)
        if KHFYPAY_AVAILABLE:
            print("📍 KhfyPay Webhook URL: http://your-server-ip:8080/webhook")
            print("📍 KhfyPay Auto Status Checker: Running every 2 minutes")
        if ORDER_AVAILABLE:
            print("📍 Order Polling System: Active (120s interval)")
        print("📍 Bot is now running and waiting for messages...")
        print("📍 Try sending /start to your bot")
        print("=" * 60)
        
    except Exception as e:
        logger.error(f"Error in post_init: {e}")

# ==================== SIGNAL HANDLERS ====================
def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        print(f"\n🛑 Received signal {signum}. Shutting down gracefully...")
        bot_singleton = BotSingleton.get_instance()
        bot_singleton.remove_pid_file()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

# ==================== MAIN FUNCTION ====================
def main():
    """Main function - Initialize dan start bot"""
    try:
        print("🚀 Starting Modern Telegram Bot with All Features...")
        
        # Setup signal handlers
        setup_signal_handlers()
        
        # Check for existing bot instance
        bot_singleton = BotSingleton.get_instance()
        if bot_singleton.is_already_running():
            print("❌ Bot is already running! Please stop the existing instance first.")
            print("💡 Run: pkill -f python  (to stop all Python processes)")
            print("💡 Or run: python stop_bot.py")
            sys.exit(1)
        
        # Create PID file
        if not bot_singleton.create_pid_file():
            print("⚠️ Warning: Could not create PID file")
        
        if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
            print("❌ Please set BOT_TOKEN in config.py")
            bot_singleton.remove_pid_file()
            sys.exit(1)
        
        # Initialize database
        try:
            success = database.init_database()
            if success:
                print("✅ Database initialized successfully")
            else:
                print("❌ Database initialization failed")
        except Exception as e:
            print(f"❌ Database initialization failed: {e}")
        
        # Create Application
        persistence = PicklePersistence(filepath="bot_persistence")
        application = Application.builder()\
            .token(BOT_TOKEN)\
            .persistence(persistence)\
            .post_init(post_init)\
            .build()
        
        print("✅ Application built successfully")
        
        # ==================== HANDLER REGISTRATION ====================
        
        # 1. CONVERSATION HANDLERS
        if TOPUP_AVAILABLE:
            topup_conv_handler = get_topup_conversation_handler()
            if topup_conv_handler:
                application.add_handler(topup_conv_handler)
                print("✅ Topup conversation handler registered")
        
        if ORDER_AVAILABLE:
            order_conv_handler = get_order_conversation_handler()
            if order_conv_handler:
                application.add_handler(order_conv_handler)
                print("✅ Order conversation handler registered")
        
        # 2. TOPUP CALLBACK HANDLERS
        if TOPUP_AVAILABLE:
            topup_handlers = get_topup_handlers()
            for handler in topup_handlers:
                application.add_handler(handler)
            print("✅ Topup callback handlers registered")
        
        # 3. ADMIN CALLBACK HANDLERS
        if ADMIN_AVAILABLE:
            admin_handlers = get_admin_handlers()
            for handler in admin_handlers:
                application.add_handler(handler)
            print("✅ Admin callback handlers registered")
        
        # 4. STOK HANDLER
        if STOK_AVAILABLE:
            application.add_handler(CallbackQueryHandler(stock_akrab_callback, pattern="^stock_"))
            print("✅ Stok handler registered")
        
        # 5. HISTORY HANDLERS
        application.add_handler(CallbackQueryHandler(show_history_menu, pattern="^history_menu$"))
        application.add_handler(CallbackQueryHandler(show_order_history, pattern="^history_orders$"))
        application.add_handler(CallbackQueryHandler(show_topup_history, pattern="^history_topups$"))
        application.add_handler(CallbackQueryHandler(show_all_history, pattern="^history_all$"))
        print("✅ History handlers registered")
        
        # 6. MAIN MENU CALLBACK HANDLER
        application.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^main_menu_"))
        application.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^topup_menu$"))
        application.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^history_"))
        print("✅ Main menu callback handler registered")
        
        # 7. COMMAND HANDLERS
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("saldo", saldo_command))
        application.add_handler(CommandHandler("history", history_command))
        application.add_handler(CommandHandler("topup", topup_command_handler))
        application.add_handler(CommandHandler("stock", stock_command_handler))
        application.add_handler(CommandHandler("order", order_command))
        application.add_handler(CommandHandler("admin", admin_command))
        
        # Admin commands
        application.add_handler(CommandHandler("broadcast", broadcast_command))
        application.add_handler(CommandHandler("topup_list", topup_list_command))
        application.add_handler(CommandHandler("cek_user", cek_user_command))
        
        print("✅ Command handlers registered")
        
        # 8. MESSAGE HANDLER
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))
        print("✅ Unknown message handler registered")
        
        # 9. ERROR HANDLER
        application.add_error_handler(error_handler)
        print("✅ Error handler registered")
        
        # ==================== START BOT ====================
        print("🎯 Starting bot polling...")
        
        # Store application in singleton
        bot_singleton._application = application
        
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            close_loop=False
        )
                
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        logger.error(f"Failed to start bot: {e}", exc_info=True)
    finally:
        # Cleanup
        bot_singleton = BotSingleton.get_instance()
        bot_singleton.remove_pid_file()
        print("🧹 Cleanup completed")

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 MODERN TELEGRAM BOT - PRODUCTION READY")
    print("🎨 Enhanced UI & User Experience") 
    print("⚡ Full Features - Order, Topup, Admin, History")
    print("🌐 KhfyPay Integration with Auto Polling")
    print("🛡️  Conflict Protection & Graceful Shutdown")
    print("📊 Real-time Statistics & Notifications")
    print("=" * 60)
    
    main()
