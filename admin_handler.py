import config
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
import aiohttp
import aiosqlite
import database
import sqlite3
from datetime import datetime

DB_PATH = "bot_topup.db"

def is_admin(user):
    return str(user.id) in config.ADMIN_TELEGRAM_IDS

# Fungsi untuk memastikan tabel products dengan deskripsi dan migrasi
async def ensure_products_table():
    async with aiosqlite.connect(DB_PATH) as conn:
        # Buat tabel jika belum ada
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
        
        # Cek dan tambahkan kolom yang belum ada
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

# Fungsi untuk menentukan kategori berdasarkan nama produk
def determine_category(name, code):
    name_lower = name.lower()
    code_lower = code.lower()
    
    # Deteksi berdasarkan nama produk
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

# Handler untuk update produk dari API ke database
async def updateproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text(
            "❌ **Akses Ditolak**\n\n"
            "Hanya admin yang dapat menggunakan perintah ini.",
            parse_mode='Markdown'
        )
        return

    await update.message.reply_text("🔄 **Memperbarui Produk...**\n\nSedang mengambil data dari provider...")

    api_key = config.API_KEY_PROVIDER
    url = f"https://panel.khfy-store.com/api_v2/list_product?api_key={api_key}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as resp:
                resp.raise_for_status()
                data = await resp.json()
    except Exception as e:
        await update.message.reply_text(
            f"❌ **Gagal Mengambil Data**\n\n"
            f"Error: `{e}`\n\n"
            "Pastikan koneksi internet stabil dan API key valid.",
            parse_mode='Markdown'
        )
        return

    # Periksa struktur response
    if not data.get("ok", False):
        await update.message.reply_text(
            f"❌ **Response Error dari Provider**\n\n"
            f"Pesan: {data.get('message', 'Unknown error')}",
            parse_mode='Markdown'
        )
        return

    produk_list = data.get("data", [])
    
    if not produk_list:
        await update.message.reply_text(
            "⚠️ **Tidak Ada Data dari Provider**\n\n"
            "Provider tidak mengembalikan data produk.",
            parse_mode='Markdown'
        )
        return

    await ensure_products_table()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        # Reset status produk lama menjadi inactive
        await conn.execute("UPDATE products SET status = 'inactive'")
        
        count = 0
        skipped = 0
        skipped_gangguan = 0
        valid_products = []
        
        for prod in produk_list:
            # Extract data dari provider sesuai format JSON
            code = str(prod.get("kode_produk", "")).strip()
            name = str(prod.get("nama_produk", "")).strip()
            price = float(prod.get("harga_final", 0))
            gangguan = int(prod.get("gangguan", 0))
            kosong = int(prod.get("kosong", 0))
            provider_code = str(prod.get("kode_provider", "")).strip()
            
            # Ambil deskripsi dari provider
            description = str(prod.get("deskripsi", "")).strip()
            if description == "a":  # Handle deskripsi default "a"
                description = f"Produk {name}"
            
            # Tentukan kategori
            category = determine_category(name, code)
            
            # Validasi data produk - skip jika gangguan atau kosong
            if not code or not name or price <= 0:
                skipped += 1
                continue
                
            # Skip produk yang sedang gangguan atau kosong
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
            valid_products.append((code, name, price, description, category, provider_code))
        
        await conn.commit()

    # Hitung kategori produk
    categories = {}
    for code, name, price, description, category, provider_code in valid_products:
        categories[category] = categories.get(category, 0) + 1
    
    # Ambil sample produk untuk preview
    sample_products = valid_products[:8]
    
    category_summary = "\n".join([f"• **{cat}**: {count} produk" for cat, count in list(categories.items())[:6]])
    
    msg = (
        f"✅ **Update Produk Berhasil**\n\n"
        f"📊 **Statistik Update:**\n"
        f"├ Total dari Provider: {len(produk_list)} produk\n"
        f"├ Berhasil diupdate: {count} produk\n"
        f"├ Dilewati (data invalid): {skipped} produk\n"
        f"└ Dilewati (gangguan/kosong): {skipped_gangguan} produk\n\n"
    )
    
    if categories:
        msg += f"📦 **Kategori Produk:**\n{category_summary}\n\n"
    
    msg += "🆕 **Contoh Produk Terbaru:**\n"
    for code, name, price, description, category, provider_code in sample_products:
        msg += f"• **{name}**\n  💰 Rp {price:,.0f} | 📁 {category}\n"
    
    if len(valid_products) > 8:
        msg += f"\n📈 ... dan {len(valid_products) - 8} produk lainnya\n"
    
    msg += f"\n⏰ **Update Terakhir:** {datetime.now().strftime('%d-%m-%Y %H:%M')}"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

updateproduk_handler = CommandHandler("updateproduk", updateproduk)

# Handler untuk list produk dari database dengan pagination
async def listproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text(
            "❌ **Akses Ditolak**\n\n"
            "Hanya admin yang dapat menggunakan perintah ini.",
            parse_mode='Markdown'
        )
        return

    await ensure_products_table()
    
    # Handle pagination
    page = int(context.args[0]) if context.args and context.args[0].isdigit() else 1
    limit = 20
    offset = (page - 1) * limit

    async with aiosqlite.connect(DB_PATH) as conn:
        # Hitung total produk
        async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
            total_count = (await cursor.fetchone())[0]
        
        # Ambil produk dengan pagination
        async with conn.execute("""
            SELECT code, name, price, description, category, provider, gangguan, kosong 
            FROM products 
            WHERE status='active' 
            ORDER BY category, name ASC 
            LIMIT ? OFFSET ?
        """, (limit, offset)) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await update.message.reply_text(
            "📭 **Database Produk Kosong**\n\n"
            "Belum ada produk yang tersedia. Gunakan `/updateproduk` untuk mengimpor produk.",
            parse_mode='Markdown'
        )
        return

    total_pages = (total_count + limit - 1) // limit
    
    msg = f"📋 **DAFTAR PRODUK AKTIF**\n\n"
    msg += f"📊 **Halaman {page} dari {total_pages}**\n"
    msg += f"📈 **Total Produk:** {total_count} produk\n\n"

    # Kelompokkan produk berdasarkan kategori
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

    # Tambahkan navigasi halaman
    if total_pages > 1:
        nav_buttons = []
        if page > 1:
            nav_buttons.append(f"« Halaman {page-1}")
        if page < total_pages:
            nav_buttons.append(f"Halaman {page+1} »")
        
        nav_text = " | ".join(nav_buttons)
        msg += f"\n**Navigasi:** `/listproduk <nomor_halaman>`\n"
        msg += f"**Halaman saat ini:** {page}\n"
        if nav_buttons:
            msg += f"**Halaman lain:** {nav_text}\n"

    await update.message.reply_text(msg, parse_mode='Markdown')

listproduk_handler = CommandHandler("listproduk", listproduk)

# Handler untuk melihat detail produk spesifik
async def detailproduk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text(
            "❌ **Akses Ditolak**\n\n"
            "Hanya admin yang dapat menggunakan perintah ini.",
            parse_mode='Markdown'
        )
        return

    if not context.args:
        await update.message.reply_text(
            "❌ **Format Salah**\n\n"
            "**Penggunaan:**\n"
            "`/detailproduk <kode_produk>`\n\n"
            "**Contoh:**\n"
            "`/detailproduk BPAL1`",
            parse_mode='Markdown'
        )
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
        await update.message.reply_text(
            f"❌ **Produk Tidak Ditemukan**\n\n"
            f"Kode/Nama: `{kode_produk}`\n"
            f"Produk tidak ditemukan dalam database.",
            parse_mode='Markdown'
        )
        return

    if len(products) > 1:
        # Jika ada multiple results, tampilkan list singkat
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
        # Tampilkan detail lengkap untuk satu produk
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

detailproduk_handler = CommandHandler("detailproduk", detailproduk)

# Handler untuk konfirmasi topup
async def topup_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text(
            "❌ **Akses Ditolak**\n\n"
            "Hanya admin yang dapat menggunakan perintah ini.",
            parse_mode='Markdown'
        )
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ **Format Salah**\n\n"
            "**Penggunaan:**\n"
            "`/topup_confirm <topup_id>`\n\n"
            "**Contoh:**\n"
            "`/topup_confirm topup_123456`",
            parse_mode='Markdown'
        )
        return
    
    topup_id = args[0]
    
    try:
        database.update_topup_status(topup_id, "paid")
        await update.message.reply_text(
            f"✅ **Topup Dikonfirmasi**\n\n"
            f"**ID Topup:** `{topup_id}`\n"
            f"**Status:** Berhasil dikonfirmasi sebagai PAID",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ **Gagal Konfirmasi**\n\n"
            f"**ID Topup:** `{topup_id}`\n"
            f"**Error:** `{e}`",
            parse_mode='Markdown'
        )

topup_confirm_handler = CommandHandler("topup_confirm", topup_confirm)

# Handler cek user
async def cek_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text(
            "❌ **Akses Ditolak**\n\n"
            "Hanya admin yang dapat menggunakan perintah ini.",
            parse_mode='Markdown'
        )
        return
    
    args = context.args
    username = args[0] if args else None
    
    if not username:
        await update.message.reply_text(
            "❌ **Format Salah**\n\n"
            "**Penggunaan:**\n"
            "`/cek_user <username>`\n\n"
            "**Contoh:**\n"
            "`/cek_user johndoe`",
            parse_mode='Markdown'
        )
        return
    
    conn = sqlite3.connect(database.DB_PATH)
    c = conn.cursor()
    c.execute("SELECT saldo, telegram_id FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        await update.message.reply_text(
            f"❌ **User Tidak Ditemukan**\n\n"
            f"Username: `{username}`\n"
            f"User tidak terdaftar dalam database.",
            parse_mode='Markdown'
        )
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

cek_user_handler = CommandHandler("cek_user", cek_user)

# Handler jadikan admin
async def jadikan_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text(
            "❌ **Akses Ditolak**\n\n"
            "Hanya admin yang dapat menggunakan perintah ini.",
            parse_mode='Markdown'
        )
        return
    
    args = context.args
    telegram_id = args[0] if args else None
    
    if not telegram_id:
        await update.message.reply_text(
            "❌ **Format Salah**\n\n"
            "**Penggunaan:**\n"
            "`/jadikan_admin <telegram_id>`\n\n"
            "**Contoh:**\n"
            "`/jadikan_admin 123456789`",
            parse_mode='Markdown'
        )
        return
    
    try:
        database.add_user_admin(telegram_id)
        await update.message.reply_text(
            f"✅ **Admin Berhasil Ditambahkan**\n\n"
            f"**Telegram ID:** `{telegram_id}`\n"
            f"**Status:** Sekarang memiliki akses admin",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ **Gagal Menambahkan Admin**\n\n"
            f"**Telegram ID:** `{telegram_id}`\n"
            f"**Error:** `{e}`",
            parse_mode='Markdown'
        )

jadikan_admin_handler = CommandHandler("jadikan_admin", jadikan_admin)

# Handler menu admin utama yang diperbarui
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user):
        await update.message.reply_text(
            "❌ **Akses Ditolak**\n\n"
            "Menu admin hanya untuk pengguna dengan hak akses admin.",
            parse_mode='Markdown'
        )
        return
    
    # Pastikan tabel sudah ada dan terupdate
    await ensure_products_table()
    
    # Hitung statistik dengan error handling
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as cursor:
                active_products = (await cursor.fetchone())[0]
            
            async with conn.execute("SELECT COUNT(DISTINCT category) FROM products WHERE status='active'") as cursor:
                total_categories = (await cursor.fetchone())[0]
            
            async with conn.execute("SELECT COUNT(*) FROM products WHERE status='active' AND gangguan = 0 AND kosong = 0") as cursor:
                available_products = (await cursor.fetchone())[0]
    except Exception as e:
        # Jika ada error, set default values
        active_products = 0
        total_categories = 0
        available_products = 0
        print(f"Error counting stats: {e}")
    
    await update.message.reply_text(
        f"👑 **MENU ADMIN**\n\n"
        f"📊 **Statistik Sistem:**\n"
        f"├ 📦 Total Produk: {active_products}\n"
        f"├ ✅ Produk Tersedia: {available_products}\n"
        f"└ 📁 Kategori: {total_categories}\n\n"
        "📦 **Manajemen Produk:**\n"
        "`/updateproduk` - Update semua produk dari API provider\n"
        "`/listproduk <halaman>` - List produk dengan pagination\n"
        "`/detailproduk <kode>` - Detail lengkap produk\n\n"
        "💳 **Manajemen Transaksi:**\n"
        "`/topup_confirm <topup_id>` - Konfirmasi topup user\n\n"
        "👥 **Manajemen User:**\n"
        "`/cek_user <username>` - Cek info user\n"
        "`/jadikan_admin <telegram_id>` - Jadikan user sebagai admin\n\n"
        "📢 **Broadcast:**\n"
        "`/broadcast pesan` - Broadcast ke semua user\n\n"
        f"⏰ **Waktu Server:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
        parse_mode='Markdown'
    )

admin_menu_handler = CommandHandler("admin", admin_menu)
