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
                username TEXT,
                kode_produk TEXT,
                nama_produk TEXT,
                tujuan TEXT,
                harga REAL,
                saldo_awal REAL,
                reff_id TEXT,
                status_api TEXT,
                keterangan TEXT,
                waktu TEXT
            )
        ''')
        c.execute("UPDATE products SET stock = 10 WHERE stock IS NULL OR stock = 0")
        conn.commit()
        conn.close()

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

    def get_user_saldo(self, user_id):
        import database
        return database.get_user_saldo(user_id)

    def decrement_user_saldo(self, user_id, amount):
        import database
        return database.increment_user_saldo(user_id, -amount)

    def save_riwayat(self, username, kode_produk, nama_produk, tujuan, harga, saldo_awal, reff_id, status_api, keterangan):
        waktu = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = sqlite3.connect(self.DB_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO riwayat_pembelian 
            (username, kode_produk, nama_produk, tujuan, harga, saldo_awal, reff_id, status_api, keterangan, waktu)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            username, kode_produk, nama_produk, tujuan, harga, saldo_awal, reff_id, status_api, keterangan, waktu
        ))
        conn.commit()
        conn.close()

    async def order_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        import database
        user = update.message.from_user
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = self.get_user_saldo(user_id)
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
        import database
        user = update.message.from_user
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        username = user.username
        # PATCH: Ambil kode produk apapun formatnya
        match = re.match(r'(?:🛒 *)?([A-Za-z0-9]+)', user_input)
        if match:
            kode_produk = match.group(1)
        else:
            kode_produk = user_input.split(" ")[0].replace("🛒", "").strip()
        if user_input == "❌ Batalkan Order":
            await update.message.reply_text("❌ Order dibatalkan.", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        product = self.get_product_by_code(kode_produk)
        if not product:
            await update.message.reply_text("❌ Produk tidak valid atau stok habis.", reply_markup=ReplyKeyboardRemove())
            return ASK_ORDER_PRODUK
        context.user_data["order_produk"] = product
        context.user_data["username"] = username
        await update.message.reply_text(
            f"✅ Produk: {product[1]}\nHarga: Rp {product[2]:,}\nStok: {product[4]}\n\nKetik nomor tujuan (ex: 08123456789):",
            reply_markup=ReplyKeyboardRemove()
        )
        return ASK_ORDER_TUJUAN

    async def order_tujuan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tujuan = ''.join(filter(str.isdigit, update.message.text.strip()))
        if not tujuan or not tujuan.startswith("08") or not (10 <= len(tujuan) <= 14):
            await update.message.reply_text("❌ Nomor tujuan tidak valid.\nCoba lagi.", reply_markup=ReplyKeyboardRemove())
            return ASK_ORDER_TUJUAN
        context.user_data["order_tujuan"] = tujuan
        product = context.user_data["order_produk"]
        confirm_keyboard = [["✅ Konfirmasi & Bayar", "❌ Batalkan Order"]]
        await update.message.reply_text(
            f"📋 KONFIRMASI\nProduk: {product[1]}\nKode: {product[0]}\nHarga: Rp {product[2]:,}\nTujuan: {tujuan}\n\nKonfirmasi?",
            reply_markup=ReplyKeyboardMarkup(confirm_keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return ASK_ORDER_CONFIRM

    async def order_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        import database
        user = update.message.from_user
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        username = user.username
        user_input = update.message.text.strip()
        if user_input == "❌ Batalkan Order":
            await update.message.reply_text("❌ Order dibatalkan.", reply_markup=ReplyKeyboardRemove())
            context.user_data.clear()
            return ConversationHandler.END
        if user_input != "✅ Konfirmasi & Bayar":
            await update.message.reply_text("❌ Konfirmasi tidak valid. Order dibatalkan.", reply_markup=ReplyKeyboardRemove())
            context.user_data.clear()
            return ConversationHandler.END

        product = context.user_data["order_produk"]
        tujuan = context.user_data["order_tujuan"]
        kode_produk = product[0]
        nama_produk = product[1]
        harga_produk = int(product[2])
        saldo_awal = self.get_user_saldo(user_id)

        if saldo_awal < harga_produk:
            await update.message.reply_text(
                f"❌ Saldo tidak cukup.\nSaldo Anda: Rp {saldo_awal:,}\nHarga: Rp {harga_produk:,}\nSilakan topup saldo.",
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data.clear()
            return ConversationHandler.END

        # Potong saldo dulu sebelum call API
        self.decrement_user_saldo(user_id, harga_produk)

        reff_id = "akrab_" + uuid.uuid4().hex
        api_url = f"{API_URL}/trx?produk={kode_produk}&tujuan={tujuan}&reff_id={reff_id}&api_key={API_KEY}"
        try:
            response = requests.get(api_url, timeout=20)
            status_api = "PROSES"
            keterangan = "Order terkirim, menunggu update provider"
            if response.ok:
                api_json = response.json()
                status_api = api_json.get("status", "PROSES").upper()
                keterangan = api_json.get("msg", keterangan)
        except Exception as e:
            status_api = "ERROR"
            keterangan = "Gagal proses ke provider"

        # Simpan ke riwayat
        self.save_riwayat(username, kode_produk, nama_produk, tujuan, harga_produk, saldo_awal, reff_id, status_api, keterangan)

        # Feedback ke user
        if status_api in ("SUKSES", "SUCCESS"):
            await update.message.reply_text(
                f"🎉 SUKSES!\nProduk: {nama_produk}\nHarga: Rp {harga_produk:,}\nTujuan: {tujuan}\nID: {reff_id}\n{status_api}: {keterangan}",
                reply_markup=ReplyKeyboardRemove()
            )
        elif status_api in ("GAGAL", "FAILED", "ERROR"):
            await update.message.reply_text(
                f"❌ GAGAL!\nProduk: {nama_produk}\nHarga: Rp {harga_produk:,}\nTujuan: {tujuan}\nID: {reff_id}\n{status_api}: {keterangan}",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await update.message.reply_text(
                f"📦 PROSES!\nProduk: {nama_produk}\nHarga: Rp {harga_produk:,}\nTujuan: {tujuan}\nID: {reff_id}\n{status_api}: {keterangan}\nTunggu update status.",
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
        saldo = self.get_user_saldo(user_id)
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
                MessageHandler(filters.Regex('^❌ Batalkan Order$'), self.order_cancel)
            ]
        )

order_handler = OrderHandler()
