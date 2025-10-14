import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = config.BOT_TOKEN

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👑 ADMIN PANEL", callback_data="menu_admin")],
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="menu_order")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Test Bot - Pilih menu:", reply_markup=reply_markup)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "menu_admin":
        # Test langsung membuat menu admin
        keyboard = [
            [InlineKeyboardButton("🔄 Update Produk", callback_data="admin_update")],
            [InlineKeyboardButton("📋 List Produk", callback_data="admin_list_produk")],
            [InlineKeyboardButton("✏️ Edit Produk", callback_data="admin_edit_produk")],
            [InlineKeyboardButton("💳 Kelola Topup", callback_data="admin_topup")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "👑 **MENU ADMIN**\n\nPilih fitur admin:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    elif query.data == "menu_main":
        await start(update, context)

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.run_polling()

if __name__ == '__main__':
    main()
