#!/usr/bin/env python3
"""
Bot Telegram Full Feature - COMPLETE FIXED VERSION
Semua fitur: Topup, Order, Stok, Admin berfungsi normal
"""

import logging
import sys
import os
import asyncio
import traceback
from typing import Dict, Any, List
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

# Initialize availability flags
ADMIN_AVAILABLE = STOK_AVAILABLE = ORDER_AVAILABLE = TOPUP_AVAILABLE = False

# Admin Handler
try:
    from admin_handler import (
        admin_menu,
        admin_callback_handler,
        edit_produk_conv_handler,
        broadcast_handler,
        cek_user_handler,
        jadikan_admin_handler,
        topup_list_handler,
        approve_topup_handler
    )
    ADMIN_AVAILABLE = True
    print("✅ Admin handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing admin_handler: {e}")
    ADMIN_AVAILABLE = False
    
    # Fallback functions
    async def admin_menu(update, context):
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text("❌ Admin features sedang dalam perbaikan.")
        elif hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.reply_text("❌ Admin features sedang dalam perbaikan.")
    
    async def admin_callback_handler(update, context):
        if hasattr(update, 'callback_query'):
            await update.callback_query.answer("❌ Admin features sedang dalam perbaikan.", show_alert=True)
    
    # Create dummy handlers
    edit_produk_conv_handler = None
    broadcast_handler = CommandHandler("broadcast", admin_menu)
    cek_user_handler = CommandHandler("cek_user", admin_menu)
    jadikan_admin_handler = CommandHandler("jadikan_admin", admin_menu)
    topup_list_handler = CommandHandler("topup_list", admin_menu)
    approve_topup_handler = CallbackQueryHandler(admin_menu, pattern="^admin_approve_topup_")

# Stok Handler
try:
    from stok_handler import (
        stock_akrab_callback, 
        stock_command,
        stok_callback_handler
    )
    STOK_AVAILABLE = True
    print("✅ Stok handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing stok_handler: {e}")
    STOK_AVAILABLE = False
    
    async def stock_akrab_callback(update, context):
        if hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text("❌ Fitur stok sedang dalam perbaikan.")
        else:
            await update.message.reply_text("❌ Fitur stok sedang dalam perbaikan.")
    
    async def stock_command(update, context):
        await update.message.reply_text("❌ Fitur stok sedang dalam perbaikan.")
    
    async def stok_callback_handler(update, context):
        if hasattr(update, 'callback_query'):
            await update.callback_query.answer("❌ Fitur stok sedang dalam perbaikan.", show_alert=True)

# Order Handler
try:
    from order_handler import (
        get_conversation_handler as get_order_conversation_handler,
        menu_handler as order_menu_handler,
        order_callback_handler,
        order_command_handler
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
    
    async def order_callback_handler(update, context):
        if hasattr(update, 'callback_query'):
            await update.callback_query.answer("❌ Fitur order sedang dalam perbaikan.", show_alert=True)
    
    async def order_command_handler(update, context):
        await update.message.reply_text("❌ Fitur order sedang dalam perbaikan.")

# Topup Handler
try:
    from topup_handler import (
        get_topup_conversation_handler,
        show_topup_menu,
        show_topup_history, 
        show_pending_topups,
        handle_proof_upload,
        get_topup_handlers
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
BOT_TOKEN = getattr(config, 'BOT_TOKEN', '')
ADMIN_IDS = getattr(config, 'ADMIN_TELEGRAM_IDS', [])

# ==================== BASIC COMMAND HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start - Menu utama"""
    try:
        user = update.message.from_user
        logger.info(f"User {user.id} ({user.username}) started the bot")
        
        # Get or create user in database
        saldo = 0
        try:
            user_id = database.get_or_create_user(str(user.id), user.username or "", user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception as e:
            logger.error(f"Error getting user saldo: {e}")
            saldo = 0
        
        # Main menu keyboard
        keyboard = [
            [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="order_menu")],
            [InlineKeyboardButton("💳 CEK SALDO", callback_data="main_menu_saldo")],
            [InlineKeyboardButton("📊 CEK STOK", callback_data="stock_menu")],
            [InlineKeyboardButton("📞 BANTUAN", callback_data="main_menu_help")],
            [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="topup_menu")]
        ]
        
        # Add admin button if user is admin
        if str(user.id) in ADMIN_IDS:
            keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="admin_menu")])
        
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
        error_msg = "❌ Terjadi error. Silakan coba lagi."
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(error_msg)

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
        elif data == "stock_menu":
            if STOK_AVAILABLE:
                await stock_akrab_callback(update, context)
            else:
                await query.message.reply_text("❌ Fitur stok sedang dalam perbaikan.")
        elif data == "admin_menu":
            if str(user.id) in ADMIN_IDS:
                if ADMIN_AVAILABLE:
                    await admin_menu(update, context)
                else:
                    await query.answer("❌ Fitur admin sedang dalam perbaikan!", show_alert=True)
            else:
                await query.answer("❌ Anda bukan admin!", show_alert=True)
        elif data == "order_menu":
            if ORDER_AVAILABLE:
                await order_menu_handler(update, context)
            else:
                await query.message.reply_text("❌ Fitur order sedang dalam perbaikan.")
        elif data == "topup_menu":
            if TOPUP_AVAILABLE:
                await show_topup_menu(update, context)
            else:
                await query.message.reply_text("❌ Fitur topup sedang dalam perbaikan.")
        else:
            await query.message.reply_text("❌ Menu tidak dikenali.")
            
    except Exception as e:
        logger.error(f"Error in main_menu_handler for {data}: {e}")
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu utama"""
    try:
        if hasattr(update, 'callback_query'):
            query = update.callback_query
            user = query.from_user
            message_func = query.edit_message_text
        else:
            user = update.message.from_user
            message_func = update.message.reply_text

        saldo = 0
        try:
            user_id = database.get_or_create_user(str(user.id), user.username or "", user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception as e:
            logger.error(f"Error getting user saldo: {e}")
            saldo = 0
        
        keyboard = [
            [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="order_menu")],
            [InlineKeyboardButton("💳 CEK SALDO", callback_data="main_menu_saldo")],
            [InlineKeyboardButton("📊 CEK STOK", callback_data="stock_menu")],
            [InlineKeyboardButton("📞 BANTUAN", callback_data="main_menu_help")],
            [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="topup_menu")]
        ]
        
        if str(user.id) in ADMIN_IDS:
            keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="admin_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            f"🏠 **MENU UTAMA**\n\n"
            f"Halo {user.full_name}!\n"
            f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
            f"Pilih menu di bawah:"
        )
        
        await message_func(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error in show_main_menu: {e}")
        error_msg = "❌ Terjadi error. Silakan coba lagi."
        if hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text(error_msg)
        else:
            await update.message.reply_text(error_msg)

async def show_saldo_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu saldo"""
    query = update.callback_query
    user = query.from_user
    
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username or "", user.full_name)
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
        user_id = database.get_or_create_user(str(user.id), user.username or "", user.full_name)
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
    if STOK_AVAILABLE:
        await stock_command(update, context)
    else:
        await update.message.reply_text("❌ Fitur stok sedang dalam perbaikan.")

async def order_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /order"""
    if ORDER_AVAILABLE:
        await order_command_handler(update, context)
    else:
        await update.message.reply_text("❌ Fitur order sedang dalam perbaikan.")

async def topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /topup"""
    if TOPUP_AVAILABLE:
        await show_topup_menu(update, context)
    else:
        await update.message.reply_text("❌ Fitur topup sedang dalam perbaikan.")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /admin"""
    if str(update.message.from_user.id) in ADMIN_IDS:
        if ADMIN_AVAILABLE:
            await admin_menu(update, context)
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
    
    # Log detailed error information
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    logger.error(f"Traceback: {tb_string}")
    
    if isinstance(update, Update):
        if update.message:
            await update.message.reply_text(
                "❌ Terjadi kesalahan sistem. Silakan coba lagi dalam beberapa saat.\n\n"
                "Jika error berlanjut, hubungi admin.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")],
                    [InlineKeyboardButton("📞 BANTUAN", callback_data="main_menu_help")]
                ])
            )
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                "❌ Terjadi kesalahan sistem. Silakan coba lagi.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]
                ])
            )

async def post_init(application: Application):
    """Function yang dijalankan setelah bot berhasil initialized"""
    logger.info("🤖 Bot has been initialized successfully!")
    
    try:
        # Get bot statistics
        stats = database.get_bot_statistics()
        
        status_info = (
            f"📊 Handler Status:\n"
            f"• Database: ✅\n"
            f"• Topup: {'✅' if TOPUP_AVAILABLE else '❌'}\n"
            f"• Order: {'✅' if ORDER_AVAILABLE else '❌'}\n"
            f"• Admin: {'✅' if ADMIN_AVAILABLE else '❌'}\n"
            f"• Stok: {'✅' if STOK_AVAILABLE else '❌'}\n"
        )
        
        stats_info = (
            f"📈 Bot Statistics:\n"
            f"• Total Users: {stats['total_users']}\n"
            f"• Active Users: {stats['active_users']}\n"
            f"• Products: {stats['active_products']}\n"
            f"• Revenue: Rp {stats['total_revenue']:,.0f}\n"
            f"• Pending Topups: {stats['pending_topups']}\n"
        )
        
        print("=" * 50)
        print("🤖 BOT STARTUP SUCCESSFUL")
        print("=" * 50)
        print(status_info)
        print(stats_info)
        print("=" * 50)
        
        # Send startup message to admin
        for admin_id in ADMIN_IDS:
            try:
                await application.bot.send_message(
                    chat_id=admin_id,
                    text=f"🤖 Bot started successfully!\n\n{status_info}\n{stats_info}",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send startup message to admin {admin_id}: {e}")
        
    except Exception as e:
        logger.error(f"Error in post_init: {e}")

# ==================== MAIN FUNCTION ====================
def main():
    """Main function - Initialize dan start bot"""
    try:
        logger.info("🚀 Starting Telegram Bot...")
        
        # Check BOT_TOKEN
        if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
            logger.critical("❌ Please set BOT_TOKEN in config.py")
            sys.exit(1)
        
        # Initialize database
        try:
            success = database.init_database()
            if success:
                logger.info("✅ Database initialized successfully")
            else:
                logger.error("❌ Database initialization failed")
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
        
        # Create Application
        persistence = PicklePersistence(filepath="bot_persistence")
        application = Application.builder()\
            .token(BOT_TOKEN)\
            .persistence(persistence)\
            .post_init(post_init)\
            .build()
        
        logger.info("✅ Application built successfully")
        
        # ==================== HANDLER REGISTRATION ====================
        
        # 1. CONVERSATION HANDLERS (PRIORITAS TERTINGGI)
        if TOPUP_AVAILABLE:
            topup_conv_handler = get_topup_conversation_handler()
            if topup_conv_handler:
                application.add_handler(topup_conv_handler)
                logger.info("✅ Topup conversation handler registered")
        
        if ORDER_AVAILABLE:
            order_conv_handler = get_order_conversation_handler()
            if order_conv_handler:
                application.add_handler(order_conv_handler)
                logger.info("✅ Order conversation handler registered")
        
        if edit_produk_conv_handler and ADMIN_AVAILABLE:
            application.add_handler(edit_produk_conv_handler)
            logger.info("✅ Admin edit produk conversation handler registered")
        
        # 2. TOPUP CALLBACK HANDLERS
        if TOPUP_AVAILABLE:
            topup_handlers = get_topup_handlers()
            for handler in topup_handlers:
                application.add_handler(handler)
            logger.info(f"✅ {len(topup_handlers)} Topup callback handlers registered")
        
        # 3. COMMAND HANDLERS
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("saldo", saldo_command))
        application.add_handler(CommandHandler("topup", topup_command))
        application.add_handler(CommandHandler("stock", stock_command_handler))
        application.add_handler(CommandHandler("order", order_command))
        application.add_handler(CommandHandler("admin", admin_command))
        
        # 4. ADMIN COMMAND HANDLERS
        if ADMIN_AVAILABLE:
            application.add_handler(broadcast_handler)
            application.add_handler(cek_user_handler)
            application.add_handler(jadikan_admin_handler)
            application.add_handler(topup_list_handler)
            logger.info("✅ Admin command handlers registered")
        
        # 5. CALLBACK QUERY HANDLERS - FIXED PATTERNS
        application.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^main_menu_"))
        
        # Admin callbacks
        if ADMIN_AVAILABLE:
            application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))
            application.add_handler(CallbackQueryHandler(approve_topup_handler, pattern="^admin_approve_topup_"))
        
        # Order callbacks  
        if ORDER_AVAILABLE:
            application.add_handler(CallbackQueryHandler(order_callback_handler, pattern="^order_"))
            application.add_handler(CallbackQueryHandler(order_menu_handler, pattern="^order_menu$"))
        
        # Stock callbacks
        if STOK_AVAILABLE:
            application.add_handler(CallbackQueryHandler(stok_callback_handler, pattern="^stock_"))
            application.add_handler(CallbackQueryHandler(stock_akrab_callback, pattern="^stock_menu$"))
        
        # Topup callbacks
        if TOPUP_AVAILABLE:
            application.add_handler(CallbackQueryHandler(show_topup_menu, pattern="^topup_menu$"))
            application.add_handler(CallbackQueryHandler(show_topup_history, pattern="^topup_history$"))
            application.add_handler(CallbackQueryHandler(show_pending_topups, pattern="^topup_pending_list$"))
            application.add_handler(CallbackQueryHandler(handle_proof_upload, pattern="^upload_proof_"))
        
        # 6. FALLBACK HANDLER (PRIORITAS TERENDAH)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))
        
        # 7. ERROR HANDLER
        application.add_error_handler(error_handler)
        
        logger.info("✅ All handlers registered successfully")
        
        # ==================== START BOT ====================
        logger.info("🤖 Bot is starting...")
        
        # Run bot
        if os.name == 'nt':  # Windows
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        print("=" * 60)
        print("🤖 BOT TELAH SIAP!")
        print("=" * 60)
        print("Fitur yang aktif:")
        print(f"• Topup: {'✅' if TOPUP_AVAILABLE else '❌'}")
        print(f"• Order: {'✅' if ORDER_AVAILABLE else '❌'}")
        print(f"• Admin: {'✅' if ADMIN_AVAILABLE else '❌'}")
        print(f"• Stok:  {'✅' if STOK_AVAILABLE else '❌'}")
        print("=" * 60)
        print("Bot sedang berjalan...")
        print("Tekan Ctrl+C untuk menghentikan bot")
        print("=" * 60)
        
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            timeout=30
        )
        
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
        print("\n🛑 Bot stopped successfully!")
    except Exception as e:
        logger.critical(f"❌ Failed to start bot: {e}")
        print(f"❌ CRITICAL ERROR: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
