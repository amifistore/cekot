import config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes, CallbackQueryHandler
import aiohttp
import aiosqlite
import database
import sqlite3
from datetime import datetime

DB_PATH = "bot_topup.db"

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

def determine_category(name, code):
    name_lower = name.lower()
    code_lower = code.lower()
    
    if any(keyword in name_lower for keyword in ['pulsa', 'telkomsel', 'tsel', 'simpati', 'as']):
        return "Pulsa"
    elif any(keyword in name_lower for keyword in ['data', 'kuota', 'internet', 'gb', 'mb', 'mini', 'jumbo', 'mega', 'super']):
        return "Internet"
    elif any(keyword in name_lower for keyword in ['listrik', 'pln', 'token']):
        return "Listrik"
    elif any(keyword in name_lower for keyword in ['game', 'voucher game', 'pubg', 'mobile legend', 'ml', 'ff', 'free fire']):
        return "Game"
    elif any(keyword in name_lower for keyword in ['emoney', 'gopay', 'dana', 'ovo', 'linkaja', 'shopeepay']):
        return "E-Money"
    elif any(keyword in name_lower for keyword in ['tv', 'kabel', 'streaming']):
        return "TV Kabel"
    elif any(keyword in name_lower for keyword in ['akrab', 'bonus']):
        return "Paket Bonus"
    else:
        return "Umum"

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
            
            category = determine_category(name, code)
            
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

async def listproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return

    await ensure_products_table()
    
    page = int(context.args[0]) if context.args and context.args[0].isdigit() else 1
    limit = 20
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
            msg += f"│ └ Provider: {provider}\n"
            if description and len(description) > 0 and description != f"Produk {name}":
                short_desc = description[:50] + "..." if len(description) > 50 else description
                msg += f"│ └ Deskripsi: {short_desc}\n"
            msg += "│\n"
        msg += "\n"

    if total_pages > 1:
        msg += f"\n**Navigasi:** `/listproduk <nomor_halaman>`"

    await update.message.reply_text(msg, parse_mode='Markdown')

async def detailproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return

    if not context.args:
        await update.message.reply_text("❌ Format: `/detailproduk <kode_produk>`")
        return

    kode_produk = context.args[0].upper()

    await ensure_products_table()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("""
            SELECT code, name, price, description, category, provider, gangguan, kosong, status, updated_at 
            FROM products 
            WHERE code = ? OR name LIKE ?
        """, (kode_produk, f"%{kode_produk}%")) as cursor:
            products = await cursor.fetchall()

    if not products:
        await update.message.reply_text(f"❌ Produk tidak ditemukan: `{kode_produk}`")
        return

    if len(products) > 1:
        msg = f"🔍 **Multiple Results untuk '{kode_produk}'**\n\n"
        for code, name, price, description, category, provider, gangguan, kosong, status, updated_at in products[:10]:
            status_emoji = "✅" if status == 'active' and gangguan == 0 and kosong == 0 else "⚠️"
            msg += f"{status_emoji} **{name}**\n"
            msg += f"   Kode: `{code}` | Harga: Rp {price:,.0f}\n"
            msg += f"   Kategori: {category} | Provider: {provider}\n\n"
        
        if len(products) > 10:
            msg += f"📝 ... dan {len(products) - 10} produk lainnya\n\n"
        
        msg += "**Gunakan kode yang tepat:** `/detailproduk <kode>`"
        
    else:
        code, name, price, description, category, provider, gangguan, kosong, status, updated_at = products[0]
        status_emoji = "✅" if status == 'active' and gangguan == 0 and kosong == 0 else "⚠️"
        
        gangguan_status = "✅ Normal" if gangguan == 0 else "❌ Gangguan"
        kosong_status = "✅ Tersedia" if kosong == 0 else "❌ Kosong"
        
        msg = (
            f"📄 **DETAIL PRODUK**\n\n"
            f"🎯 **Nama:** {name}\n"
            f"📌 **Kode:** `{code}`\n"
            f"💰 **Harga:** Rp {price:,.0f}\n"
            f"📁 **Kategori:** {category}\n"
            f"🏢 **Provider:** {provider}\n"
            f"🔄 **Status:** {status_emoji} {status}\n"
            f"⚡ **Gangguan:** {gangguan_status}\n"
            f"📦 **Stok:** {kosong_status}\n\n"
        )
        
        if description and description != f"Produk {name}":
            msg += f"📝 **Deskripsi:**\n{description}\n\n"
        
        msg += f"⏰ **Update Terakhir:** {updated_at}"

    await update.message.reply_text(msg, parse_mode='Markdown')

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
                 f"⏰ **Waktu:** {updated_at}",
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
                 f"⏰ **Waktu:** {updated_at}",
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

async def topup_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Format: `/topup_confirm <request_id>`")
        return
    
    request_id = args[0]
    await approve_topup_manual(request_id, update.message, context)

async def approve_topup_manual(request_id: str, message, context: ContextTypes.DEFAULT_TYPE):
    await ensure_topup_requests_table()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("""
            SELECT user_id, username, full_name, amount 
            FROM topup_requests 
            WHERE id = ? AND status = 'pending'
        """, (request_id,))
        request_data = await cursor.fetchone()

        if not request_data:
            await message.reply_text("❌ Permintaan topup tidak ditemukan.")
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
                 f"⏰ **Waktu:** {updated_at}",
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Gagal mengirim notifikasi: {e}")

    await message.reply_text(
        f"✅ **Topup Disetujui**\n\n"
        f"**ID Request:** `{request_id}`\n"
        f"**User:** {full_name or username or user_id}\n"
        f"**Jumlah:** Rp {amount:,.0f}\n"
        f"**Saldo Baru:** Rp {new_balance:,.0f}\n"
        f"**Waktu:** {updated_at}",
        parse_mode='Markdown'
    )

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
            
            async with conn.execute("SELECT COUNT(DISTINCT category) FROM products WHERE status='active'") as cursor:
                total_categories = (await cursor.fetchone())[0]
            
            async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active' AND gangguan = 0 AND kosong = 0") as cursor:
                available_products = (await cursor.fetchone())[0]
            
            async with conn.execute("SELECT COUNT(*) FROM topup_requests WHERE status='pending'") as cursor:
                pending_topups = (await cursor.fetchone())[0]
    except Exception as e:
        active_products = total_categories = available_products = pending_topups = 0

    keyboard = [
        [InlineKeyboardButton("📦 Kelola Produk", callback_data="admin_products")],
        [InlineKeyboardButton("💳 Kelola Topup", callback_data="admin_topup")],
        [InlineKeyboardButton("👥 Kelola User", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Statistik Sistem", callback_data="admin_stats")],
        [InlineKeyboardButton("🔄 Update Produk", callback_data="admin_update")],
        [InlineKeyboardButton("📋 List Produk", callback_data="admin_list")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👑 **MENU ADMIN**\n\n"
        f"📊 **Statistik Cepat:**\n"
        f"├ 📦 Produk Aktif: {active_products}\n"
        f"├ ✅ Produk Tersedia: {available_products}\n"
        f"├ 📁 Kategori: {total_categories}\n"
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
    elif data == "admin_update":
        await update_produk_from_menu(query, context)
    elif data == "admin_list":
        await list_produk_from_menu(query, context)
    elif data == "admin_back":
        await admin_menu_back(query, context)

async def show_products_menu(query):
    keyboard = [
        [InlineKeyboardButton("🔄 Update Semua Produk", callback_data="admin_update")],
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
        [InlineKeyboardButton("✅ Lihat Topup Approved", callback_data="topup_filter:approved")],
        [InlineKeyboardButton("❌ Lihat Topup Rejected", callback_data="topup_filter:rejected")],
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
            async with conn.execute("SELECT COUNT(DISTINCT category) FROM products WHERE status='active'") as cursor:
                total_categories = (await cursor.fetchone())[0]
            
            async with conn.execute("SELECT COUNT(*) FROM topup_requests WHERE status='pending'") as cursor:
                pending_topups = (await cursor.fetchone())[0]
            async with conn.execute("SELECT COUNT(*) FROM topup_requests WHERE status='approved'") as cursor:
                approved_topups = (await cursor.fetchone())[0]
            async with conn.execute("SELECT COUNT(*) FROM topup_requests") as cursor:
                total_topups = (await cursor.fetchone())[0]
            
    except Exception as e:
        total_products = available_products = total_categories = 0
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
        f"├ Tersedia: {available_products}\n"
        f"└ Kategori: {total_categories}\n\n"
        f"💳 **TOPUP:**\n"
        f"├ Total: {total_topups}\n"
        f"├ Pending: {pending_topups}\n"
        f"└ Approved: {approved_topups}\n\n"
        f"⏰ **Update:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def update_produk_from_menu(query, context):
    await query.edit_message_text("🔄 Memperbarui produk...")
    
    try:
        api_key = config.API_KEY_PROVIDER
        url = f"https://panel.khfy-store.com/api_v2/list_product?api_key={api_key}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as resp:
                resp.raise_for_status()
                data = await resp.json()

        if not data.get("ok", False):
            await query.edit_message_text("❌ Gagal mengambil data dari provider.")
            return

        produk_list = data.get("data", [])
        
        if not produk_list:
            await query.edit_message_text("⚠️ Tidak ada data dari provider.")
            return

        await ensure_products_table()
        
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute("UPDATE products SET status = 'inactive'")
            
            count = 0
            for prod in produk_list:
                code = str(prod.get("kode_produk", "")).strip()
                name = str(prod.get("nama_produk", "")).strip()
                price = float(prod.get("harga_final", 0))
                gangguan = int(prod.get("gangguan", 0))
                kosong = int(prod.get("kosong", 0))
                
                if not code or not name or price <= 0 or gangguan == 1 or kosong == 1:
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
                """, (code, name, price, "Produk " + name, "Umum", "Provider", gangguan, kosong, now))
                count += 1
            
            await conn.commit()

        keyboard = [
            [InlineKeyboardButton("📋 Lihat Produk", callback_data="admin_list")],
            [InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"✅ **Update Berhasil!**\n\n"
            f"📊 **Statistik:**\n"
            f"├ Dari Provider: {len(produk_list)} produk\n"
            f"└ Berhasil diupdate: {count} produk\n\n"
            f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    except Exception as e:
        await query.edit_message_text(f"❌ Error: {str(e)}")

async def list_produk_from_menu(query, context):
    await ensure_products_table()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
            total_count = (await cursor.fetchone())[0]
        
        async with conn.execute("""
            SELECT code, name, price, category 
            FROM products 
            WHERE status='active' 
            ORDER BY category, name ASC 
            LIMIT 10
        """) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await query.edit_message_text("📭 Tidak ada produk yang tersedia.")
        return

    msg = f"📋 **PRODUK AKTIF**\n\n"
    msg += f"📈 **Total:** {total_count} produk\n\n"

    categories = {}
    for code, name, price, category in rows:
        if category not in categories:
            categories[category] = []
        categories[category].append((code, name, price))

    for category, products in categories.items():
        msg += f"**{category.upper()}**\n"
        for code, name, price in products:
            msg += f"• {name} - Rp {price:,.0f}\n"
        msg += "\n"

    keyboard = [
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_menu_back(query, context):
    await admin_menu_from_query(query, context)

async def admin_menu_from_query(query, context):
    user = query.from_user
    
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
                active_products = (await cursor.fetchone())[0]
            
            async with conn.execute("SELECT COUNT(DISTINCT category) FROM products WHERE status='active'") as cursor:
                total_categories = (await cursor.fetchone())[0]
            
            async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active' AND gangguan = 0 AND kosong = 0") as cursor:
                available_products = (await cursor.fetchone())[0]
            
            async with conn.execute("SELECT COUNT(*) FROM topup_requests WHERE status='pending'") as cursor:
                pending_topups = (await cursor.fetchone())[0]
    except Exception as e:
        active_products = total_categories = available_products = pending_topups = 0

    keyboard = [
        [InlineKeyboardButton("📦 Kelola Produk", callback_data="admin_products")],
        [InlineKeyboardButton("💳 Kelola Topup", callback_data="admin_topup")],
        [InlineKeyboardButton("👥 Kelola User", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Statistik Sistem", callback_data="admin_stats")],
        [InlineKeyboardButton("🔄 Update Produk", callback_data="admin_update")],
        [InlineKeyboardButton("📋 List Produk", callback_data="admin_list")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"👑 **MENU ADMIN**\n\n"
        f"📊 **Statistik Cepat:**\n"
        f"├ 📦 Produk Aktif: {active_products}\n"
        f"├ ✅ Produk Tersedia: {available_products}\n"
        f"├ 📁 Kategori: {total_categories}\n"
        f"└ ⏳ Topup Pending: {pending_topups}\n\n"
        f"Pilih menu di bawah:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

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

updateproduk_handler = CommandHandler("updateproduk", updateproduk)
listproduk_handler = CommandHandler("listproduk", listproduk)
detailproduk_handler = CommandHandler("detailproduk", detailproduk)
topup_list_handler = CommandHandler("topup_list", topup_list)
topup_confirm_handler = CommandHandler("topup_confirm", topup_confirm)
cek_user_handler = CommandHandler("cek_user", cek_user)
jadikan_admin_handler = CommandHandler("jadikan_admin", jadikan_admin)
admin_menu_handler_cmd = CommandHandler("admin", admin_menu)

admin_menu_callback_handler = CallbackQueryHandler(admin_menu_handler, pattern=r'^admin_')
topup_button_callback_handler = CallbackQueryHandler(topup_button_handler, pattern=r'^(approve_topup:|reject_topup:|view_topup:|topup_filter:)')