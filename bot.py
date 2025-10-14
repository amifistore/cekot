import logging
import sys
import os
import socket
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
from topup_handler import topup_conv_handler, show_topup_menu, show_manage_topup
import stok_handler

# ===== MULTI-INSTANCE PREVENTION =====
def check_port_in_use(port=8443):
    """Check if port is already in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def prevent_multiple_instances():
    """Prevent multiple bot instances from running"""
    try:
        # Check if another instance is already running
        if check_port_in_use(8443):
            logger.error("Another bot instance is already running!")
            sys.exit(1)
            
        # Create a lock file
        lock_file = "bot_instance.lock"
        if os.path.exists(lock_file):
            logger.error("Lock file exists! Another instance may be running.")
            # Remove stale lock file if process isn't running
            try:
                os.remove(lock_file)
            except:
                pass
        
        with open(lock_file, 'w') as f:
            f.write(str(os.getpid()))
            
    except Exception as e:
        logger.error(f"Error in instance prevention: {e}")

def cleanup_lock_file():
    """Clean up lock file on exit"""
    try:
        lock_file = "bot_instance.lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)
    except:
        pass

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = config.BOT_TOKEN
ADMIN_IDS = set(str(admin_id) for admin_id in getattr(config, "ADMIN_TELEGRAM_IDS", []))

# Panggil prevention di awal
prevent_multiple_instances()

# ... (kode handler lainnya tetap sama) ...

def main():
    """Main function untuk menjalankan bot"""
    try:
        # Pastikan hanya satu instance yang berjalan
        prevent_multiple_instances()
        
        application = Application.builder().token(BOT_TOKEN).build()
        
        logger.info("🤖 Starting bot with integrated menu system...")
        logger.info("✅ Single instance check passed!")
        
        # Basic command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("saldo", saldo_command))
        application.add_handler(CommandHandler("stock", stok_handler.stock_command))
        
        # Admin command handlers
        if hasattr(admin_handler, 'admin_menu'):
            application.add_handler(CommandHandler("admin", admin_handler.admin_menu))
        
        # Conversation handlers
        if hasattr(order_handler, 'get_conversation_handler'):
            application.add_handler(order_handler.get_conversation_handler())
        
        # Topup conversation handler
        application.add_handler(topup_conv_handler)
        
        # Admin command handlers
        if hasattr(admin_handler, 'approve_topup_command'):
            application.add_handler(CommandHandler("approve_topup", admin_handler.approve_topup_command))
        if hasattr(admin_handler, 'cancel_topup_command'):
            application.add_handler(CommandHandler("cancel_topup", admin_handler.cancel_topup_command))
        
        # Menu callback handlers
        application.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu_"))
        
        # Admin callback handlers
        application.add_handler(CallbackQueryHandler(admin_handler.admin_callback_handler, pattern="^admin_"))
        application.add_handler(CallbackQueryHandler(admin_handler.edit_produk_menu_handler, pattern="^edit_"))
        application.add_handler(CallbackQueryHandler(admin_handler.select_product_handler, pattern="^select_product:"))
        
        # Topup callback handlers
        application.add_handler(CallbackQueryHandler(show_manage_topup, pattern="^manage_topup$"))
        
        # Order callback handler
        application.add_handler(CallbackQueryHandler(order_handler.menu_handler, pattern="^order_"))
        
        # Global error handler
        application.add_error_handler(error_handler)
        
        logger.info("✅ Bot started successfully!")
        
        # Jalankan bot dengan error handling
        try:
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True  # Bersihkan update yang tertunda
            )
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Bot polling error: {e}")
        finally:
            cleanup_lock_file()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        cleanup_lock_file()
        sys.exit(1)

if __name__ == '__main__':
    main()
