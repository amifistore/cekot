import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    MessageHandler,
    ConversationHandler
)
import config
import database
import order_handler
import admin_handler
import stok_handler  # IMPORT STOK_HANDLER
from topup_handler import topup_conv_handler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = config.BOT_TOKEN
ADMIN_IDS = set(str(i) for i in getattr(config, "ADMIN_TELEGRAM_IDS", []))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        saldo = 0
    
    keyboard = [
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="menu_order")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="menu_saldo")],
        [InlineKeyboardButton("📊 CEK STOK", callback_data="menu_stock")],
        [InlineKeyboardButton("📞 BANTUAN", callback_data="menu_help")],
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="menu_topup")]
    ]
    
    if str(user.id) in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="menu_admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🤖 Selamat Datang!\n\nHalo {user.full_name}!\n💰 Saldo Anda: Rp {saldo:,.0f}\nPilih menu di bawah.",
        reply_markup=reply_markup
    )

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    logger.info(f"Menu callback received: {data}")
    
    if data == "menu_main":
        await show_main_menu(query)
    elif data == "menu_saldo":
        await show_saldo_menu(query)
    elif data == "menu_help":
        await show_help_menu(query)
    elif data == "menu_topup":
        await show_topup_menu(query)
    elif data == "menu_order":
        from order_handler import order_start
        await order_start(update, context)
    elif data == "menu_stock":
        # GUNAKAN stok_handler YANG SUDAH ADA
        await stok_handler.stock_akrab_callback(update, context)
    elif data == "menu_admin":
        # Langsung panggil admin_menu dari admin_handler
        await admin_handler.admin_menu(update, context)
    else:
        # Fallback untuk callback data lain
        await query.edit_message_text("Menu tidak dikenal.")

async def show_main_menu(query):
    user = query.from_user
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        saldo = 0
    
    keyboard = [
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="menu_order")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="menu_saldo")],
        [InlineKeyboardButton("📊 CEK STOK", callback_data="menu_stock")],
        [InlineKeyboardButton("📞 BANTUAN", callback_data="menu_help")],
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="menu_topup")]
    ]
    
    if str(user.id) in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="menu_admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🤖 Menu Utama\n\nHalo {user.full_name}!\n💰 Saldo Anda: Rp {saldo:,.0f}\nPilih menu di bawah.",
        reply_markup=reply_markup
    )

async def show_saldo_menu(query):
    user = query.from_user
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        saldo = 0
    
    keyboard = [[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"💰 SALDO ANDA\n\nSaldo saat ini: Rp {saldo:,.0f}",
        reply_markup=reply_markup
    )

async def show_help_menu(query):
    keyboard = [[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📞 BANTUAN\n\nJika Anda membutuhkan bantuan, silakan hubungi admin.",
        reply_markup=reply_markup
    )

async def show_topup_menu(query):
    keyboard = [[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "💸 TOP UP SALDO\n\nUntuk top up saldo, ketik perintah /topup dan ikuti instruksi.",
        reply_markup=reply_markup
    )

# HAPUS FUNGSI show_stock_menu YANG LAMA KARENA SUDAH ADA DI stok_handler.py

# GUNAKAN stok_handler.stock_command UNTUK COMMAND /stock
async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stok_handler.stock_command(update, context)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Basic command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stock", stock_command))  # GUNAKAN stok_handler
    application.add_handler(CommandHandler("admin", admin_handler.admin_menu))
    
    # Conversation handlers
    application.add_handler(order_handler.get_conversation_handler())
    application.add_handler(topup_conv_handler)
    
    # Menu callback handler
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    
    # Stock handler - TAMBAHKAN INI
    application.add_handler(CallbackQueryHandler(stok_handler.stock_akrab_callback, pattern="^menu_stock$"))
    
    # Admin callback handlers
    application.add_handler(CallbackQueryHandler(admin_handler.admin_callback_handler, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(admin_handler.edit_produk_menu_handler, pattern="^edit_"))
    application.add_handler(CallbackQueryHandler(admin_handler.select_product_handler, pattern="^select_product:"))
    
    # Fallback untuk callback yang tidak ditangani
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=".*"))
    
    application.add_error_handler(error_handler)
    
    logger.info("🤖 Bot starting with integrated stock handler...")
    application.run_polling()

if __name__ == '__main__':
    main()
