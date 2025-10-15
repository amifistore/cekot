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

# Setup logging dengan level DEBUG
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Ubah ke DEBUG untuk detail lebih
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
            f"🤖 **Selamat Datang!**\n\n"
            f"Halo {user.full_name}!\n"
            f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
            f"Pilih menu di bawah untuk mulai berbelanja.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler utama untuk menu callback"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    logger.info(f"🔧 [MENU_HANDLER] Menu callback received: {data}")
    
    try:
        if data == "menu_main":
            await show_main_menu(update, context)
        elif data == "menu_saldo":
            await show_saldo_menu(update, context)
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
            await query.message.reply_text("❌ Menu tidak dikenali.")
            
    except Exception as e:
        logger.error(f"Error in menu_handler for {data}: {e}")
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

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
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="menu_order")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="menu_saldo")],
        [InlineKeyboardButton("📊 CEK STOK", callback_data="menu_stock")],
        [InlineKeyboardButton("📞 BANTUAN", callback_data="menu_help")],
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="menu_topup")]
    ]
    
    if str(user.id) in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="menu_admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            f"🏠 **MENU UTAMA**\n\n"
            f"Halo {user.full_name}!\n"
            f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
            f"Pilih menu di bawah:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"Could not edit message, sending new: {e}")
        await query.message.reply_text(
            f"🏠 **MENU UTAMA**\n\n"
            f"Halo {user.full_name}!\n"
            f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
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
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="menu_topup")],
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            f"💰 **SALDO ANDA**\n\n"
            f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
            f"Gunakan menu Top Up untuk menambah saldo.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"Could not edit message, sending new: {e}")
        await query.message.reply_text(
            f"💰 **SALDO ANDA**\n\n"
            f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
            f"Gunakan menu Top Up untuk menambah saldo.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def show_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu bantuan"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            "📞 **BANTUAN**\n\n"
            "Untuk bantuan, silakan hubungi admin.\n"
            "Kami siap membantu 24/7.\n\n"
            "**Fitur Bot:**\n"
            "• 🛒 Beli Produk\n"
            "• 💳 Top Up Saldo\n" 
            "• 📊 Cek Stok\n"
            "• 📞 Bantuan",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"Could not edit message, sending new: {e}")
        await query.message.reply_text(
            "📞 **BANTUAN**\n\n"
            "Untuk bantuan, silakan hubungi admin.\n"
            "Kami siap membantu 24/7.\n\n"
            "**Fitur Bot:**\n"
            "• 🛒 Beli Produk\n"
            "• 💳 Top Up Saldo\n" 
            "• 📊 Cek Stok\n"
            "• 📞 Bantuan",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def saldo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /saldo"""
    user = update.message.from_user
    saldo = 0
    
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        saldo = 0
    
    keyboard = [
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="menu_topup")],
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"💰 **SALDO ANDA**\n\n"
        f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
        f"Gunakan menu Top Up untuk menambah saldo.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /help"""
    keyboard = [
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📞 **BANTUAN**\n\n"
        "Untuk bantuan, silakan hubungi admin.\n"
        "Kami siap membantu 24/7.\n\n"
        "**Fitur Bot:**\n"
        "• 🛒 Beli Produk\n"
        "• 💳 Top Up Saldo\n" 
        "• 📊 Cek Stok\n"
        "• 📞 Bantuan",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk pesan yang tidak dikenal - FIXED VERSION"""
    logger.debug(f"🔧 [UNKNOWN_MESSAGE] Received unknown text: '{update.message.text}'")
    
    # JANGAN lakukan apa-apa, biarkan conversation handler yang menangani
    # Pesan ini akan diabaikan dan conversation handler akan menangkapnya
    return

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"❌ [ERROR_HANDLER] Update {update} caused error {context.error}", exc_info=True)
    
    # Coba untuk memberi tahu user tentang error
    if isinstance(update, Update):
        if update.message:
            await update.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        elif update.callback_query:
            await update.callback_query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

def main():
    """Main function untuk menjalankan bot - DEBUG VERSION"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        logger.info("🤖 Starting bot dengan sistem menu terintegrasi...")
        
        # ========== URUTAN HANDLER YANG BENAR ==========
        
        # 1. Conversation handlers PERTAMA (yang paling penting)
        logger.info("🔧 [MAIN] Registering conversation handlers FIRST...")
        application.add_handler(topup_conv_handler)
        logger.info("✅ [MAIN] topup_conv_handler registered")
        
        # 2. Order conversation handler jika ada
        if hasattr(order_handler, 'get_conversation_handler'):
            order_conv_handler = order_handler.get_conversation_handler()
            if order_conv_handler:
                logger.info("🔧 [MAIN] Registering order conversation handler...")
                application.add_handler(order_conv_handler)
                logger.info("✅ [MAIN] order_conv_handler registered")
        
        # 3. Command handlers
        logger.info("🔧 [MAIN] Registering command handlers...")
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("stock", stok_handler.stock_command))
        application.add_handler(CommandHandler("saldo", saldo_command))
        application.add_handler(CommandHandler("help", help_command))
        logger.info("✅ [MAIN] Command handlers registered")
        
        # 4. Admin command handlers
        if hasattr(admin_handler, 'admin_menu'):
            application.add_handler(CommandHandler("admin", admin_handler.admin_menu))
        if hasattr(admin_handler, 'approve_topup_command'):
            application.add_handler(CommandHandler("approve_topup", admin_handler.approve_topup_command))
        if hasattr(admin_handler, 'cancel_topup_command'):
            application.add_handler(CommandHandler("cancel_topup", admin_handler.cancel_topup_command))
        
        # 5. Menu callback handlers - pattern spesifik
        logger.info("🔧 [MAIN] Registering menu callback handlers...")
        application.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu_"))
        logger.info("✅ [MAIN] menu_ callback handler registered")
        
        # 6. Topup callback handlers untuk menu
        application.add_handler(CallbackQueryHandler(show_topup_menu, pattern="^menu_topup$"))
        application.add_handler(CallbackQueryHandler(show_manage_topup, pattern="^manage_topup$"))
        application.add_handler(CallbackQueryHandler(handle_topup_history, pattern="^topup_history$"))
        logger.info("✅ [MAIN] Topup menu callback handlers registered")
        
        # 7. Admin callback handlers
        application.add_handler(CallbackQueryHandler(admin_handler.admin_callback_handler, pattern="^admin_"))
        
        # 8. Order callback handler jika ada
        if hasattr(order_handler, 'callback_handler'):
            application.add_handler(CallbackQueryHandler(order_handler.callback_handler, pattern="^order_"))
        
        # 9. Stock callback handler jika ada
        if hasattr(stok_handler, 'callback_handler'):
            application.add_handler(CallbackQueryHandler(stok_handler.callback_handler, pattern="^stock_"))
        
        # 10. Fallback handler untuk pesan teks yang tidak dikenali - HARUS TERAKHIR
        logger.info("🔧 [MAIN] Registering fallback handler LAST...")
        # HANYA tangkap pesan yang BUKAN angka (untuk menghindari conflict dengan nominal topup)
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^\d+$'),
            unknown_message
        ))
        logger.info("✅ [MAIN] Fallback handler registered")
        
        # 11. Error handler
        application.add_error_handler(error_handler)
        
        # Debug: Print semua handler yang terdaftar
        logger.info("=== 🔍 REGISTERED HANDLERS DEBUG ===")
        for i, handler in enumerate(application.handlers[0]):
            handler_type = type(handler).__name__
            logger.info(f"Handler {i}: {handler_type}")
            
            if isinstance(handler, ConversationHandler):
                logger.info(f"  - ConversationHandler with {len(handler.entry_points)} entry points")
                for ep in handler.entry_points:
                    logger.info(f"    * {ep}")
                logger.info(f"  - States: {len(handler.states)}")
                for state, handlers in handler.states.items():
                    logger.info(f"    * State {state}: {len(handlers)} handlers")
        
        logger.info("=== ✅ END HANDLERS DEBUG ===")
        
        logger.info("✅ Bot berhasil dimulai!")
        logger.info("📱 Bot siap menerima pesan...")
        
        # Jalankan bot
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.error(f"Gagal memulai bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
