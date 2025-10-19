#!/usr/bin/env python3
"""
Bot Telegram Full Feature - Integrated dengan semua handler
Author: Your Name
Version: 1.0
"""

import logging
import sys
import os
import asyncio
from typing import Dict, Any

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

# Import handlers dengan error handling
try:
    from topup_handler import (
        topup_conv_handler, 
        show_topup_menu, 
        show_manage_topup,
        handle_topup_manual,
        handle_topup_history
    )
except ImportError as e:
    print(f"Error importing topup_handler: {e}")
    # Fallback dummy handlers
    topup_conv_handler = None
    async def show_topup_menu(update, context): 
        await update.callback_query.message.reply_text("❌ Topup handler tidak tersedia")
    show_manage_topup = handle_topup_manual = handle_topup_history = show_topup_menu

try:
    import order_handler
    # Cek jika order_handler memiliki conversation handler
    if hasattr(order_handler, 'get_conversation_handler'):
        order_conv_handler = order_handler.get_conversation_handler()
    else:
        # Buat simple fallback
        order_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(lambda u,c: u.callback_query.message.reply_text("❌ Order system tidak tersedia"), pattern="^menu_order$")],
            states={},
            fallbacks=[]
        )
except ImportError as e:
    print(f"Error importing order_handler: {e}")
    order_conv_handler = None

try:
    from admin_handler import admin_menu, admin_callback_handler
except ImportError as e:
    print(f"Error importing admin_handler: {e}")
    async def admin_menu(update, context):
        await update.message.reply_text("❌ Admin handler tidak tersedia")
    async def admin_callback_handler(update, context):
        await update.callback_query.answer("❌ Admin features tidak tersedia")

try:
    import stok_handler
except ImportError as e:
    print(f"Error importing stok_handler: {e}")
    # Buat fallback untuk stok_handler
    class DummyStokHandler:
        async def stock_akrab_callback(update, context):
            await update.callback_query.message.reply_text("❌ Stok handler tidak tersedia")
        async def stock_command(update, context):
            await update.message.reply_text("❌ Stok handler tidak tersedia")
    stok_handler = DummyStokHandler()

# ==================== LOGGING SETUP ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ==================== GLOBAL VARIABLES ====================
BOT_TOKEN = config.BOT_TOKEN
ADMIN_IDS = set(str(admin_id) for admin_id in getattr(config, "ADMIN_TELEGRAM_IDS", []))

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
            [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="menu_order")],
            [InlineKeyboardButton("💳 CEK SALDO", callback_data="menu_saldo")],
            [InlineKeyboardButton("📊 CEK STOK", callback_data="menu_stock")],
            [InlineKeyboardButton("📞 BANTUAN", callback_data="menu_help")],
            [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="menu_topup")]
        ]
        
        # Add admin button if user is admin
        if str(user.id) in ADMIN_IDS:
            keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="menu_admin")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = (
            f"🤖 **Selamat Datang!**\n\n"
            f"Halo {user.full_name}!\n"
            f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
            f"Pilih menu di bawah untuk mulai berbelanja:\n\n"
            f"• 🛒 **BELI PRODUK** - Pesan pulsa, kuota, dll\n"
            f"• 💳 **CEK SALDO** - Lihat saldo akun\n" 
            f"• 📊 **CEK STOK** - Cek ketersediaan produk\n"
            f"• 💸 **TOP UP** - Tambah saldo\n"
            f"• 📞 **BANTUAN** - Bantuan penggunaan bot"
        )
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main menu handler untuk semua callback"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    logger.info(f"Menu callback: {data} from user {user.id}")
    
    try:
        if data == "menu_main":
            await show_main_menu(update, context)
        elif data == "menu_saldo":
            await show_saldo_menu(update, context)
        elif data == "menu_help":
            await show_help_menu(update, context)
        elif data == "menu_stock":
            await stok_handler.stock_akrab_callback(update, context)
        elif data == "menu_topup":
            await show_topup_menu(update, context)
        elif data == "menu_admin":
            if str(user.id) in ADMIN_IDS:
                await admin_menu(update, context)
            else:
                await query.answer("❌ Anda bukan admin!", show_alert=True)
        elif data == "menu_order":
            # Direct order handler call
            try:
                await order_handler.menu_handler(update, context)
            except Exception as e:
                logger.error(f"Error in order handler: {e}")
                await query.message.reply_text("❌ Sistem order sedang tidak tersedia.")
        else:
            await query.message.reply_text("❌ Menu tidak dikenali.")
            
    except Exception as e:
        logger.error(f"Error in menu_handler for {data}: {e}")
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
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="menu_order")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="menu_saldo")],
        [InlineKeyboardButton("📊 CEK STOK", callback_data="menu_stock")],
        [InlineKeyboardButton("📞 BANTUAN", callback_data="menu_help")],
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="menu_topup")]
    ]
    
    if str(user.id) in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="menu_admin")])
    
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
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="menu_topup")],
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")]
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
        "3. Transfer sesuai instruksi\n"
        "4. Tunggu konfirmasi admin\n\n"
        
        "**FITUR LAIN:**\n"
        "• 📊 **CEK STOK** - Lihat ketersediaan produk\n"
        "• 💳 **CEK SALDO** - Lihat saldo akun\n"
        "• 📞 **BANTUAN** - Menu bantuan ini\n\n"
        
        "**BUTUH BANTUAN?**\n"
        "Hubungi Admin untuk bantuan lebih lanjut.\n"
        "CS siap membantu!\n\n"
        
        "**KETENTUAN:**\n"
        "• Semua transaksi bersifat final\n"
        "• Tidak ada pengembalian dana\n"
        "• Pastikan data benar sebelum order"
    )
    
    keyboard = [
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")]
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
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="menu_topup")],
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")]
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
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")]
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
        "• /admin - Panel admin\n\n"
        
        "**CARA PENGGUNAAN:**\n"
        "Gunakan tombol menu untuk navigasi yang mudah!\n"
        "Atau ketik command di atas."
    )
    
    await update.message.reply_text(
        help_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /stock"""
    await stok_handler.stock_command(update, context)

async def order_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /order"""
    try:
        await order_handler.menu_handler(update, context)
    except Exception as e:
        logger.error(f"Error in order command: {e}")
        await update.message.reply_text("❌ Sistem order sedang tidak tersedia.")

# ==================== UTILITY HANDLERS ====================
async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk pesan yang tidak dikenal"""
    logger.debug(f"Unknown message from {update.message.from_user.id}: {update.message.text}")
    
    await update.message.reply_text(
        "🤔 Saya tidak mengerti perintah tersebut.\n\n"
        "Gunakan /help untuk melihat daftar perintah yang tersedia "
        "atau gunakan tombol menu untuk navigasi.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📞 BANTUAN", callback_data="menu_help")],
            [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")]
        ])
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler untuk menangani semua error"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
    
    if isinstance(update, Update):
        if update.message:
            await update.message.reply_text(
                "❌ Terjadi kesalahan sistem. Silakan coba lagi dalam beberapa saat.\n\n"
                "Jika error berlanjut, hubungi admin.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")],
                    [InlineKeyboardButton("📞 BANTUAN", callback_data="menu_help")]
                ])
            )
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                "❌ Terjadi kesalahan sistem. Silakan coba lagi.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")]
                ])
            )

async def post_init(application: Application):
    """Function yang dijalankan setelah bot berhasil initialized"""
    logger.info("🤖 Bot has been initialized successfully!")
    
    # Kirim notification ke admin bahwa bot aktif
    admin_ids = getattr(config, 'ADMIN_TELEGRAM_IDS', [])
    for admin_id in admin_ids:
        try:
            await application.bot.send_message(
                chat_id=admin_id,
                text="✅ **Bot Started Successfully!**\n\n"
                     f"🤖 Bot is now running and ready to serve users.\n"
                     f"⏰ Started at: {database.get_current_timestamp()}\n\n"
                     "Use /admin to access admin panel.",
                parse_mode='Markdown'
            )
            logger.info(f"✅ Startup notification sent to admin {admin_id}")
        except Exception as e:
            logger.error(f"❌ Failed to send startup notification to admin {admin_id}: {e}")

# ==================== MAIN FUNCTION ====================
def main():
    """Main function - Initialize dan start bot"""
    try:
        logger.info("🚀 Starting Telegram Bot...")
        
        # Initialize database
        database.init_database()
        logger.info("✅ Database initialized")
        
        # Create Application dengan persistence
        persistence = PicklePersistence(filepath="bot_persistence")
        application = Application.builder()\
            .token(BOT_TOKEN)\
            .persistence(persistence)\
            .post_init(post_init)\
            .build()
        
        logger.info("✅ Application built successfully")
        
        # ==================== HANDLER REGISTRATION ====================
        
        # 1. CONVERSATION HANDLERS (harus pertama)
        logger.info("📝 Registering conversation handlers...")
        
        # Topup Conversation Handler
        if topup_conv_handler:
            application.add_handler(topup_conv_handler)
            logger.info("  ✅ Topup conversation handler registered")
        else:
            logger.warning("  ⚠️ Topup conversation handler not available")
        
        # Order Conversation Handler  
        if order_conv_handler:
            application.add_handler(order_conv_handler)
            logger.info("  ✅ Order conversation handler registered")
        else:
            logger.warning("  ⚠️ Order conversation handler not available")
        
        # 2. COMMAND HANDLERS
        logger.info("⌨️ Registering command handlers...")
        
        command_handlers = [
            CommandHandler("start", start),
            CommandHandler("help", help_command),
            CommandHandler("saldo", saldo_command),
            CommandHandler("topup", show_topup_menu),
            CommandHandler("stock", stock_command),
            CommandHandler("order", order_command),
            CommandHandler("admin", admin_menu),
        ]
        
        for handler in command_handlers:
            application.add_handler(handler)
        logger.info("  ✅ All command handlers registered")
        
        # 3. CALLBACK QUERY HANDLERS
        logger.info("🔘 Registering callback query handlers...")
        
        callback_handlers = [
            # Main menu handlers
            CallbackQueryHandler(menu_handler, pattern="^menu_"),
            
            # Topup handlers
            CallbackQueryHandler(show_topup_menu, pattern="^menu_topup$"),
            CallbackQueryHandler(show_manage_topup, pattern="^manage_topup$"),
            CallbackQueryHandler(handle_topup_history, pattern="^topup_history$"),
            CallbackQueryHandler(handle_topup_manual, pattern="^topup_manual$"),
            
            # Admin handlers
            CallbackQueryHandler(admin_callback_handler, pattern="^admin_"),
        ]
        
        for handler in callback_handlers:
            application.add_handler(handler)
        logger.info("  ✅ All callback query handlers registered")
        
        # 4. MESSAGE HANDLERS (harus terakhir)
        logger.info("💬 Registering message handlers...")
        
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            unknown_message
        ))
        logger.info("  ✅ Message handler registered")
        
        # 5. ERROR HANDLER
        application.add_error_handler(error_handler)
        logger.info("  ✅ Error handler registered")
        
        # ==================== START BOT ====================
        logger.info("🎉 All handlers registered successfully!")
        logger.info("🤖 Bot is now starting polling...")
        
        # Start bot polling
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            timeout=30,
            pool_timeout=30
        )
        
    except Exception as e:
        logger.critical(f"💥 Failed to start bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
