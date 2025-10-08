import logging
import sqlite3
from datetime import datetime
from telegram import (
    Update, 
    ReplyKeyboardMarkup, 
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
import config

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = "bot_topup.db"

# Conversation states
ASK_ORDER_PRODUK, ASK_ORDER_TUJUAN, ASK_ORDER_CONFIRM = range(3)

# Database functions
def init_database():
    """Initialize database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            saldo REAL DEFAULT 0,
            created_at TEXT
        )
    ''')
    
    # Products table
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            code TEXT PRIMARY KEY,
            name TEXT,
            price REAL,
            status TEXT DEFAULT 'active',
            updated_at TEXT
        )
    ''')
    
    # Orders history table
    c.execute('''
        CREATE TABLE IF NOT EXISTS riwayat_pembelian (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
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
    
    # Insert sample products if empty
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        sample_products = [
            ('XLA14', 'SuperMini', 40000, 'active', datetime.now().isoformat()),
            ('TES', 'Produk TES', 20000, 'active', datetime.now().isoformat()),
            ('XLA39', 'XLA39 Premium', 50000, 'active', datetime.now().isoformat())
        ]
        c.executemany(
            "INSERT INTO products (code, name, price, status, updated_at) VALUES (?, ?, ?, ?, ?)",
            sample_products
        )
        logger.info("Sample products inserted")
    
    conn.commit()
    conn.close()

def get_or_create_user(user_id, username, full_name):
    """Get or create user in database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    
    if not user:
        c.execute(
            "INSERT INTO users (user_id, username, full_name, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, full_name, datetime.now().isoformat())
        )
        conn.commit()
        logger.info(f"New user created: {user_id}")
    
    conn.close()
    return user_id

def get_user_saldo(user_id):
    """Get user balance"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT saldo FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    return result[0] if result else 0

def increment_user_saldo(user_id, amount):
    """Update user balance"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET saldo = saldo + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# Start Command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message with inline keyboard"""
    user = update.message.from_user
    user_id = get_or_create_user(str(user.id), user.username, user.full_name)
    
    keyboard = [
        [
            InlineKeyboardButton("🛒 BELI PRODUK", callback_data="order"),
            InlineKeyboardButton("💰 TOP UP SALDO", callback_data="topup")
        ],
        [
            InlineKeyboardButton("💳 CEK SALDO", callback_data="saldo"),
            InlineKeyboardButton("📞 BANTUAN", callback_data="help")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🤖 **Selamat Datang di AmifiVPS Bot!**\n\n"
        f"Halo {user.full_name}! 👋\n\n"
        "Silakan pilih menu di bawah untuk mulai berbelanja:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Callback Query Handler
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline keyboard"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user = query.from_user
    
    if callback_data == "order":
        await start_order_from_callback(query, context)
    elif callback_data == "saldo":
        await cek_saldo_from_callback(query, context)
    elif callback_data == "topup":
        await topup_instructions(query, context)
    elif callback_data == "help":
        await help_message(query, context)

async def start_order_from_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """Start order process from callback query"""
    user = query.from_user
    user_id = get_or_create_user(str(user.id), user.username, user.full_name)
    saldo = get_user_saldo(user_id)
    
    # Get products from database
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT code, name, price FROM products WHERE status='active' ORDER BY name ASC")
    produk_list = c.fetchall()
    conn.close()
    
    context.user_data["produk_list"] = produk_list
    
    if not produk_list:
        await query.edit_message_text(
            "❌ **Produk Belum Tersedia**\n\n"
            "Silakan minta admin untuk update produk terlebih dahulu.",
            parse_mode='Markdown'
        )
        return
    
    # Create product keyboard
    produk_keyboard = []
    for code, name, price in produk_list:
        produk_keyboard.append([f"🛒 {code} - {name} - Rp {price:,}"])
    
    produk_keyboard.append(["❌ Batalkan Order"])
    
    # Send new message with product selection
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
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
    
    # Set conversation state
    context.user_data['conversation_state'] = ASK_ORDER_PRODUK

# Order Conversation Handlers
async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start order process from command"""
    user = update.message.from_user
    user_id = get_or_create_user(str(user.id), user.username, user.full_name)
    saldo = get_user_saldo(user_id)
    
    # Get products from database
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT code, name, price FROM products WHERE status='active' ORDER BY name ASC")
    produk_list = c.fetchall()
    conn.close()
    
    context.user_data["produk_list"] = produk_list
    
    if not produk_list:
        await update.message.reply_text(
            "❌ **Produk Belum Tersedia**\n\n"
            "Silakan minta admin untuk update produk terlebih dahulu.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Create product keyboard
    produk_keyboard = []
    for code, name, price in produk_list:
        produk_keyboard.append([f"🛒 {code} - {name} - Rp {price:,}"])
    
    produk_keyboard.append(["❌ Batalkan Order"])
    
    await update.message.reply_text(
        f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
        "🎮 **PILIH PRODUK:**\n\n"
        "Silakan pilih produk dari keyboard di bawah:",
        reply_markup=ReplyKeyboardMarkup(
            produk_keyboard,
            one_time_keyboard=True,
            resize_keyboard=True,
            input_field_placeholder="Pilih produk..."
        ),
        parse_mode='Markdown'
    )
    
    return ASK_ORDER_PRODUK

async def order_produk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product selection"""
    user_input = update.message.text.strip()
    
    # Handle cancellation
    if user_input == "❌ Batalkan Order":
        await update.message.reply_text(
            "❌ **Order Dibatalkan**\n\nKetik /order untuk memulai lagi.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    # Extract product code from input
    if user_input.startswith("🛒 "):
        kode_produk = user_input.split(" - ")[0].replace("🛒 ", "").strip()
    else:
        kode_produk = user_input.split(" - ")[0].strip()
    
    produk_list = context.user_data.get("produk_list", [])
    produk = next((p for p in produk_list if p[0] == kode_produk), None)
    
    if not produk:
        # Show products keyboard again
        produk_keyboard = []
        for code, name, price in produk_list:
            produk_keyboard.append([f"🛒 {code} - {name} - Rp {price:,}"])
        produk_keyboard.append(["❌ Batalkan Order"])
        
        await update.message.reply_text(
            "❌ **Produk Tidak Ditemukan**\n\nSilakan pilih produk dari keyboard:",
            reply_markup=ReplyKeyboardMarkup(
                produk_keyboard,
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return ASK_ORDER_PRODUK
    
    context.user_data["order_produk"] = produk
    
    await update.message.reply_text(
        f"✅ **{produk[1]}** dipilih\n"
        f"💵 **Harga:** Rp {produk[2]:,.0f}\n\n"
        "📱 **Masukkan nomor tujuan:**\n"
        "Contoh: `081234567890`",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    
    return ASK_ORDER_TUJUAN

async def order_tujuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle destination number input"""
    tujuan = update.message.text.strip()
    
    # Validate phone number format
    if not tujuan.startswith("08") or not (10 <= len(tujuan) <= 14) or not tujuan.isdigit():
        await update.message.reply_text(
            "❌ **Format Nomor Tidak Valid**\n\n"
            "Format yang benar: `08xxxxxxxxxx`\n"
            "Panjang: 10-14 digit\n\n"
            "Silakan masukkan ulang nomor tujuan:",
            parse_mode='Markdown'
        )
        return ASK_ORDER_TUJUAN
    
    context.user_data["order_tujuan"] = tujuan
    produk = context.user_data["order_produk"]
    
    # Create confirmation keyboard
    confirm_keyboard = [
        ["✅ Ya, Lanjutkan Order"],
        ["❌ Batalkan Order"]
    ]
    
    await update.message.reply_text(
        f"📋 **KONFIRMASI ORDER**\n\n"
        f"📦 **Produk:** {produk[1]}\n"
        f"💵 **Harga:** Rp {produk[2]:,.0f}\n"
        f"📱 **Tujuan:** {tujuan}\n\n"
        "**Apakah data sudah benar?**",
        reply_markup=ReplyKeyboardMarkup(
            confirm_keyboard,
            one_time_keyboard=True,
            resize_keyboard=True
        ),
        parse_mode='Markdown'
    )
    
    return ASK_ORDER_CONFIRM

async def order_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle order confirmation"""
    user = update.message.from_user
    user_input = update.message.text.strip()
    
    # Handle cancellation
    if user_input == "❌ Batalkan Order":
        await update.message.reply_text(
            "❌ **Order Dibatalkan**\n\nKetik /order untuk memulai lagi.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    # Check confirmation
    if user_input != "✅ Ya, Lanjutkan Order":
        await update.message.reply_text(
            "❌ **Order Dibatalkan**\n\nKetik /order untuk memulai lagi.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    user_id = get_or_create_user(str(user.id), user.username, user.full_name)
    produk = context.user_data["order_produk"]
    tujuan = context.user_data["order_tujuan"]
    saldo = get_user_saldo(user_id)
    
    # Check balance
    if saldo < produk[2]:
        await update.message.reply_text(
            f"❌ **Saldo Tidak Cukup**\n\n"
            f"Saldo Anda: Rp {saldo:,.0f}\n"
            f"Dibutuhkan: Rp {produk[2]:,.0f}\n\n"
            "Silakan topup saldo terlebih dahulu.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Process order
    increment_user_saldo(user_id, -produk[2])
    reff_id = f"ORDER_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    waktu = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        INSERT INTO riwayat_pembelian 
        (user_id, kode_produk, nama_produk, tujuan, harga, saldo_awal, reff_id, status_api, keterangan, waktu)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id, produk[0], produk[1], tujuan, produk[2], saldo, reff_id, "SUCCESS", "Order berhasil", waktu
    ))
    
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"🎉 **ORDER BERHASIL!**\n\n"
        f"📦 **Produk:** {produk[1]}\n"
        f"💵 **Harga:** Rp {produk[2]:,.0f}\n"
        f"📱 **Tujuan:** {tujuan}\n"
        f"💰 **Saldo Sekarang:** Rp {saldo - produk[2]:,.0f}\n\n"
        f"📋 **ID Transaksi:** `{reff_id}`\n\n"
        "Terima kasih telah berbelanja! 😊",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    
    # Clear user data
    context.user_data.clear()
    return ConversationHandler.END

async def order_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel order process"""
    await update.message.reply_text(
        "❌ **Proses Order Dibatalkan**\n\nKetik /order untuk memulai lagi.",
        reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END

# Other command handlers
async def cek_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check user balance"""
    user = update.message.from_user
    user_id = get_or_create_user(str(user.id), user.username, user.full_name)
    saldo = get_user_saldo(user_id)
    
    await update.message.reply_text(
        f"💰 **SALDO ANDA**\n\n"
        f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
        "Gunakan menu di bawah untuk topup atau belanja:",
        parse_mode='Markdown'
    )

async def cek_saldo_from_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """Check balance from callback"""
    user = query.from_user
    user_id = get_or_create_user(str(user.id), user.username, user.full_name)
    saldo = get_user_saldo(user_id)
    
    await query.edit_message_text(
        f"💰 **SALDO ANDA**\n\n"
        f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
        "Gunakan menu di bawah untuk topup atau belanja:",
        parse_mode='Markdown'
    )

async def topup_instructions(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """Show topup instructions"""
    instructions = (
        "💰 **TOP UP SALDO**\n\n"
        "Untuk topup saldo, silakan transfer ke:\n\n"
        "📍 **BCA**: 123-456-7890 (Amifi Store)\n"
        "📍 **BRI**: 098-765-4321 (Amifi Store)\n\n"
        "Setelah transfer, kirim bukti transfer ke @admin\n"
        "Saldo akan ditambahkan dalam 1-5 menit.\n\n"
        "Terima kasih! 😊"
    )
    
    await query.edit_message_text(
        instructions,
        parse_mode='Markdown'
    )

async def help_message(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """Show help message"""
    help_text = (
        "📞 **BANTUAN & SUPPORT**\n\n"
        "Jika Anda mengalami kendala atau butuh bantuan:\n\n"
        "🔹 **Cara Order**:\n"
        "1. Pilih 'BELI PRODUK'\n"
        "2. Pilih produk yang diinginkan\n"
        "3. Masukkan nomor tujuan\n"
        "4. Konfirmasi order\n\n"
        "🔹 **Top Up Saldo**:\n"
        "Transfer ke rekening yang tersedia\n"
        "Kirim bukti ke admin\n\n"
        "🔹 **Admin Support**:\n"
        "@admin_amifi (24/7)\n\n"
        "Terima kasih! 😊"
    )
    
    await query.edit_message_text(
        help_text,
        parse_mode='Markdown'
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Exception while handling an update: {context.error}")
    
    # Send error message to user
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Terjadi kesalahan sistem. Silakan coba lagi atau hubungi admin."
        )

def main():
    """Start the bot"""
    # Initialize database
    init_database()
    
    # Create application
    application = Application.builder().token(config.TOKEN).build()
    
    # Add conversation handler for order
    order_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('order', order_start),
            CommandHandler('start', start)
        ],
        states={
            ASK_ORDER_PRODUK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_produk)
            ],
            ASK_ORDER_TUJUAN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_tujuan)
            ],
            ASK_ORDER_CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_confirm)
            ],
        },
        fallbacks=[
            CommandHandler('cancel', order_cancel),
            MessageHandler(filters.Regex('^❌ Batalkan Order$'), order_cancel)
        ]
    )
    
    # Add handlers
    application.add_handler(order_conv_handler)
    application.add_handler(CommandHandler('saldo', cek_saldo))
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start bot
    logger.info("Bot started successfully!")
    application.run_polling()

if __name__ == '__main__':
    main()
