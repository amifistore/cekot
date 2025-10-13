import logging
import requests
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import database
import config

logger = logging.getLogger(__name__)

# State untuk ConversationHandler
CHOOSING_PRODUCT, ENTER_TUJUAN, CONFIRM_ORDER = range(3)

def get_product_list():
    """Ambil daftar produk aktif, tidak kosong, tidak gangguan."""
    conn = database.sqlite3.connect(database.DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT code, name, price, description 
        FROM products 
        WHERE kosong=0 AND gangguan=0 AND status='active'
        ORDER BY name ASC
    """)
    products = [{'code': row[0], 'name': row[1], 'price': row[2], 'description': row[3]} for row in c.fetchall()]
    conn.close()
    return products

async def start_order_from_callback(query, context):
    products = get_product_list()
    if not products:
        await query.edit_message_text("❌ Tidak ada produk tersedia saat ini.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(
            f"{prod['name']} ({prod['code']}) - Rp {prod['price']:,.0f}",
            callback_data=f"prod_{prod['code']}")]
        for prod in products
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🛒 PILIH PRODUK\nSilakan pilih produk digital yang ingin Anda beli:",
        reply_markup=reply_markup
    )
    return CHOOSING_PRODUCT

async def choose_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if not data.startswith("prod_"):
        await query.edit_message_text("❌ Produk tidak valid.")
        return ConversationHandler.END

    kode_produk = data.replace("prod_", "")
    products = get_product_list()
    found = next((p for p in products if p['code'] == kode_produk), None)
    if not found:
        await query.edit_message_text("❌ Produk tidak ditemukan atau tidak tersedia.")
        return ConversationHandler.END

    context.user_data['selected_product'] = found
    desc = found['description'] or "(Deskripsi produk tidak tersedia)"
    await query.edit_message_text(
        f"🛒 Produk: {found['name']}\nKode: {found['code']}\nHarga: Rp {found['price']:,.0f}\n\n"
        f"Deskripsi:\n{desc}\n\nMasukkan nomor tujuan (misal: 08xxxxxxxxxx):"
    )
    return ENTER_TUJUAN

async def enter_tujuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tujuan = update.message.text.strip()
    if not tujuan.isdigit() or not (10 <= len(tujuan) <= 14) or not tujuan.startswith('0'):
        await update.message.reply_text("❌ Nomor tujuan tidak valid. Masukkan nomor seperti: 08xxxxxxxxxx")
        return ENTER_TUJUAN

    context.user_data['tujuan'] = tujuan
    prod = context.user_data['selected_product']
    await update.message.reply_text(
        f"Konfirmasi order:\n\nProduk: {prod['name']} ({prod['code']})\n"
        f"Harga: Rp {prod['price']:,.0f}\nTujuan: {tujuan}\n\n"
        "Ketik 'YA' untuk konfirmasi atau 'TIDAK' untuk membatalkan."
    )
    return CONFIRM_ORDER

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text != "ya":
        await update.message.reply_text("Order dibatalkan.")
        return ConversationHandler.END

    user = update.message.from_user
    user_id = str(user.id)
    username = user.username or f"user_{user_id}"
    full_name = user.full_name or ""
    prod = context.user_data['selected_product']
    tujuan = context.user_data['tujuan']

    # Pastikan user ada di database
    database.get_or_create_user(user_id, username, full_name)
    saldo = database.get_user_saldo(user_id)
    harga = prod['price']
    if saldo < harga:
        await update.message.reply_text(
            f"❌ Saldo Anda kurang.\nSaldo: Rp {saldo:,.0f}\nHarga produk: Rp {harga:,.0f}"
        )
        return ConversationHandler.END

    reff_id = f"akrab_{uuid.uuid4().hex[:10]}"

    # Potong saldo
    if not database.increment_user_saldo(user_id, -harga):
        await update.message.reply_text("❌ Gagal memotong saldo. Silakan coba lagi.")
        return ConversationHandler.END

    # Kirim ke API provider
    payload = {
        "produk": prod['code'],
        "tujuan": tujuan,
        "reff_id": reff_id,
        "api_key": config.API_KEY_PROVIDER
    }
    try:
        resp = requests.get("https://panel.khfy-store.com/api_v2/trx", params=payload, timeout=20)
        api_response = resp.json() if resp.ok else None
    except Exception as e:
        logger.error(f"Error API Provider: {e}")
        api_response = None

    status_api = "PROSES"
    keterangan = "Order terkirim, menunggu update provider"
    if api_response:
        status_api = api_response.get('status', 'PROSES').upper()
        keterangan = api_response.get('msg', keterangan)

    # Simpan ke riwayat pembelian
    try:
        conn = database.sqlite3.connect(database.DB_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO riwayat_pembelian (
                username, kode_produk, nama_produk, tujuan, harga, saldo_awal,
                reff_id, status_api, keterangan, waktu
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            username,
            prod['code'],
            prod['name'],
            tujuan,
            harga,
            saldo,
            reff_id,
            status_api,
            keterangan,
            database.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error riwayat_pembelian: {e}")

    # Feedback ke user
    if status_api in ['SUKSES', 'SUCCESS']:
        await update.message.reply_text(f"✅ Order berhasil!\n{prod['name']} untuk {tujuan} diproses.\n{keterangan}")
    elif status_api in ['GAGAL', 'FAILED']:
        await update.message.reply_text(f"❌ Order gagal!\n{keterangan}")
    else:
        await update.message.reply_text(f"🕑 Order diproses.\n{keterangan}")

    return ConversationHandler.END

def get_conversation_handler():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(choose_product, pattern=r'^prod_')],
        states={
            CHOOSING_PRODUCT: [CallbackQueryHandler(choose_product, pattern=r'^prod_')],
            ENTER_TUJUAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_tujuan)],
            CONFIRM_ORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_order)],
        },
        fallbacks=[],
        allow_reentry=True
    )
