import config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import aiohttp
import aiosqlite
import database
import sqlite3
from datetime import datetime

DB_PATH = "bot_topup.db"

# State untuk conversation handler
EDIT_PRODUK_MENU, EDIT_PRODUK_PILIH, EDIT_HARGA, EDIT_DESKRIPSI = range(4)

def is_admin(user):
    return str(user.id) in config.ADMIN_TELEGRAM_IDS

async def ensure_products_table():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                code TEXT PRIMARY KEY,
                name TEXT,
                price REAL,
                status TEXT,
                description TEXT,
                category TEXT,
                provider TEXT,
                gangguan INTEGER DEFAULT 0,
                kosong INTEGER DEFAULT 0,
                updated_at TEXT
            )
        """)
        
        columns_to_add = [
            ("category", "TEXT DEFAULT 'Umum'"),
            ("description", "TEXT DEFAULT ''"),
            ("provider", "TEXT DEFAULT ''"),
            ("gangguan", "INTEGER DEFAULT 0"),
            ("kosong", "INTEGER DEFAULT 0")
        ]
        
        for column_name, column_type in columns_to_add:
            try:
                await conn.execute(f"SELECT {column_name} FROM products LIMIT 1")
            except aiosqlite.OperationalError:
                await conn.execute(f"ALTER TABLE products ADD COLUMN {column_name} {column_type}")
        
        await conn.commit()

async def ensure_topup_requests_table():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS topup_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                username TEXT,
                full_name TEXT,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                proof_image TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        await conn.commit()

# ============================
# FITUR EDIT PRODUK
# ============================

async def edit_produk_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return EDIT_PRODUK_MENU

    await ensure_products_table()
    
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Harga Produk", callback_data="edit_harga")],
        [InlineKeyboardButton("📝 Edit Deskripsi Produk", callback_data="edit_deskripsi")],
        [InlineKeyboardButton("⬅️ Kembali ke Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🛠️ **MENU EDIT PRODUK**\n\n"
        "Pilih jenis edit yang ingin dilakukan:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return EDIT_PRODUK_MENU

async def edit_produk_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    context.user_data['edit_type'] = data

    if data in ['edit_harga', 'edit_deskripsi']:
        # Ambil daftar produk untuk dipilih
        await ensure_products_table()
        
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute("""
                SELECT code, name, price 
                FROM products 
                WHERE status='active' 
                ORDER BY name ASC 
                LIMIT 50
            """) as cursor:
                products = await cursor.fetchall()

        if not products:
            await query.edit_message_text("❌ Tidak ada produk yang tersedia untuk diedit.")
            return EDIT_PRODUK_MENU

        keyboard = []
        for code, name, price in products:
            btn_text = f"{name} - Rp {price:,.0f}"
            if len(btn_text) > 50:  # Telegram button text limit
                btn_text = f"{name[:30]}... - Rp {price:,.0f}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"select_product:{code}")])
        
        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_edit_menu")])

        edit_type_text = "harga" if data == "edit_harga" else "deskripsi"
        await query.edit_message_text(
            f"📦 **PILIH PRODUK UNTUK EDIT {edit_type_text.upper()}**\n\n"
            f"Pilih produk dari daftar di bawah:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return EDIT_PRODUK_PILIH

    elif data == "admin_back":
        await admin_menu_back(query, context)
        return EDIT_PRODUK_MENU
    elif data == "back_to_edit_menu":
        await edit_produk_start_from_query(query, context)
        return EDIT_PRODUK_MENU

async def select_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith('select_product:'):
        product_code = data.split(':')[1]
        context.user_data['selected_product'] = product_code
        
        # Dapatkan info produk
        await ensure_products_table()
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute("""
                SELECT code, name, price, description 
                FROM products 
                WHERE code = ?
            """, (product_code,)) as cursor:
                product = await cursor.fetchone()

        if product:
            code, name, price, description = product
            context.user_data['current_product'] = {
                'code': code,
                'name': name,
                'price': price,
                'description': description
            }

            edit_type = context.user_data.get('edit_type')
            
            if edit_type == 'edit_harga':
                await query.edit_message_text(
                    f"💰 **EDIT HARGA PRODUK**\n\n"
                    f"📦 **Produk:** {name}\n"
                    f"📌 **Kode:** {code}\n"
                    f"💰 **Harga Saat Ini:** Rp {price:,.0f}\n\n"
                    f"Silakan kirim harga baru (hanya angka):",
                    parse_mode='Markdown'
                )
                return EDIT_HARGA
            elif edit_type == 'edit_deskripsi':
                current_desc = description if description else "Belum ada deskripsi"
                await query.edit_message_text(
                    f"📝 **EDIT DESKRIPSI PRODUK**\n\n"
                    f"📦 **Produk:** {name}\n"
                    f"📌 **Kode:** {code}\n"
                    f"📄 **Deskripsi Saat Ini:**\n{current_desc}\n\n"
                    f"Silakan kirim deskripsi baru:",
                    parse_mode='Markdown'
                )
                return EDIT_DESKRIPSI

    await query.edit_message_text("❌ Terjadi kesalahan. Silakan coba lagi.")
    return EDIT_PRODUK_MENU

async def edit_harga_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return EDIT_PRODUK_MENU

    try:
        new_price = float(update.message.text.replace(',', '').strip())
        if new_price <= 0:
            await update.message.reply_text("❌ Harga harus lebih dari 0. Silakan coba lagi:")
            return EDIT_HARGA
    except ValueError:
        await update.message.reply_text("❌ Format harga tidak valid. Kirim hanya angka. Silakan coba lagi:")
        return EDIT_HARGA

    product_data = context.user_data.get('current_product')
    if not product_data:
        await update.message.reply_text("❌ Data produk tidak ditemukan. Silakan mulai ulang.")
        return EDIT_PRODUK_MENU

    product_code = product_data['code']
    product_name = product_data['name']
    old_price = product_data['price']

    # Update harga di database
    await ensure_products_table()
    async with aiosqlite.connect(DB_PATH) as conn:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        await conn.execute("""
            UPDATE products 
            SET price = ?, updated_at = ?
            WHERE code = ?
        """, (new_price, now, product_code))
        await conn.commit()

    keyboard = [
        [InlineKeyboardButton("✏️ Edit Produk Lain", callback_data="back_to_edit_menu")],
        [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"✅ **HARGA BERHASIL DIUPDATE!**\n\n"
        f"📦 **Produk:** {product_name}\n"
        f"📌 **Kode:** {product_code}\n"
        f"💰 **Harga Lama:** Rp {old_price:,.0f}\n"
        f"💰 **Harga Baru:** Rp {new_price:,.0f}\n\n"
        f"⏰ **Update:** {now}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return EDIT_PRODUK_MENU

async def edit_deskripsi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return EDIT_PRODUK_MENU

    new_description = update.message.text.strip()
    if not new_description:
        await update.message.reply_text("❌ Deskripsi tidak boleh kosong. Silakan coba lagi:")
        return EDIT_DESKRIPSI

    product_data = context.user_data.get('current_product')
    if not product_data:
        await update.message.reply_text("❌ Data produk tidak ditemukan. Silakan mulai ulang.")
        return EDIT_PRODUK_MENU

    product_code = product_data['code']
    product_name = product_data['name']
    old_description = product_data['description'] or "Belum ada deskripsi"

    # Update deskripsi di database
    await ensure_products_table()
    async with aiosqlite.connect(DB_PATH) as conn:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        await conn.execute("""
            UPDATE products 
            SET description = ?, updated_at = ?
            WHERE code = ?
        """, (new_description, now, product_code))
        await conn.commit()

    keyboard = [
        [InlineKeyboardButton("✏️ Edit Produk Lain", callback_data="back_to_edit_menu")],
        [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Potong deskripsi jika terlalu panjang untuk preview
    new_desc_preview = new_description[:100] + "..." if len(new_description) > 100 else new_description
    old_desc_preview = old_description[:100] + "..." if len(old_description) > 100 else old_description

    await update.message.reply_text(
        f"✅ **DESKRIPSI BERHASIL DIUPDATE!**\n\n"
        f"📦 **Produk:** {product_name}\n"
        f"📌 **Kode:** {product_code}\n\n"
        f"📄 **Deskripsi Lama:**\n{old_desc_preview}\n\n"
        f"📄 **Deskripsi Baru:**\n{new_desc_preview}\n\n"
        f"⏰ **Update:** {now}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return EDIT_PRODUK_MENU

async def edit_produk_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Proses edit produk dibatalkan.")
    return EDIT_PRODUK_MENU

async def edit_produk_start_from_query(query, context):
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Harga Produk", callback_data="edit_harga")],
        [InlineKeyboardButton("📝 Edit Deskripsi Produk", callback_data="edit_deskripsi")],
        [InlineKeyboardButton("⬅️ Kembali ke Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "🛠️ **MENU EDIT PRODUK**\n\n"
        "Pilih jenis edit yang ingin dilakukan:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ============================
# FITUR UPDATE PRODUK
# ============================

async def updateproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return

    await update.message.reply_text("🔄 Memperbarui Produk...")

    api_key = config.API_KEY_PROVIDER
    url = f"https://panel.khfy-store.com/api_v2/list_product?api_key={api_key}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as resp:
                resp.raise_for_status()
                data = await resp.json()
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal mengambil data: {e}")
        return

    if not data.get("ok", False):
        await update.message.reply_text("❌ Response error dari provider.")
        return

    produk_list = data.get("data", [])
    
    if not produk_list:
        await update.message.reply_text("⚠️ Tidak ada data dari provider.")
        return

    await ensure_products_table()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE products SET status = 'inactive'")
        
        count = 0
        skipped = 0
        skipped_gangguan = 0
        
        for prod in produk_list:
            code = str(prod.get("kode_produk", "")).strip()
            name = str(prod.get("nama_produk", "")).strip()
            price = float(prod.get("harga_final", 0))
            gangguan = int(prod.get("gangguan", 0))
            kosong = int(prod.get("kosong", 0))
            provider_code = str(prod.get("kode_provider", "")).strip()
            
            description = str(prod.get("deskripsi", "")).strip()
            if description == "a":
                description = f"Produk {name}"
            
            # Tentukan kategori
            category = "Umum"
            name_lower = name.lower()
            if "pulsa" in name_lower:
                category = "Pulsa"
            elif "data" in name_lower or "internet" in name_lower or "kuota" in name_lower:
                category = "Internet"
            elif "listrik" in name_lower or "pln" in name_lower:
                category = "Listrik"
            elif "game" in name_lower:
                category = "Game"
            elif "emoney" in name_lower or "gopay" in name_lower or "dana" in name_lower:
                category = "E-Money"
            elif "akrab" in name_lower or "bonus" in name_lower:
                category = "Paket Bonus"
            
            if not code or not name or price <= 0:
                skipped += 1
                continue
                
            if gangguan == 1 or kosong == 1:
                skipped_gangguan += 1
                continue
                
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await conn.execute("""
                INSERT INTO products (code, name, price, status, description, category, provider, gangguan, kosong, updated_at)
                VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name=excluded.name,
                    price=excluded.price,
                    status='active',
                    description=excluded.description,
                    category=excluded.category,
                    provider=excluded.provider,
                    gangguan=excluded.gangguan,
                    kosong=excluded.kosong,
                    updated_at=excluded.updated_at
            """, (code, name, price, description, category, provider_code, gangguan, kosong, now))
            count += 1
        
        await conn.commit()

    msg = (
        f"✅ **Update Produk Berhasil**\n\n"
        f"📊 **Statistik:**\n"
        f"├ Total dari Provider: {len(produk_list)} produk\n"
        f"├ Berhasil diupdate: {count} produk\n"
        f"├ Dilewati (data invalid): {skipped} produk\n"
        f"└ Dilewati (gangguan/kosong): {skipped_gangguan} produk\n\n"
        f"⏰ **Update Terakhir:** {datetime.now().strftime('%d-%m-%Y %H:%M')}"
    )
    
    await update.message.reply_text(msg, parse_mode='Markdown')

# ============================
# FITUR LIST PRODUK
# ============================

async def listproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return

    await ensure_products_table()
    
    page = int(context.args[0]) if context.args and context.args[0].isdigit() else 1
    limit = 15
    offset = (page - 1) * limit

    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
            total_count = (await cursor.fetchone())[0]
        
        async with conn.execute("""
            SELECT code, name, price, description, category, provider, gangguan, kosong 
            FROM products 
            WHERE status='active' 
            ORDER BY category, name ASC 
            LIMIT ? OFFSET ?
        """, (limit, offset)) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await update.message.reply_text("📭 Database produk kosong.")
        return

    total_pages = (total_count + limit - 1) // limit
    
    msg = f"📋 **DAFTAR PRODUK AKTIF**\n\n"
    msg += f"📊 **Halaman {page} dari {total_pages}**\n"
    msg += f"📈 **Total Produk:** {total_count} produk\n\n"

    categories = {}
    for code, name, price, description, category, provider, gangguan, kosong in rows:
        if category not in categories:
            categories[category] = []
        categories[category].append((code, name, price, description, provider, gangguan, kosong))

    for category, products in categories.items():
        msg += f"**{category.upper()}** ({len(products)} produk)\n"
        for code, name, price, description, provider, gangguan, kosong in products:
            status_emoji = "✅" if gangguan == 0 and kosong == 0 else "⚠️"
            msg += f"├ {status_emoji} **{name}**\n"
            msg += f"│ ├ Kode: `{code}`\n"
            msg += f"│ ├ Harga: Rp {price:,.0f}\n"
            if description and len(description) > 0 and description != f"Produk {name}":
                short_desc = description[:50] + "..." if len(description) > 50 else description
                msg += f"│ └ Deskripsi: {short_desc}\n"
            msg += "│\n"
        msg += "\n"

    if total_pages > 1:
        msg += f"\n**Navigasi:** `/listproduk <nomor_halaman>`"

    await update.message.reply_text(msg, parse_mode='Markdown')

# ============================
# SISTEM TOPUP YANG DIPERBAIKI
# ============================

async def topup_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return

    await ensure_topup_requests_table()
    
    status_filter = context.args[0].lower() if context.args else 'pending'
    valid_statuses = ['pending', 'approved', 'rejected', 'all']
    
    if status_filter not in valid_statuses:
        status_filter = 'pending'

    async with aiosqlite.connect(DB_PATH) as conn:
        if status_filter == 'all':
            cursor = await conn.execute("""
                SELECT id, user_id, username, full_name, amount, status, created_at 
                FROM topup_requests 
                ORDER BY created_at DESC LIMIT 20
            """)
        else:
            cursor = await conn.execute("""
                SELECT id, user_id, username, full_name, amount, status, created_at 
                FROM topup_requests 
                WHERE status = ? 
                ORDER BY created_at DESC LIMIT 20
            """, (status_filter,))
        
        requests = await cursor.fetchall()

    if not requests:
        await update.message.reply_text(f"📭 Tidak ada permintaan topup dengan status: `{status_filter}`")
        return

    keyboard = []
    msg = f"💳 **DAFTAR PERMINTAAN TOPUP**\n\n"
    msg += f"📊 **Status Filter:** `{status_filter}`\n"
    msg += f"📈 **Total:** {len(requests)} permintaan\n\n"

    for req_id, user_id, username, full_name, amount, status, created_at in requests:
        status_emoji = "⏳" if status == 'pending' else "✅" if status == 'approved' else "❌"
        
        msg += f"{status_emoji} **ID:** `{req_id}`\n"
        msg += f"👤 **User:** {full_name or username or user_id}\n"
        msg += f"💰 **Jumlah:** Rp {amount:,.0f}\n"
        msg += f"🕒 **Waktu:** {created_at}\n"
        msg += f"📊 **Status:** {status}\n\n"

        if status == 'pending':
            keyboard.append([
                InlineKeyboardButton(f"✅ Approve {req_id}", callback_data=f"approve_topup:{req_id}"),
                InlineKeyboardButton(f"❌ Reject {req_id}", callback_data=f"reject_topup:{req_id}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(f"📋 Lihat {req_id}", callback_data=f"view_topup:{req_id}")
            ])

    keyboard.append([
        InlineKeyboardButton("⏳ Pending", callback_data="topup_filter:pending"),
        InlineKeyboardButton("✅ Approved", callback_data="topup_filter:approved"),
        InlineKeyboardButton("❌ Rejected", callback_data="topup_filter:rejected"),
        InlineKeyboardButton("📋 All", callback_data="topup_filter:all")
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

async def topup_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user = query.from_user

    if not is_admin(user):
        await query.edit_message_text("❌ Tidak memiliki akses admin.")
        return

    if data.startswith('approve_topup:'):
        request_id = data.split(':')[1]
        await approve_topup(request_id, query, context)
    
    elif data.startswith('reject_topup:'):
        request_id = data.split(':')[1]
        await reject_topup(request_id, query, context)
    
    elif data.startswith('view_topup:'):
        request_id = data.split(':')[1]
        await view_topup_detail(request_id, query, context)
    
    elif data.startswith('topup_filter:'):
        status_filter = data.split(':')[1]
        await show_topup_list_by_status(status_filter, query, context)

async def approve_topup(request_id: str, query, context: ContextTypes.DEFAULT_TYPE):
    await ensure_topup_requests_table()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("""
            SELECT user_id, username, full_name, amount 
            FROM topup_requests 
            WHERE id = ? AND status = 'pending'
        """, (request_id,))
        request_data = await cursor.fetchone()

        if not request_data:
            await query.edit_message_text("❌ Permintaan topup tidak ditemukan.")
            return

        user_id, username, full_name, amount = request_data
        
        updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        await conn.execute("""
            UPDATE topup_requests 
            SET status = 'approved', updated_at = ? 
            WHERE id = ?
        """, (updated_at, request_id))
        
        database.increment_user_saldo(user_id, amount)
        await conn.commit()

    new_balance = database.get_user_saldo(user_id)

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎉 **TOPUP DITERIMA!**\n\n"
                 f"💰 **Jumlah:** Rp {amount:,.0f}\n"
                 f"💳 **Saldo Sekarang:** Rp {new_balance:,.0f}\n"
                 f"⏰ **Waktu:** {updated_at}\n\n"
                 f"Terima kasih telah topup!",
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Gagal mengirim notifikasi: {e}")

    await query.edit_message_text(
        f"✅ **Topup Disetujui**\n\n"
        f"**ID Request:** `{request_id}`\n"
        f"**User:** {full_name or username or user_id}\n"
        f"**Jumlah:** Rp {amount:,.0f}\n"
        f"**Saldo Baru:** Rp {new_balance:,.0f}\n"
        f"**Waktu:** {updated_at}",
        parse_mode='Markdown'
    )

async def reject_topup(request_id: str, query, context: ContextTypes.DEFAULT_TYPE):
    await ensure_topup_requests_table()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("""
            SELECT user_id, username, full_name, amount 
            FROM topup_requests 
            WHERE id = ? AND status = 'pending'
        """, (request_id,))
        request_data = await cursor.fetchone()

        if not request_data:
            await query.edit_message_text("❌ Permintaan topup tidak ditemukan.")
            return

        user_id, username, full_name, amount = request_data
        
        updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        await conn.execute("""
            UPDATE topup_requests 
            SET status = 'rejected', updated_at = ? 
            WHERE id = ?
        """, (updated_at, request_id))
        await conn.commit()

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❌ **TOPUP DITOLAK**\n\n"
                 f"💰 **Jumlah:** Rp {amount:,.0f}\n"
                 f"⏰ **Waktu:** {updated_at}\n\n"
                 f"Silakan hubungi admin untuk informasi lebih lanjut.",
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Gagal mengirim notifikasi: {e}")

    await query.edit_message_text(
        f"❌ **Topup Ditolak**\n\n"
        f"**ID Request:** `{request_id}`\n"
        f"**User:** {full_name or username or user_id}\n"
        f"**Jumlah:** Rp {amount:,.0f}\n"
        f"**Waktu:** {updated_at}",
        parse_mode='Markdown'
    )

async def view_topup_detail(request_id: str, query, context: ContextTypes.DEFAULT_TYPE):
    await ensure_topup_requests_table()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("""
            SELECT id, user_id, username, full_name, amount, status, proof_image, created_at, updated_at 
            FROM topup_requests 
            WHERE id = ?
        """, (request_id,))
        request_data = await cursor.fetchone()

    if not request_data:
        await query.edit_message_text("❌ Data topup tidak ditemukan.")
        return

    (req_id, user_id, username, full_name, amount, status, proof_image, created_at, updated_at) = request_data
    
    status_emoji = "⏳" if status == 'pending' else "✅" if status == 'approved' else "❌"
    
    msg = (
        f"📄 **DETAIL TOPUP**\n\n"
        f"🆔 **ID:** `{req_id}`\n"
        f"👤 **User ID:** `{user_id}`\n"
        f"📛 **Nama:** {full_name or 'Tidak ada'}\n"
        f"🔖 **Username:** @{username or 'Tidak ada'}\n"
        f"💰 **Jumlah:** Rp {amount:,.0f}\n"
        f"📊 **Status:** {status_emoji} {status}\n"
        f"🕒 **Dibuat:** {created_at}\n"
        f"🔄 **Diupdate:** {updated_at or 'Belum'}\n"
    )
    
    if proof_image:
        msg += f"\n📎 **Bukti Transfer:** Tersedia"
    
    keyboard = []
    if status == 'pending':
        keyboard = [
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_topup:{req_id}")],
            [InlineKeyboardButton("❌ Reject", callback_data=f"reject_topup:{req_id}")],
            [InlineKeyboardButton("📋 Kembali ke List", callback_data="topup_filter:all")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Kembali ke List", callback_data="topup_filter:all")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

async def show_topup_list_by_status(status_filter: str, query, context: ContextTypes.DEFAULT_TYPE):
    await ensure_topup_requests_table()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        if status_filter == 'all':
            cursor = await conn.execute("""
                SELECT id, user_id, username, full_name, amount, status, created_at 
                FROM topup_requests 
                ORDER BY created_at DESC LIMIT 20
            """)
        else:
            cursor = await conn.execute("""
                SELECT id, user_id, username, full_name, amount, status, created_at 
                FROM topup_requests 
                WHERE status = ? 
                ORDER BY created_at DESC LIMIT 20
            """, (status_filter,))
        
        requests = await cursor.fetchall()

    if not requests:
        await query.edit_message_text(f"📭 Tidak ada permintaan topup: `{status_filter}`")
        return

    keyboard = []
    msg = f"💳 **DAFTAR PERMINTAAN TOPUP**\n\n"
    msg += f"📊 **Status Filter:** `{status_filter}`\n"
    msg += f"📈 **Total:** {len(requests)} permintaan\n\n"

    for req_id, user_id, username, full_name, amount, status, created_at in requests:
        status_emoji = "⏳" if status == 'pending' else "✅" if status == 'approved' else "❌"
        
        msg += f"{status_emoji} **ID:** `{req_id}`\n"
        msg += f"👤 **User:** {full_name or username or user_id}\n"
        msg += f"💰 **Jumlah:** Rp {amount:,.0f}\n"
        msg += f"🕒 **Waktu:** {created_at}\n"
        msg += f"📊 **Status:** {status}\n\n"

        if status == 'pending':
            keyboard.append([
                InlineKeyboardButton(f"✅ Approve {req_id}", callback_data=f"approve_topup:{req_id}"),
                InlineKeyboardButton(f"❌ Reject {req_id}", callback_data=f"reject_topup:{req_id}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(f"📋 Lihat {req_id}", callback_data=f"view_topup:{req_id}")
            ])

    keyboard.append([
        InlineKeyboardButton("⏳ Pending", callback_data="topup_filter:pending"),
        InlineKeyboardButton("✅ Approved", callback_data="topup_filter:approved"),
        InlineKeyboardButton("❌ Rejected", callback_data="topup_filter:rejected"),
        InlineKeyboardButton("📋 All", callback_data="topup_filter:all")
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

# ============================
# MENU ADMIN UTAMA
# ============================

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Menu admin hanya untuk admin.")
        return
    
    await ensure_products_table()
    await ensure_topup_requests_table()
    
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
                active_products = (await cursor.fetchone())[0]
            
            async with conn.execute("SELECT COUNT(*) FROM topup_requests WHERE status='pending'") as cursor:
                pending_topups = (await cursor.fetchone())[0]
    except Exception as e:
        active_products = 0
        pending_topups = 0

    keyboard = [
        [InlineKeyboardButton("📦 Kelola Produk", callback_data="admin_products")],
        [InlineKeyboardButton("💳 Kelola Topup", callback_data="admin_topup")],
        [InlineKeyboardButton("👥 Kelola User", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Statistik Sistem", callback_data="admin_stats")],
        [InlineKeyboardButton("🛠️ Edit Produk", callback_data="admin_edit_produk")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👑 **MENU ADMIN**\n\n"
        f"📊 **Statistik Cepat:**\n"
        f"├ 📦 Produk Aktif: {active_products}\n"
        f"└ ⏳ Topup Pending: {pending_topups}\n\n"
        f"Pilih menu di bawah:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user = query.from_user

    if not is_admin(user):
        await query.edit_message_text("❌ Tidak memiliki akses admin.")
        return

    if data == "admin_products":
        await show_products_menu(query)
    elif data == "admin_topup":
        await show_topup_menu(query)
    elif data == "admin_users":
        await show_users_menu(query)
    elif data == "admin_stats":
        await show_stats_menu(query, context)
    elif data == "admin_edit_produk":
        await edit_produk_start_from_query(query, context)
    elif data == "admin_back":
        await admin_menu_back(query, context)

async def show_products_menu(query):
    keyboard = [
        [InlineKeyboardButton("🔄 Update Produk", callback_data="admin_update")],
        [InlineKeyboardButton("📋 List Produk", callback_data="admin_list")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📦 **MENU KELOLA PRODUK**\n\nPilih opsi:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_topup_menu(query):
    keyboard = [
        [InlineKeyboardButton("⏳ Lihat Topup Pending", callback_data="topup_filter:pending")],
        [InlineKeyboardButton("📋 Semua Topup", callback_data="topup_filter:all")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "💳 **MENU KELOLA TOPUP**\n\nPilih opsi:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_users_menu(query):
    keyboard = [
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "👥 **MENU KELOLA USER**\n\nGunakan command:\n`/cek_user <username>` - Cek user\n`/jadikan_admin <telegram_id>` - Tambah admin",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_stats_menu(query, context):
    await ensure_products_table()
    await ensure_topup_requests_table()
    
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
                total_products = (await cursor.fetchone())[0]
            async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active' AND gangguan = 0 AND kosong = 0") as cursor:
                available_products = (await cursor.fetchone())[0]
            
            async with conn.execute("SELECT COUNT(*) FROM topup_requests WHERE status='pending'") as cursor:
                pending_topups = (await cursor.fetchone())[0]
            async with conn.execute("SELECT COUNT(*) FROM topup_requests WHERE status='approved'") as cursor:
                approved_topups = (await cursor.fetchone())[0]
            async with conn.execute("SELECT COUNT(*) FROM topup_requests") as cursor:
                total_topups = (await cursor.fetchone())[0]
            
    except Exception as e:
        total_products = available_products = 0
        pending_topups = approved_topups = total_topups = 0

    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_stats")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📊 **STATISTIK SISTEM**\n\n"
        f"📦 **PRODUK:**\n"
        f"├ Total Produk: {total_products}\n"
        f"└ Tersedia: {available_products}\n\n"
        f"💳 **TOPUP:**\n"
        f"├ Total: {total_topups}\n"
        f"├ Pending: {pending_topups}\n"
        f"└ Approved: {approved_topups}\n\n"
        f"⏰ **Update:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def admin_menu_back(query, context):
    await admin_menu_from_query(query, context)

async def admin_menu_from_query(query, context):
    user = query.from_user
    
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
                active_products = (await cursor.fetchone())[0]
            
            async with conn.execute("SELECT COUNT(*) FROM topup_requests WHERE status='pending'") as cursor:
                pending_topups = (await cursor.fetchone())[0]
    except Exception as e:
        active_products = 0
        pending_topups = 0

    keyboard = [
        [InlineKeyboardButton("📦 Kelola Produk", callback_data="admin_products")],
        [InlineKeyboardButton("💳 Kelola Topup", callback_data="admin_topup")],
        [InlineKeyboardButton("👥 Kelola User", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Statistik Sistem", callback_data="admin_stats")],
        [InlineKeyboardButton("🛠️ Edit Produk", callback_data="admin_edit_produk")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"👑 **MENU ADMIN**\n\n"
        f"📊 **Statistik Cepat:**\n"
        f"├ 📦 Produk Aktif: {active_products}\n"
        f"└ ⏳ Topup Pending: {pending_topups}\n\n"
        f"Pilih menu di bawah:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ============================
# HANDLER LAINNYA
# ============================

async def cek_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return
    
    args = context.args
    username = args[0] if args else None
    
    if not username:
        await update.message.reply_text("❌ Format: `/cek_user <username>`")
        return
    
    conn = sqlite3.connect(database.DB_PATH)
    c = conn.cursor()
    c.execute("SELECT saldo, telegram_id FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        await update.message.reply_text(f"❌ User tidak ditemukan: `{username}`")
        return
    
    saldo, telegram_id = row
    admin_status = "✅ Ya" if str(telegram_id) in config.ADMIN_TELEGRAM_IDS else "❌ Tidak"
    
    await update.message.reply_text(
        f"👤 **INFORMASI USER**\n\n"
        f"📛 **Username:** `{username}`\n"
        f"💰 **Saldo:** Rp {saldo:,.0f}\n"
        f"🆔 **Telegram ID:** `{telegram_id}`\n"
        f"👑 **Status Admin:** {admin_status}",
        parse_mode='Markdown'
    )

async def jadikan_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return
    
    args = context.args
    telegram_id = args[0] if args else None
    
    if not telegram_id:
        await update.message.reply_text("❌ Format: `/jadikan_admin <telegram_id>`")
        return
    
    try:
        database.add_user_admin(telegram_id)
        await update.message.reply_text(
            f"✅ **Admin Berhasil Ditambahkan**\n\n"
            f"**Telegram ID:** `{telegram_id}`",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ **Gagal Menambahkan Admin**\n\n"
            f"**Error:** `{e}`",
            parse_mode='Markdown'
        )

# ============================
# REGISTER HANDLERS
# ============================

from telegram.ext import ConversationHandler

# Conversation handler untuk edit produk
edit_produk_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('edit_produk', edit_produk_start)],
    states={
        EDIT_PRODUK_MENU: [CallbackQueryHandler(edit_produk_menu_handler, pattern='^(edit_harga|edit_deskripsi|admin_back|back_to_edit_menu)$')],
        EDIT_PRODUK_PILIH: [CallbackQueryHandler(select_product_handler, pattern='^select_product:')],
        EDIT_HARGA: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_harga_handler)],
        EDIT_DESKRIPSI: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_deskripsi_handler)],
    },
    fallbacks=[CommandHandler('cancel', edit_produk_cancel)],
    map_to_parent={
        EDIT_PRODUK_MENU: EDIT_PRODUK_MENU
    }
)

# Command handlers
admin_menu_handler = CommandHandler("admin", admin_menu)
updateproduk_handler = CommandHandler("updateproduk", updateproduk)
listproduk_handler = CommandHandler("listproduk", listproduk)
topup_list_handler = CommandHandler("topup_list", topup_list)
cek_user_handler = CommandHandler("cek_user", cek_user)
jadikan_admin_handler = CommandHandler("jadikan_admin", jadikan_admin)

# Callback query handlers
admin_callback_handler = CallbackQueryHandler(admin_menu_handler, pattern=r'^admin_')
topup_callback_handler = CallbackQueryHandler(topup_button_handler, pattern=r'^(approve_topup:|reject_topup:|view_topup:|topup_filter:)')