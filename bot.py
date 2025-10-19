# main.py - Complete Bot Application
import logging
import sys
import asyncio
import random
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
from database import db

# ==================== LOGGING SETUP ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ==================== START & HELP COMMANDS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start - Welcome message dengan menu"""
    try:
        user = update.message.from_user
        user_data = db.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = db.get_user_balance(str(user.id))
        
        # Get user statistics
        user_stats = db.get_user_stats(str(user.id))
        total_orders = user_stats.get('successful_orders', 0)
        total_spent = user_stats.get('total_spent', 0)
        
        keyboard = [
            [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="menu_order")],
            [InlineKeyboardButton("💰 CEK SALDO", callback_data="menu_saldo")],
            [InlineKeyboardButton("📊 CEK STOK", callback_data="stock_menu")],
            [InlineKeyboardButton("💳 TOP UP SALDO", callback_data="menu_topup")],
            [InlineKeyboardButton("📜 RIWAYAT", callback_data="order_history")],
            [InlineKeyboardButton("❓ BANTUAN", callback_data="menu_help")]
        ]
        
        # Add admin button jika user adalah admin
        if str(user.id) in [str(admin_id) for admin_id in config.ADMIN_TELEGRAM_IDS]:
            keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="menu_admin")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_message = f"""
👋 **Selamat Datang di {config.BOT_NAME}!**

🆔 **User:** {user.full_name}
💼 **Username:** @{user.username if user.username else 'Tidak ada'}
💰 **Saldo:** Rp {saldo:,.0f}

📊 **Statistik Anda:**
• 🛒 Total Pesanan: {total_orders}
• 💰 Total Belanja: Rp {total_spent:,.0f}
• 📅 Member sejak: {user_data.get('registered_at', 'Baru saja')[:10]}

✨ **Fitur Bot:**
• 🛒 Beli produk pulsa, data, listrik, game, dll
• 💳 Top up saldo dengan QRIS/transfer bank  
• 📊 Cek stok produk real-time
• 📜 Lihat riwayat transaksi
• 👑 Admin panel (untuk admin)

Pilih menu di bawah untuk mulai:
"""
        
        await update.message.reply_text(
            welcome_message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text(
            "❌ Terjadi error saat memulai bot. Silakan coba lagi atau hubungi admin."
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /help"""
    help_text = f"""
🤖 **{config.BOT_NAME} - BANTUAN**

**📋 DAFTAR PERINTAH:**
• /start - Memulai bot dan menampilkan menu
• /help - Menampilkan pesan bantuan ini  
• /saldo - Cek saldo Anda
• /topup - Top up saldo
• /order - Beli produk
• /stock - Cek stok produk
• /history - Lihat riwayat pesanan

**🛒 CARA BELANJA:**
1. Pilih menu **BELI PRODUK**
2. Pilih kategori produk
3. Pilih produk yang diinginkan
4. Masukkan data yang diminta (nomor HP, dll)
5. Konfirmasi pesanan
6. Tunggu proses selesai

**💳 CARA TOP UP:**
1. Pilih menu **TOP UP SALDO**
2. Masukkan nominal top up
3. Pilih metode pembayaran (QRIS/Transfer)
4. Lakukan pembayaran
5. Upload bukti transfer
6. Tunggu konfirmasi admin

**📞 BANTUAN:**
Jika mengalami kendala, silakan hubungi admin.

**⚠️ PENTING:**
• Simpan bukti transaksi
• Cek saldo sebelum bertransaksi
• Pastikan data yang dimasukkan benar
"""
    
    keyboard = [
        [InlineKeyboardButton("🛒 Beli Produk", callback_data="menu_order")],
        [InlineKeyboardButton("💳 Top Up", callback_data="menu_topup")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(help_text, reply_markup=reply_markup)

# ==================== MAIN MENU HANDLERS ====================
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main menu handler untuk semua callback"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    logger.info(f"Menu callback: {data} from user {user.id}")
    
    try:
        # Routing berdasarkan callback data
        if data == "menu_main":
            await show_main_menu(update, context)
        elif data == "menu_saldo":
            await show_saldo_menu(update, context)
        elif data == "menu_help":
            await show_help_menu(update, context)
        elif data == "menu_order":
            await show_feature_coming_soon(update, context, "🛒 Fitur Beli Produk")
        elif data == "menu_topup":
            await show_feature_coming_soon(update, context, "💳 Fitur Top Up")
        elif data == "menu_admin":
            await show_feature_coming_soon(update, context, "👑 Panel Admin")
        elif data == "stock_menu":
            await show_feature_coming_soon(update, context, "📊 Fitur Cek Stok")
        elif data == "order_history":
            await show_feature_coming_soon(update, context, "📜 Fitur Riwayat")
        else:
            logger.warning(f"Unknown menu callback: {data}")
            await query.message.reply_text("❌ Menu tidak dikenali.")
            
    except Exception as e:
        logger.error(f"Error in menu_handler for {data}: {e}")
        error_msg = "❌ Terjadi error. Silakan coba lagi."
        try:
            await query.edit_message_text(error_msg)
        except:
            await query.message.reply_text(error_msg)

async def show_feature_coming_soon(update: Update, context: ContextTypes.DEFAULT_TYPE, feature_name: str):
    """Show coming soon message for features not yet implemented"""
    query = update.callback_query
    
    message = f"""
{feature_name}

⏳ **Fitur Dalam Pengembangan**

Fitur ini sedang dalam tahap pengembangan dan akan segera hadir.

**Fitur yang akan datang:**
• Proses belanja yang mudah dan cepat
• Top up saldo dengan berbagai metode
• Panel admin untuk management
• Cek stok real-time
• Riwayat transaksi lengkap

Tetap pantau update terbaru! 🚀
"""
    
    keyboard = [
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")],
        [InlineKeyboardButton("❓ Bantuan", callback_data="menu_help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu utama"""
    query = update.callback_query
    user = query.from_user
    
    try:
        user_data = db.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = db.get_user_balance(str(user.id))
        
        # Get user statistics
        user_stats = db.get_user_stats(str(user.id))
        total_orders = user_stats.get('successful_orders', 0)
        
        keyboard = [
            [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="menu_order")],
            [InlineKeyboardButton("💰 CEK SALDO", callback_data="menu_saldo")],
            [InlineKeyboardButton("📊 CEK STOK", callback_data="stock_menu")],
            [InlineKeyboardButton("💳 TOP UP SALDO", callback_data="menu_topup")],
            [InlineKeyboardButton("📜 RIWAYAT", callback_data="order_history")],
            [InlineKeyboardButton("❓ BANTUAN", callback_data="menu_help")]
        ]
        
        # Add admin button jika user adalah admin
        if str(user.id) in [str(admin_id) for admin_id in config.ADMIN_TELEGRAM_IDS]:
            keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="menu_admin")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🏠 **MENU UTAMA**\n\n"
            f"👋 Halo, {user.full_name}!\n\n"
            f"💳 **Saldo:** Rp {saldo:,.0f}\n"
            f"🛒 **Total Pesanan:** {total_orders}\n\n"
            f"Pilih menu di bawah:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in show_main_menu: {e}")
        await query.edit_message_text("❌ Terjadi error. Silakan coba lagi.")

async def show_saldo_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu saldo dengan informasi lengkap"""
    query = update.callback_query
    user = query.from_user
    
    try:
        user_data = db.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = db.get_user_balance(str(user.id))
        
        # Get user statistics
        user_stats = db.get_user_stats(str(user.id))
        total_orders = user_stats.get('successful_orders', 0)
        total_spent = user_stats.get('total_spent', 0)
        total_topups = user_stats.get('successful_topups', 0)
        
        # Get pending topups
        user_transactions = db.get_user_transactions(str(user.id), limit=5)
        pending_topups = [t for t in user_transactions if t.get('status') == 'pending' and t.get('type') == 'topup']
        
        message = (
            f"💳 **INFORMASI SALDO**\n\n"
            f"👤 **User:** {user.full_name}\n"
            f"💰 **Saldo Saat Ini:** Rp {saldo:,.0f}\n\n"
            f"📊 **Statistik:**\n"
            f"• 🛒 Total Pesanan: {total_orders}\n"
            f"• 💰 Total Belanja: Rp {total_spent:,.0f}\n"
            f"• 💳 Total Topup: {total_topups}\n"
            f"• ⏳ Topup Pending: {len(pending_topups)}\n"
        )
        
        if pending_topups:
            message += f"\n⏳ **Topup Pending:**\n"
            for topup in pending_topups[:3]:
                message += f"• Rp {topup.get('amount', 0):,} - Menunggu\n"
            if len(pending_topups) > 3:
                message += f"• ... dan {len(pending_topups) - 3} lainnya\n"
        
        keyboard = [
            [InlineKeyboardButton("💳 TOP UP SALDO", callback_data="menu_topup")],
            [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in show_saldo_menu: {e}")
        await query.edit_message_text("❌ Terjadi error. Silakan coba lagi.")

async def show_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu bantuan"""
    query = update.callback_query
    
    help_text = f"""
❓ **BANTUAN & SUPPORT - {config.BOT_NAME}**

**📞 KONTAK ADMIN:**
• Support tersedia 24/7
• Respon cepat dalam beberapa menit
• Bantuan teknis dan informasi

**🔧 TROUBLESHOOTING:**
• **Pesanan gagal?** - Cek saldo dan data yang dimasukkan
• **Topup lama?** - Proses verifikasi 1-10 menit
• **Bot tidak respons?** - Restart bot dengan /start

**💡 TIPS:**
• Simpan bukti transaksi
• Cek saldo sebelum bertransaksi  
• Pastikan data yang dimasukkan benar
• Gunakan menu riwayat untuk tracking

**🚀 FITUR UNGGULAN:**
• 🛒 Belanja mudah & cepat
• 💳 Topup instan dengan QRIS
• 📊 Stok real-time
• 📜 Riwayat lengkap
• 👑 Admin panel
"""
    
    keyboard = [
        [InlineKeyboardButton("🛒 Beli Produk", callback_data="menu_order")],
        [InlineKeyboardButton("💳 Top Up", callback_data="menu_topup")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(help_text, reply_markup=reply_markup)

# ==================== UTILITY COMMANDS ====================
async def saldo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /saldo"""
    user = update.message.from_user
    
    try:
        user_data = db.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = db.get_user_balance(str(user.id))
        
        # Get user statistics
        user_stats = db.get_user_stats(str(user.id))
        total_orders = user_stats.get('successful_orders', 0)
        total_spent = user_stats.get('total_spent', 0)
        
        message = (
            f"💳 **INFORMASI SALDO**\n\n"
            f"👤 **User:** {user.full_name}\n"
            f"💰 **Saldo Saat Ini:** Rp {saldo:,.0f}\n\n"
            f"📊 **Statistik:**\n"
            f"• 🛒 Total Pesanan: {total_orders}\n"
            f"• 💰 Total Belanja: Rp {total_spent:,.0f}\n"
        )
        
        keyboard = [
            [InlineKeyboardButton("💳 TOP UP SALDO", callback_data="menu_topup")],
            [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="menu_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in saldo_command: {e}")
        await update.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /history"""
    await show_feature_coming_soon_message(update, context, "📜 Fitur Riwayat")

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /stock"""
    await show_feature_coming_soon_message(update, context, "📊 Fitur Cek Stok")

async def show_feature_coming_soon_message(update: Update, context: ContextTypes.DEFAULT_TYPE, feature_name: str):
    """Show coming soon message for command-based features"""
    message = f"""
{feature_name}

⏳ **Fitur Dalam Pengembangan**

Fitur ini sedang dalam tahap pengembangan dan akan segera hadir.

Gunakan menu di bawah untuk navigasi:
"""
    
    keyboard = [
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")],
        [InlineKeyboardButton("❓ Bantuan", callback_data="menu_help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, reply_markup=reply_markup)

# ==================== MESSAGE HANDLERS ====================
async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pesan text biasa yang bukan command"""
    message_text = update.message.text
    
    # Ignore messages that are likely part of conversations
    if (update.message.reply_to_message or 
        context.user_data.get('in_conversation')):
        return
    
    # Respons untuk pesan random
    responses = [
        "Halo! Gunakan menu atau command untuk berinteraksi dengan bot 🤖",
        "Silakan pilih menu di keyboard atau ketik /help untuk bantuan 📋",
        "Butuh bantuan? Ketik /help atau gunakan menu bantuan ❓",
        "Gunakan command /start untuk menampilkan menu utama 🏠"
    ]
    
    response = random.choice(responses)
    
    keyboard = [
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")],
        [InlineKeyboardButton("❓ Bantuan", callback_data="menu_help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(response, reply_markup=reply_markup)

# ==================== ERROR HANDLER ====================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler untuk menangani semua error"""
    try:
        # Log the error
        logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
        
        # Notify user about the error
        if update and hasattr(update, 'effective_chat'):
            error_message = """
❌ **Terjadi Error**

Maaf, terjadi error tak terduga. Tim developer telah diberitahu.

**Yang bisa dilakukan:**
1. Coba lagi dalam beberapa saat
2. Gunakan command /start untuk restart bot
3. Hubungi admin jika error berlanjut

Terima kasih atas pengertiannya! 🙏
"""
            keyboard = [
                [InlineKeyboardButton("🔄 Restart Bot", callback_data="menu_main")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=error_message,
                reply_markup=reply_markup
            )
        
    except Exception as e:
        logger.error(f"Error in error_handler: {e}")

# ==================== SYSTEM HEALTH CHECK ====================
async def health_check():
    """Periodic health check untuk memastikan bot berjalan normal"""
    try:
        # Check database connection
        stats = db.get_system_stats()
        logger.info(f"🤖 Bot Health Check - Users: {stats['total_users']}, Orders: {stats['total_orders']}")
        
        # Log system status
        db.add_system_log('INFO', 'Health Check', f"Bot running - Users: {stats['total_users']}")
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        db.add_system_log('ERROR', 'Health Check Failed', str(e))

# ==================== BOT INITIALIZATION ====================
def setup_handlers(application: Application):
    """Setup semua handlers untuk bot"""
    
    # Basic commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("saldo", saldo_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("stock", stock_command))
    
    # Callback query handlers
    application.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu_"))
    application.add_handler(CallbackQueryHandler(show_saldo_menu, pattern="^menu_saldo$"))
    
    # Fallback message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
    
    # Error handler
    application.add_error_handler(error_handler)

def main():
    """Main function untuk menjalankan bot"""
    try:
        # Validate configuration
        if not hasattr(config, 'validate_config') or config.validate_config():
            logger.info("✅ Configuration validated successfully")
        else:
            logger.error("❌ Configuration validation failed")
            sys.exit(1)
        
        # Initialize database
        db.init_database()
        logger.info("✅ Database initialized successfully")
        
        # Create application
        application = Application.builder().token(config.BOT_TOKEN).build()
        
        logger.info("🤖 Starting Telegram Bot...")
        logger.info(f"📊 Bot Name: {config.BOT_NAME}")
        logger.info(f"👑 Admin IDs: {config.ADMIN_TELEGRAM_IDS}")
        
        # Setup semua handlers
        setup_handlers(application)
        
        # Run health check pertama
        asyncio.run(health_check())
        
        logger.info("✅ Bot started successfully!")
        logger.info("📱 Bot is now running and listening for messages...")
        
        # Start polling
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
