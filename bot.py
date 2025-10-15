import logging
import sys
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    MessageHandler,
    ConversationHandler
)
import config
import database
import order_handler
import admin_handler
from topup_handler import (
    topup_conv_handler, 
    show_topup_menu, 
    show_manage_topup,
    handle_topup_manual,
    handle_topup_history
)
import stok_handler

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

BOT_TOKEN = config.BOT_TOKEN
ADMIN_IDS = set(str(admin_id) for admin_id in getattr(config, "ADMIN_TELEGRAM_IDS", []))

# State constants untuk conversation handlers
MAIN_MENU = 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start"""
    try:
        user = update.message.from_user
        logger.info(f"User {user.id} ({user.username}) started the bot")
        
        saldo = 0
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
            logger.info(f"User saldo retrieved: {saldo}")
        except Exception as e:
            logger.error(f"Error getting user saldo: {e}")
            saldo = 0
        
        # Clear any existing user data
        context.user_data.clear()
        
        keyboard = [
            [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="menu_order")],
            [InlineKeyboardButton("💳 CEK SALDO", callback_data="menu_saldo")],
            [InlineKeyboardButton("📊 CEK STOK", callback_data="menu_stock")],
            [InlineKeyboardButton("📞 BANTUAN", callback_data="menu_help")],
            [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="menu_topup")]
        ]
        
        if str(user.id) in ADMIN_IDS:
            keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="menu_admin")])
            logger.info(f"Admin menu added for user {user.id}")
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🤖 **Selamat Datang!**\n\n"
            f"Halo {user.full_name}!\n"
            f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
            f"Pilih menu di bawah untuk mulai berbelanja.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in start command: {e}", exc_info=True)
        await update.message.reply_text("❌ Terjadi error saat memulai bot. Silakan coba lagi.")

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler utama untuk menu callback"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    logger.info(f"Menu callback received from {user.id}: {data}")
    
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
            await show_manage_topup(update, context)
        elif data == "menu_admin":
            if str(user.id) in ADMIN_IDS:
                await admin_handler.admin_menu(update, context)
            else:
                await query.message.reply_text("❌ Akses ditolak. Hanya admin yang bisa mengakses menu ini.")
        elif data == "menu_order":
            await order_handler.menu_handler(update, context)
        else:
            logger.warning(f"Unknown menu callback: {data}")
            await query.message.reply_text("❌ Menu tidak dikenali.")
            
    except Exception as e:
        logger.error(f"Error in menu_handler for {data}: {e}", exc_info=True)
        await query.message.reply_text("❌ Terjadi error saat memproses menu. Silakan coba lagi.")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu utama"""
    try:
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
        
        text = (
            f"🏠 **MENU UTAMA**\n\n"
            f"Halo {user.full_name}!\n"
            f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
            f"Pilih menu di bawah:"
        )
        
        try:
            await query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not edit message, sending new: {e}")
            await query.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error in show_main_menu: {e}", exc_info=True)
        if update.callback_query:
            await update.callback_query.message.reply_text("❌ Error menampilkan menu utama.")

async def show_saldo_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu saldo"""
    try:
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
            [InlineKeyboardButton("📋 RIWAYAT TOP UP", callback_data="topup_history")],
            [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            f"💰 **SALDO ANDA**\n\n"
            f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
            f"Gunakan menu Top Up untuk menambah saldo."
        )
        
        try:
            await query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not edit message, sending new: {e}")
            await query.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error in show_saldo_menu: {e}", exc_info=True)
        if update.callback_query:
            await update.callback_query.message.reply_text("❌ Error menampilkan saldo.")

async def show_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu bantuan"""
    try:
        query = update.callback_query
        
        keyboard = [
            [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")],
            [InlineKeyboardButton("📞 HUBUNGI ADMIN", url="https://t.me/username_admin")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "📞 **BANTUAN**\n\n"
            "**Cara menggunakan bot:**\n"
            "• 🛒 **Beli Produk** - Pilih dan beli produk yang tersedia\n"
            "• 💳 **Top Up Saldo** - Isi saldo untuk bertransaksi\n"
            "• 📊 **Cek Stok** - Lihat ketersediaan produk\n"
            "• 📞 **Bantuan** - Dapatkan bantuan\n\n"
            "**Untuk pertanyaan lebih lanjut:**\n"
            "Hubungi admin melalui tombol di bawah."
        )
        
        try:
            await query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not edit message, sending new: {e}")
            await query.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error in show_help_menu: {e}", exc_info=True)
        if update.callback_query:
            await update.callback_query.message.reply_text("❌ Error menampilkan bantuan.")

async def saldo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /saldo"""
    try:
        user = update.message.from_user
        logger.info(f"Saldo command from user {user.id}")
        
        saldo = 0
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception as e:
            logger.error(f"Error getting user saldo: {e}")
            saldo = 0
        
        keyboard = [
            [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="menu_topup")],
            [InlineKeyboardButton("📋 RIWAYAT TOP UP", callback_data="topup_history")],
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
        
    except Exception as e:
        logger.error(f"Error in saldo_command: {e}", exc_info=True)
        await update.message.reply_text("❌ Error mengambil data saldo.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /help"""
    try:
        user = update.message.from_user
        logger.info(f"Help command from user {user.id}")
        
        keyboard = [
            [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")],
            [InlineKeyboardButton("📞 HUBUNGI ADMIN", url="https://t.me/username_admin")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📞 **BANTUAN**\n\n"
            "**Cara menggunakan bot:**\n"
            "• 🛒 **Beli Produk** - Pilih dan beli produk yang tersedia\n"
            "• 💳 **Top Up Saldo** - Isi saldo untuk bertransaksi\n"
            "• 📊 **Cek Stok** - Lihat ketersediaan produk\n"
            "• 📞 **Bantuan** - Dapatkan bantuan\n\n"
            "**Untuk pertanyaan lebih lanjut:**\n"
            "Hubungi admin melalui tombol di bawah.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in help_command: {e}", exc_info=True)
        await update.message.reply_text("❌ Error menampilkan bantuan.")

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /stock"""
    try:
        await stok_handler.stock_command(update, context)
    except Exception as e:
        logger.error(f"Error in stock_command: {e}", exc_info=True)
        await update.message.reply_text("❌ Error menampilkan stok.")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /admin"""
    try:
        user = update.message.from_user
        if str(user.id) in ADMIN_IDS:
            await admin_handler.admin_menu(update, context)
        else:
            await update.message.reply_text("❌ Akses ditolak. Hanya admin yang bisa mengakses menu ini.")
    except Exception as e:
        logger.error(f"Error in admin_command: {e}", exc_info=True)
        await update.message.reply_text("❌ Error mengakses admin panel.")

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command yang tidak dikenal"""
    await update.message.reply_text(
        "❌ Perintah tidak dikenali.\n\n"
        "Gunakan /start untuk memulai bot atau /help untuk bantuan."
    )

async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk pesan teks yang tidak dikenali"""
    # Biarkan conversation handler yang menangani pesan teks
    logger.debug(f"Ignoring unknown text message: {update.message.text}")
    return

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler yang komprehensif"""
    logger.error("Exception occurred while handling update:", exc_info=context.error)
    
    # Log detail error
    error_msg = f"Error: {context.error}"
    if update:
        if hasattr(update, 'callback_query') and update.callback_query:
            error_msg += f" | Callback: {update.callback_query.data}"
        elif hasattr(update, 'message') and update.message:
            error_msg += f" | Message: {update.message.text}"
    
    logger.error(error_msg)
    
    # Kirim pesan error ke user
    try:
        if isinstance(update, Update):
            error_text = "❌ Terjadi kesalahan sistem. Silakan coba lagi atau gunakan /start untuk memulai ulang."
            
            if update.message:
                await update.message.reply_text(error_text)
            elif update.callback_query:
                await update.callback_query.message.reply_text(error_text)
    except Exception as e:
        logger.error(f"Failed to send error message to user: {e}")

async def post_init(application: Application):
    """Function yang dijalankan setelah bot berhasil diinisialisasi"""
    logger.info("🤖 Bot successfully initialized!")
    logger.info("📊 Handler groups summary:")
    
    for group_num in sorted(application.handlers.keys()):
        handlers = application.handlers[group_num]
        logger.info(f"  Group {group_num}: {len(handlers)} handlers")
        for handler in handlers:
            logger.info(f"    - {type(handler).__name__}")

def main():
    """Main function dengan urutan handler yang sempurna"""
    try:
        # Create application
        application = Application.builder().token(BOT_TOKEN).build()
        
        logger.info("🚀 Starting bot dengan konfigurasi sempurna...")
        
        # ========== URUTAN HANDLER YANG OPTIMAL ==========
        
        # 1. CONVERSATION HANDLERS (priority tertinggi)
        logger.info("1. Registering conversation handlers...")
        application.add_handler(topup_conv_handler)
        
        # Tambahkan order conversation handler jika ada
        if hasattr(order_handler, 'get_conversation_handler'):
            try:
                order_conv_handler = order_handler.get_conversation_handler()
                if order_conv_handler:
                    application.add_handler(order_conv_handler)
                    logger.info("  ✓ Order conversation handler registered")
            except Exception as e:
                logger.error(f"  ✗ Failed to register order conversation handler: {e}")
        
        # 2. COMMAND HANDLERS
        logger.info("2. Registering command handlers...")
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("saldo", saldo_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("stock", stock_command))
        application.add_handler(CommandHandler("admin", admin_command))
        
        # Fallback untuk unknown commands
        application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
        
        # 3. CALLBACK QUERY HANDLERS
        logger.info("3. Registering callback query handlers...")
        
        # Menu handlers
        application.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu_"))
        
        # Topup handlers
        application.add_handler(CallbackQueryHandler(show_manage_topup, pattern="^manage_topup$"))
        application.add_handler(CallbackQueryHandler(handle_topup_history, pattern="^topup_history$"))
        application.add_handler(CallbackQueryHandler(handle_topup_manual, pattern="^topup_manual$"))
        
        # Admin handlers
        application.add_handler(CallbackQueryHandler(admin_handler.admin_callback_handler, pattern="^admin_"))
        
        # Order handlers (jika ada)
        if hasattr(order_handler, 'callback_handler'):
            application.add_handler(CallbackQueryHandler(order_handler.callback_handler, pattern="^order_"))
        
        # Stock handlers (jika ada)
        if hasattr(stok_handler, 'callback_handler'):
            application.add_handler(CallbackQueryHandler(stok_handler.callback_handler, pattern="^stock_"))
        
        # 4. FALLBACK MESSAGE HANDLER (priority terendah)
        logger.info("4. Registering fallback message handler...")
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            unknown_message
        ))
        
        # 5. ERROR HANDLER
        application.add_error_handler(error_handler)
        
        # 6. POST INIT
        application.post_init = post_init
        
        logger.info("✅ Bot configuration completed successfully!")
        logger.info("📋 Final handler summary:")
        
        # Print final handler summary
        for group_num in sorted(application.handlers.keys()):
            handlers = application.handlers[group_num]
            logger.info(f"Group {group_num} ({len(handlers)} handlers):")
            for handler in handlers:
                handler_info = type(handler).__name__
                if hasattr(handler, 'pattern') and handler.pattern:
                    handler_info += f" [pattern: {handler.pattern}]"
                logger.info(f"  → {handler_info}")
        
        # Jalankan bot
        logger.info("🎯 Bot is now running...")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            close_loop=False
        )
        
    except Exception as e:
        logger.error(f"💥 Failed to start bot: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
