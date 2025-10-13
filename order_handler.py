import logging
import uuid
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
import database
import config
import sqlite3
import telegram

logger = logging.getLogger(__name__)

MENU, CHOOSING_PRODUCT, ENTER_TUJUAN, CONFIRM_ORDER = range(4)
PRODUCTS_PER_PAGE = 5

def get_product_list():
    conn = sqlite3.connect(database.DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT code, name, price, category, description
        FROM products
        WHERE status='active' AND gangguan=0 AND kosong=0
        ORDER BY category ASC, name ASC
    """)
    products = [
        {
            'code': row[0],
            'name': row[1],
            'price': row[2],
            'category': row[3] or "Umum",
            'description': row[4] or ""
        }
        for row in c.fetchall()
    ]
    conn.close()
    return products

def get_products_keyboard(products, page=0):
    total_pages = (len(products) - 1) // PRODUCTS_PER_PAGE + 1
    start = page * PRODUCTS_PER_PAGE
    end = start + PRODUCTS_PER_PAGE
    page_products = products[start:end]
    keyboard = [
        [InlineKeyboardButton(
            f"{prod['name']} ({prod['code']}) - Rp {prod['price']:,.0f} [{prod['category']}]",
            callback_data=f"prod_{prod['code']}")
        ] for prod in page_products
    ]
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{page-1}"))
    if page < total_pages - 1:
        navigation.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{page+1}"))
    if navigation:
        keyboard.append(navigation)
    keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard), total_pages

async def menu_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    saldo = database.get_user_saldo(str(user.id))
    keyboard = [
        [InlineKeyboardButton("🛒 Beli Produk", callback_data="menu_order")],
        [InlineKeyboardButton("💳 Cek Saldo", callback_data="menu_saldo")],
        [InlineKeyboardButton("📞 Bantuan", callback_data="menu_help")]
    ]
    if str(user.id) in config.ADMIN_TELEGRAM_IDS:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="menu_admin")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        f"🤖 *Selamat Datang!*\n\n"
        f"Halo, *{user.full_name or user.username or user.id}*!\n"
        f"💰 Saldo Anda: *Rp {saldo:,.0f}*\n\n"
        f"Pilih menu di bawah:"
    )
    # PATCH: handle Message is not modified
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e):
            return MENU
        raise
    return MENU

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "menu_order":
        return await show_product_menu(update, context, page=0)
    elif data == "menu_saldo":
        saldo = database.get_user_saldo(str(query.from_user.id))
        try:
            await query.edit_message_text(
                f"💳 *SALDO ANDA*\n\nSaldo: *Rp {saldo:,.0f}*\n\nGunakan menu untuk topup atau order produk.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
                parse_mode="Markdown"
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                return MENU
            raise
        return MENU
    elif data == "menu_help":
        try:
            await query.edit_message_text(
                "📞 *BANTUAN*\n\n"
                "Jika mengalami masalah, hubungi admin @username_admin.\n\n"
                "Cara order: pilih *Beli Produk*, pilih produk, isi nomor tujuan, konfirmasi.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
                parse_mode="Markdown"
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                return MENU
            raise
        return MENU
    elif data == "menu_admin" and str(query.from_user.id) in config.ADMIN_TELEGRAM_IDS:
        try:
            await query.edit_message_text(
                "👑 *ADMIN PANEL*\n\nFitur admin bisa dikembangkan di sini.\nContoh: tambah produk, cek riwayat, dsb.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
                parse_mode="Markdown"
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                return MENU
            raise
        return MENU
    elif data == "menu_main":
        return await menu_main(update, context)
    elif data.startswith("page_"):
        page = int(data.split("_")[1])
        return await show_product_menu(update, context, page)
    else:
        await query.answer()
        try:
            await query.edit_message_text("Menu tidak dikenal.")
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                return MENU
            raise
        return MENU

async def show_product_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    products = get_product_list()
    if not products:
        try:
            await update.callback_query.edit_message_text(
                "❌ Tidak ada produk tersedia saat ini.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                return MENU
            raise
        return MENU
    reply_markup, total_pages = get_products_keyboard(products, page)
    try:
        await update.callback_query.edit_message_text(
            f"🛒 *PILIH PRODUK*\nHalaman {page+1} dari {total_pages}\n\nSilakan pilih produk digital yang ingin Anda beli:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e):
            return CHOOSING_PRODUCT
        raise
    context.user_data["product_list"] = products
    context.user_data["product_page"] = page
    return CHOOSING_PRODUCT

async def choose_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "menu_main":
        return await menu_main(update, context)
    if not data.startswith("prod_"):
        await query.answer()
        try:
            await query.edit_message_text("❌ Produk tidak valid.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]))
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                return MENU
            raise
        return MENU
    kode_produk = data.replace("prod_", "")
    products = context.user_data.get("product_list") or get_product_list()
    found = next((p for p in products if p['code'] == kode_produk), None)
    if not found:
        try:
            await query.edit_message_text("❌ Produk tidak ditemukan atau tidak tersedia.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]))
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                return MENU
            raise
        return MENU
    context.user_data['selected_product'] = found
    desc = found['description'] or "(Deskripsi produk tidak tersedia)"
    try:
        await query.edit_message_text(
            f"🛒 *Produk*: {found['name']}\n"
            f"*Kode*: {found['code']}\n"
            f"*Kategori*: {found['category']}\n"
            f"*Harga*: Rp {found['price']:,.0f}\n\n"
            f"*Deskripsi:*\n{desc}\n\n"
            f"Masukkan nomor tujuan (misal: 08xxxxxxxxxx):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
            parse_mode="Markdown"
        )
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e):
            return ENTER_TUJUAN
        raise
    return ENTER_TUJUAN

async def enter_tujuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tujuan = update.message.text.strip()
    if not tujuan.isdigit() or not (10 <= len(tujuan) <= 14) or not tujuan.startswith('0'):
        await update.message.reply_text(
            "❌ Nomor tujuan tidak valid. Masukkan nomor seperti: 08xxxxxxxxxx",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return ENTER_TUJUAN
    context.user_data['tujuan'] = tujuan
    prod = context.user_data['selected_product']
    keyboard = [
        [
            InlineKeyboardButton("✅ Konfirmasi", callback_data="confirm_order"),
            InlineKeyboardButton("❌ Batal", callback_data="menu_main"),
        ]
    ]
    await update.message.reply_text(
        f"*Konfirmasi Order:*\n\n"
        f"Produk: *{prod['name']} ({prod['code']})*\n"
        f"Kategori: *{prod['category']}*\n"
        f"Harga: *Rp {prod['price']:,.0f}*\n"
        f"Tujuan: *{tujuan}*\n\n"
        f"Tekan *Konfirmasi* untuk melanjutkan atau *Batal* untuk kembali ke menu utama.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CONFIRM_ORDER

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query and update.callback_query.data == "menu_main":
        return await menu_main(update, context)
    if update.callback_query and update.callback_query.data != "confirm_order":
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text("Order dibatalkan.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]))
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                return MENU
            raise
        return MENU
    user = update.effective_user
    user_id = str(user.id)
    username = user.username or f"user_{user_id}"
    full_name = user.full_name or ""
    prod = context.user_data['selected_product']
    tujuan = context.user_data['tujuan']

    database.get_or_create_user(user_id, username, full_name)
    saldo = database.get_user_saldo(user_id)
    harga = prod['price']
    if saldo < harga:
        try:
            await update.callback_query.edit_message_text(
                f"❌ Saldo Anda kurang.\nSaldo: Rp {saldo:,.0f}\nHarga produk: Rp {harga:,.0f}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                return MENU
            raise
        return MENU

    reff_id = f"akrab_{uuid.uuid4().hex[:10]}"

    if not database.increment_user_saldo(user_id, -harga):
        try:
            await update.callback_query.edit_message_text(
                "❌ Gagal memotong saldo. Silakan coba lagi.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                return MENU
            raise
        return MENU

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
    try:
        conn = sqlite3.connect(database.DB_PATH)
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

    try:
        if status_api in ['SUKSES', 'SUCCESS']:
            await update.callback_query.edit_message_text(
                f"✅ Order berhasil!\n\nProduk: *{prod['name']}*\nKategori: *{prod['category']}*\nTujuan: *{tujuan}*\n\n{keterangan}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
                parse_mode="Markdown"
            )
        elif status_api in ['GAGAL', 'FAILED']:
            await update.callback_query.edit_message_text(
                f"❌ Order gagal!\n{keterangan}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
                parse_mode="Markdown"
            )
        else:
            await update.callback_query.edit_message_text(
                f"🕑 Order diproses.\n{keterangan}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
                parse_mode="Markdown"
            )
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e):
            return MENU
        raise
    return MENU

def get_conversation_handler():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler, pattern=r'^menu_')],
        states={
            MENU: [
                CallbackQueryHandler(menu_handler, pattern=r'^menu_'),
                CallbackQueryHandler(menu_handler, pattern=r'^page_\d+')
            ],
            CHOOSING_PRODUCT: [
                CallbackQueryHandler(choose_product, pattern=r'^prod_'),
                CallbackQueryHandler(menu_handler, pattern=r'^menu_main'),
                CallbackQueryHandler(menu_handler, pattern=r'^page_\d+')
            ],
            ENTER_TUJUAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_tujuan)],
            CONFIRM_ORDER: [
                CallbackQueryHandler(confirm_order, pattern=r'^(confirm_order|menu_main)$')
            ],
        },
        fallbacks=[CallbackQueryHandler(menu_main, pattern=r'^menu_main')],
        allow_reentry=True
    )
