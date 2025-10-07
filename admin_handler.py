from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
import database
import sqlite3

def admin_menu(update: Update, context: CallbackContext):
    user = update.message.from_user
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    if not database.is_admin(user_id):
        update.message.reply_text("Menu admin hanya untuk admin.")
        return
    update.message.reply_text(
        "/topup_confirm <topup_id> - Konfirmasi topup user\n"
        "/cek_user <username> - Cek info user\n"
        "/jadikan_admin <telegram_id> - Jadikan user sebagai admin\n"
        "/broadcast pesan - Kirim pengumuman ke semua user\n"
    )

def topup_confirm(update: Update, context: CallbackContext):
    user_id = database.get_or_create_user(str(update.message.from_user.id), update.message.from_user.username, update.message.from_user.full_name)
    if not database.is_admin(user_id):
        update.message.reply_text("Hanya admin yang bisa konfirmasi.")
        return
    args = context.args
    if not args:
        update.message.reply_text("Format: /topup_confirm <topup_id>")
        return
    topup_id = args[0]
    database.update_topup_status(topup_id, "paid")
    update.message.reply_text(f"Top up ID {topup_id} berhasil dikonfirmasi.")

def cek_user(update: Update, context: CallbackContext):
    user_id = database.get_or_create_user(str(update.message.from_user.id), update.message.from_user.username, update.message.from_user.full_name)
    if not database.is_admin(user_id):
        update.message.reply_text("Hanya admin yang bisa cek user.")
        return
    args = context.args
    username = args[0] if args else None
    if not username:
        update.message.reply_text("Format: /cek_user <username>")
        return
    conn = sqlite3.connect(database.DB_PATH)
    c = conn.cursor()
    c.execute("SELECT saldo, is_admin, telegram_id FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if not row:
        update.message.reply_text("User tidak ditemukan.")
        return
    saldo, is_admin, telegram_id = row
    update.message.reply_text(
        f"Username: {username}\nSaldo: Rp {saldo}\nAdmin: {'Ya' if is_admin else 'Tidak'}\nTelegram ID: {telegram_id}"
    )

def jadikan_admin(update: Update, context: CallbackContext):
    user_id = database.get_or_create_user(str(update.message.from_user.id), update.message.from_user.username, update.message.from_user.full_name)
    if not database.is_admin(user_id):
        update.message.reply_text("Hanya admin yang bisa menjadikan admin.")
        return
    args = context.args
    telegram_id = args[0] if args else None
    if not telegram_id:
        update.message.reply_text("Format: /jadikan_admin <telegram_id>")
        return
    database.add_user_admin(telegram_id)
    update.message.reply_text(f"User dengan telegram_id {telegram_id} sudah jadi admin.")

admin_menu_handler = CommandHandler("admin", admin_menu)
topup_confirm_handler = CommandHandler("topup_confirm", topup_confirm)
cek_user_handler = CommandHandler("cek_user", cek_user)
jadikan_admin_handler = CommandHandler("jadikan_admin", jadikan_admin)
