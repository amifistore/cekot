#!/usr/bin/env python3
# bot.py - Main Bot File with Customized Menu for Your Products
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import config
from admin_handler import get_admin_handlers
import database

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
    
    # Main menu keyboard - SESUAI PRODUK YANG DIJUAL
    keyboard = [
        [InlineKeyboardButton("📱 Pulsa & Data", callback_data="category_pulsa")],
        [InlineKeyboardButton("⚡ Token Listrik", callback_data="category_pln")],
        [InlineKeyboardButton("🎮 Voucher Game", callback_data="category_game")],
        [InlineKeyboardButton("💳 Top Up Saldo", callback_data="user_topup")],
        [InlineKeyboardButton("💰 Cek Saldo", callback_data="user_balance")],
    ]
    
    # Add admin button if user is admin
    if is_admin(user):
        keyboard.append([InlineKeyboardButton("👑 Menu Admin", callback_data="admin_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"👋 **Selamat Datang, {user.full_name}!**\n\n"
        f"🤖 **Saya adalah Bot TopUp & Payment**\n\n"
        f"🛍️ **Produk yang tersedia:**\n"
        f"• 📱 **Pulsa & Paket Data**\n"
        f"• ⚡ **Token Listrik PLN**\n"
        f"• 🎮 **Voucher Game**\n\n"
        f"💳 **Fitur Lainnya:**\n"
        f"• Top Up Saldo\n"
        f"• Cek Saldo\n\n"
        f"Pilih produk yang ingin dibeli:"
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
        [InlineKeyboardButton("📱 Pulsa & Data", callback_data="category_pulsa")],
        [InlineKeyboardButton("⚡ Token Listrik", callback_data="category_pln")],
        [InlineKeyboardButton("🎮 Voucher Game", callback_data="category_game")],
        [InlineKeyboardButton("💳 Top Up Saldo", callback_data="user_topup")],
        [InlineKeyboardButton("💰 Cek Saldo", callback_data="user_balance")],
    ]
    
    if is_admin(user):
        keyboard.append([InlineKeyboardButton("👑 Menu Admin", callback_data="admin_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🛍️ **MENU PRODUK**\n\nPilih produk yang ingin dibeli:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message."""
    help_text = (
        "🆘 **BANTUAN & CARA PENGGUNAAN**\n\n"
        "📋 **Menu Utama:**\n"
        "• /start - Memulai bot\n"
        "• /menu - Menampilkan menu produk\n"
        "• /help - Menampilkan bantuan\n\n"
        "🛍️ **Cara Beli Produk:**\n"
        "1. Pilih kategori produk (Pulsa, Token Listrik, atau Game)\n"
        "2. Pilih produk yang diinginkan\n"
        "3. Ikuti instruksi pembelian\n\n"
        "💰 **Top Up Saldo:**\n"
        "1. Klik 'Top Up Saldo' di menu\n"
        "2. Transfer ke rekening yang tertera\n"
        "3. Kirim bukti transfer dengan command `/topup <jumlah>`\n"
        "4. Tunggu konfirmasi admin (1-15 menit)\n\n"
        "💳 **Cek Saldo:**\n"
        "Klik 'Cek Saldo' untuk melihat saldo terkini\n\n"
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
        f"🛍️ **Cukup untuk beli:**\n"
    )
    
    # Add product examples based on balance
    if saldo >= 5000:
        balance_text += f"• 📱 Pulsa Rp 5,000\n"
    if saldo >= 10000:
        balance_text += f"• ⚡ Token Listrik Rp 10,000\n"
    if saldo >= 25000:
        balance_text += f"• 🎮 Voucher Mobile Legends\n"
    if saldo >= 50000:
        balance_text += f"• 📦 Paket Data 5GB\n"
    
    balance_text += f"\n💡 **Tips:** Gunakan saldo untuk beli produk lebih cepat!"
    
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
    
    if data == "user_topup":
        await show_topup_instructions(query, context)
    elif data == "user_balance":
        await show_user_balance(query, context)
    elif data == "category_pulsa":
        await show_pulsa_products(query, context)
    elif data == "category_pln":
        await show_pln_products(query, context)
    elif data == "category_game":
        await show_game_products(query, context)
    elif data == "admin_menu":
        if is_admin(user):
            await show_admin_menu(query, context)
        else:
            await query.edit_message_text("❌ Anda bukan admin.")
    elif data == "back_to_menu":
        await show_main_menu(query, context)

async def show_topup_instructions(query, context):
    """Show topup instructions"""
    instructions = (
        "💰 **CARA TOP UP SALDO**\n\n"
        "📋 **Langkah-langkah:**\n"
        "1. Transfer ke rekening berikut:\n"
        "   **Bank:** BCA\n"
        "   **No.Rek:** 123-456-7890\n"
        "   **A/N:** NAMA ADMIN\n\n"
        "2. Setelah transfer, kirim bukti transfer dengan command:\n"
        "   `/topup <jumlah>`\n"
        "   Contoh: `/topup 50000`\n\n"
        "3. Admin akan memverifikasi dan menambahkan saldo\n\n"
        "💡 **Catatan:**\n"
        "- Minimal topup: Rp 10,000\n"
        "- Maksimal topup: Rp 5,000,000\n"
        "- Proses verifikasi 1-15 menit"
    )
    
    keyboard = [
        [InlineKeyboardButton("💳 Cek Saldo", callback_data="user_balance")],
        [InlineKeyboardButton("📱 Beli Pulsa", callback_data="category_pulsa")],
        [InlineKeyboardButton("⚡ Token Listrik", callback_data="category_pln")],
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        instructions,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_pulsa_products(query, context):
    """Show pulsa and data products"""
    products_text = (
        "📱 **PULSA & PAKET DATA**\n\n"
        "🛍️ **Pilihan Produk:**\n\n"
        "**📞 Pulsa Reguler:**\n"
        "• Rp 5.000\n"
        "• Rp 10.000\n"
        "• Rp 25.000\n"
        "• Rp 50.000\n"
        "• Rp 100.000\n\n"
        "**📦 Paket Data:**\n"
        "• 1GB - Rp 10.000\n"
        "• 3GB - Rp 25.000\n"
        "• 5GB - Rp 40.000\n"
        "• 10GB - Rp 70.000\n\n"
        "🔧 **Fitur pembelian otomatis sedang dalam pengembangan.**\n"
        "Untuk saat ini, silakan hubungi admin untuk pemesanan."
    )
    
    keyboard = [
        [InlineKeyboardButton("⚡ Token Listrik", callback_data="category_pln")],
        [InlineKeyboardButton("🎮 Voucher Game", callback_data="category_game")],
        [InlineKeyboardButton("💳 Top Up Saldo", callback_data="user_topup")],
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        products_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_pln_products(query, context):
    """Show PLN token products"""
    products_text = (
        "⚡ **TOKEN LISTRIK PLN**\n\n"
        "🛍️ **Pilihan Produk:**\n\n"
        "**💡 Token Listrik:**\n"
        "• Rp 10.000\n"
        "• Rp 20.000\n"
        "• Rp 50.000\n"
        "• Rp 100.000\n"
        "• Rp 200.000\n"
        "• Rp 500.000\n"
        "• Rp 1.000.000\n\n"
        "📝 **Cara Beli:**\n"
        "1. Pastikan saldo mencukupi\n"
        "2. Kirim format: `PLN <NOMOR METER> <JUMLAH>`\n"
        "3. Contoh: `PLN 12345678901 20000`\n\n"
        "🔧 **Fitur pembelian otomatis sedang dalam pengembangan.**\n"
        "Untuk saat ini, silakan hubungi admin untuk pemesanan."
    )
    
    keyboard = [
        [InlineKeyboardButton("📱 Pulsa & Data", callback_data="category_pulsa")],
        [InlineKeyboardButton("🎮 Voucher Game", callback_data="category_game")],
        [InlineKeyboardButton("💳 Top Up Saldo", callback_data="user_topup")],
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        products_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_game_products(query, context):
    """Show game voucher products"""
    products_text = (
        "🎮 **VOUCHER GAME**\n\n"
        "🛍️ **Pilihan Produk:**\n\n"
        "**📱 Mobile Legends:**\n"
        "• 86 Diamond - Rp 20.000\n"
        "• 172 Diamond - Rp 40.000\n"
        "• 257 Diamond - Rp 60.000\n"
        "• 344 Diamond - Rp 80.000\n"
        "• 429 Diamond - Rp 100.000\n\n"
        "**🎯 Free Fire:**\n"
        "• 70 Diamond - Rp 10.000\n"
        "• 140 Diamond - Rp 20.000\n"
        "• 355 Diamond - Rp 50.000\n"
        "• 720 Diamond - Rp 100.000\n\n"
        "**⚡ PUBG Mobile:**\n"
        "• 75 UC - Rp 15.000\n"
        "• 150 UC - Rp 30.000\n"
        "• 385 UC - Rp 75.000\n"
        "• 770 UC - Rp 150.000\n\n"
        "🔧 **Fitur pembelian otomatis sedang dalam pengembangan.**\n"
        "Untuk saat ini, silakan hubungi admin untuk pemesanan."
    )
    
    keyboard = [
        [InlineKeyboardButton("📱 Pulsa & Data", callback_data="category_pulsa")],
        [InlineKeyboardButton("⚡ Token Listrik", callback_data="category_pln")],
        [InlineKeyboardButton("💳 Top Up Saldo", callback_data="user_topup")],
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        products_text,
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
        f"🛍️ **Cukup untuk beli:**\n"
    )
    
    # Add product examples based on balance
    if saldo >= 5000:
        balance_text += f"• 📱 Pulsa Rp 5,000\n"
    if saldo >= 10000:
        balance_text += f"• ⚡ Token Listrik Rp 10,000\n"
    if saldo >= 20000:
        balance_text += f"• 🎮 ML 86 Diamond\n"
    if saldo >= 50000:
        balance_text += f"• 📦 Paket Data 5GB\n"
    
    balance_text += f"\n💡 **Tips:** Gunakan saldo untuk beli produk lebih cepat!"
    
    keyboard = [
        [InlineKeyboardButton("📱 Beli Pulsa", callback_data="category_pulsa")],
        [InlineKeyboardButton("⚡ Token Listrik", callback_data="category_pln")],
        [InlineKeyboardButton("🎮 Voucher Game", callback_data="category_game")],
        [InlineKeyboardButton("💳 Top Up", callback_data="user_topup")],
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        balance_text,
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
        [InlineKeyboardButton("📱 Pulsa & Data", callback_data="category_pulsa")],
        [InlineKeyboardButton("⚡ Token Listrik", callback_data="category_pln")],
        [InlineKeyboardButton("🎮 Voucher Game", callback_data="category_game")],
        [InlineKeyboardButton("💳 Top Up Saldo", callback_data="user_topup")],
        [InlineKeyboardButton("💰 Cek Saldo", callback_data="user_balance")],
    ]
    
    if is_admin(user):
        keyboard.append([InlineKeyboardButton("👑 Menu Admin", callback_data="admin_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🛍️ **MENU PRODUK**\n\nPilih produk yang ingin dibeli:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ============================
# TOPUP COMMAND HANDLER
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
        "🤖 Saya adalah bot TopUp & Payment.\n\n"
        "Gunakan /menu untuk melihat menu produk atau /help untuk bantuan."
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

    # Add admin handlers
    admin_handlers = get_admin_handlers()
    for handler in admin_handlers:
        application.add_handler(handler)

    # Start the Bot
    print("🤖 Starting Telegram Bot...")
    print("🛍️  Product Menu: READY")
    print("📱 Pulsa & Data: READY")
    print("⚡ Token Listrik: READY") 
    print("🎮 Voucher Game: READY")
    print("💳 TopUp System: READY")
    print("👑 Admin Menu: READY")
    print("🔧 Bot is now running...")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
