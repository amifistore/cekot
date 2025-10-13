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

MENU, CHOOSING_GROUP, CHOOSING_PRODUCT, ENTER_TUJUAN, CONFIRM_ORDER = range(5)
PRODUCTS_PER_PAGE = 8

# PATCH: Helper agar edit_message_text tidak error jika "Message is not modified"
async def safe_edit_message_text(callback_query, *args, **kwargs):
    try:
        await callback_query.edit_message_text(*args, **kwargs)
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e):
            return
        raise

def get_grouped_products():
    conn = sqlite3.connect(database.DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT code, name, price, category, description
        FROM products
        WHERE status='active' AND gangguan=0 AND kosong=0
        ORDER BY code ASC
    """)
    products = c.fetchall()
    conn.close()

    groups = {}
    for code, name, price, category, description in products:
        if code.startswith("BPAL"):
            group = "BPAL (Bonus Akrab L)"
        elif code.startswith("BPAXXL"):
            group = "BPAXXL (Bonus Akrab XXL)"
        elif code.startswith("XLA"):
            group = "XLA (Umum)"
        else:
            group = category or "Lainnya"
        if group not in groups:
            groups[group] = []
        groups[group].append({
            'code': code,
            'name': name,
            'price': price,
            'category': category,
            'description': description
        })
    return groups

async def menu_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = getattr(update, 'effective_user', None)
    if user is None and hasattr(update, "callback_query"):
        user = getattr(update.callback_query, "from_user", None)
    saldo = database.get_user_saldo(str(user.id)) if user else 0
    keyboard = [
        [InlineKeyboardButton("🛒 Beli Produk", callback_data="menu_order")],
        [InlineKeyboardButton("💳 Cek Saldo", callback_data="menu_saldo")],
        [InlineKeyboardButton("📞 Bantuan", callback_data="menu_help")]
    ]
    if user and str(user.id) in config.ADMIN_TELEGRAM_IDS:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="menu_admin")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        f"🤖 *Selamat Datang!*\n\n"
        f"Halo, *{getattr(user, 'full_name', None) or getattr(user, 'username', None) or getattr(user, 'id', None)}*!\n"
        f"💰 Saldo Anda: *Rp {saldo:,.0f}*\n\n"
        f"Pilih menu di bawah:"
    )
    if hasattr(update, "callback_query") and update.callback_query:
        await safe_edit_message_text(update.callback_query, text, reply_markup=reply_markup, parse_mode="Markdown")
    elif hasattr(update, "message") and update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    return MENU

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "menu_order":
        return await show_group_menu(update, context)
    elif data == "menu_saldo":
        saldo = database.get_user_saldo(str(query.from_user.id))
        await safe_edit_message_text(
            query,
            f"💳 *SALDO ANDA*\n\nSaldo: *Rp {saldo:,.0f}*\n\nGunakan menu untuk topup atau order produk.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
            parse_mode="Markdown"
        )
        return MENU
    elif data == "menu_help":
        await safe_edit_message_text(
            query,
            "📞 *BANTUAN*\n\n"
            "Jika mengalami masalah, hubungi admin @username_admin.\n\n"
            "Cara order: pilih *Beli Produk*, pilih produk, isi nomor tujuan, konfirmasi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
            parse_mode="Markdown"
        )
        return MENU
    elif data == "menu_admin" and str(query.from_user.id) in config.ADMIN_TELEGRAM_IDS:
        await safe_edit_message_text(
            query,
            "👑 *ADMIN PANEL*\n\nFitur admin bisa dikembangkan di sini.\nContoh: tambah produk, cek riwayat, dsb.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
            parse_mode="Markdown"
        )
        return MENU
    elif data == "menu_main":
        return await menu_main(update, context)
    else:
        await query.answer()
        await safe_edit_message_text(query, "Menu tidak dikenal.")
        return MENU

async def show_group_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    groups = get_grouped_products()
    keyboard = [
        [InlineKeyboardButton(group, callback_data=f"group_{group}")]
        for group in groups.keys()
    ]
    keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_message_text(
        update.callback_query,
        "📦 *PILIH GRUP PRODUK*\nSilakan pilih grup kuota/produk yang diinginkan:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["groups"] = groups
    return CHOOSING_GROUP

def get_products_keyboard_group(products, page=0):
    total_pages = (len(products) - 1) // PRODUCTS_PER_PAGE + 1
    start = page * PRODUCTS_PER_PAGE
    end = start + PRODUCTS_PER_PAGE
    page_products = products[start:end]
    keyboard = [
        [InlineKeyboardButton(
            f"{prod['name']} ({prod['code']}) - Rp {prod['price']:,.0f}",
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
    keyboard.append([InlineKeyboardButton("⬅️ Kembali Grup", callback_data="menu_order")])
    keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard), total_pages

async def choose_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    group_name = query.data.replace("group_", "")
    groups = context.user_data.get("groups")
    products = groups.get(group_name, [])
    context.user_data["current_group"] = group_name
    context.user_data["product_list"] = products
    context.user_data["product_page"] = 0
    return await show_product_in_group(query, context, page=0)

async def show_product_in_group(query, context, page=0):
    products = context.user_data.get("product_list", [])
    group_name = context.user_data.get("current_group", "")
    if not products:
        await safe_edit_message_text(
            query,
            f"❌ Tidak ada produk di grup {group_name}.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali Grup", callback_data="menu_order")]])
        )
        return CHOOSING_GROUP
    reply_markup, total_pages = get_products_keyboard_group(products, page)
    await safe_edit_message_text(
        query,
        f"🛒 *PILIH PRODUK DI {group_name}*\nHalaman {page+1} dari {total_pages}\n\nSilakan pilih produk:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["product_page"] = page
    return CHOOSING_PRODUCT

async def choose_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "menu_main":
        return await menu_main(update, context)
    if data == "menu_order":
        return await show_group_menu(update, context)
    if data.startswith("page_"):
        page = int(data.split("_")[1])
        return await show_product_in_group(query, context, page)
    if not data.startswith("prod_"):
        await query.answer()
        await safe_edit_message_text(query, "❌ Produk tidak valid.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]))
        return CHOOSING_PRODUCT
    kode_produk = data.replace("prod_", "")
    products = context.user_data.get("product_list") or []
    found = next((p for p in products if p['code'] == kode_produk), None)
    if not found:
        await safe_edit_message_text(query, "❌ Produk tidak ditemukan atau tidak tersedia.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]))
        return CHOOSING_PRODUCT
    context.user_data['selected_product'] = found
    desc = found['description'] or "(Deskripsi produk tidak tersedia)"
    await safe_edit_message_text(
        query,
        f"🛒 *Produk*: {found['name']}\n"
        f"*Kode*: {found['code']}\n"
        f"*Kategori*: {found['category']}\n"
        f"*Harga*: Rp {found['price']:,.0f}\n\n"
        f"*Deskripsi:*\n{desc}\n\n"
        f"Masukkan nomor tujuan (misal: 08xxxxxxxxxx):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
        parse_mode="Markdown"
    )
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
        await safe_edit_message_text(update.callback_query, "Order dibatalkan.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]))
        return MENU
    user = getattr(update, 'effective_user', None)
    if user is None and hasattr(update, "callback_query"):
        user = getattr(update.callback_query, "from_user", None)
    user_id = str(user.id)
    username = user.username or f"user_{user_id}"
    full_name = user.full_name or ""
    prod = context.user_data['selected_product']
    tujuan = context.user_data['tujuan']

    database.get_or_create_user(user_id, username, full_name)
    saldo = database.get_user_saldo(user_id)
    harga = prod['price']
    if saldo < harga:
        await safe_edit_message_text(
            update.callback_query,
            f"❌ Saldo Anda kurang.\nSaldo: Rp {saldo:,.0f}\nHarga produk: Rp {harga:,.0f}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return MENU

    reff_id = f"akrab_{uuid.uuid4().hex[:10]}"

    if not database.increment_user_saldo(user_id, -harga):
        await safe_edit_message_text(
            update.callback_query,
            "❌ Gagal memotong saldo. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
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

    if status_api in ['SUKSES', 'SUCCESS']:
        await safe_edit_message_text(
            update.callback_query,
            f"✅ Order berhasil!\n\nProduk: *{prod['name']}*\nKategori: *{prod['category']}*\nTujuan: *{tujuan}*\n\n{keterangan}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
            parse_mode="Markdown"
        )
    elif status_api in ['GAGAL', 'FAILED']:
        await safe_edit_message_text(
            update.callback_query,
            f"❌ Order gagal!\n{keterangan}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
            parse_mode="Markdown"
        )
    else:
        await safe_edit_message_text(
            update.callback_query,
            f"🕑 Order diproses.\n{keterangan}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
            parse_mode="Markdown"
        )
    return MENU

def get_conversation_handler():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler, pattern=r'^menu_')],
        states={
            MENU: [
                CallbackQueryHandler(menu_handler, pattern=r'^menu_'),
                CallbackQueryHandler(menu_main, pattern=r'^menu_main$'),
            ],
            CHOOSING_GROUP: [
                CallbackQueryHandler(choose_group, pattern=r'^group_'),
                CallbackQueryHandler(menu_main, pattern=r'^menu_main$'),
            ],
            CHOOSING_PRODUCT: [
                CallbackQueryHandler(choose_product, pattern=r'^prod_'),
                CallbackQueryHandler(choose_product, pattern=r'^menu_order$'),
                CallbackQueryHandler(choose_product, pattern=r'^page_\d+$'),
                CallbackQueryHandler(menu_main, pattern=r'^menu_main$'),
            ],
            ENTER_TUJUAN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_tujuan),
                CallbackQueryHandler(menu_main, pattern=r'^menu_main$'),
            ],
            CONFIRM_ORDER: [
                CallbackQueryHandler(confirm_order, pattern=r'^(confirm_order)$'),
                CallbackQueryHandler(menu_main, pattern=r'^menu_main$'),
            ],
        },
        fallbacks=[CallbackQueryHandler(menu_main, pattern=r'^menu_main$')],
        allow_reentry=True
    )
