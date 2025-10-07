import config
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, ContextTypes, filters
import sqlite3
import database
from datetime import datetime

DB_PATH = "bot_topup.db"
ASK_ORDER_PRODUK = 1
ASK_ORDER_TUJUAN = 2
ASK_ORDER_CONFIRM = 3

async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    saldo = database.get_user_saldo(user_id)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            code TEXT PRIMARY KEY,
            name TEXT,
            price REAL,
            status TEXT,
            updated_at TEXT
        )
    """)
    c.execute("SELECT code, name, price FROM products WHERE status='active' ORDER BY name ASC LIMIT 30")
    produk_list = c.fetchall()
    conn.close()
    context.user_data["produk_list"] = produk_list

    if not produk_list:
        await update.message.reply_text("Produk belum tersedia. Silakan minta admin untuk update produk terlebih dahulu dengan /updateproduk")
        return ConversationHandler.END

    msg = f"Saldo Anda: Rp {saldo}\n\nPilih produk:\n"
    produk_keyboard = []
    for code, name, price in produk_list:
        msg += f"- {name} (Kode: {code}) - Rp {price:,.0f}\n"
        produk_keyboard.append([code])
    await update.message.reply_text(
        msg,
        reply_markup=ReplyKeyboardMarkup(produk_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ASK_ORDER_PRODUK

async def order_produk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kode_produk = update.message.text.strip()
    produk_list = context.user_data.get("produk_list", [])
    produk = next((p for p in produk_list if p[0] == kode_produk), None)
    if not produk:
        await update.message.reply_text("Produk tidak ditemukan. Pilih ulang.")
        return ASK_ORDER_PRODUK
    context.user_data["order_produk"] = produk
    await update.message.reply_text(
        f"{produk[1]} dipilih.\nHarga: Rp {produk[2]:,.0f}\n\nMasukkan nomor tujuan (08xxxxxxxxxx):"
    )
    return ASK_ORDER_TUJUAN

async def order_tujuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tujuan = update.message.text.strip()
    if not tujuan.startswith("08") or not (10 <= len(tujuan) <= 14) or not tujuan.isdigit():
        await update.message.reply_text("Nomor tujuan tidak valid. Format 08xxxxxxxxxx.")
        return ASK_ORDER_TUJUAN
    context.user_data["order_tujuan"] = tujuan

    produk = context.user_data["order_produk"]
    await update.message.reply_text(
        f"Konfirmasi pesanan:\nProduk: {produk[1]}\nHarga: Rp {produk[2]:,.0f}\nTujuan: {tujuan}\n\nKetik 'ya' untuk konfirmasi, atau 'batal' untuk membatalkan."
    )
    return ASK_ORDER_CONFIRM

async def order_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    produk = context.user_data["order_produk"]
    tujuan = context.user_data["order_tujuan"]
    saldo = database.get_user_saldo(user_id)
    confirm = update.message.text.strip().lower()
    if confirm != "ya":
        await update.message.reply_text("Order dibatalkan.")
        return ConversationHandler.END
    if saldo < produk[2]:
        await update.message.reply_text("Saldo tidak cukup.")
        return ConversationHandler.END
    database.increment_user_saldo(user_id, -produk[2])
    reff_id = f"order_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    waktu = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO riwayat_pembelian
        (username, kode_produk, nama_produk, tujuan, harga, saldo_awal, reff_id, status_api, keterangan, waktu)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user.username, produk[0], produk[1], tujuan,
        produk[2], saldo, reff_id, "PROSES", "Order dikirim", waktu
    ))
    conn.commit()
    conn.close()
    await update.message.reply_text(
        f"Order berhasil!\nProduk: {produk[1]}\nHarga: Rp {produk[2]:,.0f}\nTujuan: {tujuan}\nSaldo sekarang: Rp {saldo - produk[2]:,.0f}"
    )
    return ConversationHandler.END

async def order_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Proses order dibatalkan.")
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
