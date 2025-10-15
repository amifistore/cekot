import logging
import sys
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
from topup_handler import topup_conv_handler, show_topup_menu, handle_topup_manual

# Setup logging EXTREME DEBUG
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

BOT_TOKEN = config.BOT_TOKEN

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
    """Handler utama untuk menu callback"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    logger.debug(f"🔧 [MENU_HANDLER] Menu callback received: {data}")
    
    try:
        if data == "menu_topup":
            await show_topup_menu(update, context)
        else:
            await query.message.reply_text("❌ Fitur sedang dikembangkan.")
            
    except Exception as e:
        logger.error(f"Error in menu_handler: {e}")
        await query.message.reply_text("❌ Terjadi error.")

# Handler untuk melihat update yang diterima
async def debug_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug handler untuk melihat semua pesan"""
    logger.debug(f"🔍 [DEBUG_ALL] Update received: {update}")
    
    if update.message:
        logger.debug(f"🔍 [DEBUG_ALL] Message text: '{update.message.text}'")
        logger.debug(f"🔍 [DEBUG_ALL] Message type: {update.message.content_type}")
        
    # JANGAN lakukan apa-apa, biarkan handler lain yang proses
    return

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"❌ [ERROR_HANDLER] Error: {context.error}")
    logger.error(f"❌ [ERROR_HANDLER] Update: {update}")

def main():
    """Main function dengan DEBUG EXTREME"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        logger.info("🤖 Starting bot dengan DEBUG EXTREME...")
        
        # ========== URUTAN HANDLER YANG SUPER SIMPLE ==========
        
        # 1. DEBUG HANDLER - untuk melihat semua pesan yang masuk
        logger.info("1. Registering DEBUG handler...")
        application.add_handler(MessageHandler(filters.ALL, debug_all_messages), group=1)
        
        # 2. CONVERSATION HANDLER - group 2 (lebih tinggi priority)
        logger.info("2. Registering CONVERSATION handler...")
        application.add_handler(topup_conv_handler, group=2)
        
        # 3. COMMAND HANDLERS - group 3
        logger.info("3. Registering COMMAND handlers...")
        application.add_handler(CommandHandler("start", start), group=3)
        
        # 4. CALLBACK HANDLERS - group 4  
        logger.info("4. Registering CALLBACK handlers...")
        application.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu_"), group=4)
        application.add_handler(CallbackQueryHandler(handle_topup_manual, pattern="^topup_manual$"), group=4)
        
        # 5. ERROR HANDLER
        application.add_error_handler(error_handler)
        
        # Print handler groups
        logger.info("=== 🔍 HANDLER GROUPS ===")
        for group_num in [1, 2, 3, 4]:
            if group_num in application.handlers:
                logger.info(f"Group {group_num}: {len(application.handlers[group_num])} handlers")
                for handler in application.handlers[group_num]:
                    logger.info(f"  - {type(handler).__name__}")
        
        logger.info("=== ✅ BOT READY ===")
        
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.error(f"Gagal memulai bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
