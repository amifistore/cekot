import config
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, CallbackContext, filters
import database
import sqlite3
from datetime import datetime

ASK_ORDER_PRODUK = 1
ASK_ORDER_TUJUAN = 2
ASK_ORDER_CONFIRM = 3

def order_start(update: Update, context: CallbackContext):
    user = update.message.from_user
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    saldo = database.get_user_saldo(user_id)
    produk_list = database.get_produk_list()
    context.user_data["produk_list"] = produk_list

    msg = f"Saldo Anda: Rp {saldo}\n\nPilih produk:\n"
    produk_keyboard = []
    for prod in produk_list:
        msg += f"- {prod['nama_produk']} (Kode: {prod['kode_produk']}) - Rp {prod['harga_final']}\n"
        produk_keyboard.append([prod["kode_produk"]])
    update.message.reply_text(
        msg,
        reply_markup=ReplyKeyboardMarkup(produk_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ASK_ORDER_PRODUK

def order_produk(update: Update, context: CallbackContext):
    kode_produk = update.message.text.strip()
    produk_list = context.user_data.get("produk_list", [])
    produk = next((p for p in produk_list if p["kode_produk"] == kode_produk), None)
    if not produk:
        update.message.reply_text("Produk tidak ditemukan. Pilih ulang.")
        return ASK_ORDER_PRODUK
    context.user_data["order_produk"] = produk
    update.message.reply_text(
        f"{produk['nama_produk']} dipilih.\nDeskripsi: {produk['deskripsi']}\nHarga: Rp {produk['harga_final']}\n\nMasukkan nomor tujuan (08xxxxxxxxxx):"
    )
    return ASK_ORDER_TUJUAN

def order_tujuan(update: Update, context: CallbackContext):
    tujuan = update.message.text.strip()
    if not tujuan.startswith("08") or not (10 <= len(tujuan) <= 14) or not tujuan.isdigit():
        update.message.reply_text("Nomor tujuan tidak valid. Format 08xxxxxxxxxx.")
        return ASK_ORDER_TUJUAN
    context.user_data["order_tujuan"] = tujuan

    produk = context.user_data["order_produk"]
    update.message.reply_text(
        f"Konfirmasi pesanan:\nProduk: {produk['nama_produk']}\nHarga: Rp {produk['harga_final']}\nTujuan: {tujuan}\n\nKetik 'ya' untuk konfirmasi, atau 'batal' untuk membatalkan."
    )
    return ASK_ORDER_CONFIRM

def order_confirm(update: Update, context: CallbackContext):
    user = update.message.from_user
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    produk = context.user_data["order_produk"]
    tujuan = context.user_data["order_tujuan"]
    saldo = database.get_user_saldo(user_id)
    confirm = update.message.text.strip().lower()
    if confirm != "ya":
        update.message.reply_text("Order dibatalkan.")
        return ConversationHandler.END
    if saldo < produk["harga_final"]:
        update.message.reply_text("Saldo tidak cukup.")
        return ConversationHandler.END
    database.increment_user_saldo(user_id, -produk["harga_final"])
    reff_id = f"akrab_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    waktu = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect(database.DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO riwayat_pembelian
        (username, kode_produk, nama_produk, tujuan, harga, saldo_awal, reff_id, status_api, keterangan, waktu)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user.username, produk["kode_produk"], produk["nama_produk"], tujuan,
        produk["harga_final"], saldo, reff_id, "PROSES", "Order dikirim", waktu
    ))
    conn.commit()
    conn.close()
    update.message.reply_text(
        f"Order berhasil!\nProduk: {produk['nama_produk']}\nHarga: Rp {produk['harga_final']}\nTujuan: {tujuan}\nSaldo sekarang: Rp {saldo - produk['harga_final']}"
    )
    return ConversationHandler.END

def order_cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Proses order dibatalkan.")
    return ConversationHandler.END

order_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('order', order_start)],
    states={
        ASK_ORDER_PRODUK: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_produk)],
        ASK_ORDER_TUJUAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_tujuan)],
        ASK_ORDER_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_confirm)],
    },
    fallbacks=[CommandHandler('cancel', order_cancel)]
)
