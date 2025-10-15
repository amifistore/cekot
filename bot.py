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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start"""
    try:
        user = update.message.from_user
        logger.info(f"User {user.id} ({user.username}) started the bot")
        
        saldo = 0
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception as e:
            logger.error(f"Error getting user saldo: {e}")
            saldo = 0
        
        # Clear user data
        context.user_data.clear()
        
        keyboard = [
            [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="main_menu_order")],
            [InlineKeyboardButton("💳 CEK SALDO", callback_data="main_menu_saldo")],
            [InlineKeyboardButton("📊 CEK STOK", callback_data="main_menu_stock")],
            [InlineKeyboardButton("📞 BANTUAN", callback_data="main_menu_help")],
            [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="main_menu_topup")]
        ]
        
        if str(user.id) in ADMIN_IDS:
            keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="main_menu_admin")])
        
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

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler khusus untuk menu utama saja - TIDAK ADA KONFLIK"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    logger.info(f"Main menu callback: {data} from user {user.id}")
    
    try:
        if data == "main_menu_order":
            # Arahkan ke order handler
            try:
                import order_handler
                await order_handler.menu_handler(update, context)
            except Exception as e:
                logger.error(f"Error starting order: {e}")
                await query.message.reply_text("❌ Error memulai order. Silakan coba lagi.")
                
        elif data == "main_menu_saldo":
            await show_saldo_menu(update, context)
        elif data == "main_menu_help":
            await show_help_menu(update, context)
        elif data == "main_menu_stock":
            await show_stock_menu(update, context)
        elif data == "main_menu_topup":
            await show_topup_menu(update, context)
        elif data == "main_menu_admin":
            if str(user.id) in ADMIN_IDS:
                try:
                    import admin_handler
                    await admin_handler.admin_menu(update, context)
                except Exception as e:
                    logger.error(f"Error loading admin: {e}")
                    await query.message.reply_text("❌ Error memuat admin panel.")
            else:
                await query.answer("❌ Akses ditolak!", show_alert=True)
        else:
            await query.answer("❌ Menu tidak dikenali!")
            
    except Exception as e:
        logger.error(f"Error in main_menu_handler: {e}", exc_info=True)
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

async def show_saldo_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu saldo"""
    query = update.callback_query
    user = query.from_user
    
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception as e:
        logger.error(f"Error getting saldo: {e}")
    
    keyboard = [
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="main_menu_topup")],
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"💰 **SALDO ANDA**\n\nSaldo: **Rp {saldo:,.0f}**"
    
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except:
        await query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu bantuan"""
    query = update.callback_query
    
    keyboard = [[InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "📞 **BANTUAN**\n\n"
        "Untuk bantuan silakan hubungi admin.\n"
        "Kami siap membantu 24/7."
    )
    
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except:
        await query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_stock_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu stok"""
    query = update.callback_query
    await query.answer()
    
    try:
        import stok_handler
        await stok_handler.stock_akrab_callback(update, context)
    except Exception as e:
        logger.error(f"Error showing stock: {e}")
        await query.message.reply_text("❌ Error menampilkan stok.")

async def show_topup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu topup"""
    query = update.callback_query
    await query.answer()
    
    try:
        from topup_handler import show_manage_topup
        await show_manage_topup(update, context)
    except Exception as e:
        logger.error(f"Error showing topup: {e}")
        await query.message.reply_text("❌ Error memuat menu topup.")

async def saldo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /saldo"""
    user = update.message.from_user
    
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception as e:
        logger.error(f"Error getting saldo: {e}")
    
    await update.message.reply_text(f"💰 Saldo Anda: **Rp {saldo:,.0f}**", parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /help"""
    await update.message.reply_text(
        "📞 **BANTUAN**\n\nGunakan /start untuk memulai bot atau hubungi admin untuk bantuan.",
        parse_mode='Markdown'
    )

async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk pesan tidak dikenal"""
    logger.debug(f"Ignoring unknown message: {update.message.text}")
    return

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"Error: {context.error}", exc_info=True)

def main():
    """Main function dengan handler yang TIDAK KONFLIK"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        logger.info("🚀 Starting bot dengan handler bebas konflik...")
        
        # ========== HANDLER TANPA KONFLIK ==========
        
        # 1. IMPORT DAN DAFTARKAN CONVERSATION HANDLER DARI MODUL LAIN
        try:
            from topup_handler import topup_conv_handler
            application.add_handler(topup_conv_handler)
            logger.info("✓ Topup conversation handler registered")
        except Exception as e:
            logger.error(f"✗ Failed to register topup handler: {e}")
        
        try:
            import order_handler
            if hasattr(order_handler, 'get_conversation_handler'):
                order_conv = order_handler.get_conversation_handler()
                if order_conv:
                    application.add_handler(order_conv)
                    logger.info("✓ Order conversation handler registered")
        except Exception as e:
            logger.error(f"✗ Failed to register order handler: {e}")
        
        # 2. COMMAND HANDLERS
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("saldo", saldo_command))
        application.add_handler(CommandHandler("help", help_command))
        
        # 3. CALLBACK HANDLERS - HANYA UNTUK MENU UTAMA
        application.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^main_menu_"))
        
        # 4. FALLBACK HANDLER
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))
        
        # 5. ERROR HANDLER
        application.add_error_handler(error_handler)
        
        # DEBUG: Print semua handler
        logger.info("📋 Registered handlers:")
        for group in sorted(application.handlers.keys()):
            for handler in application.handlers[group]:
                handler_name = type(handler).__name__
                if hasattr(handler, 'pattern'):
                    logger.info(f"  Group {group}: {handler_name} (pattern: {handler.pattern})")
                else:
                    logger.info(f"  Group {group}: {handler_name}")
        
        logger.info("✅ Bot started successfully!")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
