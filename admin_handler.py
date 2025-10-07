import config
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
import database
import sqlite3

def is_admin(user):
    return str(user.id) in config.ADMIN_TELEGRAM_IDS

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("Menu admin hanya untuk admin.")
        return
    await update.message.reply_text(
        "/topup_confirm <topup_id> - Konfirmasi topup user\n"
        "/cek_user <username> - Cek info user\n"
        "/jadikan_admin <telegram_id> - Jadikan user sebagai admin\n"
        "/broadcast pesan - Kirim pengumuman ke semua user\n"
    )

async def topup_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("Hanya admin yang bisa konfirmasi.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Format: /topup_confirm <topup_id>")
        return
    topup_id = args[0]
    database.update_topup_status(topup_id, "paid")
    await update.message.reply_text(f"Top up ID {topup_id} berhasil dikonfirmasi.")

async def cek_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("Hanya admin yang bisa cek user.")
        return
    args = context.args
    username = args[0] if args else None
    if not username:
        await update.message.reply_text("Format: /cek_user <username>")
        return
    conn = sqlite3.connect(database.DB_PATH)
    c = conn.cursor()
    c.execute("SELECT saldo, telegram_id FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if not row:
        await update.message.reply_text("User tidak ditemukan.")
        return
    saldo, telegram_id = row
    admin_status = "Ya" if telegram_id in config.ADMIN_TELEGRAM_IDS else "Tidak"
    await update.message.reply_text(
        f"Username: {username}\nSaldo: Rp {saldo}\nAdmin: {admin_status}\nTelegram ID: {telegram_id}"
    )

async def jadikan_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("Hanya admin yang bisa menjadikan admin.")
        return
    args = context.args
    telegram_id = args[0] if args else None
    if not telegram_id:
        await update.message.reply_text("Format: /jadikan_admin <telegram_id>")
        return
    database.add_user_admin(telegram_id)
    await update.message.reply_text(f"User dengan telegram_id {telegram_id} sudah jadi admin.")

admin_menu_handler = CommandHandler("admin", admin_menu)
topup_confirm_handler = CommandHandler("topup_confirm", topup_confirm)
cek_user_handler = CommandHandler("cek_user", cek_user)
jadikan_admin_handler = CommandHandler("jadikan_admin", jadikan_admin)
