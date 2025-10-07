import config
from telegram.ext import CommandHandler, ContextTypes
from telegram import Update, Bot
import database

bot = Bot(config.BOT_TOKEN)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) not in config.ADMIN_TELEGRAM_IDS:
        await update.message.reply_text("Hanya admin yang bisa broadcast.")
        return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Format: /broadcast pesan")
        return
    for telegram_id in database.get_all_telegram_ids():
        try:
            await bot.send_message(chat_id=telegram_id, text=f"[INFO]: {text}")
        except Exception:
            pass
    await update.message.reply_text("Pesan broadcast sudah dikirim ke semua user.")

broadcast_handler = CommandHandler("broadcast", broadcast)
