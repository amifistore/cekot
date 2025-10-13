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

# PATCH: Helper agar edit_message_text tidak error jika "Message is not modified"
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

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception:
        saldo = 0
    try:
        if data == "menu_order":
            return await order_handler.menu_main(update, context)
        elif data == "menu_saldo":
            await safe_edit_message_text(
                query,
                f"💳 SALDO ANDA\nSaldo: Rp {saldo:,.0f}\nGunakan menu untuk topup/order produk.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💸 Top Up", callback_data="menu_topup")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ])
            )
        elif data == "menu_help":
            await safe_edit_message_text(
                query,
                "📞 BANTUAN\n\n"
                "Jika mengalami masalah, hubungi admin @username_admin.\n"
                "Cara order: pilih BELI PRODUK, pilih produk, isi nomor tujuan, konfirmasi.\n"
                "Untuk top up saldo, gunakan tombol Top Up di bawah atau ketik /topup.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💸 Top Up", callback_data="menu_topup")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ])
            )
        elif data == "menu_topup":
            await safe_edit_message_text(
                query,
                "💸 *TOP UP SALDO*\n\n"
                "Untuk top up saldo, ketik perintah /topup di chat bot ini dan ikuti instruksi.\n"
                "Nominal transfer akan diberi kode unik untuk verifikasi otomatis.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ]),
                parse_mode="Markdown"
            )
        elif data == "menu_admin" and str(user.id) in ADMIN_IDS:
            await admin_handler.admin_menu_from_query(query, context)
        elif data == "menu_main":
            await start(update, context)
        else:
            await safe_edit_message_text(query, "Menu tidak dikenal.")
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e):
            return
        raise

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
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=r'^menu_'))
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
