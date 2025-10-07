import config
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
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
        await update.message.reply_text(
            "❌ **Produk Belum Tersedia**\n\n"
            "Silakan minta admin untuk update produk terlebih dahulu dengan /updateproduk",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    # Format pesan yang lebih menarik
    msg = (
        f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
        "🎮 **PILIH PRODUK:**\n\n"
    )
    
    produk_keyboard = []
    for code, name, price in produk_list:
        msg += f"▪️ **{name}**\n   Kode: `{code}` - Rp {price:,.0f}\n\n"
        produk_keyboard.append([f"🛒 {code}"])

    # Tambahkan opsi batal
    produk_keyboard.append(["❌ Batalkan Order"])
    
    await update.message.reply_text(
        msg,
        reply_markup=ReplyKeyboardMarkup(
            produk_keyboard, 
            one_time_keyboard=True, 
            resize_keyboard=True,
            input_field_placeholder="Pilih produk atau ketik kode..."
        ),
        parse_mode='Markdown'
    )
    return ASK_ORDER_PRODUK

async def order_produk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    
    # Handle pembatalan
    if user_input == "❌ Batalkan Order":
        await update.message.reply_text(
            "❌ **Order Dibatalkan**\n\nKetik /order untuk memulai lagi.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Hapus emoji jika ada
    kode_produk = user_input.replace("🛒 ", "").strip()
    
    produk_list = context.user_data.get("produk_list", [])
    produk = next((p for p in produk_list if p[0] == kode_produk), None)
    
    if not produk:
        await update.message.reply_text(
            "❌ **Produk Tidak Ditemukan**\n\nSilakan pilih produk dari keyboard atau ketik kode yang valid.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ASK_ORDER_PRODUK
    
    context.user_data["order_produk"] = produk
    
    await update.message.reply_text(
        f"✅ **{produk[1]}** dipilih\n"
        f"💵 **Harga:** Rp {produk[2]:,.0f}\n\n"
        "📱 **Masukkan nomor tujuan:**\n"
        "Contoh: `081234567890`",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    return ASK_ORDER_TUJUAN

async def order_tujuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tujuan = update.message.text.strip()
    
    # Validasi format nomor
    if not tujuan.startswith("08") or not (10 <= len(tujuan) <= 14) or not tujuan.isdigit():
        await update.message.reply_text(
            "❌ **Format Nomor Tidak Valid**\n\n"
            "Format yang benar: `08xxxxxxxxxx`\n"
            "Panjang: 10-14 digit\n\n"
            "Silakan masukkan ulang:",
            parse_mode='Markdown'
        )
        return ASK_ORDER_TUJUAN
    
    context.user_data["order_tujuan"] = tujuan
    produk = context.user_data["order_produk"]
    
    # Buat keyboard konfirmasi
    confirm_keyboard = [
        ["✅ Ya, Lanjutkan Order"],
        ["❌ Batalkan Order"]
    ]
    
    await update.message.reply_text(
        f"📋 **KONFIRMASI ORDER**\n\n"
        f"📦 **Produk:** {produk[1]}\n"
        f"💵 **Harga:** Rp {produk[2]:,.0f}\n"
        f"📱 **Tujuan:** {tujuan}\n\n"
        "**Apakah data sudah benar?**",
        reply_markup=ReplyKeyboardMarkup(
            confirm_keyboard,
            one_time_keyboard=True,
            resize_keyboard=True
        ),
        parse_mode='Markdown'
    )
    return ASK_ORDER_CONFIRM

async def order_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_input = update.message.text.strip().lower()
    
    # Handle pembatalan
    if user_input in ["❌ batalkan order", "batal", "cancel"]:
        await update.message.reply_text(
            "❌ **Order Dibatalkan**\n\nKetik /order untuk memulai lagi.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Jika tidak konfirmasi "ya"
    if user_input not in ["✅ ya, lanjutkan order", "ya", "y"]:
        await update.message.reply_text(
            "❌ **Order Dibatalkan**\n\nKetik /order untuk memulai lagi.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    produk = context.user_data["order_produk"]
    tujuan = context.user_data["order_tujuan"]
    saldo = database.get_user_saldo(user_id)
    
    # Cek saldo
    if saldo < produk[2]:
        await update.message.reply_text(
            f"❌ **Saldo Tidak Cukup**\n\n"
            f"Saldo Anda: Rp {saldo:,.0f}\n"
            f"Dibutuhkan: Rp {produk[2]:,.0f}\n\n"
            "Silakan topup saldo terlebih dahulu.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Proses order
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
        f"🎉 **ORDER BERHASIL!**\n\n"
        f"📦 **Produk:** {produk[1]}\n"
        f"💵 **Harga:** Rp {produk[2]:,.0f}\n"
        f"📱 **Tujuan:** {tujuan}\n"
        f"💰 **Saldo Sekarang:** Rp {saldo - produk[2]:,.0f}\n\n"
        f"📋 **ID Transaksi:** `{reff_id}`",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def order_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ **Proses Order Dibatalkan**\n\nKetik /order untuk memulai lagi.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
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
