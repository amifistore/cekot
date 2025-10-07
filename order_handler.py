from telegram import Update
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, Filters, CallbackContext
import database

ASK_ORDER_DETAIL = 1
ASK_ORDER_CONFIRM = 2

def order_start(update: Update, context: CallbackContext):
    update.message.reply_text("Kirim detail pesanan kamu (contoh: Produk X, Qty: 2):")
    return ASK_ORDER_DETAIL

def order_detail(update: Update, context: CallbackContext):
    user = update.message.from_user
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    detail = update.message.text.strip()
    context.user_data["order_detail"] = detail
    update.message.reply_text(
        f"Detail pesanan: {detail}\nKetik 'ya' untuk konfirmasi dan lanjut potong saldo, atau 'batal' untuk membatalkan."
    )
    return ASK_ORDER_CONFIRM

def order_confirm(update: Update, context: CallbackContext):
    user = update.message.from_user
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    confirm = update.message.text.strip().lower()
    if confirm == "ya":
        # Contoh potong saldo otomatis Rp 5000 per order
        order_cost = 5000
        saldo = database.get_user_saldo(user_id)
        if saldo < order_cost:
            update.message.reply_text("Saldo tidak cukup! Silakan top up dahulu.")
        else:
            database.increment_user_saldo(user_id, -order_cost)
            # Simpan riwayat order di transaksi
            # (tambahkan di database.py jika belum ada)
            update.message.reply_text(f"Order diterima! Saldo kamu sudah dipotong Rp {order_cost}.")
    else:
        update.message.reply_text("Order dibatalkan.")
    return ConversationHandler.END

def order_cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Proses order dibatalkan.")
    return ConversationHandler.END

order_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('order', order_start)],
    states={
        ASK_ORDER_DETAIL: [MessageHandler(Filters.text & ~Filters.command, order_detail)],
        ASK_ORDER_CONFIRM: [MessageHandler(Filters.text & ~Filters.command, order_confirm)]
    },
    fallbacks=[CommandHandler('cancel', order_cancel)]
)
