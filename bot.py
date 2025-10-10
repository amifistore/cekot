import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Konfigurasi logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load token dari config.py atau environment
try:
    import config
    BOT_TOKEN = config.BOT_TOKEN
except (ImportError, AttributeError):
    BOT_TOKEN = os.getenv('BOT_TOKEN')

from order_handler import order_handler

try:
    import database
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False

# Ganti dengan Telegram user ID admin (integer)
ADMIN_IDS = [123456789, 987654321]  # isi dengan id admin

# ----------- MENU UTAMA USER -----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    saldo = 0
    if DATABASE_AVAILABLE:
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception:
            saldo = 0

    keyboard = [
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="order"),
         InlineKeyboardButton("💳 CEK SALDO", callback_data="saldo")],
        [InlineKeyboardButton("📞 BANTUAN", callback_data="help")]
    ]
    # Tampilkan menu admin jika user adalah admin
    if user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="admin")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🤖 Selamat Datang!\n\n"
        f"Halo {user.full_name}! 👋\n"
        f"💰 Saldo Anda: Rp {saldo:,.0f}\n\n"
        "Silakan pilih menu di bawah untuk mulai berbelanja:",
        reply_markup=reply_markup
    )

# ----------- MENU CALLBACK HANDLER -----------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    user = query.from_user

    saldo = 0
    if DATABASE_AVAILABLE:
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception:
            saldo = 0

    if callback_data == "order":
        await order_handler.start_order_from_callback(query, context)
    elif callback_data == "saldo":
        await query.edit_message_text(
            f"💰 SALDO ANDA\n\nSaldo saat ini: Rp {saldo:,.0f}\n\n"
            "Gunakan menu di bawah untuk topup atau belanja."
        )
    elif callback_data == "help":
        help_text = (
            "📞 **BANTUAN & SUPPORT**\n\n"
            "Jika Anda mengalami kendala atau butuh bantuan:\n"
            "Hubungi admin @username_admin\n"
            "atau gunakan menu di bawah untuk order/topup saldo."
        )
        await query.edit_message_text(help_text, parse_mode='Markdown')
    elif callback_data == "admin":
        if user.id not in ADMIN_IDS:
            await query.edit_message_text("❌ Anda bukan admin!")
            return
        await admin_menu(query, context)

# ----------- ADMIN MENU & HANDLER -----------
async def admin_menu(query, context):
    keyboard = [
        [InlineKeyboardButton("📦 Produk", callback_data="admin_produk"),
         InlineKeyboardButton("👤 User", callback_data="admin_user")],
        [InlineKeyboardButton("📄 Riwayat Order", callback_data="admin_order")],
        [InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "👑 **ADMIN PANEL**\n\nSilakan pilih menu admin:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Handler untuk submenu admin (simple, bisa dikembangkan)
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    user = query.from_user

    if user.id not in ADMIN_IDS:
        await query.edit_message_text("❌ Anda bukan admin!")
        return

    if callback_data == "admin_produk":
        await query.edit_message_text("📦 Manajemen produk (fitur belum dibuat)")
    elif callback_data == "admin_user":
        await query.edit_message_text("👤 Manajemen user (fitur belum dibuat)")
    elif callback_data == "admin_order":
        await query.edit_message_text("📄 Riwayat order (fitur belum dibuat)")
    elif callback_data == "admin_back":
        await start(update, context)

# ----------- ERROR HANDLER -----------
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Terjadi kesalahan sistem. Silakan coba lagi atau hubungi admin."
            )
        except Exception:
            pass

# ----------- MAIN FUNCTION -----------
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(order_handler.get_conversation_handler())
    application.add_handler(CallbackQueryHandler(handle_callback, filters=filters.Regex(r'^(order|saldo|help|admin)$')))
    application.add_handler(CallbackQueryHandler(admin_callback, filters=filters.Regex(r'^admin_')))
    application.add_error_handler(error_handler)

    logger.info("🤖 Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
