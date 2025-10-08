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

# Import handlers
from order_handler import order_handler
from admin_handler import admin_handler
import database

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

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message with inline keyboard"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    user = update.message.from_user
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    saldo = database.get_user_saldo(user_id)
    
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
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    saldo = database.get_user_saldo(user_id)
    
    if callback_data == "order":
        # Start order process
        await order_handler.start_order_from_callback(query, context)
        
    elif callback_data == "saldo":
        # Check balance
        await query.edit_message_text(
            f"💰 **SALDO ANDA**\n\n"
            f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
            "Gunakan menu di bawah untuk topup atau belanja:",
            parse_mode='Markdown'
        )
        
    elif callback_data == "topup":
        # Topup instructions
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
        # Help message
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
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", start))
        
        # Add order conversation handler
        application.add_handler(order_handler.get_conversation_handler())
        
        # Add callback query handler
        application.add_handler(CallbackQueryHandler(handle_callback))
        
        # Add admin handlers if available
        try:
            if hasattr(admin_handler, 'get_admin_handlers'):
                admin_handlers = admin_handler.get_admin_handlers()
                for handler in admin_handlers:
                    application.add_handler(handler)
                logger.info("✅ Admin handlers loaded")
        except Exception as e:
            logger.warning(f"⚠️ Admin handlers not loaded: {e}")
        
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
