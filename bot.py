# bot.py
import logging
import os
import sqlite3
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Import config - dengan error handling
try:
    import config
    BOT_TOKEN = config.TOKEN
except (ImportError, AttributeError) as e:
    logger.error(f"Error loading config: {e}")
    # Fallback to environment variable
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN tidak ditemukan. Pastikan file config.py ada dan berisi TOKEN, atau set environment variable BOT_TOKEN")

# Import order handler
try:
    from order_handler import order_handler
    ORDER_HANDLER_AVAILABLE = True
    logger.info("✅ Order handler loaded successfully")
except ImportError as e:
    logger.error(f"❌ Failed to load order handler: {e}")
    ORDER_HANDLER_AVAILABLE = False

# Import admin handler dengan error handling
try:
    from admin_handler import admin_handler
    ADMIN_HANDLER_AVAILABLE = True
    logger.info("✅ Admin handler loaded successfully")
except ImportError as e:
    logger.warning(f"⚠️ Admin handler not available: {e}")
    ADMIN_HANDLER_AVAILABLE = False

# Import database
try:
    import database
    DATABASE_AVAILABLE = True
    logger.info("✅ Database module loaded successfully")
except ImportError as e:
    logger.error(f"❌ Failed to load database module: {e}")
    DATABASE_AVAILABLE = False

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message with inline keyboard"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    user = update.message.from_user
    
    # Get user balance if database available
    saldo = 0
    if DATABASE_AVAILABLE:
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception as e:
            logger.error(f"Error getting user balance: {e}")
            saldo = 0
    
    keyboard = [
        [
            InlineKeyboardButton("🛒 BELI PRODUK", callback_data="order"),
            InlineKeyboardButton("💰 TOP UP SALDO", callback_data="topup")
        ],
        [
            InlineKeyboardButton("💳 CEK SALDO", callback_data="saldo"),
            InlineKeyboardButton("📞 BANTUAN", callback_data="help")
        ]
    ]
    
    if ADMIN_HANDLER_AVAILABLE:
        keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🤖 **Selamat Datang di AmifiVPS Bot!**\n\n"
        f"Halo {user.full_name}! 👋\n"
        f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
        "Silakan pilih menu di bawah untuk mulai berbelanja:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Callback query handler
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline keyboard"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user = query.from_user
    
    if DATABASE_AVAILABLE:
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception as e:
            logger.error(f"Error getting user balance: {e}")
            saldo = 0
    else:
        saldo = 0
    
    if callback_data == "order":
        if ORDER_HANDLER_AVAILABLE:
            await order_handler.start_order_from_callback(query, context)
        else:
            await query.edit_message_text(
                "❌ **Fitur Order Sedang Tidak Tersedia**\n\n"
                "Maaf, sistem order sedang dalam perbaikan.\n"
                "Silakan coba lagi nanti atau hubungi admin.",
                parse_mode='Markdown'
            )
        
    elif callback_data == "saldo":
        await query.edit_message_text(
            f"💰 **SALDO ANDA**\n\n"
            f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
            "Gunakan menu di bawah untuk topup atau belanja:",
            parse_mode='Markdown'
        )
        
    elif callback_data == "topup":
        instructions = (
            "💰 **TOP UP SALDO**\n\n"
            "Untuk topup saldo, silakan transfer ke:\n\n"
            "📍 **BCA**: 123-456-7890 (Amifi Store)\n"
            "📍 **BRI**: 098-765-4321 (Amifi Store)\n\n"
            "Setelah transfer, kirim bukti transfer ke @admin\n"
            "Saldo akan ditambahkan dalam 1-5 menit.\n\n"
            "Terima kasih! 😊"
        )
        await query.edit_message_text(instructions, parse_mode='Markdown')
        
    elif callback_data == "help":
        help_text = (
            "📞 **BANTUAN & SUPPORT**\n\n"
            "Jika Anda mengalami kendala atau butuh bantuan:\n\n"
            "🔹 **Cara Order**:\n"
            "1. Pilih 'BELI PRODUK'\n"
            "2. Pilih produk yang diinginkan\n"
            "3. Masukkan nomor tujuan\n"
            "4. Konfirmasi order\n\n"
            "🔹 **Top Up Saldo**:\n"
            "Transfer ke rekening yang tersedia\n"
            "Kirim bukti ke admin\n\n"
            "🔹 **Admin Support**:\n"
            "@admin_amifi (24/7)\n\n"
            "Terima kasih! 😊"
        )
        await query.edit_message_text(help_text, parse_mode='Markdown')
        
    elif callback_data == "admin" and ADMIN_HANDLER_AVAILABLE:
        # Handle admin panel callback
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        admin_keyboard = [
            [InlineKeyboardButton("📊 Statistik", callback_data="admin_stats")],
            [InlineKeyboardButton("📦 Kelola Produk", callback_data="admin_products")],
            [InlineKeyboardButton("👥 Kelola User", callback_data="admin_users")],
            [InlineKeyboardButton("🔙 Kembali", callback_data="back_to_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(admin_keyboard)
        
        await query.edit_message_text(
            "👑 **ADMIN PANEL**\n\n"
            "Silakan pilih menu admin:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the bot"""
    logger.error(f"Exception while handling an update: {context.error}")
    
    # Send error message to user
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Terjadi kesalahan sistem. Silakan coba lagi atau hubungi admin."
            )
        except Exception as e:
            logger.error(f"Error sending error message: {e}")

# Main function
def main():
    """Start the bot"""
    try:
        # Check if token is available
        if not BOT_TOKEN:
            logger.error("❌ BOT_TOKEN tidak ditemukan!")
            return
        
        logger.info("🚀 Starting bot...")
        
        # Create application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Add basic handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", start))
        
        # Add order conversation handler jika available
        if ORDER_HANDLER_AVAILABLE:
            application.add_handler(order_handler.get_conversation_handler())
            logger.info("✅ Order handler registered")
        else:
            logger.warning("⚠️ Order handler not available")
        
        # Add callback query handler
        application.add_handler(CallbackQueryHandler(handle_callback))
        
        # Add admin handlers jika available
        if ADMIN_HANDLER_AVAILABLE:
            try:
                # Coba berbagai cara untuk mendapatkan admin handlers
                if hasattr(admin_handler, 'get_admin_handlers'):
                    admin_handlers = admin_handler.get_admin_handlers()
                    for handler in admin_handlers:
                        application.add_handler(handler)
                    logger.info("✅ Admin handlers loaded via get_admin_handlers()")
                elif hasattr(admin_handler, 'get_conversation_handler'):
                    application.add_handler(admin_handler.get_conversation_handler())
                    logger.info("✅ Admin conversation handler loaded")
                elif isinstance(admin_handler, list):
                    for handler in admin_handler:
                        application.add_handler(handler)
                    logger.info("✅ Admin handlers loaded as list")
                else:
                    logger.warning("⚠️ Unknown admin handler format")
            except Exception as e:
                logger.error(f"❌ Failed to load admin handlers: {e}")
        else:
            logger.warning("⚠️ Admin handler not available")
        
        # Add error handler
        application.add_error_handler(error_handler)
        
        # Start bot
        logger.info("🤖 Bot is running...")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        raise

if __name__ == '__main__':
    main()
