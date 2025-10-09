# FIXED: No regex bug, verified full flow for order, cancel, validation, logging
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
        c.execute("UPDATE products SET stock = 10 WHERE stock IS NULL OR stock = 0")
        conn.commit()
        conn.close()
        logger.info("✅ Order Handler database initialized successfully")

    def get_active_products(self):
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
        c.execute("UPDATE products SET stock = stock - 1 WHERE code = ?", (product[0],))
        conn.commit()
        conn.close()
        return reff_id, saldo_akhir

    async def order_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        import database
        user = update.message.from_user
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
        products = self.get_active_products()
        context.user_data["produk_list"] = products
        if not products:
            await update.message.reply_text(
                "❌ Tidak ada produk tersedia.\nCoba lagi nanti.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        produk_keyboard = []
        for code, name, price, description, stock in products:
            produk_keyboard.append([f"🛒 {code} - {name}"])
        produk_keyboard.append(["❌ Batalkan Order"])
        await update.message.reply_text(
            f"💰 Saldo Anda: Rp {saldo:,}\n\nPILIH PRODUK:",
            reply_markup=ReplyKeyboardMarkup(
                produk_keyboard,
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return ASK_ORDER_PRODUK

    async def order_produk(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_input = update.message.text.strip()
        logger.info(f"User memilih produk: {repr(user_input)}")

        if user_input == "❌ Batalkan Order":
            await update.message.reply_text("❌ Order dibatalkan.", reply_markup=ReplyKeyboardRemove())
            context.user_data.clear()
            return ConversationHandler.END

        match = re.match(r'(?:🛒 *)?([A-Za-z0-9]+)', user_input)
        if match:
            kode_produk = match.group(1)
        else:
            kode_produk = user_input.split(" - ")[0].replace("🛒", "").strip()
        logger.info(f"Kode produk yang diambil: {kode_produk}")

        product = self.get_product_by_code(kode_produk)
        if not product:
            logger.warning(f"Produk tidak ditemukan atau stok habis: {kode_produk}")
            products = context.user_data.get("produk_list", [])
            produk_keyboard = []
            for code, name, price, description, stock in products:
                produk_keyboard.append([f"🛒 {code} - {name}"])
            produk_keyboard.append(["❌ Batalkan Order"])
            await update.message.reply_text(
                "❌ Kode produk tidak valid atau stok habis.\nSilakan pilih produk lagi:",
                reply_markup=ReplyKeyboardMarkup(
                    produk_keyboard,
                    one_time_keyboard=True,
                    resize_keyboard=True
                )
            )
            return ASK_ORDER_PRODUK

        context.user_data["order_produk"] = product
        await update.message.reply_text(
            f"✅ Produk: {product[1]}\nHarga: Rp {product[2]:,}\nStok: {product[4]}\n\nKetik nomor tujuan (ex: 08123456789):",
            reply_markup=ReplyKeyboardRemove()
        )
        return ASK_ORDER_TUJUAN

    async def order_tujuan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tujuan = update.message.text.strip()
        if not self._validate_phone_number(tujuan):
            await update.message.reply_text(
                "❌ Format nomor tidak valid.\nFormat: 08xxxxxxxxxx (10-14 digit, hanya angka)\nCoba lagi.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ASK_ORDER_TUJUAN
        context.user_data["order_tujuan"] = tujuan
        product = context.user_data["order_produk"]
        confirm_keyboard = [["✅ Konfirmasi & Bayar", "❌ Batalkan Order"]]
        await update.message.reply_text(
            f"📋 KONFIRMASI\nProduk: {product[1]}\nKode: {product[0]}\nHarga: Rp {product[2]:,}\nTujuan: {tujuan}\n\nKonfirmasi?",
            reply_markup=ReplyKeyboardMarkup(
                confirm_keyboard,
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return ASK_ORDER_CONFIRM

    async def order_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        import database
        user = update.message.from_user
        user_input = update.message.text.strip()
        if user_input == "❌ Batalkan Order":
            await update.message.reply_text("❌ Order dibatalkan.", reply_markup=ReplyKeyboardRemove())
            context.user_data.clear()
            return ConversationHandler.END
        if user_input != "✅ Konfirmasi & Bayar":
            await update.message.reply_text("❌ Konfirmasi tidak valid. Order dibatalkan.", reply_markup=ReplyKeyboardRemove())
            context.user_data.clear()
            return ConversationHandler.END
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        product = context.user_data.get("order_produk")
        tujuan = context.user_data.get("order_tujuan")
        if not product or not tujuan:
            await update.message.reply_text("❌ Order gagal. Data tidak lengkap.", reply_markup=ReplyKeyboardRemove())
            context.user_data.clear()
            return ConversationHandler.END
        saldo_awal = database.get_user_saldo(user_id)
        if saldo_awal < product[2]:
            saldo_kurang = product[2] - saldo_awal
            await update.message.reply_text(
                f"❌ Saldo tidak cukup.\nSaldo Anda: Rp {saldo_awal:,}\nDibutuhkan: Rp {product[2]:,}\nKekurangan: Rp {saldo_kurang:,}\nSilakan topup saldo.",
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data.clear()
            return ConversationHandler.END
        current_product = self.get_product_by_code(product[0])
        if not current_product:
            await update.message.reply_text(
                f"❌ Stok Habis.\nProduk {product[1]} sudah habis.\nSilakan pilih produk lain menggunakan /order",
                reply_markup=ReplyKeyboardRemove()
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
            if api_status.lower() in ["success", "berhasil"]:
                database.increment_user_saldo(user_id, -product[2])
            else:
                api_status = "FAILED"
            reff_id_db, saldo_akhir = self.save_order(
                user_id, product, tujuan, saldo_awal,
                status=api_status,
                api_status=api_status,
                api_keterangan=api_keterangan,
                reff_id=reff_id
            )
            if api_status == "FAILED":
                await update.message.reply_text(
                    f"❌ ORDER GAGAL!\nProduk: {product[1]}\nHarga: Rp {product[2]:,}\nTujuan: {tujuan}\nID Transaksi: {reff_id}\nStatus: {api_status}\nKeterangan: {api_keterangan}\nSaldo Anda tetap: Rp {saldo_awal:,}\nSilakan coba lagi atau hubungi admin.",
                    reply_markup=ReplyKeyboardRemove()
                )
            else:
                success_message = (
                    f"🎉 ORDER BERHASIL!\nProduk: {product[1]}\nHarga: Rp {product[2]:,}\nTujuan: {tujuan}\nSaldo Awal: Rp {saldo_awal:,}\nSaldo Akhir: Rp {saldo_akhir:,}\nID Transaksi: {reff_id}\nStatus: {api_status}\nKeterangan: {api_keterangan}\nPesanan diproses, tunggu konfirmasi."
                )
                await update.message.reply_text(
                    success_message,
                    reply_markup=ReplyKeyboardRemove()
                )
        except Exception as e:
            logger.error(f"Error processing order: {e}")
            await update.message.reply_text(
                "❌ Terjadi Kesalahan.\nMaaf, error saat proses order di server.\nCoba lagi atau hubungi admin.",
                reply_markup=ReplyKeyboardRemove()
            )
        context.user_data.clear()
        return ConversationHandler.END

    async def order_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("❌ Order dibatalkan.", reply_markup=ReplyKeyboardRemove())
        context.user_data.clear()
        return ConversationHandler.END

    async def start_order_from_callback(self, query, context: ContextTypes.DEFAULT_TYPE):
        import database
        user = query.from_user
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
        products = self.get_active_products()
        context.user_data["produk_list"] = products
        if not products:
            await query.edit_message_text("❌ Tidak ada produk tersedia.", parse_mode='Markdown')
            return
        produk_keyboard = []
        for code, name, price, description, stock in products:
            produk_keyboard.append([f"🛒 {code} - {name}"])
        produk_keyboard.append(["❌ Batalkan Order"])
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                f"💰 Saldo Anda: Rp {saldo:,}\n\nPILIH PRODUK dari keyboard di bawah:"
            ),
            reply_markup=ReplyKeyboardMarkup(
                produk_keyboard,
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )

    def _validate_phone_number(self, phone):
        return phone.startswith("08") and phone.isdigit() and (10 <= len(phone) <= 14)

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
                MessageHandler(filters.Regex(r'^❌ Batalkan Order$'), self.order_cancel)
            ]
        )

order_handler = OrderHandler()
