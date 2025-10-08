import logging
import sqlite3
import requests
import uuid
import re
from datetime import datetime
from telegram import (
    Update, 
    ReplyKeyboardMarkup, 
    ReplyKeyboardRemove
)
from telegram.ext import (
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

logger = logging.getLogger(__name__)

DB_PATH = "bot_database.db"

ASK_ORDER_PRODUK, ASK_ORDER_TUJUAN, ASK_ORDER_CONFIRM = range(3)

API_URL = "https://panel.khfy-store.com/api_v2"
from config import API_KEY_PROVIDER
API_KEY = API_KEY_PROVIDER

class OrderHandler:
    def __init__(self, db_path=DB_PATH):
        self.DB_PATH = db_path
        self._init_database()

    def _init_database(self):
        """Initialize database with required tables and columns (full fitur)"""
        conn = sqlite3.connect(self.DB_PATH)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS products (
                code TEXT PRIMARY KEY,
                name TEXT,
                price REAL,
                status TEXT DEFAULT 'active',
                description TEXT,
                category TEXT,
                provider TEXT,
                gangguan INTEGER DEFAULT 0,
                kosong INTEGER DEFAULT 0,
                stock INTEGER DEFAULT 0,
                updated_at TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS riwayat_pembelian (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                kode_produk TEXT,
                nama_produk TEXT,
                tujuan TEXT,
                harga REAL,
                saldo_awal REAL,
                saldo_akhir REAL,
                reff_id TEXT,
                status_api TEXT,
                keterangan TEXT,
                waktu TEXT
            )
        ''')
        # Patch: make sure required columns always exist
        for col, dtype, dflt in [
            ("provider", "TEXT", None),
            ("gangguan", "INTEGER", "0"),
            ("kosong", "INTEGER", "0"),
            ("stock", "INTEGER", "0"),
        ]:
            try:
                c.execute(f"SELECT {col} FROM products LIMIT 1")
            except sqlite3.OperationalError:
                dflt_str = f" DEFAULT {dflt}" if dflt is not None else ""
                c.execute(f"ALTER TABLE products ADD COLUMN {col} {dtype}{dflt_str}")
        # Ensure stock always at least 1 for all products
        c.execute("UPDATE products SET stock = 10 WHERE stock IS NULL OR stock = 0")
        conn.commit()
        conn.close()
        logger.info("✅ Order Handler database initialized successfully")

    def get_all_products(self):
        """Get all products (active, non-active, kosong, gangguan, stok 0)"""
        conn = sqlite3.connect(self.DB_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT code, name, price, description, category, provider, gangguan, kosong, stock, status
            FROM products
            ORDER BY category, name ASC
        ''')
        products = c.fetchall()
        conn.close()
        return products

    def get_active_products(self):
        """Get all active products from database, fallback if field NULL."""
        conn = sqlite3.connect(self.DB_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT code, name, price, description, stock 
            FROM products 
            WHERE status='active'
              AND COALESCE(gangguan,0)=0
              AND COALESCE(kosong,0)=0
              AND COALESCE(stock,10)>0
            ORDER BY category, name ASC
        ''')
        products = c.fetchall()
        conn.close()
        return products

    def get_product_by_code(self, code):
        """Get product by code, fallback if field NULL."""
        conn = sqlite3.connect(self.DB_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT code, name, price, description, stock 
            FROM products 
            WHERE code = ?
              AND status='active'
              AND COALESCE(gangguan,0)=0
              AND COALESCE(kosong,0)=0
              AND COALESCE(stock,10)>0
        ''', (code,))
        product = c.fetchone()
        conn.close()
        return product

    def save_order(self, user_id, product, tujuan, saldo_awal, status="SUCCESS", api_status="", api_keterangan="", reff_id=None):
        """Save order to database"""
        waktu = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        saldo_akhir = saldo_awal - product[2]
        reff_id = reff_id if reff_id else f"ORDER_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        conn = sqlite3.connect(self.DB_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO riwayat_pembelian 
            (user_id, kode_produk, nama_produk, tujuan, harga, saldo_awal, saldo_akhir, reff_id, status_api, keterangan, waktu)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, product[0], product[1], tujuan, product[2], 
            saldo_awal, saldo_akhir, reff_id, api_status, api_keterangan, waktu
        ))
        # Update product stock
        c.execute("UPDATE products SET stock = stock - 1 WHERE code = ?", (product[0],))
        conn.commit()
        conn.close()
        return reff_id, saldo_akhir

    # --- Conversation Handlers ---
    async def order_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        import database
        user = update.message.from_user
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
        products = self.get_active_products()
        context.user_data["produk_list"] = products
        if not products:
            await update.message.reply_text(
                "❌ **Produk Belum Tersedia**\n\n"
                "Maaf, saat ini tidak ada produk yang tersedia.\n"
                "Silakan coba lagi nanti atau hubungi admin.",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        produk_keyboard = []
        product_details = []
        for code, name, price, description, stock in products:
            emoji = "🟢" if stock > 5 else "🟡" if stock > 0 else "🔴"
            product_details.append(f"{emoji} **{name}**\n   💰 Rp {price:,} | 📦 Stok: {stock} | 🆔 `{code}`")
            produk_keyboard.append([f"🛒 {code} - {name}"])
        produk_keyboard.append(["❌ Batalkan Order"])
        message = (
            f"👋 **Halo {user.full_name}!**\n\n"
            f"💰 **Saldo Anda:** Rp {saldo:,}\n\n"
            "🎮 **DAFTAR PRODUK TERSEDIA:**\n\n" +
            "\n".join(product_details) +
            "\n\nSilakan pilih produk dari keyboard di bawah:"
        )
        await update.message.reply_text(
            message,
            reply_markup=ReplyKeyboardMarkup(
                produk_keyboard,
                one_time_keyboard=True,
                resize_keyboard=True,
                input_field_placeholder="Pilih produk yang diinginkan..."
            ),
            parse_mode='Markdown'
        )
        return ASK_ORDER_PRODUK

    async def order_produk(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_input = update.message.text.strip()
        logger.info(f"User memilih produk: {repr(user_input)}")
        # PATCH: Ambil kode produk apapun formatnya (emoji, tanpa emoji, strip, dsb)
        match = re.match(r'(?:🛒 *)?([A-Za-z0-9]+)', user_input)
        if user_input == "❌ Batalkan Order":
            await update.message.reply_text(
                "❌ **Order Dibatalkan**\n\nGunakan /order untuk memulai pemesanan kembali.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        if match:
            kode_produk = match.group(1)
        else:
            # Fallback ambil kode produk dari awal string
            kode_produk = user_input.split(" ")[0].replace("🛒", "").strip()
        logger.info(f"Kode produk yang diambil: {kode_produk}")
        product = self.get_product_by_code(kode_produk)
        if not product:
            products = context.user_data.get("produk_list", [])
            produk_keyboard = []
            for code, name, price, description, stock in products:
                produk_keyboard.append([f"🛒 {code} - {name}"])
            produk_keyboard.append(["❌ Batalkan Order"])
            await update.message.reply_text(
                "❌ **Kode produk tidak valid atau stok habis**\n\nSilakan pilih produk yang tersedia dari keyboard.",
                reply_markup=ReplyKeyboardMarkup(
                    produk_keyboard,
                    one_time_keyboard=True,
                    resize_keyboard=True
                )
            )
            return ASK_ORDER_PRODUK
        context.user_data["order_produk"] = product
        await update.message.reply_text(
            f"✅ **PRODUK DIPILIH**\n\n"
            f"📦 **Nama:** {product[1]}\n"
            f"💵 **Harga:** Rp {product[2]:,}\n"
            f"📝 **Deskripsi:** {product[3]}\n"
            f"📊 **Stok Tersisa:** {product[4]}\n\n"
            "📱 **Silakan masukkan nomor tujuan:**\n"
            "Contoh: `081234567890`\n\n"
            "⚠️ **Pastikan nomor tujuan sudah benar!**",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        return ASK_ORDER_TUJUAN

    async def order_tujuan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tujuan = update.message.text.strip()
        if not self._validate_phone_number(tujuan):
            await update.message.reply_text(
                "❌ **Format Nomor Tidak Valid**\n\nFormat yang benar: `08xxxxxxxxxx`\nPanjang: 10-14 digit\nHanya angka yang diperbolehkan\n\nSilakan masukkan ulang nomor tujuan:",
                parse_mode='Markdown'
            )
            return ASK_ORDER_TUJUAN
        context.user_data["order_tujuan"] = tujuan
        product = context.user_data["order_produk"]
        confirm_keyboard = [
            ["✅ Konfirmasi & Bayar", "❌ Batalkan Order"]
        ]
        await update.message.reply_text(
            f"📋 **KONFIRMASI ORDER**\n\n"
            f"📦 **Produk:** {product[1]}\n"
            f"🆔 **Kode:** {product[0]}\n"
            f"💵 **Harga:** Rp {product[2]:,}\n"
            f"📱 **Tujuan:** `{tujuan}`\n\n"
            "**Apakah data sudah benar?**\nTekan 'Konfirmasi & Bayar' untuk melanjutkan.",
            reply_markup=ReplyKeyboardMarkup(
                confirm_keyboard,
                one_time_keyboard=True,
                resize_keyboard=True,
                input_field_placeholder="Pilih konfirmasi..."
            ),
            parse_mode='Markdown'
        )
        return ASK_ORDER_CONFIRM

    async def order_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        import database
        user = update.message.from_user
        user_input = update.message.text.strip()
        if user_input == "❌ Batalkan Order":
            await update.message.reply_text(
                "❌ **Order Dibatalkan**\n\nTidak ada yang ditagih. Gunakan /order untuk memulai lagi.",
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data.clear()
            return ConversationHandler.END
        if user_input != "✅ Konfirmasi & Bayar":
            await update.message.reply_text(
                "❌ **Order Dibatalkan**\n\nKonfirmasi tidak valid. Gunakan /order untuk memulai lagi.",
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data.clear()
            return ConversationHandler.END
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        product = context.user_data["order_produk"]
        tujuan = context.user_data["order_tujuan"]
        saldo_awal = database.get_user_saldo(user_id)
        if saldo_awal < product[2]:
            saldo_kurang = product[2] - saldo_awal
            await update.message.reply_text(
                f"❌ **Saldo Tidak Cukup**\n\n💰 **Saldo Anda:** Rp {saldo_awal:,}\n💵 **Dibutuhkan:** Rp {product[2]:,}\n📊 **Kekurangan:** Rp {saldo_kurang:,}\n\nSilakan topup saldo terlebih dahulu menggunakan /topup",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode='Markdown'
            )
            context.user_data.clear()
            return ConversationHandler.END
        current_product = self.get_product_by_code(product[0])
        if not current_product:
            await update.message.reply_text(
                f"❌ **Stok Habis**\n\nMaaf, produk {product[1]} sudah habis.\nSilakan pilih produk lain menggunakan /order",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode='Markdown'
            )
            context.user_data.clear()
            return ConversationHandler.END
        reff_id = str(uuid.uuid4())
        api_endpoint = f"{API_URL}/trx"
        params = {
            "produk": product[0],
            "tujuan": tujuan,
            "reff_id": reff_id,
            "api_key": API_KEY
        }
        try:
            response = requests.get(api_endpoint, params=params, timeout=20)
            api_json = response.json()
            api_status = str(api_json.get("status", "unknown"))
            api_keterangan = api_json.get("keterangan", "")
            database.increment_user_saldo(user_id, -product[2])
            reff_id_db, saldo_akhir = self.save_order(
                user_id, product, tujuan, saldo_awal,
                status=api_status,
                api_status=api_status,
                api_keterangan=api_keterangan,
                reff_id=reff_id
            )
            success_message = (
                f"🎉 **ORDER BERHASIL!**\n\n"
                f"📦 **Produk:** {product[1]}\n"
                f"💵 **Harga:** Rp {product[2]:,}\n"
                f"📱 **Tujuan:** {tujuan}\n"
                f"💰 **Saldo Awal:** Rp {saldo_awal:,}\n"
                f"💳 **Saldo Akhir:** Rp {saldo_akhir:,}\n\n"
                f"📋 **ID Transaksi:** `{reff_id}`\n"
                f"🕐 **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                f"Status API: {api_status}\n"
                f"Keterangan: {api_keterangan}\n\n"
                "✅ **Pesanan sedang diproses...**\nAnda akan menerima konfirmasi dalam 1-5 menit.\n\nTerima kasih telah berbelanja! 😊"
            )
            await update.message.reply_text(
                success_message,
                reply_markup=ReplyKeyboardRemove(),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error processing external order: {e}")
            await update.message.reply_text(
                "❌ **Terjadi Kesalahan**\n\nMaaf, terjadi kesalahan saat memproses order di server.\nSilakan coba lagi atau hubungi admin.",
                reply_markup=ReplyKeyboardRemove()
            )
        context.user_data.clear()
        return ConversationHandler.END

    async def order_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "❌ **Proses Order Dibatalkan**\n\nTidak ada yang ditagih.\nGunakan /order untuk memulai pemesanan baru.",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data.clear()
        return ConversationHandler.END

    def get_conversation_handler(self):
        return ConversationHandler(
            entry_points=[
                CommandHandler('order', self.order_start),
                CommandHandler('beli', self.order_start),
                CommandHandler('buy', self.order_start)
            ],
            states={
                ASK_ORDER_PRODUK: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.order_produk)
                ],
                ASK_ORDER_TUJUAN: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.order_tujuan)
                ],
                ASK_ORDER_CONFIRM: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.order_confirm)
                ],
            },
            fallbacks=[
                CommandHandler('cancel', self.order_cancel),
                CommandHandler('batal', self.order_cancel),
                MessageHandler(filters.Regex('^❌ Batalkan Order$'), self.order_cancel)
            ]
        )

order_handler = OrderHandler()
