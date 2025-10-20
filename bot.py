#!/usr/bin/env python3
"""
Bot Telegram Full Feature - FINAL FIXED VERSION
Sesuai struktur asli dari CekotDev - Dilengkapi oleh Gemini
"""

import logging
import sys
import os
import asyncio
import traceback
from typing import Dict, Any
from datetime import datetime

# Telegram Imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# ==================== IMPORTS DENGAN ERROR HANDLING (STRUKTUR ASLI ANDA) ====================
print("🔄 Loading handlers...")

# Admin Handler
try:
    from admin_handler import (
        admin_menu,
        admin_callback_handler,
        edit_produk_conv_handler,
        broadcast_handler,
        cek_user_handler,
        jadikan_admin_handler,
        topup_list_handler
    )
    ADMIN_AVAILABLE = True
    print("✅ Admin handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing admin_handler: {e}")
    ADMIN_AVAILABLE = False
    admin_menu = admin_callback_handler = edit_produk_conv_handler = broadcast_handler = cek_user_handler = jadikan_admin_handler = topup_list_handler = None

# Stok Handler
try:
    from stok_handler import stock_akrab_callback, stock_command
    STOK_AVAILABLE = True
    print("✅ Stok handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing stok_handler: {e}")
    STOK_AVAILABLE = False
    stock_akrab_callback = stock_command = None

# Order Handler
try:
    from order_handler import (
        get_conversation_handler as get_order_conversation_handler,
        menu_handler as order_menu_handler
    )
    ORDER_AVAILABLE = True
    print("✅ Order handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing order_handler: {e}")
    ORDER_AVAILABLE = False
    get_order_conversation_handler = lambda: None
    order_menu_handler = None

# Topup Handler
try:
    from topup_handler import (
        get_topup_conversation_handler,
        show_topup_menu,
        show_topup_history, 
        show_pending_topups,
        handle_proof_upload
    )
    TOPUP_AVAILABLE = True
    print("✅ Topup handler loaded successfully")
except Exception as e:
    print(f"❌ Error importing topup_handler: {e}")
    TOPUP_AVAILABLE = False
    get_topup_conversation_handler = lambda: None
    show_topup_menu = show_topup_history = show_pending_topups = handle_proof_upload = None

# ==================== LOGGING SETUP ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== GLOBAL VARIABLES ====================
BOT_TOKEN = config.BOT_TOKEN
ADMIN_IDS = [str(admin_id) for admin_id in getattr(config, 'ADMIN_TELEGRAM_IDS', [])]

def format_currency(amount: int) -> str:
    """Utility function to format currency."""
    if amount is None: amount = 0
    return f"Rp {amount:,.0f}".replace(",", ".")

# ==================== BASIC COMMAND HANDLERS (KODE ASLI ANDA) ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start - Menu utama"""
    try:
        user = update.message.from_user
        logger.info(f"User {user.id} started the bot")
        
        saldo = 0
        try:
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            saldo = database.get_user_saldo(user_id)
        except Exception as e:
            logger.error(f"Error getting user saldo: {e}")
            saldo = 0
        
        keyboard = [
            [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="main_menu_order")],
            [InlineKeyboardButton("💳 CEK SALDO", callback_data="main_menu_saldo")],
            [InlineKeyboardButton("📊 CEK STOK", callback_data="main_menu_stock")],
            [InlineKeyboardButton("📞 BANTUAN", callback_data="main_menu_help")],
            [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="topup_menu")]
        ]
        
        if str(user.id) in ADMIN_IDS:
            keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="main_menu_admin")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        welcome_text = (
            f"🤖 **Selamat Datang!**\n\n"
            f"Halo {user.full_name}!\n"
            f"💰 **Saldo Anda:** {format_currency(saldo)}\n\n"
            f"Pilih menu di bawah untuk mulai berbelanja:"
        )
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main menu handler untuk semua callback"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    logger.info(f"Main menu callback: {data} from user {user.id}")
    
    try:
        if data == "main_menu_main":
            await show_main_menu(update, context)
        elif data == "main_menu_saldo":
            await show_saldo_menu(update, context)
        elif data == "main_menu_help":
            await show_help_menu(update, context)
        elif data == "main_menu_stock" and STOK_AVAILABLE:
            await stock_akrab_callback(update, context)
        elif data == "main_menu_admin":
            if str(user.id) in ADMIN_IDS and ADMIN_AVAILABLE:
                await admin_menu(update, context)
            else:
                await query.answer("❌ Anda bukan admin!", show_alert=True)
        elif data == "main_menu_order" and ORDER_AVAILABLE:
            await order_menu_handler(update, context)
        elif data == "topup_menu" and TOPUP_AVAILABLE:
            await show_topup_menu(update, context)
        else:
            await query.message.reply_text("❌ Menu tidak dikenali.")
            
    except Exception as e:
        logger.error(f"Error in main_menu_handler for {data}: {e}")
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu utama"""
    query = update.callback_query
    user = query.from_user
    saldo = database.get_user_saldo(str(user.id))
    
    keyboard = [
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="main_menu_order")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="main_menu_saldo")],
        [InlineKeyboardButton("📊 CEK STOK", callback_data="main_menu_stock")],
        [InlineKeyboardButton("📞 BANTUAN", callback_data="main_menu_help")],
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="topup_menu")]
    ]
    if str(user.id) in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 ADMIN PANEL", callback_data="main_menu_admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"🏠 **MENU UTAMA**\n\n"
        f"Halo {user.full_name}!\n"
        f"💰 **Saldo Anda:** {format_currency(saldo)}\n\n"
        f"Pilih menu di bawah:",
        reply_markup=reply_markup, parse_mode='Markdown'
    )

async def show_saldo_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu saldo"""
    query = update.callback_query
    saldo = database.get_user_saldo(str(query.from_user.id))
    
    keyboard = [
        [InlineKeyboardButton("💸 TOP UP SALDO", callback_data="topup_menu")],
        [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]
    ]
    await query.edit_message_text(
        f"💰 **SALDO ANDA**\n\nSaldo saat ini: **{format_currency(saldo)}**\n\n",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
    )

async def show_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu bantuan"""
    query = update.callback_query
    help_text = "📞 **BANTUAN & PANDUAN**\n\nHubungi Admin untuk bantuan."
    keyboard = [[InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]]
    await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def saldo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /saldo"""
    user = update.message.from_user
    saldo = database.get_user_saldo(str(user.id))
    await update.message.reply_text(
        f"💰 **SALDO ANDA**\n\nSaldo saat ini: **{format_currency(saldo)}**",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /help"""
    help_text = "🤖 **BOT COMMANDS**\n\n/start\n/help\n/saldo\n/topup\n/stock\n/order\n/admin"
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def stock_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /stock"""
    if STOK_AVAILABLE: await stock_command(update, context)

async def order_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /order"""
    if ORDER_AVAILABLE: await order_menu_handler(update, context)

async def topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /topup"""
    if TOPUP_AVAILABLE: await show_topup_menu(update, context)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /admin"""
    if str(update.message.from_user.id) in ADMIN_IDS and ADMIN_AVAILABLE:
        await admin_menu(update, context)
    else:
        await update.message.reply_text("❌ Anda bukan admin!")

async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk pesan yang tidak dikenal"""
    await update.message.reply_text("🤔 Saya tidak mengerti. Gunakan /start untuk kembali.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)

async def post_init(application: Application):
    """Function yang dijalankan setelah bot berhasil initialized"""
    logger.info("🤖 Bot has been initialized successfully!")

# ==================== MAIN FUNCTION ====================
def main():
    """Main function - Initialize dan start bot"""
    logger.info("🚀 Starting Telegram Bot...")
    
    if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        logger.critical("❌ Please set BOT_TOKEN in config.py")
        sys.exit(1)
        
    try:
        database.init_database()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.critical(f"❌ Database initialization failed: {e}")
        sys.exit(1)
        
    persistence = PicklePersistence(filepath="bot_persistence")
    application = Application.builder()\
        .token(BOT_TOKEN)\
        .persistence(persistence)\
        .post_init(post_init)\
        .build()
    
    logger.info("✅ Application built successfully")
    
    # ==================== HANDLER REGISTRATION (SESUAI STRUKTUR ASLI) ====================
    
    # 1. CONVERSATION HANDLERS
    if TOPUP_AVAILABLE and get_topup_conversation_handler:
        application.add_handler(get_topup_conversation_handler())
    if ORDER_AVAILABLE and get_order_conversation_handler:
        application.add_handler(get_order_conversation_handler())
    if ADMIN_AVAILABLE and edit_produk_conv_handler:
        application.add_handler(edit_produk_conv_handler)
    
    # 2. COMMAND HANDLERS
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("saldo", saldo_command))
    application.add_handler(CommandHandler("topup", topup_command))
    application.add_handler(CommandHandler("stock", stock_command_handler))
    
    # BAGIAN YANG SAYA LENGKAPI DAN PERBAIKI
    application.add_handler(CommandHandler("order", order_command))
    application.add_handler(CommandHandler("admin", admin_command))

    if ADMIN_AVAILABLE:
        application.add_handler(CommandHandler("broadcast", broadcast_handler))
        application.add_handler(CommandHandler("topup_list", topup_list_handler))
        application.add_handler(CommandHandler("cek_user", cek_user_handler))
        # Perintah jadikan_admin_handler biasanya butuh argumen, jadi didaftar terpisah jika diperlukan
        application.add_handler(CommandHandler("jadikanadmin", jadikan_admin_handler)) 

    # 3. CALLBACK QUERY HANDLERS
    # Router utama untuk tombol-tombol menu
    application.add_handler(CallbackQueryHandler(main_menu_handler))
    
    # Handler spesifik untuk admin callbacks
    if ADMIN_AVAILABLE and admin_callback_handler:
        application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))

    # Handler spesifik untuk topup callbacks (sesuai impor asli)
    if TOPUP_AVAILABLE:
        # Catatan: show_topup_menu sudah ditangani oleh main_menu_handler dengan callback "topup_menu"
        if show_topup_history:
             application.add_handler(CallbackQueryHandler(show_topup_history, pattern="^topup_history$"))
        if show_pending_topups:
             application.add_handler(CallbackQueryHandler(show_pending_topups, pattern="^topup_pending$"))
        # handle_proof_upload adalah bagian dari conversation, tidak perlu didaftar di sini.
    
    # 4. MESSAGE HANDLERS (Untuk pesan teks biasa)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))
    
    # 5. ERROR HANDLER
    application.add_error_handler(error_handler)
    
    logger.info("✅ All handlers registered following original structure.")
    print("================ BOT IS RUNNING ================")
    
    application.run_polling()

if __name__ == '__main__':
    main()
