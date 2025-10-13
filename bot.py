import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

try:
    import config
    BOT_TOKEN = config.BOT_TOKEN
    ADMIN_IDS = set(str(i) for i in getattr(config, "ADMIN_TELEGRAM_IDS", []))
except (ImportError, AttributeError):
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    ADMIN_IDS = set(["123456789", "987654321"]) # fallback manual
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN tidak ditemukan. Set di config.py atau environment.")

try:
    import database
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False

import order_handler

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    saldo = 0
    if DATABASE_AVAILABLE:
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception:
            saldo = 0
    keyboard = [
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="menu_order")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="menu_saldo")],
        [InlineKeyboardButton("📞 BANTUAN", callback_data="menu_help")]
    ]
    if str(user.id) in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="menu_admin")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🤖 Selamat Datang!\n\nHalo {user.full_name}!\n💰 Saldo Anda: Rp {saldo:,.0f}\nPilih menu di bawah.",
        reply_markup=reply_markup
    )

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    # Handler menu modern dari order_handler (ConversationHandler)
    application.add_handler(order_handler.get_conversation_handler())
    logger.info("🤖 Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
