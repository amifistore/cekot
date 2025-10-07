from telegram.ext import CommandHandler, CallbackContext
from telegram import Update, Bot
import database
import os

BOT_TOKEN = os.environ.get("TOKEN_BOT_KAMU")
bot = Bot(BOT_TOKEN)

def broadcast(update: Update, context: CallbackContext):
    user = update.message.from_user
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    if not database.is_admin(user_id):
        update.message.reply_text("Hanya admin yang bisa broadcast.")
        return
    text = " ".join(context.args)
    if not text:
        update.message.reply_text("Format: /broadcast pesan")
        return
    for telegram_id in database.get_all_telegram_ids():
        try:
            bot.send_message(chat_id=telegram_id, text=f"[INFO]: {text}")
        except Exception as e:
            pass
    update.message.reply_text("Pesan broadcast sudah dikirim ke semua user.")

broadcast_handler = CommandHandler("broadcast", broadcast)
