# order_handler.py - Sistem Pemesanan Produk Lengkap
import logging
from datetime import datetime
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

import database
import config

# Setup logging
logger = logging.getLogger(__name__)

# Ambil konfigurasi
ADMIN_CHAT_ID = getattr(config, 'ADMIN_CHAT_ID', None)
PRODUCTS_PER_PAGE = 5  # Jumlah produk per halaman

# Tahapan/State untuk ConversationHandler
SELECT_CATEGORY, SELECT_PRODUCT, ADD_TO_CART, CHECKOUT = range(4)

# ==================== UTILITY FUNCTIONS ====================
def format_currency(amount: int) -> str:
    """Format mata uang dengan titik sebagai pemisah ribuan."""
    return f"Rp {amount:,}".replace(',', '.')

# ==================== ORDER CONVERSATION ====================

async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Memulai alur pemesanan dengan menampilkan kategori produk."""
    context.user_data['cart'] = {}  # Inisialisasi keranjang belanja

    categories = database.get_categories()
    if not categories:
        await update.message.reply_text("🛒 Maaf, saat ini belum ada produk yang tersedia.")
        return ConversationHandler.END

    keyboard = []
    for cat in categories:
        keyboard.append([InlineKeyboardButton(cat['name'], callback_data=f"cat_{cat['id']}")])
    
    keyboard.append([InlineKeyboardButton("❌ Batalkan", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("🛒 Silakan pilih kategori produk yang Anda inginkan:", reply_markup=reply_markup)
    return SELECT_CATEGORY

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menampilkan produk dalam kategori yang dipilih dengan paginasi."""
    query = update.callback_query
    await query.answer()

    # Parsing callback data, contoh: "cat_1" atau "cat_1_page_2"
    parts = query.data.split('_')
    category_id = int(parts[1])
    page = int(parts[3]) if len(parts) > 3 else 1
    
    context.user_data['current_category_id'] = category_id

    result = database.get_products_by_category(category_id, page, PRODUCTS_PER_PAGE)
    products = result.get('products', [])
    total_pages = result.get('total_pages', 1)

    if not products:
        await query.edit_message_text(" kosong untuk kategori ini.")
        return SELECT_CATEGORY

    keyboard = []
    for prod in products:
        label = f"{prod['name']} - {format_currency(prod['price'])}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"prod_{prod['id']}")])

    # Tombol Paginasi
    pagination_buttons = []
    if page > 1:
        pagination_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"cat_{category_id}_page_{page - 1}"))
    if page < total_pages:
        pagination_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"cat_{category_id}_page_{page + 1}"))
    
    if pagination_buttons:
        keyboard.append(pagination_buttons)

    keyboard.append([InlineKeyboardButton("🛒 Lihat Keranjang", callback_data="view_cart")])
    keyboard.append([InlineKeyboardButton("⬅️ Kembali ke Kategori", callback_data="back_to_categories")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(f"Pilih produk (Halaman {page}/{total_pages}):", reply_markup=reply_markup)
    return SELECT_PRODUCT

async def back_to_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kembali ke menu pemilihan kategori."""
    query = update.callback_query
    await query.answer()
    
    categories = database.get_categories()
    keyboard = []
    for cat in categories:
        keyboard.append([InlineKeyboardButton(cat['name'], callback_data=f"cat_{cat['id']}")])
    keyboard.append([InlineKeyboardButton("❌ Batalkan", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("🛒 Silakan pilih kategori produk:", reply_markup=reply_markup)
    return SELECT_CATEGORY

async def select_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Meminta pengguna memasukkan detail (misal: nomor tujuan) untuk produk yang dipilih."""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[1])
    product = database.get_product_by_id(product_id)

    if not product or product.get('stock', 0) <= 0:
        await query.message.reply_text("⚠️ Maaf, produk ini sedang habis atau tidak tersedia.")
        return SELECT_PRODUCT

    context.user_data['selected_product'] = product
    
    # Untuk produk seperti pulsa/voucher, biasanya butuh nomor tujuan
    await query.edit_message_text(
        f"Anda memilih: **{product['name']}**\n"
        f"Harga: {format_currency(product['price'])}\n\n"
        "➡️ Silakan masukkan **Nomor Tujuan** (contoh: 081234567890).",
        parse_mode='Markdown'
    )
    return ADD_TO_CART

async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menambahkan produk ke keranjang setelah menerima nomor tujuan."""
    target_number = update.message.text
    product = context.user_data.get('selected_product')
    cart = context.user_data.get('cart', {})

    if not product:
        await update.message.reply_text("Terjadi kesalahan, silakan pilih produk lagi.")
        return SELECT_PRODUCT

    # Simpan produk beserta nomor tujuannya. Kunci unik untuk item yang sama ke nomor yang sama.
    item_key = f"{product['id']}_{target_number}"
    
    if item_key in cart:
        # Jika produk dengan nomor tujuan yang sama sudah ada, mungkin beri notifikasi atau update.
        # Untuk simplicity, kita replace.
        cart[item_key] = {'product': product, 'target': target_number, 'quantity': 1}
    else:
        cart[item_key] = {'product': product, 'target': target_number, 'quantity': 1}
    
    context.user_data['cart'] = cart
    
    keyboard = [
        [InlineKeyboardButton("🛍️ Lanjutkan Belanja", callback_data=f"cat_{context.user_data['current_category_id']}")],
        [InlineKeyboardButton("🛒 Lihat Keranjang & Checkout", callback_data="view_cart")],
        [InlineKeyboardButton("❌ Batalkan Pesanan", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"✅ Berhasil ditambahkan ke keranjang:\n"
        f"**Produk:** {product['name']}\n"
        f"**Tujuan:** `{target_number}`\n\n"
        "Apa langkah Anda selanjutnya?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return SELECT_PRODUCT # Kembali ke state pemilihan produk, tapi user bisa navigasi dari tombol

async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menampilkan isi keranjang belanja dan total harga."""
    query = update.callback_query
    await query.answer()
    
    cart = context.user_data.get('cart', {})
    if not cart:
        await query.edit_message_text("🛒 Keranjang belanja Anda kosong.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali Belanja", callback_data=f"cat_{context.user_data.get('current_category_id', 1)}")]]))
        return SELECT_PRODUCT

    message = "🛒 **Isi Keranjang Belanja Anda:**\n\n"
    total_price = 0
    for key, item in cart.items():
        price = item['product']['price']
        message += f"• **{item['product']['name']}**\n"
        message += f"  - Tujuan: `{item['target']}`\n"
        message += f"  - Harga: {format_currency(price)}\n\n"
        total_price += price
    
    message += f"💰 **Total Belanja:** `{format_currency(total_price)}`"
    context.user_data['total_price'] = total_price

    keyboard = [
        [InlineKeyboardButton(f"✅ Bayar & Proses Pesanan", callback_data="checkout")],
        [InlineKeyboardButton("🗑️ Kosongkan Keranjang", callback_data="clear_cart")],
        [InlineKeyboardButton("⬅️ Kembali Belanja", callback_data=f"cat_{context.user_data.get('current_category_id', 1)}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    return CHECKOUT

async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mengosongkan keranjang belanja."""
    query = update.callback_query
    await query.answer()
    context.user_data['cart'] = {}
    context.user_data['total_price'] = 0
    
    await query.edit_message_text("🗑️ Keranjang belanja telah dikosongkan.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali Belanja", callback_data=f"cat_{context.user_data.get('current_category_id', 1)}")]]))
    return SELECT_PRODUCT

async def checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Memproses checkout, mengecek saldo dan meminta konfirmasi akhir."""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    total_price = context.user_data.get('total_price', 0)
    user_balance = database.get_user_saldo(user_id)

    if user_balance < total_price:
        await query.message.reply_text(
            f"⚠️ **Saldo Tidak Cukup!**\n\n"
            f"Total belanja Anda: {format_currency(total_price)}\n"
            f"Saldo Anda saat ini: {format_currency(user_balance)}\n\n"
            "Silakan lakukan top up terlebih dahulu.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Top Up Saldo", callback_data="topup_start")]])
        )
        context.user_data.clear()
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("👍 Ya, Konfirmasi & Bayar", callback_data="confirm_purchase")],
        [InlineKeyboardButton("❌ Tidak, Batalkan", callback_data="view_cart")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"**KONFIRMASI PEMBAYARAN**\n\n"
        f"Total Belanja: **{format_currency(total_price)}**\n"
        f"Saldo Anda: {format_currency(user_balance)}\n"
        f"Sisa Saldo Setelah Transaksi: {format_currency(user_balance - total_price)}\n\n"
        "Apakah Anda yakin ingin melanjutkan pembayaran?",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    return CHECKOUT

async def confirm_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menyelesaikan pembelian, mengurangi saldo, dan mencatat pesanan."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_id = str(user.id)
    total_price = context.user_data.get('total_price', 0)
    cart = context.user_data.get('cart', {})
    user_balance = database.get_user_saldo(user_id)
    
    # Double check saldo
    if user_balance < total_price:
        await query.edit_message_text("⚠️ Saldo tidak cukup. Transaksi dibatalkan.")
        return ConversationHandler.END

    # Proses Transaksi
    new_balance = user_balance - total_price
    database.update_user_saldo(user_id, new_balance)

    # Buat ringkasan item untuk disimpan di DB
    cart_summary = {key: {
        'name': item['product']['name'],
        'target': item['target'],
        'price': item['product']['price']
    } for key, item in cart.items()}
    
    order_id = database.create_order(user_id, json.dumps(cart_summary), total_price)

    # Pesan untuk user
    receipt_message = (
        f"✅ **Transaksi Berhasil!**\n\n"
        f"Terima kasih telah berbelanja.\n"
        f"**ID Pesanan:** `{order_id}`\n"
        f"**Total Pembayaran:** {format_currency(total_price)}\n"
        f"**Sisa Saldo:** {format_currency(new_balance)}\n\n"
        "Pesanan Anda sedang diproses."
    )
    await query.edit_message_text(receipt_message, parse_mode='Markdown')

    # Notifikasi untuk Admin
    if ADMIN_CHAT_ID:
        try:
            admin_message = f"🔔 **Pesanan Baru Diterima!**\n\n"
            admin_message += f"**ID Pesanan:** `{order_id}`\n"
            admin_message += f"**Dari:** {user.full_name} (`{user_id}`)\n"
            admin_message += f"**Total:** {format_currency(total_price)}\n\n"
            admin_message += "**Detail Item:**\n"
            for _, item in cart.items():
                admin_message += f"- {item['product']['name']} ke `{item['target']}`\n"
            
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Gagal mengirim notifikasi ke admin: {e}")

    context.user_data.clear()
    return ConversationHandler.END

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Membatalkan seluruh proses pemesanan."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("🛒 Proses pemesanan dibatalkan.")
    else:
        await update.message.reply_text("🛒 Proses pemesanan dibatalkan.")
        
    context.user_data.clear()
    return ConversationHandler.END

# ==================== STANDALONE HANDLERS ====================

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan riwayat 5 pesanan terakhir pengguna."""
    user_id = str(update.effective_user.id)
    orders = database.get_user_orders(user_id) # Asumsi fungsi ini mengembalikan pesanan terbaru dulu

    if not orders:
        await update.message.reply_text("Anda belum memiliki riwayat pesanan.")
        return

    message = "📜 **5 Riwayat Pesanan Terakhir Anda:**\n\n"
    for order in orders[:5]:
        order_date = order['created_at'].strftime('%d %b %Y, %H:%M')
        message += f"• **ID:** `{order['id']}`\n"
        message += f"  - **Tanggal:** {order_date}\n"
        message += f"  - **Total:** {format_currency(order['total_price'])}\n\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

# ==================== HANDLER SETUP ====================

def get_order_conversation_handler() -> ConversationHandler:
    """Membuat dan mengembalikan ConversationHandler untuk alur pemesanan."""
    return ConversationHandler(
        entry_points=[CommandHandler('order', order_start)],
        states={
            SELECT_CATEGORY: [
                CallbackQueryHandler(select_category, pattern="^cat_"),
            ],
            SELECT_PRODUCT: [
                CallbackQueryHandler(select_product, pattern="^prod_"),
                CallbackQueryHandler(view_cart, pattern="^view_cart$"),
                CallbackQueryHandler(select_category, pattern="^cat_"), # Untuk Lanjutkan Belanja
                CallbackQueryHandler(back_to_categories, pattern="^back_to_categories$"),
            ],
            ADD_TO_CART: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_to_cart),
            ],
            CHECKOUT: [
                CallbackQueryHandler(checkout, pattern="^checkout$"),
                CallbackQueryHandler(confirm_purchase, pattern="^confirm_purchase$"),
                CallbackQueryHandler(view_cart, pattern="^view_cart$"), # Kembali dari konfirmasi
                CallbackQueryHandler(clear_cart, pattern="^clear_cart$"),
                CallbackQueryHandler(select_category, pattern="^cat_"), # Kembali Belanja
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_order, pattern="^cancel$"),
            CommandHandler('cancel', cancel_order)
        ],
        map_to_parent={
            # Jika user topup di tengah jalan, kembali ke menu utama setelahnya
            ConversationHandler.END: ConversationHandler.END,
        }
    )

def get_order_handlers():
    """Mengembalikan semua handler yang terkait dengan fitur order."""
    return [
        get_order_conversation_handler(),
        CommandHandler('myorders', my_orders),
    ]
