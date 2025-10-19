#!/usr/bin/env python3
"""
Bot Telegram Full Feature dengan Database Manager Lengkap
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
import database  # Now using the new DatabaseManager

# Import handlers
try:
    from topup_handler import (
        topup_conv_handler, 
        show_topup_menu, 
        show_manage_topup,
        handle_topup_manual,
        handle_topup_history
    )
    TOPUP_AVAILABLE = True
except ImportError as e:
    print(f"❌ Error importing topup_handler: {e}")
    TOPUP_AVAILABLE = False
    topup_conv_handler = None
    async def show_topup_menu(update, context): 
        if hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text("❌ Topup handler tidak tersedia")
        else:
            await update.message.reply_text("❌ Topup handler tidak tersedia")
    show_manage_topup = handle_topup_manual = handle_topup_history = show_topup_menu

try:
    import order_handler
    ORDER_AVAILABLE = True
except ImportError as e:
    print(f"❌ Error importing order_handler: {e}")
    ORDER_AVAILABLE = False
    async def order_menu_handler(update, context):
        if hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text("❌ Order system tidak tersedia")
        else:
            await update.message.reply_text("❌ Order system tidak tersedia")

try:
    import stok_handler
    STOK_AVAILABLE = True
except ImportError as e:
    print(f"❌ Error importing stok_handler: {e}")
    STOK_AVAILABLE = False
    class DummyStokHandler:
        @staticmethod
        async def stock_akrab_callback(update, context):
            await update.callback_query.message.reply_text("❌ Stok handler tidak tersedia")
        @staticmethod
        async def stock_command(update, context):
            await update.message.reply_text("❌ Stok handler tidak tersedia")
    stok_handler = DummyStokHandler()

try:
    from admin_handler import (
        admin_menu,
        admin_callback_handler,
        edit_produk_conv_handler,
        broadcast_handler,
        cek_user_handler,
        jadikan_admin_handler,
        topup_list_handler,
        get_admin_handlers
    )
    ADMIN_AVAILABLE = True
except ImportError as e:
    print(f"❌ Error importing admin_handler: {e}")
    ADMIN_AVAILABLE = False
    async def admin_menu(update, context):
        if hasattr(update, 'message'):
            await update.message.reply_text("❌ Admin handler tidak tersedia")
        else:
            await update.callback_query.message.reply_text("❌ Admin handler tidak tersedia")
    async def admin_callback_handler(update, context):
        await update.callback_query.answer("❌ Admin features tidak tersedia", show_alert=True)
    edit_produk_conv_handler = None

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
ADMIN_IDS = set(str(admin_id) for admin_id in config.ADMIN_TELEGRAM_IDS)

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
        "**BUTUH BANTUAN?**\n"
        "Hubungi Admin untuk bantuan lebih lanjut."
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

async def topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /topup"""
    await show_topup_menu(update, context)

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
    
    # Status handler availability
    status_info = (
        f"📊 Handler Status:\n"
        f"• Database: ✅ (Advanced)\n"
        f"• Topup: {'✅' if TOPUP_AVAILABLE else '❌'}\n"
        f"• Order: {'✅' if ORDER_AVAILABLE else '❌'}\n"
        f"• Admin: {'✅' if ADMIN_AVAILABLE else '❌'}\n"
        f"• Stok: {'✅' if STOK_AVAILABLE else '❌'}\n"
    )
    print(status_info)
    
    # Get bot statistics
    try:
        stats = database.get_bot_statistics()
        stats_info = (
            f"📈 Bot Statistics:\n"
            f"• Users: {stats['total_users']}\n"
            f"• Active Users: {stats['active_users']}\n"
            f"• Products: {stats['active_products']}\n"
            f"• Revenue: Rp {stats['total_revenue']:,.0f}\n"
            f"• Pending Topups: {stats['pending_topups']}\n"
        )
        print(stats_info)
    except Exception as e:
        logger.error(f"Error getting bot statistics: {e}")
    
    # Kirim notification ke admin bahwa bot aktif
    admin_ids = getattr(config, 'ADMIN_TELEGRAM_IDS', [])
    for admin_id in admin_ids:
        try:
            if not str(admin_id).isdigit():
                logger.warning(f"⚠️ Invalid admin ID format: {admin_id}")
                continue
                
            await application.bot.send_message(
                chat_id=int(admin_id),
                text="✅ **Bot Started Successfully!**\n\n"
                     f"🤖 Bot is now running with advanced database system.\n"
                     f"⏰ Started at: {database.get_current_timestamp()}\n\n"
                     f"{status_info}",
                parse_mode='Markdown'
            )
            logger.info(f"✅ Startup notification sent to admin {admin_id}")
        except Exception as e:
            logger.warning(f"⚠️ Cannot send notification to admin {admin_id}: {e}")

# ==================== MAIN FUNCTION ====================
def main():
    """Main function - Initialize dan start bot"""
    try:
        logger.info("🚀 Starting Telegram Bot with Advanced Database...")
        
        # Check BOT_TOKEN
        if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
            logger.critical("❌ Please set BOT_TOKEN in config.py")
            sys.exit(1)
        
        # Initialize database dengan new DatabaseManager
        try:
            database.init_database()
            logger.info("✅ Advanced database initialized successfully")
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            sys.exit(1)
        
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
        
        # Admin Edit Produk Conversation Handler
        if edit_produk_conv_handler:
            application.add_handler(edit_produk_conv_handler)
            logger.info("  ✅ Admin edit produk conversation handler registered")
        else:
            logger.warning("  ⚠️ Admin edit produk conversation handler not available")
        
        # 2. COMMAND HANDLERS
        logger.info("⌨️ Registering command handlers...")
        
        command_handlers = [
            CommandHandler("start", start),
            CommandHandler("help", help_command),
            CommandHandler("saldo", saldo_command),
            CommandHandler("topup", topup_command),
            CommandHandler("stock", stock_command),
            CommandHandler("order", order_command),
        ]
        
        # Add admin commands if available
        if ADMIN_AVAILABLE:
            command_handlers.extend([
                CommandHandler("admin", admin_menu),
                CommandHandler("broadcast", broadcast_handler),
                CommandHandler("cek_user", cek_user_handler),
                CommandHandler("jadikan_admin", jadikan_admin_handler),
                CommandHandler("topup_list", topup_list_handler),
            ])
        
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
        ]
        
        # Add admin callback handlers if available
        if ADMIN_AVAILABLE:
            callback_handlers.extend([
                CallbackQueryHandler(admin_callback_handler, pattern="^admin_"),
            ])
        
        for handler in callback_handlers:
            application.add_handler(handler)
        logger.info("  ✅ All callback query handlers registered")
        
        # 4. MESSAGE HANDLERS (harus terakhir)
        logger.info("💬 Registering message handlers...")
        
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            unknown_message
        ))
        
        # 5. ERROR HANDLER
        application.add_error_handler(error_handler)
        
        logger.info("🎉 All handlers registered successfully!")
        
        # Start Bot Polling
        logger.info("🤖 Bot is starting polling...")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.critical(f"💥 Failed to start bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
