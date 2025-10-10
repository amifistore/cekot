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
except (ImportError, AttributeError):
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN tidak ditemukan. Set di config.py atau environment.")

from order_handler import order_handler

# Ganti dengan ID Telegram admin kamu di bawah!
ADMIN_IDS = [123456789, 987654321]

try:
    import database
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False

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
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="order")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="saldo")],
        [InlineKeyboardButton("📞 BANTUAN", callback_data="help")]
    ]
    if user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="admin")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🤖 Selamat Datang!\n\nHalo {user.full_name}!\n💰 Saldo Anda: Rp {saldo:,.0f}\nPilih menu di bawah.",
        reply_markup=reply_markup
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    user = query.from_user
    saldo = 0
    if DATABASE_AVAILABLE:
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception:
            saldo = 0
    if callback_data == "order":
        await order_handler.start_order_from_callback(query, context)
    elif callback_data == "saldo":
        await query.edit_message_text(
            f"💰 SALDO ANDA\nSaldo: Rp {saldo:,.0f}\nGunakan menu untuk topup/order produk."
        )
    elif callback_data == "help":
        await query.edit_message_text(
            "📞 BANTUAN\n\nJika mengalami masalah, hubungi admin @username_admin.\n"
            "Cara order: pilih BELI PRODUK, pilih produk, isi nomor tujuan, konfirmasi."
        )
    elif callback_data == "admin" and user.id in ADMIN_IDS:
        await query.edit_message_text(
            "👑 ADMIN PANEL\n\nFitur admin bisa dikembangkan di sini.\nContoh: tambah produk, cek riwayat, dsb."
        )

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(order_handler.get_conversation_handler())
    application.add_handler(CallbackQueryHandler(handle_callback))
    logger.info("🤖 Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
