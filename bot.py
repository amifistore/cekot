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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = config.BOT_TOKEN
ADMIN_IDS = set(str(i) for i in getattr(config, "ADMIN_TELEGRAM_IDS", []))

# Helper anti error "Message is not modified"
async def safe_edit_message_text(callback_query, *args, **kwargs):
    try:
        await callback_query.edit_message_text(*args, **kwargs)
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e):
            return
        raise

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception:
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

# Handler untuk menu utama
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "menu_main":
        # Recreate start menu for callback
        user = query.from_user
        saldo = 0
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception:
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
        
        await safe_edit_message_text(
            query,
            f"🤖 Selamat Datang!\n\nHalo {user.full_name}!\n💰 Saldo Anda: Rp {saldo:,.0f}\nPilih menu di bawah.",
            reply_markup=reply_markup
        )
        
    elif data == "menu_topup":
        await safe_edit_message_text(
            query,
            "💸 *TOP UP SALDO*\n\nUntuk top up saldo, ketik perintah /topup dan ikuti instruksi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
            ]),
            parse_mode="Markdown"
        )
    elif data == "menu_saldo":
        user = query.from_user
        saldo = 0
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception:
            saldo = 0
            
        await safe_edit_message_text(
            query,
            f"💰 *SALDO ANDA*\n\nSaldo saat ini: Rp {saldo:,.0f}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
            ]),
            parse_mode="Markdown"
        )
    elif data == "menu_help":
        await safe_edit_message_text(
            query,
            "📞 *BANTUAN*\n\nJika Anda membutuhkan bantuan, silakan hubungi admin.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
            ]),
            parse_mode="Markdown"
        )
    elif data == "menu_order":
        # Handle order menu - panggil order handler
        from order_handler import order_start
        await order_start(update, context)
    elif data == "menu_stock":
        # Handle stock menu - langsung di sini tanpa file terpisah
        await stock_callback(update, context)

# Handler untuk cek stok
async def stock_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        msg_func = query.edit_message_text
    else:
        msg_func = update.message.reply_text

    try:
        # Cek stok dari provider
        api_key = getattr(config, 'API_KEY_PROVIDER', '')
        url = f"https://panel.khfy-store.com/api_v3/cek_stock_akrab"
        params = {}
        if api_key:
            params['api_key'] = api_key
            
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                resp.raise_for_status()
                data = await resp.json()
        
        if not data.get("ok", False):
            msg = "❌ Gagal mengambil data stok dari provider."
        else:
            stocks = data.get("data", {})
            if not stocks:
                msg = "📭 Tidak ada data stok yang tersedia."
            else:
                msg = "📊 **STOK PRODUK AKRAB**\n\n"
                for product_name, stock_info in stocks.items():
                    stock = stock_info.get("stock", 0)
                    status = "✅ TERSEDIA" if stock > 0 else "❌ HABIS"
                    msg += f"• **{product_name}**: {stock} pcs - {status}\n"
                msg += f"\n⏰ Terakhir diperbarui: {data.get('timestamp', 'N/A')}"
                
    except Exception as e:
        msg = f"❌ **Gagal mengambil data stok:**\n{str(e)}"

    # Keyboard untuk kembali ke menu utama
    keyboard = [[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await msg_func(
        msg,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# Handler untuk perintah /stock
async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stock_callback(update, context)

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
    
    # Add basic command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stock", stock_command))
    
    # Add conversation handlers
    application.add_handler(order_handler.get_conversation_handler())
    application.add_handler(topup_conv_handler)
    
    # Add admin command handlers
    application.add_handler(CommandHandler("approve_topup", approve_topup_command))
    application.add_handler(CommandHandler("cancel_topup", cancel_topup_command))
    
    # Add callback query handlers untuk menu user
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=r'^menu_(main|topup|saldo|help|order|stock)$'))
    
    # Add semua admin handlers dari admin_handler module
    admin_handlers = admin_handler.get_admin_handlers()
    for handler in admin_handlers:
        application.add_handler(handler)
    
    application.add_error_handler(error_handler)
    logger.info("🤖 Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
