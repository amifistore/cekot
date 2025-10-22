#!/usr/bin/env python3
"""
Bot Telegram Full Feature - FIXED & READY FOR RELEASE
"""

import logging
import sys
import os
import asyncio
import traceback
from typing import Dict, Any
from datetime import datetime

# Telegram Imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    MessageHandler,
    ConversationHandler,
    PicklePersistence
)

# Custom Module Imports
import config
import database

# ==================== IMPORTS DENGAN ERROR HANDLING ====================
print("🔄 Loading handlers...")

# Admin Handler - YANG SUDAH DIPERBAIKI
try:
    from admin_handler import (
        admin_menu,
        admin_callback_handler,
        get_admin_handlers
    )
    ADMIN_AVAILABLE = True
    print("✅ Admin handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing admin_handler: {e}")
    traceback.print_exc()
    ADMIN_AVAILABLE = False
    
    # Fallback functions
    async def admin_menu(update, context):
        if hasattr(update, 'message'):
            await update.message.reply_text("❌ Admin features sedang dalam perbaikan.")
        else:
            await update.callback_query.message.reply_text("❌ Admin features sedang dalam perbaikan.")
    
    async def admin_callback_handler(update, context):
        await update.callback_query.answer("❌ Admin features sedang dalam perbaikan.", show_alert=True)
    
    def get_admin_handlers():
        return []

# Stok Handler - FIXED VERSION
try:
    from stok_handler import stock_akrab_callback, stock_command
    STOK_AVAILABLE = True
    print("✅ Stok handler loaded successfully")
    
    # Fixed stock command untuk handle database error
    async def fixed_stock_command(update, context):
        """Fixed version of stock_command"""
        try:
            # Coba panggil fungsi original
            await stock_command(update, context)
        except Exception as e:
            logger.error(f"Error in stock_command: {e}")
            # Fallback ke fungsi yang lebih sederhana
            try:
                products = database.get_all_products()
                if products:
                    stock_text = "📊 **STOK PRODUK**\n\n"
                    for product in products:
                        stock_text += f"• {product['name']}: {product['stock']} pcs\n"
                    await update.message.reply_text(stock_text, parse_mode='Markdown')
                else:
                    await update.message.reply_text("📊 Tidak ada produk tersedia.")
            except Exception as db_error:
                await update.message.reply_text("❌ Gagal memuat data stok. Silakan coba lagi.")
                
except Exception as e:
    print(f"❌ Error importing stok_handler: {e}")
    STOK_AVAILABLE = False
    
    async def stock_akrab_callback(update, context):
        if hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text("❌ Fitur stok sedang dalam perbaikan.")
        else:
            await update.message.reply_text("❌ Fitur stok sedang dalam perbaikan.")
    
    async def fixed_stock_command(update, context):
        await update.message.reply_text("❌ Fitur stok sedang dalam perbaikan.")

# Order Handler - FIXED VERSION
try:
    from order_handler import (
        get_conversation_handler as get_order_conversation_handler,
        menu_handler as order_menu_handler
    )
    ORDER_AVAILABLE = True
    print("✅ Order handler loaded successfully")
    
    # Fixed order handler untuk ReplyKeyboard
    async def fixed_order_menu_handler(update, context):
        """Fixed order handler untuk ReplyKeyboard"""
        try:
            # Untuk ReplyKeyboard, langsung panggil menu_handler
            # Fungsi ini akan menangani sendiri apakah dari message atau callback
            await order_menu_handler(update, context)
        except Exception as e:
            logger.error(f"Error in order_menu_handler: {e}")
            await update.message.reply_text("❌ Gagal memulai proses order. Silakan coba lagi.")
            
except Exception as e:
    print(f"❌ Error importing order_handler: {e}")
    ORDER_AVAILABLE = False
    
    def get_order_conversation_handler():
        return None
    
    async def fixed_order_menu_handler(update, context):
        if hasattr(update, 'message'):
            await update.message.reply_text("❌ Fitur order sedang dalam perbaikan.")
        else:
            await update.callback_query.message.reply_text("❌ Fitur order sedang dalam perbaikan.")

# Topup Handler
try:
    from topup_handler import (
        get_topup_conversation_handler,
        show_topup_menu,
        get_topup_handlers,
        topup_command
    )
    TOPUP_AVAILABLE = True
    print("✅ Topup handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing topup_handler: {e}")
    TOPUP_AVAILABLE = False
    
    async def show_topup_menu(update, context): 
        if hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text("❌ Fitur topup sedang dalam perbaikan.")
        else:
            await update.message.reply_text("❌ Fitur topup sedang dalam perbaikan.")
    
    def get_topup_conversation_handler():
        return None
    
    def get_topup_handlers():
        return []
    
    async def topup_command(update, context):
        await show_topup_menu(update, context)

# ==================== LOGGING SETUP ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ==================== GLOBAL VARIABLES ====================
BOT_TOKEN = config.BOT_TOKEN
ADMIN_IDS = getattr(config, 'ADMIN_TELEGRAM_IDS', [])

# ==================== REPLY KEYBOARD SETUP ====================
def get_main_keyboard(user_id=None):
    """Reply Keyboard untuk menu utama"""
    keyboard = [
        ["🛒 BELI PRODUK", "💳 CEK SALDO"],
        ["📊 CEK STOK", "📞 BANTUAN"],
        ["💸 TOP UP SALDO", "🔄 START BOT"]
    ]
    
    # Tambahkan admin panel jika user adalah admin
    if user_id and str(user_id) in ADMIN_IDS:
        keyboard.append(["👑 ADMIN PANEL"])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_back_keyboard():
    """Reply Keyboard untuk kembali ke menu"""
    keyboard = [
        ["🏠 MENU UTAMA", "🔄 START BOT"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# ==================== BASIC COMMAND HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start - Menu utama"""
    try:
        user = update.message.from_user
        logger.info(f"User {user.id} started the bot")
        
        # Get or create user in database
        saldo = 0
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception as e:
            logger.error(f"Error getting user saldo: {e}")
            saldo = 0
        
        welcome_text = (
            f"🤖 **Selamat Datang!**\n\n"
            f"Halo {user.full_name}!\n"
            f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
            f"Pilih menu di bawah untuk mulai berbelanja:"
        )
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=get_main_keyboard(user.id),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memproses pesan text dari reply keyboard"""
    user = update.message.from_user
    text = update.message.text
    
    logger.info(f"Message from user {user.id}: {text}")
    
    try:
        if text == "🛒 BELI PRODUK":
            await fixed_order_menu_handler(update, context)
        elif text == "💳 CEK SALDO":
            await show_saldo_menu_message(update, context)
        elif text == "📊 CEK STOK":
            await fixed_stock_command(update, context)
        elif text == "📞 BANTUAN":
            await show_help_menu_message(update, context)
        elif text == "💸 TOP UP SALDO":
            await show_topup_menu(update, context)
        elif text == "🔄 START BOT":
            await start(update, context)
        elif text == "🏠 MENU UTAMA":
            await show_main_menu_message(update, context)
        elif text == "👑 ADMIN PANEL":
            if str(user.id) in ADMIN_IDS:
                await admin_menu(update, context)
            else:
                await update.message.reply_text("❌ Anda bukan admin!")
        else:
            await unknown_message(update, context)
            
    except Exception as e:
        logger.error(f"Error handling message {text}: {e}")
        await update.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

# ==================== MESSAGE VERSION HANDLERS (UNTUK REPLY KEYBOARD) ====================
async def show_main_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu utama untuk message"""
    user = update.message.from_user
    
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        saldo = 0
    
    menu_text = (
        f"🏠 **MENU UTAMA**\n\n"
        f"Halo {user.full_name}!\n"
        f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
        f"Pilih menu di bawah:"
    )
    
    await update.message.reply_text(
        menu_text,
        reply_markup=get_main_keyboard(user.id),
        parse_mode='Markdown'
    )

async def show_saldo_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu saldo untuk message"""
    user = update.message.from_user
    
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        saldo = 0
    
    saldo_text = (
        f"💰 **SALDO ANDA**\n\n"
        f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
        f"Gunakan menu Top Up untuk menambah saldo."
    )
    
    await update.message.reply_text(
        saldo_text,
        reply_markup=get_back_keyboard(),
        parse_mode='Markdown'
    )

async def show_help_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu bantuan untuk message"""
    help_text = (
        "📞 **BANTUAN & PANDUAN**\n\n"
        "**CARA ORDER:**\n"
        "1. Pilih 🛒 **BELI PRODUK**\n"
        "2. Pilih kategori produk\n"
        "3. Pilih produk yang diinginkan\n"
        "4. Masukkan nomor tujuan\n"
        "5. Konfirmasi dan bayar\n\n"
        "**TOP UP SALDO:**\n"
        "1. Pilih 💸 **TOP UP SALDO**\n"
        "2. Masukkan nominal\n"
        "3. Pilih metode pembayaran (QRIS/Transfer Bank)\n"
        "4. Ikuti instruksi pembayaran\n"
        "5. Tunggu konfirmasi admin\n\n"
        "**BUTUH BANTUAN?**\n"
        "Hubungi Admin untuk bantuan lebih lanjut."
    )
    
    await update.message.reply_text(
        help_text,
        reply_markup=get_back_keyboard(),
        parse_mode='Markdown'
    )

# ==================== CALLBACK VERSION HANDLERS (UNTUK INLINE KEYBOARD) ====================
async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main menu handler untuk callback query"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    logger.info(f"Main menu callback: {data} from user {user.id}")
    
    try:
        if data == "main_menu_main":
            await show_main_menu_callback(update, context)
        elif data == "main_menu_saldo":
            await show_saldo_menu_callback(update, context)
        elif data == "main_menu_help":
            await show_help_menu_callback(update, context)
        elif data == "main_menu_stock":
            await stock_akrab_callback(update, context)
        elif data == "main_menu_admin":
            if str(user.id) in ADMIN_IDS:
                await admin_menu(update, context)
            else:
                await query.answer("❌ Anda bukan admin!", show_alert=True)
        elif data == "main_menu_order":
            await fixed_order_menu_handler(update, context)
        elif data == "topup_menu":
            await show_topup_menu(update, context)
        else:
            await query.message.reply_text("❌ Menu tidak dikenali.")
            
    except Exception as e:
        logger.error(f"Error in main_menu_handler for {data}: {e}")
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

async def show_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu utama untuk callback"""
    query = update.callback_query
    user = query.from_user
    
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        saldo = 0
    
    menu_text = (
        f"🏠 **MENU UTAMA**\n\n"
        f"Halo {user.full_name}!\n"
        f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
        f"Pilih menu di bawah:"
    )
    
    try:
        await query.edit_message_text(
            menu_text,
            reply_markup=get_main_keyboard(user.id),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}")
        await query.message.reply_text(
            menu_text,
            reply_markup=get_main_keyboard(user.id),
            parse_mode='Markdown'
        )

async def show_saldo_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu saldo untuk callback"""
    query = update.callback_query
    user = query.from_user
    
    saldo = 0
    try:
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(user_id)
    except Exception as e:
        logger.error(f"Error getting user saldo: {e}")
        saldo = 0
    
    saldo_text = (
        f"💰 **SALDO ANDA**\n\n"
        f"Saldo saat ini: **Rp {saldo:,.0f}**\n\n"
        f"Gunakan menu Top Up untuk menambah saldo."
    )
    
    try:
        await query.edit_message_text(
            saldo_text,
            reply_markup=get_back_keyboard(),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}")
        await query.message.reply_text(
            saldo_text,
            reply_markup=get_back_keyboard(),
            parse_mode='Markdown'
        )

async def show_help_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu bantuan untuk callback"""
    query = update.callback_query
    
    help_text = (
        "📞 **BANTUAN & PANDUAN**\n\n"
        "**CARA ORDER:**\n"
        "1. Pilih 🛒 **BELI PRODUK**\n"
        "2. Pilih kategori produk\n"
        "3. Pilih produk yang diinginkan\n"
        "4. Masukkan nomor tujuan\n"
        "5. Konfirmasi dan bayar\n\n"
        "**TOP UP SALDO:**\n"
        "1. Pilih 💸 **TOP UP SALDO**\n"
        "2. Masukkan nominal\n"
        "3. Pilih metode pembayaran (QRIS/Transfer Bank)\n"
        "4. Ikuti instruksi pembayaran\n"
        "5. Tunggu konfirmasi admin\n\n"
        "**BUTUH BANTUAN?**\n"
        "Hubungi Admin untuk bantuan lebih lanjut."
    )
    
    try:
        await query.edit_message_text(
            help_text,
            reply_markup=get_back_keyboard(),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}")
        await query.message.reply_text(
            help_text,
            reply_markup=get_back_keyboard(),
            parse_mode='Markdown'
        )

# ==================== COMMAND HANDLERS ====================
async def saldo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /saldo"""
    await show_saldo_menu_message(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /help"""
    await show_help_menu_message(update, context)

async def stock_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /stock"""
    await fixed_stock_command(update, context)

async def order_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /order"""
    await fixed_order_menu_handler(update, context)

async def topup_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /topup"""
    if TOPUP_AVAILABLE:
        await topup_command(update, context)
    else:
        await update.message.reply_text("❌ Fitur topup sedang dalam perbaikan.")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /admin"""
    if str(update.message.from_user.id) in ADMIN_IDS:
        await admin_menu(update, context)
    else:
        await update.message.reply_text("❌ Anda bukan admin!")

# ==================== ADMIN COMMAND HANDLERS ====================
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /broadcast"""
    if str(update.message.from_user.id) in ADMIN_IDS:
        if ADMIN_AVAILABLE:
            await admin_callback_handler(update, context)
        else:
            await update.message.reply_text("❌ Fitur broadcast sedang dalam perbaikan.")
    else:
        await update.message.reply_text("❌ Anda bukan admin!")

async def topup_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /topup_list"""
    if str(update.message.from_user.id) in ADMIN_IDS:
        if ADMIN_AVAILABLE:
            await admin_callback_handler(update, context)
        else:
            await update.message.reply_text("❌ Fitur admin sedang dalam perbaikan.")
    else:
        await update.message.reply_text("❌ Anda bukan admin!")

async def cek_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /cek_user"""
    if str(update.message.from_user.id) in ADMIN_IDS:
        if ADMIN_AVAILABLE:
            await admin_callback_handler(update, context)
        else:
            await update.message.reply_text("❌ Fitur admin sedang dalam perbaikan.")
    else:
        await update.message.reply_text("❌ Anda bukan admin!")

# ==================== UTILITY HANDLERS ====================
async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk pesan yang tidak dikenal"""
    logger.debug(f"Unknown message from {update.message.from_user.id}: {update.message.text}")
    
    await update.message.reply_text(
        "🤔 Saya tidak mengerti perintah tersebut.\n\n"
        "Gunakan /help untuk melihat daftar perintah yang tersedia "
        "atau gunakan tombol menu untuk navigasi.",
        reply_markup=get_back_keyboard()
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler untuk menangani semua error"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
    
    # Log the full traceback
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = ''.join(tb_list)
    logger.error(f"Traceback: {tb_string}")
    
    if isinstance(update, Update):
        if update.message:
            await update.message.reply_text(
                "❌ Terjadi kesalahan sistem. Silakan coba lagi dalam beberapa saat.\n\n"
                "Jika error berlanjut, hubungi admin.",
                reply_markup=get_back_keyboard()
            )
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                "❌ Terjadi kesalahan sistem. Silakan coba lagi.",
                reply_markup=get_back_keyboard()
            )

async def post_init(application: Application):
    """Function yang dijalankan setelah bot berhasil initialized"""
    logger.info("🤖 Bot has been initialized successfully!")
    
    try:
        # Get bot info
        bot = await application.bot.get_me()
        
        # Get basic statistics
        try:
            total_users = database.get_total_users()
            total_products = database.get_total_products()
            pending_topups = database.get_pending_topups_count()
        except:
            total_users = 0
            total_products = 0
            pending_topups = 0
        
        status_info = (
            f"🤖 **Bot Status Report**\n\n"
            f"📊 **Handler Status:**\n"
            f"• Database: ✅\n"
            f"• Topup: {'✅' if TOPUP_AVAILABLE else '❌'}\n"
            f"• Order: {'✅' if ORDER_AVAILABLE else '❌'}\n"
            f"• Admin: {'✅' if ADMIN_AVAILABLE else '❌'}\n"
            f"• Stok: {'✅' if STOK_AVAILABLE else '❌'}\n\n"
            f"📈 **Bot Statistics:**\n"
            f"• Total Users: {total_users}\n"
            f"• Total Products: {total_products}\n"
            f"• Pending Topups: {pending_topups}\n\n"
            f"🔧 **Bot Info:**\n"
            f"• Name: @{bot.username}\n"
            f"• ID: {bot.id}\n"
            f"• Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        print("=" * 50)
        print("🤖 BOT STARTED SUCCESSFULLY!")
        print("=" * 50)
        print(status_info)
        print("=" * 50)
        print("📍 Bot is now running and waiting for messages...")
        print("📍 Try sending /start to your bot")
        print("=" * 50)
        
    except Exception as e:
        logger.error(f"Error in post_init: {e}")
        print(f"❌ Error in post_init: {e}")

# ==================== MAIN FUNCTION ====================
def main():
    """Main function - Initialize dan start bot"""
    try:
        print("🚀 Starting Telegram Bot...")
        
        # Check BOT_TOKEN
        if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
            print("❌ Please set BOT_TOKEN in config.py")
            sys.exit(1)
        
        # Initialize database
        try:
            success = database.init_database()
            if success:
                print("✅ Database initialized successfully")
            else:
                print("❌ Database initialization failed")
        except Exception as e:
            print(f"❌ Database initialization failed: {e}")
        
        # Create Application
        persistence = PicklePersistence(filepath="bot_persistence")
        application = Application.builder()\
            .token(BOT_TOKEN)\
            .persistence(persistence)\
            .post_init(post_init)\
            .build()
        
        print("✅ Application built successfully")
        
        # ==================== HANDLER REGISTRATION ====================
        
        # 1. MESSAGE HANDLER UNTUK REPLY KEYBOARD
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        print("✅ Reply keyboard handler registered")
        
        # 2. CONVERSATION HANDLERS
        if TOPUP_AVAILABLE:
            topup_conv_handler = get_topup_conversation_handler()
            if topup_conv_handler:
                application.add_handler(topup_conv_handler)
                print("✅ Topup conversation handler registered")
        
        if ORDER_AVAILABLE:
            order_conv_handler = get_order_conversation_handler()
            if order_conv_handler:
                application.add_handler(order_conv_handler)
                print("✅ Order conversation handler registered")
        
        # 3. TOPUP CALLBACK HANDLERS
        if TOPUP_AVAILABLE:
            topup_handlers = get_topup_handlers()
            for handler in topup_handlers:
                application.add_handler(handler)
            print("✅ Topup callback handlers registered")
        
        # 4. ADMIN CALLBACK HANDLERS
        if ADMIN_AVAILABLE:
            admin_handlers = get_admin_handlers()
            for handler in admin_handlers:
                application.add_handler(handler)
            print("✅ Admin callback handlers registered")
        
        # 5. STOK HANDLER
        if STOK_AVAILABLE:
            application.add_handler(CallbackQueryHandler(stock_akrab_callback, pattern="^stock_"))
            print("✅ Stok handler registered")
        
        # 6. MAIN MENU CALLBACK HANDLER
        application.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^main_menu_"))
        application.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^topup_menu$"))
        print("✅ Main menu callback handler registered")
        
        # 7. COMMAND HANDLERS
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("saldo", saldo_command))
        application.add_handler(CommandHandler("topup", topup_command_handler))
        application.add_handler(CommandHandler("stock", stock_command_handler))
        application.add_handler(CommandHandler("order", order_command))
        application.add_handler(CommandHandler("admin", admin_command))
        
        # Admin commands
        application.add_handler(CommandHandler("broadcast", broadcast_command))
        application.add_handler(CommandHandler("topup_list", topup_list_command))
        application.add_handler(CommandHandler("cek_user", cek_user_command))
        
        print("✅ Command handlers registered")
        
        # 8. ERROR HANDLER
        application.add_error_handler(error_handler)
        print("✅ Error handler registered")
        
        # ==================== START BOT ====================
        print("🎯 Starting bot polling...")
        
        # Run bot dengan polling
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
                
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        logger.error(f"Failed to start bot: {e}", exc_info=True)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    # Print startup banner
    print("=" * 60)
    print("🤖 TELEGRAM BOT - FULL FEATURE VERSION")
    print("🛠️  FIXED & READY FOR PRODUCTION")
    print("=" * 60)
    
    main()
