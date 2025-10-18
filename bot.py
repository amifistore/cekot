import logging
import sys
import os
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
from topup_handler import (
    topup_conv_handler, 
    show_topup_menu, 
    show_manage_topup,
    handle_topup_manual,
    handle_topup_history
)
import stok_handler

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = config.BOT_TOKEN
ADMIN_IDS = set(str(admin_id) for admin_id in getattr(config, "ADMIN_TELEGRAM_IDS", []))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start"""
    try:
        user = update.message.from_user
        saldo = 0
        
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception as e:
            logger.error(f"Error getting user saldo: {e}")
            saldo = 0
        
        keyboard = [
            [InlineKeyboardButton("ðŸ›’ BELI PRODUK", callback_data="menu_order")],
            [InlineKeyboardButton("ðŸ’³ CEK SALDO", callback_data="menu_saldo")],
            [InlineKeyboardButton("ðŸ“Š CEK STOK", callback_data="menu_stock")],
            [InlineKeyboardButton("ðŸ“ž BANTUAN", callback_data="menu_help")],
            [InlineKeyboardButton("ðŸ’¸ TOP UP SALDO", callback_data="menu_topup")]
        ]
        
        if str(user.id) in ADMIN_IDS:
            keyboard.append([InlineKeyboardButton("ðŸ‘‘ ADMIN PANEL", callback_data="menu_admin")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"ðŸ¤– **Selamat Datang!**\n\n"
            f"Halo {user.full_name}!\n"
            f"ðŸ’° **Saldo Anda:** Rp {saldo:,.0f}\n\n"
            f"Pilih menu di bawah untuk mulai berbelanja.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("âŒ Terjadi error. Silakan coba lagi.")

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler utama untuk menu callback"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    logger.info(f"Menu callback received: {data}")
    
    try:
        if data == "menu_main":
            await show_main_menu(update, context)
        elif data == "menu_saldo":
            await show_saldo_menu(update, context)  # Fungsi ini ada di sini
        elif data == "menu_help":
            await show_help_menu(update, context)
        elif data == "menu_stock":
            await stok_handler.stock_akrab_callback(update, context)
        elif data == "menu_topup":
            await show_topup_menu(update, context)
        elif data == "menu_admin":
            await admin_handler.admin_menu(update, context)
        elif data == "menu_order":
            await order_handler.menu_handler(update, context)
        else:
            await query.message.reply_text("âŒ Menu tidak dikenali.")
            
    except Exception as e:
        logger.error(f"Error in menu_handler for {data}: {e}")
        await query.message.reply_text("âŒ Terjadi error. Silakan coba lagi.")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu utama"""
    query = update.callback_query
    user = query.from_user
    saldo = 0
    
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        saldo = 0
    
    keyboard = [
        [InlineKeyboardButton("ðŸ›’ BELI PRODUK", callback_data="menu_order")],
        [InlineKeyboardButton("ðŸ’³ CEK SALDO", callback_data="menu_saldo")],
        [InlineKeyboardButton("ðŸ“Š CEK STOK", callback_data="menu_stock")],
        [InlineKeyboardButton("ðŸ“ž BANTUAN", callback_data="menu_help")],
        [InlineKeyboardButton("ðŸ’¸ TOP UP SALDO", callback_data="menu_topup")]
    ]
    
    if str(user.id) in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("ðŸ‘‘ ADMIN PANEL", callback_data="menu_admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"ðŸ  **MENU UTAMA**\n\n"
        f"Halo {user.full_name}!\n"
        f"ðŸ’° **Saldo Anda:** Rp {saldo:,.0f}\n\n"
        f"Pilih menu di bawah:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_saldo_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu saldo"""
    query = update.callback_query
    user = query.from_user
    saldo = 0
    
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        saldo = 0
    
    keyboard = [
        [InlineKeyboardButton("ðŸ’¸ TOP UP SALDO", callback_data="menu_topup")],
        [InlineKeyboardButton("ðŸ  MENU UTAMA", callback_data="menu_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"ðŸ’° **SALDO ANDA**\n\n"
        f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
        f"Gunakan menu Top Up untuk menambah saldo.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu bantuan"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("ðŸ  MENU UTAMA", callback_data="menu_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "ðŸ“ž **BANTUAN**\n\n"
        "Untuk bantuan, silakan hubungi admin.\n"
        "Kami siap membantu 24/7.\n\n"
        "**Fitur Bot:**\n"
        "â€¢ ðŸ›’ Beli Produk\n"
        "â€¢ ðŸ’³ Top Up Saldo\n" 
        "â€¢ ðŸ“Š Cek Stok\n"
        "â€¢ ðŸ“ž Bantuan",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"Update {update} caused error {context.error}", exc_info=True)

def main():
    """Main function untuk menjalankan bot"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        logger.info("ðŸ¤– Starting bot dengan sistem menu terintegrasi...")
        
        application.add_handler(topup_conv_handler)
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("stock", stok_handler.stock_command))
        application.add_handler(CommandHandler("saldo", show_saldo_menu))  # Pastikan ini ada
        application.add_handler(CommandHandler("help", show_help_menu))
        
        if hasattr(admin_handler, 'admin_menu'):
            application.add_handler(CommandHandler("admin", admin_handler.admin_menu))
        if hasattr(admin_handler, 'approve_topup_command'):
            application.add_handler(CommandHandler("approve_topup", admin_handler.approve_topup_command))
        if hasattr(admin_handler, 'cancel_topup_command'):
            application.add_handler(CommandHandler("cancel_topup", admin_handler.cancel_topup_command))
        
        application.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu_"))
        application.add_handler(CallbackQueryHandler(show_manage_topup, pattern="^manage_topup$"))
        application.add_handler(CallbackQueryHandler(handle_topup_manual, pattern="^topup_manual$"))
        application.add_handler(CallbackQueryHandler(handle_topup_history, pattern="^topup_history$"))
        application.add_handler(CallbackQueryHandler(admin_handler.admin_callback_handler, pattern="^admin_"))
        
        if hasattr(order_handler, 'get_conversation_handler'):
            application.add_handler(order_handler.get_conversation_handler())
        
        application.add_error_handler(error_handler)
        
        logger.info("âœ… Bot berhasil dimulai!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Gagal memulai bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
