#!/usr/bin/env python3
# bot.py - Main Bot File for Single Product Order System
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler
import config
from admin_handler import get_admin_handlers
import database
import order_handler  # Import order handler

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def is_admin(user):
    """Check if user is admin"""
    if not user:
        return False
    return str(user.id) in config.ADMIN_TELEGRAM_IDS

# ============================
# MAIN MENU & USER HANDLERS
# ============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message with main menu when the command /start is issued."""
    user = update.effective_user
    
    # Create user in database if not exists
    database.create_user(user.id, user.username, user.full_name)
    
    # Main menu keyboard - HANYA ORDER PRODUK
    keyboard = [
        [InlineKeyboardButton("🛒 Beli Produk", callback_data="buy_product")],
        [InlineKeyboardButton("💰 Cek Saldo", callback_data="check_balance")],
        [InlineKeyboardButton("🆘 Bantuan", callback_data="show_help")],
    ]
    
    # Add admin button if user is admin
    if is_admin(user):
        keyboard.append([InlineKeyboardButton("👑 Menu Admin", callback_data="admin_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"👋 **Selamat Datang, {user.full_name}!**\n\n"
        f"🤖 **Saya adalah Bot Pembelian Produk**\n\n"
        f"🎯 **Fitur yang tersedia:**\n"
        f"• 🛒 **Beli Produk** - Pembelian produk otomatis\n"
        f"• 💰 **Cek Saldo** - Lihat saldo akun Anda\n"
        f"• 🆘 **Bantuan** - Panduan penggunaan\n\n"
        f"**Untuk memulai pembelian, klik tombol di bawah:**"
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show main menu"""
    user = update.effective_user
    
    keyboard = [
        [InlineKeyboardButton("🛒 Beli Produk", callback_data="buy_product")],
        [InlineKeyboardButton("💰 Cek Saldo", callback_data="check_balance")],
        [InlineKeyboardButton("🆘 Bantuan", callback_data="show_help")],
    ]
    
    if is_admin(user):
        keyboard.append([InlineKeyboardButton("👑 Menu Admin", callback_data="admin_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📱 **MENU UTAMA**\n\nPilih opsi yang diinginkan:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message."""
    help_text = (
        "🆘 **BANTUAN & CARA PENGGUNAAN**\n\n"
        "📋 **Menu Utama:**\n"
        "• /start - Memulai bot\n"
        "• /menu - Menampilkan menu utama\n"
        "• /help - Menampilkan bantuan\n"
        "• /order - Memulai pembelian produk\n\n"
        "🛒 **Cara Beli Produk:**\n"
        "1. Klik '🛒 Beli Produk' di menu atau ketik /order\n"
        "2. Pilih produk dari daftar yang tersedia\n"
        "3. Masukkan nomor tujuan\n"
        "4. Konfirmasi pembelian\n"
        "5. Produk akan dikirim otomatis\n\n"
        "💰 **Top Up Saldo:**\n"
        "1. Transfer ke rekening admin\n"
        "2. Kirim bukti transfer dengan command `/topup <jumlah>`\n"
        "3. Tunggu konfirmasi admin\n\n"
        "💳 **Cek Saldo:**\n"
        "Gunakan menu 'Cek Saldo' atau command /balance\n\n"
        "📞 **Bantuan Admin:**\n"
        "Jika mengalami kendala, hubungi admin langsung."
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check user balance"""
    user = update.effective_user
    saldo = database.get_user_saldo(user.id)
    
    balance_text = (
        f"💳 **INFORMASI SALDO**\n\n"
        f"👤 **User:** {user.full_name}\n"
        f"💎 **Saldo:** Rp {saldo:,.0f}\n\n"
        f"💡 **Saldo digunakan untuk pembelian produk otomatis.**\n"
        f"Pastikan saldo mencukupi sebelum melakukan order."
    )
    
    await update.message.reply_text(balance_text, parse_mode='Markdown')

# ============================
# CALLBACK QUERY HANDLERS
# ============================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline keyboards"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    if data == "buy_product":
        await start_order_from_callback(query, context)
    elif data == "check_balance":
        await show_user_balance(query, context)
    elif data == "show_help":
        await show_help(query, context)
    elif data == "admin_menu":
        if is_admin(user):
            await show_admin_menu(query, context)
        else:
            await query.edit_message_text("❌ Anda bukan admin.")
    elif data == "back_to_menu":
        await show_main_menu(query, context)

async def start_order_from_callback(query, context):
    """Start order process from callback"""
    user = query.from_user
    
    # Create user in database if not exists
    database.create_user(user.id, user.username, user.full_name)
    
    # Get user balance
    saldo = database.get_user_saldo(user.id)
    
    # Get available products
    import sqlite3
    DB_PATH = "bot_topup.db"
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            code TEXT PRIMARY KEY,
            name TEXT,
            price REAL,
            status TEXT,
            updated_at TEXT
        )
    """)
    c.execute("SELECT code, name, price FROM products WHERE status='active' ORDER BY name ASC LIMIT 30")
    produk_list = c.fetchall()
    conn.close()
    
    if not produk_list:
        await query.edit_message_text(
            "❌ **Produk Belum Tersedia**\n\n"
            "Silakan minta admin untuk update produk terlebih dahulu dengan /updateproduk",
            parse_mode='Markdown'
        )
        return
    
    # Format product list message
    msg = (
        f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
        "🎮 **PILIH PRODUK:**\n\n"
    )
    
    for code, name, price in produk_list:
        msg += f"▪️ **{name}**\n   Kode: `{code}` - Rp {price:,.0f}\n\n"
    
    msg += "**Ketik /order untuk memilih produk**"
    
    keyboard = [
        [InlineKeyboardButton("🛒 Order Sekarang", switch_inline_query_current_chat="/order ")],
        [InlineKeyboardButton("💰 Cek Saldo", callback_data="check_balance")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        msg,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_user_balance(query, context):
    """Show user balance in callback"""
    user = query.from_user
    saldo = database.get_user_saldo(user.id)
    
    balance_text = (
        f"💳 **SALDO ANDA**\n\n"
        f"👤 **User:** {user.full_name}\n"
        f"💎 **Saldo:** Rp {saldo:,.0f}\n\n"
        f"💡 **Saldo digunakan untuk pembelian produk otomatis.**\n"
        f"Pastikan saldo mencukupi sebelum melakukan order."
    )
    
    keyboard = [
        [InlineKeyboardButton("🛒 Beli Produk", callback_data="buy_product")],
        [InlineKeyboardButton("💳 Top Up Saldo", callback_data="user_topup")],
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        balance_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_help(query, context):
    """Show help in callback"""
    help_text = (
        "🆘 **BANTUAN & CARA PENGGUNAAN**\n\n"
        "🛒 **Cara Beli Produk:**\n"
        "1. Klik '🛒 Beli Produk' di menu atau ketik /order\n"
        "2. Pilih produk dari daftar yang tersedia\n"
        "3. Masukkan nomor tujuan\n"
        "4. Konfirmasi pembelian\n"
        "5. Produk akan dikirim otomatis\n\n"
        "💰 **Top Up Saldo:**\n"
        "1. Transfer ke rekening admin\n"
        "2. Kirim bukti transfer dengan command `/topup <jumlah>`\n"
        "3. Tunggu konfirmasi admin (1-15 menit)\n\n"
        "💳 **Cek Saldo:**\n"
        "Gunakan menu 'Cek Saldo' atau command /balance\n\n"
        "📞 **Bantuan Admin:**\n"
        "Jika mengalami kendala, hubungi admin langsung."
    )
    
    keyboard = [
        [InlineKeyboardButton("🛒 Beli Produk", callback_data="buy_product")],
        [InlineKeyboardButton("💰 Cek Saldo", callback_data="check_balance")],
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        help_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_admin_menu(query, context):
    """Show admin menu from callback"""
    admin_text = (
        "👑 **MENU ADMIN**\n\n"
        "Pilih menu admin yang tersedia:\n\n"
        "📦 **Kelola Produk:**\n"
        "• /updateproduk - Update produk dari provider\n"
        "• /listproduk - Lihat daftar produk\n"
        "• /edit_produk - Edit harga/deskripsi produk\n\n"
        "💳 **Kelola TopUp:**\n"
        "• /topup_list - Lihat permintaan topup\n"
        "• Approve/reject via button\n\n"
        "👥 **Kelola User:**\n"
        "• /cek_user - Cek informasi user\n"
        "• /jadikan_admin - Tambah admin\n\n"
        "📊 **Lainnya:**\n"
        "• /stats - Statistik sistem\n"
        "• /broadcast - Kirim pesan ke semua user"
    )
    
    keyboard = [
        [InlineKeyboardButton("📦 Kelola Produk", callback_data="admin_products")],
        [InlineKeyboardButton("💳 Kelola Topup", callback_data="admin_topup")],
        [InlineKeyboardButton("📊 Statistik", callback_data="admin_stats")],
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        admin_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_main_menu(query, context):
    """Show main menu from callback"""
    user = query.from_user
    
    keyboard = [
        [InlineKeyboardButton("🛒 Beli Produk", callback_data="buy_product")],
        [InlineKeyboardButton("💰 Cek Saldo", callback_data="check_balance")],
        [InlineKeyboardButton("🆘 Bantuan", callback_data="show_help")],
    ]
    
    if is_admin(user):
        keyboard.append([InlineKeyboardButton("👑 Menu Admin", callback_data="admin_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📱 **MENU UTAMA**\n\nPilih opsi yang diinginkan:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ============================
# TOPUP COMMAND HANDLER (Simplified)
# ============================

async def topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle topup command"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "❌ **Format salah!**\n\n"
            "Gunakan: `/topup <jumlah>`\n"
            "Contoh: `/topup 50000`\n\n"
            "Minimal topup: Rp 10,000",
            parse_mode='Markdown'
        )
        return
    
    try:
        amount = float(context.args[0])
        if amount < 10000:
            await update.message.reply_text("❌ Minimal topup adalah Rp 10,000")
            return
        if amount > 5000000:
            await update.message.reply_text("❌ Maksimal topup adalah Rp 5,000,000")
            return
            
        # Store topup request in context for proof image
        context.user_data['pending_topup'] = {
            'user_id': user.id,
            'username': user.username,
            'full_name': user.full_name,
            'amount': amount
        }
        
        await update.message.reply_text(
            f"💰 **TOPUP REQUEST**\n\n"
            f"Jumlah: Rp {amount:,.0f}\n\n"
            f"📎 **Silakan kirim bukti transfer (foto/screenshot)**\n"
            f"atau ketik /cancel untuk membatalkan",
            parse_mode='Markdown'
        )
        
    except ValueError:
        await update.message.reply_text("❌ Jumlah harus angka!")

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle image upload for topup proof"""
    user = update.effective_user
    
    if 'pending_topup' not in context.user_data:
        await update.message.reply_text("❌ Silakan gunakan command `/topup <jumlah>` terlebih dahulu")
        return
    
    topup_data = context.user_data['pending_topup']
    
    if update.message.photo:
        # Get the largest photo
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        
        # In a real implementation, you would save this file or process it
        # For now, we'll just acknowledge receipt
        
        await update.message.reply_text(
            f"✅ **Bukti transfer diterima!**\n\n"
            f"💰 **Jumlah:** Rp {topup_data['amount']:,.0f}\n"
            f"👤 **User:** {user.full_name}\n\n"
            f"⏳ **Status:** Menunggu verifikasi admin\n"
            f"📞 Admin akan memverifikasi dalam 1-15 menit.\n\n"
            f"Terima kasih!",
            parse_mode='Markdown'
        )
        
        # Here you would save the topup request to database
        # For now, we'll just clear the pending topup
        del context.user_data['pending_topup']
        
    else:
        await update.message.reply_text("❌ Silakan kirim bukti transfer dalam format gambar/foto")

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel pending topup"""
    if 'pending_topup' in context.user_data:
        del context.user_data['pending_topup']
        await update.message.reply_text("❌ Topup request dibatalkan.")
    else:
        await update.message.reply_text("❌ Tidak ada topup request yang aktif.")

# ============================
# ECHO HANDLER (Fallback)
# ============================

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Echo the user message with menu suggestion."""
    await update.message.reply_text(
        "🤖 Saya adalah bot pembelian produk.\n\n"
        "Gunakan /menu untuk melihat menu utama atau /help untuk bantuan.\n"
        "Untuk membeli produk, ketik /order"
    )

# ============================
# MAIN APPLICATION
# ============================

def main():
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(config.BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("topup", topup_command))
    application.add_handler(CommandHandler("cancel", cancel_command))

    # Add callback query handler
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Add message handlers
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Add order conversation handler
    application.add_handler(order_handler.order_conv_handler)

    # Add admin handlers
    admin_handlers = get_admin_handlers()
    for handler in admin_handlers:
        application.add_handler(handler)

    # Start the Bot
    print("🤖 Starting Telegram Bot...")
    print("🛒 Order System: READY")
    print("💳 Single Product Focus: READY") 
    print("💰 Balance System: READY")
    print("👑 Admin Menu: READY")
    print("🔧 Bot is now running...")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
