import logging
import sys
from telegram import Update
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
from topup_handler import (
    topup_conv_handler, 
    show_topup_menu,
    handle_topup_manual
)

# Setup logging dengan level DEBUG
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

BOT_TOKEN = config.BOT_TOKEN

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start - MINIMAL VERSION"""
    try:
        user = update.message.from_user
        saldo = 0
        
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception as e:
            logger.error(f"Error getting user saldo: {e}")
            saldo = 0
        
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = [
            [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="menu_order")],
            [InlineKeyboardButton("💳 CEK SALDO", callback_data="menu_saldo")],
            [InlineKeyboardButton("📊 CEK STOK", callback_data="menu_stock")],
            [InlineKeyboardButton("📞 BANTUAN", callback_data="menu_help")],
            [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="menu_topup")]
        ]
        
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

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler utama untuk menu callback - MINIMAL VERSION"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    logger.info(f"🔧 [MENU_HANDLER] Menu callback received: {data}")
    
    try:
        if data == "menu_topup":
            await show_topup_menu(update, context)
        else:
            # Untuk sementara, handle semua menu lain dengan pesan sederhana
            await query.message.reply_text("❌ Fitur ini sedang dalam pengembangan.")
            
    except Exception as e:
        logger.error(f"Error in menu_handler for {data}: {e}")
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"❌ [ERROR_HANDLER] Update {update} caused error {context.error}", exc_info=True)

def main():
    """Main function - MINIMAL VERSION"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        logger.info("🤖 Starting bot dengan handler MINIMAL...")
        
        # ========== HANYA HANDLER YANG ESSENTIAL ==========
        
        # 1. Conversation handlers PERTAMA dan SATU-SATUNYA yang penting
        logger.info("🔧 [MAIN] Registering TOPUP conversation handler...")
        application.add_handler(topup_conv_handler)
        logger.info("✅ [MAIN] topup_conv_handler registered")
        
        # 2. Command start saja
        logger.info("🔧 [MAIN] Registering start command...")
        application.add_handler(CommandHandler("start", start))
        logger.info("✅ [MAIN] start command registered")
        
        # 3. Menu callback handler untuk topup saja
        logger.info("🔧 [MAIN] Registering menu_topup callback...")
        application.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu_topup$"))
        application.add_handler(CallbackQueryHandler(handle_topup_manual, pattern="^topup_manual$"))
        logger.info("✅ [MAIN] menu callbacks registered")
        
        # 4. TIDAK ADA fallback handler - biarkan conversation handler menangani semua
        
        # 5. Error handler
        application.add_error_handler(error_handler)
        
        # Debug: Print semua handler yang terdaftar
        logger.info("=== 🔍 MINIMAL HANDLERS DEBUG ===")
        for i, handler in enumerate(application.handlers[0]):
            handler_type = type(handler).__name__
            logger.info(f"Handler {i}: {handler_type}")
            
            if isinstance(handler, ConversationHandler):
                logger.info(f"  - ConversationHandler:")
                logger.info(f"    * Entry points: {len(handler.entry_points)}")
                for ep in handler.entry_points:
                    logger.info(f"      - {ep}")
                logger.info(f"    * States: {len(handler.states)}")
                for state, handlers in handler.states.items():
                    logger.info(f"      - State {state}: {len(handlers)} handlers")
        
        logger.info("=== ✅ END MINIMAL HANDLERS ===")
        
        logger.info("✅ Bot MINIMAL berhasil dimulai!")
        logger.info("📱 Bot siap menerima pesan...")
        
        # Jalankan bot
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.error(f"Gagal memulai bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
