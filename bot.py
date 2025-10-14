import logging
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
from topup_handler import topup_conv_handler, show_topup_menu, show_manage_topup
import stok_handler

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = config.BOT_TOKEN
ADMIN_IDS = set(str(admin_id) for admin_id in getattr(config, "ADMIN_TELEGRAM_IDS", []))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start"""
    try:
        user = update.message.from_user
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
        
        await update.message.reply_text(
            f"🤖 **Selamat Datang!**\n\n"
            f"Halo {user.full_name}!\n"
            f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
            f"Pilih menu di bawah untuk mulai berbelanja.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /help"""
    await update.message.reply_text(
        "📞 **BANTUAN**\n\n"
        "Untuk bantuan, silakan hubungi admin.\n"
        "Gunakan menu di bawah untuk navigasi.",
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
    
    await update.message.reply_text(
        f"💰 **SALDO ANDA**\n\n"
        f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
        f"Gunakan menu Top Up untuk menambah saldo.",
        parse_mode='Markdown'
    )

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler utama untuk menu callback"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    logger.info(f"Menu callback received: {data}")
    
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
            await admin_handler.admin_menu_callback(update, context)
        elif data == "menu_order":
            await order_handler.menu_handler(update, context)
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
    
    await query.edit_message_text(
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
    
    await query.edit_message_text(
        f"💰 **SALDO ANDA**\n\n"
        f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
        f"Gunakan menu Top Up untuk menambah saldo.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu bantuan"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📞 **BANTUAN**\n\n"
        "Untuk bantuan, silakan hubungi admin.\n"
        "Kami siap membantu 24/7.\n\n"
        "**Fitur Bot:**\n"
        "• 🛒 Beli Produk\n"
        "• 💳 Top Up Saldo\n" 
        "• 📊 Cek Stok\n"
        "• 📞 Bantuan",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"Update {update} caused error {context.error}", exc_info=True)
    
    # Coba kirim pesan error ke user
    try:
        if update and hasattr(update, 'effective_chat'):
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Terjadi error sistem. Silakan coba lagi nanti."
            )
    except Exception as e:
        logger.error(f"Error sending error message: {e}")

def main():
    """Main function untuk menjalankan bot"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        logger.info("🤖 Starting bot with integrated menu system...")
        
        # Basic command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("saldo", saldo_command))
        application.add_handler(CommandHandler("stock", stok_handler.stock_command))
        
        # Admin command handlers
        if hasattr(admin_handler, 'admin_menu'):
            application.add_handler(CommandHandler("admin", admin_handler.admin_menu))
        
        # Conversation handlers - IMPORTANT: Register order handler first
        if hasattr(order_handler, 'get_conversation_handler'):
            application.add_handler(order_handler.get_conversation_handler())
        
        # Topup conversation handler
        application.add_handler(topup_conv_handler)
        
        # Admin command handlers
        if hasattr(admin_handler, 'approve_topup_command'):
            application.add_handler(CommandHandler("approve_topup", admin_handler.approve_topup_command))
        if hasattr(admin_handler, 'cancel_topup_command'):
            application.add_handler(CommandHandler("cancel_topup", admin_handler.cancel_topup_command))
        
        # Menu callback handlers - URUTAN PENTING!
        application.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu_"))
        
        # Admin callback handlers
        application.add_handler(CallbackQueryHandler(admin_handler.admin_callback_handler, pattern="^admin_"))
        application.add_handler(CallbackQueryHandler(admin_handler.edit_produk_menu_handler, pattern="^edit_"))
        application.add_handler(CallbackQueryHandler(admin_handler.select_product_handler, pattern="^select_product:"))
        
        # Topup callback handlers - TAMBAHKAN INI
        application.add_handler(CallbackQueryHandler(show_manage_topup, pattern="^manage_topup$"))
        
        # Order callback handler (fallback untuk order)
        application.add_handler(CallbackQueryHandler(order_handler.menu_handler, pattern="^order_"))
        
        # Global error handler
        application.add_error_handler(error_handler)
        
        logger.info("✅ Bot started successfully!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == '__main__':
    main()
