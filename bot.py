#!/usr/bin/env python3
"""
Bot Telegram Full Feature - FIXED & READY FOR RELEASE
"""

import logging
import sys
import os
import asyncio
import traceback
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

# ==================== IMPORTS DENGAN ERROR HANDLING ====================
print("🔄 Loading handlers...")

# Admin Handler - YANG SUDAH DIPERBAIKI
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
    traceback.print_exc()
    ADMIN_AVAILABLE = False
    
    # Fallback functions
    async def admin_menu(update, context):
        if hasattr(update, 'message'):
            await update.message.reply_text("❌ Admin features sedang dalam perbaikan.")
        else:
            await update.callback_query.message.reply_text("❌ Admin features sedang dalam perbaikan.")
    
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
        await update.callback_query.message.reply_text("❌ Fitur stok sedang dalam perbaikan.")
    
    async def stock_command(update, context):
        await update.message.reply_text("❌ Fitur stok sedang dalam perbaikan.")

# Order Handler
try:
    from order_handler import (
        get_conversation_handler as get_order_conversation_handler,
        menu_handler as order_menu_handler
    )
    ORDER_AVAILABLE = True
    print("✅ Order handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing order_handler: {e}")
    ORDER_AVAILABLE = False
    
    def get_order_conversation_handler():
        return None
    
    async def order_menu_handler(update, context):
        if hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text("❌ Fitur order sedang dalam perbaikan.")
        else:
            await update.message.reply_text("❌ Fitur order sedang dalam perbaikan.")

# Topup Handler
try:
    from topup_handler import (
        get_topup_conversation_handler,
        show_topup_menu,
        show_topup_history, 
        show_pending_topups,
        handle_proof_upload,
        get_topup_handlers,
        topup_command
    )
    TOPUP_AVAILABLE = True
    print("✅ Topup handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing topup_handler: {e}")
    TOPUP_AVAILABLE = False
    
    async def show_topup_menu(update, context): 
        if hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text("❌ Fitur topup sedang dalam perbaikan.")
        else:
            await update.message.reply_text("❌ Fitur topup sedang dalam perbaikan.")
    
    show_topup_history = show_pending_topups = show_topup_menu
    
    def get_topup_conversation_handler():
        return None
    
    def get_topup_handlers():
        return []
    
    async def topup_command(update, context):
        await show_topup_menu(update, context)

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
    """Handler untuk command /start - Menu utama"""
    try:
        user = update.message.from_user
        logger.info(f"User {user.id} started the bot")
        
        # Get or create user in database
        saldo = 0
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception as e:
            logger.error(f"Error getting user saldo: {e}")
            saldo = 0
        
        # Main menu keyboard
        keyboard = [
            [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="main_menu_order")],
            [InlineKeyboardButton("💳 CEK SALDO", callback_data="main_menu_saldo")],
            [InlineKeyboardButton("📊 CEK STOK", callback_data="main_menu_stock")],
            [InlineKeyboardButton("📞 BANTUAN", callback_data="main_menu_help")],
            [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="topup_menu")]
        ]
        
        # Add admin button if user is admin
        if str(user.id) in ADMIN_IDS:
            keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="main_menu_admin")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = (
            f"🤖 **Selamat Datang!**\n\n"
            f"Halo {user.full_name}!\n"
            f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
            f"Pilih menu di bawah untuk mulai berbelanja:"
        )
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

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
        else:
            await query.message.reply_text("❌ Menu tidak dikenali.")
            
    except Exception as e:
        logger.error(f"Error in main_menu_handler for {data}: {e}")
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu utama"""
    query = update.callback_query
    user = query.from_user
    
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        saldo = 0
    
    keyboard = [
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="main_menu_order")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="main_menu_saldo")],
        [InlineKeyboardButton("📊 CEK STOK", callback_data="main_menu_stock")],
        [InlineKeyboardButton("📞 BANTUAN", callback_data="main_menu_help")],
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="topup_menu")]
    ]
    
    if str(user.id) in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="main_menu_admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            f"🏠 **MENU UTAMA**\n\n"
            f"Halo {user.full_name}!\n"
            f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
            f"Pilih menu di bawah:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}")
        await query.message.reply_text(
            f"🏠 **MENU UTAMA**\n\n"
            f"Halo {user.full_name}!\n"
            f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
            f"Pilih menu di bawah:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def show_saldo_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu saldo"""
    query = update.callback_query
    user = query.from_user
    
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        saldo = 0
    
    keyboard = [
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="topup_menu")],
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            f"💰 **SALDO ANDA**\n\n"
            f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
            f"Gunakan menu Top Up untuk menambah saldo.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}")
        await query.message.reply_text(
            f"💰 **SALDO ANDA**\n\n"
            f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
            f"Gunakan menu Top Up untuk menambah saldo.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def show_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu bantuan"""
    query = update.callback_query
    
    help_text = (
        "📞 **BANTUAN & PANDUAN**\n\n"
        "**CARA ORDER:**\n"
        "1. Pilih 🛒 **BELI PRODUK**\n"
        "2. Pilih kategori produk\n"
        "3. Pilih produk yang diinginkan\n"
        "4. Masukkan nomor tujuan\n"
        "5. Konfirmasi dan bayar\n\n"
        "**TOP UP SALDO:**\n"
        "1. Pilih 💸 **TOP UP SALDO**\n"
        "2. Masukkan nominal\n"
        "3. Pilih metode pembayaran (QRIS/Transfer Bank)\n"
        "4. Ikuti instruksi pembayaran\n"
        "5. Tunggu konfirmasi admin\n\n"
        "**BUTUH BANTUAN?**\n"
        "Hubungi Admin untuk bantuan lebih lanjut."
    )
    
    keyboard = [
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]
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

async def saldo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /saldo"""
    user = update.message.from_user
    
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        saldo = 0
    
    keyboard = [
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="topup_menu")],
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"💰 **SALDO ANDA**\n\n"
        f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
        f"Gunakan menu Top Up untuk menambah saldo.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /help"""
    keyboard = [
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    help_text = (
        "🤖 **BOT COMMANDS**\n\n"
        "**PERINTAH UTAMA:**\n"
        "• /start - Menu utama bot\n"
        "• /help - Bantuan ini\n"
        "• /saldo - Cek saldo\n"
        "• /topup - Top up saldo\n"
        "• /stock - Cek stok produk\n"
        "• /order - Beli produk\n\n"
        "**UNTUK ADMIN:**\n"
        "• /admin - Panel admin\n"
        "• /broadcast - Kirim pesan ke semua user\n"
        "• /topup_list - Lihat daftar topup\n"
        "• /cek_user - Cek info user\n"
    )
    
    await update.message.reply_text(
        help_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

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
        await update.message.reply_text("❌ Fitur topup sedang dalam perbaikan.")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /admin"""
    if str(update.message.from_user.id) in ADMIN_IDS:
        await admin_menu(update, context)
    else:
        await update.message.reply_text("❌ Anda bukan admin!")

# ==================== ADMIN COMMAND HANDLERS ====================
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /broadcast"""
    if str(update.message.from_user.id) in ADMIN_IDS:
        if ADMIN_AVAILABLE:
            # Simulasikan callback query untuk broadcast
            class FakeQuery:
                def __init__(self, message, from_user):
                    self.message = message
                    self.from_user = from_user
                    self.data = "admin_broadcast"
                
                async def answer(self):
                    pass
                
                async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
                    await self.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            
            fake_query = FakeQuery(update.message, update.message.from_user)
            await admin_callback_handler(Update(0, callback_query=fake_query), context)
        else:
            await update.message.reply_text("❌ Fitur broadcast sedang dalam perbaikan.")
    else:
        await update.message.reply_text("❌ Anda bukan admin!")

async def topup_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /topup_list"""
    if str(update.message.from_user.id) in ADMIN_IDS:
        if ADMIN_AVAILABLE:
            # Simulasikan callback query untuk topup list
            class FakeQuery:
                def __init__(self, message, from_user):
                    self.message = message
                    self.from_user = from_user
                    self.data = "admin_topup"
                
                async def answer(self):
                    pass
                
                async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
                    await self.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            
            fake_query = FakeQuery(update.message, update.message.from_user)
            await admin_callback_handler(Update(0, callback_query=fake_query), context)
        else:
            await update.message.reply_text("❌ Fitur admin sedang dalam perbaikan.")
    else:
        await update.message.reply_text("❌ Anda bukan admin!")

async def cek_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /cek_user"""
    if str(update.message.from_user.id) in ADMIN_IDS:
        if ADMIN_AVAILABLE:
            # Simulasikan callback query untuk user management
            class FakeQuery:
                def __init__(self, message, from_user):
                    self.message = message
                    self.from_user = from_user
                    self.data = "admin_users"
                
                async def answer(self):
                    pass
                
                async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
                    await self.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            
            fake_query = FakeQuery(update.message, update.message.from_user)
            await admin_callback_handler(Update(0, callback_query=fake_query), context)
        else:
            await update.message.reply_text("❌ Fitur admin sedang dalam perbaikan.")
    else:
        await update.message.reply_text("❌ Anda bukan admin!")

# ==================== UTILITY HANDLERS ====================
async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk pesan yang tidak dikenal"""
    logger.debug(f"Unknown message from {update.message.from_user.id}: {update.message.text}")
    
    await update.message.reply_text(
        "🤔 Saya tidak mengerti perintah tersebut.\n\n"
        "Gunakan /help untuk melihat daftar perintah yang tersedia "
        "atau gunakan tombol menu untuk navigasi.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📞 BANTUAN", callback_data="main_menu_help")],
            [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]
        ])
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler untuk menangani semua error"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
    
    # Log the full traceback
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = ''.join(tb_list)
    logger.error(f"Traceback: {tb_string}")
    
    if isinstance(update, Update):
        if update.message:
            await update.message.reply_text(
                "❌ Terjadi kesalahan sistem. Silakan coba lagi dalam beberapa saat.\n\n"
                "Jika error berlanjut, hubungi admin.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 BANTUAN", callback_data="main_menu_help")],
                    [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]
                ])
            )
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                "❌ Terjadi kesalahan sistem. Silakan coba lagi.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]
                ])
            )

# ==================== APPLICATION SETUP ====================
def setup_application():
    """Setup dan konfigurasi application bot"""
    print("🚀 Setting up bot application...")
    
    # Create application dengan persistence
    persistence = PicklePersistence(filepath="bot_persistence")
    application = Application.builder().token(BOT_TOKEN).persistence(persistence).build()
    
    # ==================== REGISTER HANDLERS ====================
    
    # Basic command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("saldo", saldo_command))
    application.add_handler(CommandHandler("stock", stock_command_handler))
    application.add_handler(CommandHandler("order", order_command))
    application.add_handler(CommandHandler("topup", topup_command_handler))
    application.add_handler(CommandHandler("admin", admin_command))
    
    # Admin command handlers
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("topup_list", topup_list_command))
    application.add_handler(CommandHandler("cek_user", cek_user_command))
    
    # Main menu callback handlers
    application.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^main_menu_"))
    application.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^topup_menu$"))
    
    # Add conversation handlers dari modules
    if ORDER_AVAILABLE:
        order_conv_handler = get_order_conversation_handler()
        if order_conv_handler:
            application.add_handler(order_conv_handler)
            print("✅ Order conversation handler registered")
    
    if TOPUP_AVAILABLE:
        topup_conv_handler = get_topup_conversation_handler()
        if topup_conv_handler:
            application.add_handler(topup_conv_handler)
            print("✅ Topup conversation handler registered")
        
        # Add additional topup handlers
        topup_handlers = get_topup_handlers()
        for handler in topup_handlers:
            application.add_handler(handler)
    
    # Add admin handlers
    if ADMIN_AVAILABLE:
        admin_handlers = get_admin_handlers()
        for handler in admin_handlers:
            application.add_handler(handler)
        print("✅ Admin handlers registered")
    
    # Stok handler
    if STOK_AVAILABLE:
        application.add_handler(CallbackQueryHandler(stock_akrab_callback, pattern="^stock_"))
        print("✅ Stok handler registered")
    
    # Unknown message handler (harus terakhir)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    print("✅ All handlers registered successfully")
    return application

# ==================== MAIN EXECUTION ====================
async def main():
    """Main function untuk menjalankan bot"""
    print("🤖 Starting Telegram Bot...")
    
    try:
        # Setup application
        application = setup_application()
        
        # Check database connection
        print("🔍 Checking database connection...")
        try:
            # Test database connection
            test_user = database.get_or_create_user("test", "test_user", "Test User")
            print("✅ Database connection successful")
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return
        
        # Start the bot
        print("🎉 Bot is starting...")
        print("📱 Bot is now running. Press Ctrl+C to stop.")
        
        # Run bot sampai dihentikan
        await application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.critical(f"Failed to start bot: {e}")
        print(f"❌ Critical error: {e}")
        traceback.print_exc()
        
    finally:
        print("👋 Bot stopped")

if __name__ == "__main__":
    # Print startup banner
    print("=" * 50)
    print("🤖 TELEGRAM BOT - FULL FEATURE VERSION")
    print("🛠️  FIXED & READY FOR PRODUCTION")
    print("=" * 50)
    
    # Run main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        traceback.print_exc()
