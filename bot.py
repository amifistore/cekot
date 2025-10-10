import logging
import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Import config
try:
    import config
    BOT_TOKEN = config.BOT_TOKEN
except (ImportError, AttributeError) as e:
    logger.error(f"Error loading config: {e}")
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN tidak ditemukan. Pastikan file config.py ada dan berisi BOT_TOKEN, atau set environment variable BOT_TOKEN")

# Import order handler
try:
    from order_handler import order_handler
    ORDER_HANDLER_AVAILABLE = True
    logger.info("✅ Order handler loaded successfully")
except ImportError as e:
    logger.error(f"❌ Failed to load order handler: {e}")
    ORDER_HANDLER_AVAILABLE = False

# Import topup handler
try:
    from topup_handler import topup_conv_handler
    TOPUP_HANDLER_AVAILABLE = True
    logger.info("✅ Topup handler loaded successfully")
except ImportError as e:
    logger.error(f"❌ Failed to load topup handler: {e}")
    TOPUP_HANDLER_AVAILABLE = False

# Import admin handler
try:
    from admin_handler import get_admin_handlers, admin_menu, admin_callback_handler
    admin_handlers = get_admin_handlers()
    ADMIN_HANDLER_AVAILABLE = True
    logger.info("✅ Admin handler loaded successfully")
except ImportError as e:
    logger.warning(f"⚠️ Admin handler not available: {e}")
    ADMIN_HANDLER_AVAILABLE = False
    admin_handlers = []
    admin_menu = None

# Import database
try:
    import database
    DATABASE_AVAILABLE = True
    logger.info("✅ Database module loaded successfully")
except ImportError as e:
    logger.error(f"❌ Failed to load database module: {e}")
    DATABASE_AVAILABLE = False

# User Telegram ID admin (replace with actual ID)
ADMIN_IDS = [123456789, 987654321]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    saldo = 0
    if DATABASE_AVAILABLE:
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception as e:
            logger.error(f"Error getting user balance: {e}")
            saldo = 0

    keyboard = [
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="order"),
         InlineKeyboardButton("💰 TOP UP SALDO", callback_data="topup")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="saldo"),
         InlineKeyboardButton("📞 BANTUAN", callback_data="help")]
    ]
    if ADMIN_HANDLER_AVAILABLE and user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="admin")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🤖 **Selamat Datang di AmifiVPS Bot!**\n\n"
        f"Halo {user.full_name}! 👋\n"
        f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
        "Silakan pilih menu di bawah untuk mulai berbelanja:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

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
        except Exception as e:
            logger.error(f"Error getting user balance: {e}")
            saldo = 0

    if callback_data == "order":
        if ORDER_HANDLER_AVAILABLE:
            await order_handler.start_order_from_callback(query, context)
        else:
            await query.edit_message_text(
                "❌ **Fitur Order Sedang Tidak Tersedia**\n\n"
                "Maaf, sistem order sedang dalam perbaikan.\n"
                "Silakan coba lagi nanti atau hubungi admin.",
                parse_mode='Markdown'
            )
    elif callback_data == "saldo":
        await query.edit_message_text(
            f"💰 **SALDO ANDA**\n\n"
            f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
            "Gunakan menu di bawah untuk topup atau belanja:",
            parse_mode='Markdown'
        )
    elif callback_data == "topup":
        if TOPUP_HANDLER_AVAILABLE:
            await query.edit_message_text(
                "💳 Memulai proses topup...\n\nKetik nominal yang ingin di-topup, contoh: `10000`.\nAtau ketik /topup untuk mulai.",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                "❌ **Fitur Topup Sedang Tidak Tersedia**\n\n"
                "Maaf, sistem topup sedang dalam perbaikan.\n"
                "Silakan coba lagi nanti atau hubungi admin.",
                parse_mode='Markdown'
            )
    elif callback_data == "help":
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
        await query.edit_message_text(help_text, parse_mode='Markdown')
    elif callback_data == "admin" and ADMIN_HANDLER_AVAILABLE and admin_menu is not None and user.id in ADMIN_IDS:
        await admin_menu(update, context)
    elif ADMIN_HANDLER_AVAILABLE and (callback_data.startswith("admin_") or callback_data in [
        "edit_harga", "edit_deskripsi", "back_to_edit_menu", "select_product:"
    ]) and user.id in ADMIN_IDS:
        await admin_callback_handler(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception while handling an update: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Terjadi kesalahan sistem. Silakan coba lagi atau hubungi admin."
            )
        except Exception as e:
            logger.error(f"Error sending error message: {e}")

def main():
    try:
        if not BOT_TOKEN:
            logger.error("❌ BOT_TOKEN tidak ditemukan!")
            return

        logger.info("🚀 Starting bot...")

        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", start))

        if ORDER_HANDLER_AVAILABLE:
            application.add_handler(order_handler.get_conversation_handler())
            logger.info("✅ Order handler registered")
        else:
            logger.warning("⚠️ Order handler not available")
        if TOPUP_HANDLER_AVAILABLE:
            application.add_handler(topup_conv_handler)
            logger.info("✅ Topup handler registered")
        else:
            logger.warning("⚠️ Topup handler not available")

        application.add_handler(CallbackQueryHandler(handle_callback))

        if ADMIN_HANDLER_AVAILABLE:
            for handler in admin_handlers:
                application.add_handler(handler)
            logger.info("✅ Admin handlers loaded")
        else:
            logger.warning("⚠️ Admin handler not available")

        application.add_error_handler(error_handler)

        logger.info("🤖 Bot is running...")
        application.run_polling()

    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        raise

if __name__ == '__main__':
    main()
