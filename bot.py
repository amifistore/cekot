import logging
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    MessageHandler
)
import config
import database

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
        logger.info(f"User {user.id} started the bot")
        
        saldo = 0
        try:
            user_data = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_balance(str(user.id))
        except Exception as e:
            logger.error(f"Error getting user saldo: {e}")
            saldo = 0
        
        # Bersihkan user data
        context.user_data.clear()
        
        keyboard = [
            [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="order")],
            [InlineKeyboardButton("💳 CEK SALDO", callback_data="saldo")],
            [InlineKeyboardButton("📊 CEK STOK", callback_data="stock")],
            [InlineKeyboardButton("📞 BANTUAN", callback_data="help")],
            [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="topup")]
        ]
        
        if str(user.id) in ADMIN_IDS:
            keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="admin")])
        
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

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """SINGLE callback handler untuk semua menu"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    logger.info(f"Callback received: {data} from user {user.id}")
    
    try:
        if data == "order":
            await handle_order(update, context)
        elif data == "saldo":
            await handle_saldo(update, context)
        elif data == "stock":
            await handle_stock(update, context)
        elif data == "help":
            await handle_help(update, context)
        elif data == "topup":
            await handle_topup(update, context)
        elif data == "admin":
            await handle_admin(update, context)
        elif data == "main_menu":
            await show_main_menu(update, context)
        else:
            await query.message.reply_text("❌ Menu tidak dikenali.")
            
    except Exception as e:
        logger.error(f"Error in callback_handler: {e}")
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu utama"""
    query = update.callback_query
    user = query.from_user
    
    saldo = 0
    try:
        user_data = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_balance(str(user.id))
    except Exception as e:
        logger.error(f"Error getting saldo: {e}")
    
    keyboard = [
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="order")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="saldo")],
        [InlineKeyboardButton("📊 CEK STOK", callback_data="stock")],
        [InlineKeyboardButton("📞 BANTUAN", callback_data="help")],
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="topup")]
    ]
    
    if str(user.id) in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"🏠 **MENU UTAMA**\n\n"
        f"Halo {user.full_name}!\n"
        f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
        f"Pilih menu di bawah:"
    )
    
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.warning(f"Could not edit message: {e}")
        await query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle menu order"""
    query = update.callback_query
    
    try:
        # Coba import dan panggil order handler
        import order_handler
        if hasattr(order_handler, 'menu_handler'):
            await order_handler.menu_handler(update, context)
        else:
            await query.message.reply_text("🛒 **FITUR ORDER**\n\nFitur order sedang dalam pengembangan.")
    except ImportError:
        await query.message.reply_text("🛒 **FITUR ORDER**\n\nFitur order sedang dalam pengembangan.")
    except Exception as e:
        logger.error(f"Error in handle_order: {e}")
        await query.message.reply_text("❌ Error memuat fitur order.")

async def handle_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle menu saldo"""
    query = update.callback_query
    user = query.from_user
    
    saldo = 0
    try:
        user_data = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_balance(str(user.id))
    except Exception as e:
        logger.error(f"Error getting saldo: {e}")
    
    keyboard = [
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="topup")],
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"💰 **SALDO ANDA**\n\nSaldo saat ini: **Rp {saldo:,.0f}**"
    
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except:
        await query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle menu stock"""
    query = update.callback_query
    
    try:
        import stok_handler
        if hasattr(stok_handler, 'stock_akrab_callback'):
            await stok_handler.stock_akrab_callback(update, context)
        else:
            await query.message.reply_text("📊 **CEK STOK**\n\nFitur cek stok sedang dalam pengembangan.")
    except ImportError:
        await query.message.reply_text("📊 **CEK STOK**\n\nFitur cek stok sedang dalam pengembangan.")
    except Exception as e:
        logger.error(f"Error in handle_stock: {e}")
        await query.message.reply_text("❌ Error memuat data stok.")

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle menu help"""
    query = update.callback_query
    
    keyboard = [[InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "📞 **BANTUAN**\n\n"
        "Untuk bantuan silakan hubungi admin.\n"
        "Kami siap membantu 24/7.\n\n"
        "**Fitur yang tersedia:**\n"
        "• 🛒 Beli Produk\n"
        "• 💳 Top Up Saldo\n"
        "• 📊 Cek Stok\n"
        "• 📞 Bantuan"
    )
    
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except:
        await query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle menu topup"""
    query = update.callback_query
    
    try:
        from topup_handler import show_manage_topup
        await show_manage_topup(update, context)
    except ImportError:
        await query.message.reply_text("💸 **TOP UP SALDO**\n\nFitur top up sedang dalam pengembangan.")
    except Exception as e:
        logger.error(f"Error in handle_topup: {e}")
        await query.message.reply_text("❌ Error memuat menu topup.")

async def handle_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle menu admin"""
    query = update.callback_query
    user = query.from_user
    
    if str(user.id) not in ADMIN_IDS:
        await query.answer("❌ Akses ditolak!", show_alert=True)
        return
    
    try:
        import admin_handler
        if hasattr(admin_handler, 'admin_menu'):
            await admin_handler.admin_menu(update, context)
        else:
            await query.message.reply_text("👑 **ADMIN PANEL**\n\nPanel admin sedang dalam pengembangan.")
    except ImportError:
        await query.message.reply_text("👑 **ADMIN PANEL**\n\nPanel admin sedang dalam pengembangan.")
    except Exception as e:
        logger.error(f"Error in handle_admin: {e}")
        await query.message.reply_text("❌ Error memuat panel admin.")

async def saldo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /saldo"""
    user = update.message.from_user
    
    saldo = 0
    try:
        user_data = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_balance(str(user.id))
    except Exception as e:
        logger.error(f"Error getting saldo: {e}")
    
    await update.message.reply_text(f"💰 Saldo Anda: **Rp {saldo:,.0f}**", parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /help"""
    await update.message.reply_text(
        "📞 **BANTUAN**\n\nGunakan /start untuk memulai bot atau hubungi admin untuk bantuan.",
        parse_mode='Markdown'
    )

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /stock"""
    try:
        import stok_handler
        if hasattr(stok_handler, 'stock_command'):
            await stok_handler.stock_command(update, context)
        else:
            await update.message.reply_text("📊 **CEK STOK**\n\nGunakan menu di /start untuk cek stok.")
    except ImportError:
        await update.message.reply_text("📊 **CEK STOK**\n\nGunakan menu di /start untuk cek stok.")

async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk pesan tidak dikenal"""
    # Biarkan conversation handler yang menangani
    return

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"Error: {context.error}", exc_info=True)

def main():
    """Main function yang SIMPLE dan WORK"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        logger.info("🚀 Starting bot dengan konfigurasi SIMPLE...")
        
        # ========== HANDLER SANGAT SEDERHANA ==========
        
        # 1. Conversation handlers (jika ada)
        try:
            from topup_handler import topup_conv_handler
            application.add_handler(topup_conv_handler)
            logger.info("✓ Topup handler registered")
        except Exception as e:
            logger.warning(f"✗ Topup handler not available: {e}")
        
        # 2. Command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("saldo", saldo_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("stock", stock_command))
        
        # 3. SINGLE callback handler untuk SEMUA callback
        application.add_handler(CallbackQueryHandler(callback_handler))
        
        # 4. Fallback handler
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))
        
        # 5. Error handler
        application.add_error_handler(error_handler)
        
        logger.info("✅ Bot started successfully!")
        logger.info("📋 Handler setup:")
        logger.info("  - Command: /start, /saldo, /help, /stock")
        logger.info("  - Callback: Single handler for all callbacks")
        logger.info("  - Conversation: Topup (if available)")
        
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
