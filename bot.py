import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    filters
)
import config
import database
import order_handler
import admin_handler
from topup_handler import topup_conv_handler
import telegram

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = config.BOT_TOKEN
ADMIN_IDS = set(str(i) for i in getattr(config, "ADMIN_TELEGRAM_IDS", []))

# Helper anti error "Message is not modified"
async def safe_edit_message_text(callback_query, *args, **kwargs):
    try:
        await callback_query.edit_message_text(*args, **kwargs)
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e):
            return
        raise

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception:
        saldo = 0
    keyboard = [
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="menu_order")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="menu_saldo")],
        [InlineKeyboardButton("📞 BANTUAN", callback_data="menu_help")],
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="menu_topup")]
    ]
    if str(user.id) in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="menu_admin")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🤖 Selamat Datang!\n\nHalo {user.full_name}!\n💰 Saldo Anda: Rp {saldo:,.0f}\nPilih menu di bawah.",
        reply_markup=reply_markup
    )

async def approve_topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in [str(i) for i in config.ADMIN_TELEGRAM_IDS]:
        await update.message.reply_text("❌ Hanya admin yang boleh approve topup.")
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /approve_topup <id>")
        return
    request_id = context.args[0]
    result = database.approve_topup_request(request_id, admin_id=user_id)
    if result:
        await update.message.reply_text(f"✅ Topup request #{request_id} berhasil diapprove dan saldo user sudah bertambah.")
    else:
        await update.message.reply_text(f"❌ Gagal approve request #{request_id}.")

async def cancel_topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in [str(i) for i in config.ADMIN_TELEGRAM_IDS]:
        await update.message.reply_text("❌ Hanya admin yang boleh cancel/reject topup.")
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /cancel_topup <id>")
        return
    request_id = context.args[0]
    result = database.reject_topup_request(request_id, admin_id=user_id)
    if result:
        await update.message.reply_text(f"✅ Topup request #{request_id} berhasil dibatalkan/reject.")
    else:
        await update.message.reply_text(f"❌ Gagal cancel/reject request #{request_id}.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    # HANYA register ConversationHandler dari order_handler (untuk menu/menu order)
    application.add_handler(order_handler.get_conversation_handler())
    application.add_handler(topup_conv_handler)
    application.add_handler(CommandHandler("approve_topup", approve_topup_command))
    application.add_handler(CommandHandler("cancel_topup", cancel_topup_command))
    for handler in admin_handler.get_admin_handlers():
        application.add_handler(handler)
    application.add_error_handler(error_handler)
    logger.info("🤖 Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
