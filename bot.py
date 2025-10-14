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
from topup_handler import topup_conv_handler
import telegram
import requests
import aiohttp
import sqlite3

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
        await show_stock_menu(query)
    elif data == "menu_admin":
        # Panggil admin_menu langsung dari admin_handler
        await admin_handler.admin_menu(update, context)

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

async def show_stock_menu(query):
    try:
        # Gunakan requests biasa untuk cek stok
        api_key = getattr(config, 'API_KEY_PROVIDER', '')
        url = "https://panel.khfy-store.com/api_v3/cek_stock_akrab"
        params = {'api_key': api_key} if api_key else {}
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("ok", False):
            stocks = data.get("data", {})
            if stocks:
                msg = "📊 STOK PRODUK AKRAB\n\n"
                for product_name, stock_info in stocks.items():
                    stock = stock_info.get("stock", 0)
                    status = "✅ TERSEDIA" if stock > 0 else "❌ HABIS"
                    msg += f"• {product_name}: {stock} pcs - {status}\n"
                msg += f"\n⏰ Update: {data.get('timestamp', 'N/A')}"
            else:
                msg = "📭 Tidak ada data stok yang tersedia."
        else:
            msg = "❌ Gagal mengambil data stok dari provider."
            
    except Exception as e:
        logger.error(f"Error getting stock: {e}")
        msg = f"❌ Gagal mengambil data stok: {str(e)}"

    keyboard = [[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(msg, reply_markup=reply_markup)

# Handler untuk perintah /stock
async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        api_key = getattr(config, 'API_KEY_PROVIDER', '')
        url = "https://panel.khfy-store.com/api_v3/cek_stock_akrab"
        params = {'api_key': api_key} if api_key else {}
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("ok", False):
            stocks = data.get("data", {})
            if stocks:
                msg = "📊 STOK PRODUK AKRAB\n\n"
                for product_name, stock_info in stocks.items():
                    stock = stock_info.get("stock", 0)
                    status = "✅ TERSEDIA" if stock > 0 else "❌ HABIS"
                    msg += f"• {product_name}: {stock} pcs - {status}\n"
                msg += f"\n⏰ Update: {data.get('timestamp', 'N/A')}"
            else:
                msg = "📭 Tidak ada data stok yang tersedia."
        else:
            msg = "❌ Gagal mengambil data stok dari provider."
            
    except Exception as e:
        logger.error(f"Error getting stock: {e}")
        msg = f"❌ Gagal mengambil data stok: {str(e)}"

    keyboard = [[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(msg, reply_markup=reply_markup)

async def approve_topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin yang boleh approve topup.")
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /approve_topup <id>")
        return
    request_id = context.args[0]
    result = database.approve_topup_request(request_id, admin_id=user_id)
    if result:
        await update.message.reply_text(f"✅ Topup request #{request_id} berhasil diapprove dan saldo user sudah bertambah.")
    else:
        await update.message.reply_text(f"❌ Gagal approve request #{request_id}.")

async def cancel_topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin yang boleh cancel/reject topup.")
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /cancel_topup <id>")
        return
    request_id = context.args[0]
    result = database.reject_topup_request(request_id, admin_id=user_id)
    if result:
        await update.message.reply_text(f"✅ Topup request #{request_id} berhasil dibatalkan/reject.")
    else:
        await update.message.reply_text(f"❌ Gagal cancel/reject request #{request_id}.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Basic command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stock", stock_command))
    application.add_handler(CommandHandler("admin", admin_handler.admin_menu))
    
    # Conversation handlers
    application.add_handler(order_handler.get_conversation_handler())
    application.add_handler(topup_conv_handler)
    
    # Admin command handlers
    application.add_handler(CommandHandler("approve_topup", approve_topup_command))
    application.add_handler(CommandHandler("cancel_topup", cancel_topup_command))
    
    # Menu callback handler - pattern yang lebih sederhana
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    
    # Admin callback handlers - pastikan pattern tidak overlap
    application.add_handler(CallbackQueryHandler(admin_handler.admin_callback_handler, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(admin_handler.admin_back_handler, pattern="^admin_back$"))
    
    # Admin conversation handler
    application.add_handler(admin_handler.edit_produk_conv_handler)
    
    # Other admin command handlers
    application.add_handler(admin_handler.broadcast_handler)
    application.add_handler(admin_handler.cek_user_handler)
    application.add_handler(admin_handler.jadikan_admin_handler)
    application.add_handler(admin_handler.topup_list_handler)
    
    application.add_error_handler(error_handler)
    logger.info("🤖 Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
