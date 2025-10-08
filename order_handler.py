import logging
import sqlite3
import requests
import uuid
from datetime import datetime
from telegram import (
    Update, 
    ReplyKeyboardMarkup, 
    ReplyKeyboardRemove
)
from telegram.ext import (
    CallbackQueryHandler,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# Setup logging
logger = logging.getLogger(__name__)

# Database path
DB_PATH = "bot_database.db"

# Conversation states
ASK_ORDER_PRODUK, ASK_ORDER_TUJUAN, ASK_ORDER_CONFIRM = range(3)

# KHFSY API config
API_URL = "https://panel.khfy-store.com/api_v2"
from config import API_KEY_PROVIDER
...
API_KEY = API_KEY_PROVIDER
class OrderHandler:
    def __init__(self, db_path="bot_topup.db"):
        self.DB_PATH = db_path
        self._init_database()

    def _init_database(self):
        """Initialize database with required tables"""
        conn = sqlite3.connect(self.DB_PATH)
        c = conn.cursor()
        
        # Products table
        c.execute('''
            CREATE TABLE IF NOT EXISTS products (
                code TEXT PRIMARY KEY,
                name TEXT,
                price REAL,
                status TEXT DEFAULT 'active',
                description TEXT,
                category TEXT,
                stock INTEGER DEFAULT 0,
                updated_at TEXT
            )
        ''')

        # Riwayat Pembelian table
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

        # Check if sample products exist
        c.execute("SELECT COUNT(*) FROM products WHERE status='active'")
        if c.fetchone()[0] == 0:
            self._insert_sample_products(c)
        
        conn.commit()
        conn.close()
        logger.info("✅ Order Handler database initialized successfully")

    def _insert_sample_products(self, cursor):
        """Insert sample products"""
        sample_products = [
            ('XLA14', 'SuperMini', 40000, 'active', 'Produk SuperMini terbaik', 'VPS', 10, datetime.now().isoformat()),
            ('TES', 'Produk TEST', 20000, 'active', 'Produk untuk testing', 'TEST', 5, datetime.now().isoformat()),
            ('XLA39', 'XLA39 Premium', 50000, 'active', 'Produk premium dengan fitur lengkap', 'VPS', 8, datetime.now().isoformat()),
        ]
        cursor.executemany(
            "INSERT INTO products (code, name, price, status, description, category, stock, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            sample_products
        )
        logger.info("✅ Sample products inserted")

    # Database methods
    def get_active_products(self):
        """Get all active products from database"""
        conn = sqlite3.connect(self.DB_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT code, name, price, description, stock 
            FROM products 
            WHERE status='active' AND stock > 0 
            ORDER BY category, name ASC
        ''')
        products = c.fetchall()
        conn.close()
        return products

    def get_product_by_code(self, code):
        """Get product by code"""
        conn = sqlite3.connect(self.DB_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT code, name, price, description, stock 
            FROM products 
            WHERE code = ? AND status='active' AND stock > 0
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

    # Order Conversation Handlers
    async def order_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start order process from command"""
        import database
        user = update.message.from_user
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
        
        # Get products from database
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
        
        # Create product keyboard
        produk_keyboard = []
        product_details = []
        
        for code, name, price, description, stock in products:
            emoji = "🟢" if stock > 5 else "🟡" if stock > 0 else "🔴"
            product_details.append(f"{emoji} **{name}**\n   💰 Rp {price:,} | 📦 Stok: {stock} | 🆔 `{code}`")
            produk_keyboard.append([f"🛒 {code} - {name}"])
        
        produk_keyboard.append(["❌ Batalkan Order"])
        
        # Format message with product details
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
        """Handle product selection"""
        user_input = update.message.text.strip()
        
        # Handle cancellation
        if user_input == "❌ Batalkan Order":
            await update.message.reply_text(
                "❌ **Order Dibatalkan**\n\n"
                "Gunakan /order untuk memulai pemesanan kembali.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Extract product code from input
        if user_input.startswith("🛒 "):
            kode_produk = user_input.split(" - ")[0].replace("🛒 ", "").strip()
        else:
            # Allow direct code input
            kode_produk = user_input
        
        # Get product from database
        product = self.get_product_by_code(kode_produk)
        
        if not product:
            # Show available products again
            products = context.user_data.get("produk_list", [])
            if not products:
                await update.message.reply_text(
                    "❌ **Tidak ada produk tersedia**\n\n"
                    "Silakan mulai ulang dengan /order",
                    reply_markup=ReplyKeyboardRemove()
                )
                return ConversationHandler.END
            
            produk_keyboard = []
            for code, name, price, description, stock in products:
                produk_keyboard.append([f"🛒 {code} - {name}"])
            produk_keyboard.append(["❌ Batalkan Order"])
            
            await update.message.reply_text(
                "❌ **Kode produk tidak valid atau stok habis**\n\n"
                "Silakan pilih produk yang tersedia dari keyboard:",
                reply_markup=ReplyKeyboardMarkup(
                    produk_keyboard,
                    one_time_keyboard=True,
                    resize_keyboard=True
                )
            )
            return ASK_ORDER_PRODUK
        
        context.user_data["order_produk"] = product
        
        # Show product details and ask for destination
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
        """Handle destination number input"""
        tujuan = update.message.text.strip()
        
        # Validate phone number format
        if not self._validate_phone_number(tujuan):
            await update.message.reply_text(
                "❌ **Format Nomor Tidak Valid**\n\n"
                "Format yang benar: `08xxxxxxxxxx`\n"
                "Panjang: 10-14 digit\n"
                "Hanya angka yang diperbolehkan\n\n"
                "Silakan masukkan ulang nomor tujuan:",
                parse_mode='Markdown'
            )
            return ASK_ORDER_TUJUAN
        
        context.user_data["order_tujuan"] = tujuan
        product = context.user_data["order_produk"]
        
        # Create confirmation keyboard
        confirm_keyboard = [
            ["✅ Konfirmasi & Bayar", "❌ Batalkan Order"]
        ]
        
        await update.message.reply_text(
            f"📋 **KONFIRMASI ORDER**\n\n"
            f"📦 **Produk:** {product[1]}\n"
            f"🆔 **Kode:** {product[0]}\n"
            f"💵 **Harga:** Rp {product[2]:,}\n"
            f"📱 **Tujuan:** `{tujuan}`\n\n"
            "**Apakah data sudah benar?**\n"
            "Tekan 'Konfirmasi & Bayar' untuk melanjutkan.",
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
        """Handle order confirmation and processing"""
        import database
        user = update.message.from_user
        user_input = update.message.text.strip()
        
        # Handle cancellation
        if user_input == "❌ Batalkan Order":
            await update.message.reply_text(
                "❌ **Order Dibatalkan**\n\n"
                "Tidak ada yang ditagih. Gunakan /order untuk memulai lagi.",
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data.clear()
            return ConversationHandler.END
        
        # Check confirmation
        if user_input != "✅ Konfirmasi & Bayar":
            await update.message.reply_text(
                "❌ **Order Dibatalkan**\n\n"
                "Konfirmasi tidak valid. Gunakan /order untuk memulai lagi.",
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data.clear()
            return ConversationHandler.END
        
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        product = context.user_data["order_produk"]
        tujuan = context.user_data["order_tujuan"]
        saldo_awal = database.get_user_saldo(user_id)
        
        # Check balance
        if saldo_awal < product[2]:
            saldo_kurang = product[2] - saldo_awal
            await update.message.reply_text(
                f"❌ **Saldo Tidak Cukup**\n\n"
                f"💰 **Saldo Anda:** Rp {saldo_awal:,}\n"
                f"💵 **Dibutuhkan:** Rp {product[2]:,}\n"
                f"📊 **Kekurangan:** Rp {saldo_kurang:,}\n\n"
                "Silakan topup saldo terlebih dahulu menggunakan /topup",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode='Markdown'
            )
            context.user_data.clear()
            return ConversationHandler.END
        
        # Check product stock again (in case changed since selection)
        current_product = self.get_product_by_code(product[0])
        if not current_product:
            await update.message.reply_text(
                f"❌ **Stok Habis**\n\n"
                f"Maaf, produk {product[1]} sudah habis.\n"
                f"Silakan pilih produk lain menggunakan /order",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode='Markdown'
            )
            context.user_data.clear()
            return ConversationHandler.END

        # Create a unique reff_id
        reff_id = str(uuid.uuid4())

        # Call external khfy-store API to create transaction
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
            # Optionally parse more fields from api_json if available

            # Deduct balance
            database.increment_user_saldo(user_id, -product[2])
            # Save order to internal database
            reff_id_db, saldo_akhir = self.save_order(
                user_id, product, tujuan, saldo_awal,
                status=api_status,
                api_status=api_status,
                api_keterangan=api_keterangan,
                reff_id=reff_id
            )

            # Send success message
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
                "✅ **Pesanan sedang diproses...**\n"
                "Anda akan menerima konfirmasi dalam 1-5 menit.\n\n"
                "Terima kasih telah berbelanja! 😊"
            )
            await update.message.reply_text(
                success_message,
                reply_markup=ReplyKeyboardRemove(),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error processing external order: {e}")
            await update.message.reply_text(
                "❌ **Terjadi Kesalahan**\n\n"
                "Maaf, terjadi kesalahan saat memproses order di server.\n"
                "Silakan coba lagi atau hubungi admin.",
                reply_markup=ReplyKeyboardRemove()
            )
        
        # Clear user data
        context.user_data.clear()
        return ConversationHandler.END

    async def order_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel order process"""
        await update.message.reply_text(
            "❌ **Proses Order Dibatalkan**\n\n"
            "Tidak ada yang ditagih.\n"
            "Gunakan /order untuk memulai pemesanan baru.",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Callback handlers for inline keyboard
    async def start_order_from_callback(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Start order process from callback query"""
        import database
        user = query.from_user
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
        
        # Get products from database
        products = self.get_active_products()
        context.user_data["produk_list"] = products
        
        if not products:
            await query.edit_message_text(
                "❌ **Produk Belum Tersedia**\n\n"
                "Maaf, saat ini tidak ada produk yang tersedia.\n"
                "Silakan coba lagi nanti.",
                parse_mode='Markdown'
            )
            return
        
        # Create product keyboard
        produk_keyboard = []
        for code, name, price, description, stock in products:
            produk_keyboard.append([f"🛒 {code} - {name}"])
        produk_keyboard.append(["❌ Batalkan Order"])
        
        # Send new message with product selection
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                f"💰 **Saldo Anda:** Rp {saldo:,}\n\n"
                "🎮 **PILIH PRODUK:**\n\n"
                "Silakan pilih produk dari keyboard di bawah:"
            ),
            reply_markup=ReplyKeyboardMarkup(
                produk_keyboard,
                one_time_keyboard=True,
                resize_keyboard=True,
                input_field_placeholder="Pilih produk..."
            ),
            parse_mode='Markdown'
        )

    # Utility methods
    def _validate_phone_number(self, phone):
        """Validate Indonesian phone number format"""
        if not phone.startswith("08"):
            return False
        if not (10 <= len(phone) <= 14):
            return False
        if not phone.isdigit():
            return False
        return True

    def get_conversation_handler(self):
        """Return the conversation handler for orders"""
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

# Export handler instance
order_handler = OrderHandler()
