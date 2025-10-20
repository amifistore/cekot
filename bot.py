#!/usr/bin/env python3
"""
Bot Telegram Full Feature - FINAL FIXED VERSION
By CekotDev - Adjusted and Fixed by Gemini
"""

import logging
import asyncio
from datetime import datetime

# Telegram Imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    MessageHandler,
    ConversationHandler,
    PicklePersistence
)

# Custom Module Imports
import config
import database

# ==================== IMPORTS DENGAN ERROR HANDLING ====================
print("🔄 Loading handlers...")

# Admin Handler
try:
    from admin_handler import (
        admin_menu,
        admin_callback_handler,
        edit_produk_conv_handler,
        broadcast_handler,
        cek_user_handler,
        jadikan_admin_handler,
        topup_list_handler
    )
    ADMIN_AVAILABLE = True
    print("✅ Admin handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing admin_handler: {e}")
    ADMIN_AVAILABLE = False
    admin_menu = admin_callback_handler = edit_produk_conv_handler = broadcast_handler = cek_user_handler = jadikan_admin_handler = topup_list_handler = None

# Stok Handler
try:
    from stok_handler import stock_akrab_callback, stock_command
    STOK_AVAILABLE = True
    print("✅ Stok handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing stok_handler: {e}")
    STOK_AVAILABLE = False
    stock_akrab_callback = stock_command = None

# Order Handler
try:
    # Menggunakan satu fungsi utama untuk semua handler order
    from order_handler import get_order_handlers
    ORDER_AVAILABLE = True
    print("✅ Order handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing order_handler: {e}")
    ORDER_AVAILABLE = False
    get_order_handlers = lambda: []

# Topup Handler
try:
    # Cukup impor satu fungsi utama yang mengembalikan semua handler
    from topup_handler import get_topup_handlers, show_topup_menu
    TOPUP_AVAILABLE = True
    print("✅ Topup handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing topup_handler: {e}")
    TOPUP_AVAILABLE = False
    get_topup_handlers = lambda: []
    show_topup_menu = None

# ==================== LOGGING SETUP ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== GLOBAL VARIABLES ====================
BOT_TOKEN = config.BOT_TOKEN
ADMIN_IDS = [str(admin_id) for admin_id in getattr(config, 'ADMIN_TELEGRAM_IDS', [])]

# ==================== UTILITY FUNCTION ====================
def format_currency(amount: int) -> str:
    """Utility function to format currency."""
    if amount is None: amount = 0
    return f"Rp {amount:,.0f}".replace(",", ".")

# ==================== MENU & BASIC COMMANDS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start - Menampilkan menu utama."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot")
    
    try:
        user_id_db = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id_db)
    except Exception as e:
        logger.error(f"DB Error on start for user {user.id}: {e}")
        saldo = 0
    
    keyboard = [
        [InlineKeyboardButton("🛒 Beli Produk", callback_data="main_menu_order")],
        [InlineKeyboardButton("💸 Top Up Saldo", callback_data="topup_menu")],
        [InlineKeyboardButton("💳 Cek Saldo", callback_data="main_menu_saldo")],
        [InlineKeyboardButton("📊 Cek Stok", callback_data="main_menu_stock")],
        [InlineKeyboardButton("📞 Bantuan", callback_data="main_menu_help")],
    ]
    
    if str(user.id) in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 Panel Admin", callback_data="admin_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_text = (
        f"🤖 **Selamat Datang, {user.full_name}!**\n\n"
        f"💰 Saldo Anda saat ini: **{format_currency(saldo)}**\n\n"
        "Silakan pilih menu di bawah untuk memulai."
    )
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Router callback utama untuk tombol-tombol menu."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "main_menu_main":
        await show_main_menu(update, context)
    elif data == "main_menu_saldo":
        await saldo_command(update, context, is_callback=True)
    elif data == "main_menu_help":
        await help_command(update, context, is_callback=True)
    elif data == "main_menu_stock" and STOK_AVAILABLE:
        await stock_akrab_callback(update, context)
    elif data == "main_menu_order":
        await query.message.reply_text("Untuk memulai pesanan, silakan ketik /order")
    elif data == "topup_menu" and TOPUP_AVAILABLE:
        await show_topup_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan kembali menu utama (untuk tombol 'Kembali')."""
    query = update.callback_query
    user = query.from_user
    saldo = database.get_user_saldo(str(user.id))
    
    keyboard = [
        [InlineKeyboardButton("🛒 Beli Produk", callback_data="main_menu_order")],
        [InlineKeyboardButton("💸 Top Up Saldo", callback_data="topup_menu")],
        [InlineKeyboardButton("💳 Cek Saldo", callback_data="main_menu_saldo")],
        [InlineKeyboardButton("📊 Cek Stok", callback_data="main_menu_stock")],
        [InlineKeyboardButton("📞 Bantuan", callback_data="main_menu_help")],
    ]
    if str(user.id) in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 Panel Admin", callback_data="admin_menu")])
    
    await query.edit_message_text(
        f"🏠 **Menu Utama**\n\n💰 Saldo Anda: **{format_currency(saldo)}**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def saldo_command(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
    """Handler untuk /saldo dan tombol Cek Saldo."""
    user = update.effective_user
    saldo = database.get_user_saldo(str(user.id))
    
    text = f"💳 **Informasi Saldo**\n\nSaldo Anda saat ini adalah: **{format_currency(saldo)}**"
    keyboard = [
        [InlineKeyboardButton("💸 Top Up Sekarang", callback_data="topup_menu")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu_main")]
    ]
    
    if is_callback:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
    """Handler untuk /help dan tombol Bantuan."""
    text = (
        "📞 **Pusat Bantuan**\n\n"
        "`/start` - Menampilkan menu utama\n"
        "`/order` - Memesan produk\n"
        "`/topup` - Isi ulang saldo\n"
        "`/saldo` - Cek sisa saldo\n"
        "`/myorders` - Riwayat pesanan\n"
        "`/stock` - Cek stok produk"
    )
    keyboard = [[InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu_main")]]
    
    if is_callback:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk pesan atau perintah yang tidak dikenali."""
    await update.message.reply_text("🤔 Perintah tidak dikenali. Gunakan /start untuk kembali ke menu utama.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    # Anda bisa menambahkan notifikasi error ke admin di sini

async def post_init(application: Application):
    """Fungsi yang dijalankan setelah bot berhasil terinisialisasi."""
    logger.info("🤖 Bot has been initialized successfully!")
    if ADMIN_IDS:
        try:
            await application.bot.send_message(
                chat_id=ADMIN_IDS[0],
                text=f"✅ Bot berhasil dinyalakan pada {datetime.now().strftime('%d-%m-%Y %H:%M:%S WIB')}"
            )
        except Exception as e:
            logger.warning(f"Failed to send post_init message to admin: {e}")

# ==================== MAIN FUNCTION ====================
def main():
    """Fungsi utama untuk menginisialisasi dan menjalankan bot."""
    logger.info("🚀 Starting bot...")
    
    if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        logger.critical("❌ BOT_TOKEN not set in config.py! Exiting.")
        return

    try:
        database.init_database()
        logger.info("✅ Database connection successful.")
    except Exception as e:
        logger.critical(f"❌ Failed to connect to database: {e}. Exiting.")
        return
        
    persistence = PicklePersistence(filepath="bot_persistence")
    application = Application.builder()\
        .token(BOT_TOKEN)\
        .persistence(persistence)\
        .post_init(post_init)\
        .build()
        
    # --- Registrasi Handler (Sesuai Urutan Prioritas) ---
    
    # 1. Conversation Handlers (Paling Penting)
    if ADMIN_AVAILABLE and edit_produk_conv_handler:
        application.add_handler(edit_produk_conv_handler)
    if ORDER_AVAILABLE:
        for handler in get_order_handlers():
            application.add_handler(handler)
    if TOPUP_AVAILABLE:
        for handler in get_topup_handlers():
            application.add_handler(handler)
    
    # 2. Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("saldo", saldo_command))
    if STOK_AVAILABLE:
        application.add_handler(CommandHandler("stock", stock_command))
    
    # 3. Admin Command Handlers
    if ADMIN_AVAILABLE:
        application.add_handler(CommandHandler("admin", admin_menu))
        application.add_handler(CommandHandler("broadcast", broadcast_handler))
        application.add_handler(CommandHandler("cekuser", cek_user_handler))
        application.add_handler(CommandHandler("addadmin", jadikan_admin_handler))
        application.add_handler(CommandHandler("topuplist", topup_list_handler))

    # 4. Callback Query Handlers (Tombol)
    application.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^main_menu_"))
    application.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^topup_menu$"))
    if ADMIN_AVAILABLE:
        application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))
    
    # 5. Handler untuk Perintah/Pesan Tidak Dikenal (Harus di bagian akhir)
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_command))

    # 6. Global Error Handler
    application.add_error_handler(error_handler)
    
    logger.info("✅ All handlers registered successfully.")
    print("================ BOT IS RUNNING ================")
    
    # Menjalankan bot
    application.run_polling()

if __name__ == '__main__':
    main()
