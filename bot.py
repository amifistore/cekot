#!/usr/bin/env python3
# bot.py - Main Bot File with Complete Button System
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
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
    
    # Main menu keyboard - SEMUA MENU DENGAN TOMBOL
    keyboard = [
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="buy_product")],
        [InlineKeyboardButton("💰 TOP UP SALDO", callback_data="topup_menu")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="check_balance")],
        [InlineKeyboardButton("📋 RIWAYAT TRANSAKSI", callback_data="transaction_history")],
        [InlineKeyboardButton("🆘 BANTUAN", callback_data="show_help")],
    ]
    
    # Add admin button if user is admin
    if is_admin(user):
        keyboard.append([InlineKeyboardButton("👑 MENU ADMIN", callback_data="admin_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"👋 **Selamat Datang, {user.full_name}!**\n\n"
        f"🤖 **Saya adalah Bot Pembelian Produk Digital**\n\n"
        f"🎯 **Fitur yang tersedia:**\n"
        f"• 🛒 **Beli Produk** - Pembelian pulsa, token, voucher game\n"
        f"• 💰 **Top Up Saldo** - Isi saldo akun Anda\n"
        f"• 💳 **Cek Saldo** - Lihat saldo akun Anda\n"
        f"• 📋 **Riwayat Transaksi** - Lihat history pembelian\n"
        f"• 🆘 **Bantuan** - Panduan penggunaan\n\n"
        f"**Pilih menu di bawah untuk mulai:**"
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
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="buy_product")],
        [InlineKeyboardButton("💰 TOP UP SALDO", callback_data="topup_menu")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="check_balance")],
        [InlineKeyboardButton("📋 RIWAYAT TRANSAKSI", callback_data="transaction_history")],
        [InlineKeyboardButton("🆘 BANTUAN", callback_data="show_help")],
    ]
    
    if is_admin(user):
        keyboard.append([InlineKeyboardButton("👑 MENU ADMIN", callback_data="admin_menu")])
    
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
        "• /order - Memulai pembelian produk\n"
        "• /topup - Top up saldo\n"
        "• /balance - Cek saldo\n\n"
        "🛒 **Cara Beli Produk:**\n"
        "1. Klik '🛒 BELI PRODUK' di menu\n"
        "2. Pilih produk dari daftar yang tersedia\n"
        "3. Masukkan nomor tujuan\n"
        "4. Konfirmasi pembelian\n"
        "5. Produk akan dikirim otomatis\n\n"
        "💰 **Cara Top Up Saldo:**\n"
        "1. Klik '💰 TOP UP SALDO' di menu\n"
        "2. Transfer ke rekening yang tertera\n"
        "3. Kirim bukti transfer\n"
        "4. Tunggu konfirmasi admin\n\n"
        "💳 **Cek Saldo:**\n"
        "Gunakan menu '💳 CEK SALDO' atau command /balance\n\n"
        "📞 **Bantuan Admin:**\n"
        "Jika mengalami kendala, hubungi admin langsung."
    )
    
    keyboard = [
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="buy_product")],
        [InlineKeyboardButton("💰 TOP UP SALDO", callback_data="topup_menu")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="check_balance")],
        [InlineKeyboardButton("⬅️ KEMBALI KE MENU", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        help_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

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
    
    keyboard = [
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="buy_product")],
        [InlineKeyboardButton("💰 TOP UP SALDO", callback_data="topup_menu")],
        [InlineKeyboardButton("⬅️ KEMBALI KE MENU", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        balance_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ============================
# TOP UP SYSTEM - DIPERBAIKI DENGAN TOMBOL
# ============================

async def topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle topup command"""
    user = update.effective_user
    
    if not context.args:
        # Show topup menu jika tidak ada args
        await show_topup_menu_from_message(update, context)
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
        
        keyboard = [
            [InlineKeyboardButton("❌ BATAL", callback_data="cancel_topup")],
            [InlineKeyboardButton("⬅️ KEMBALI", callback_data="topup_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"💰 **TOPUP REQUEST**\n\n"
            f"Jumlah: Rp {amount:,.0f}\n\n"
            f"📎 **Silakan kirim bukti transfer (foto/screenshot)**\n\n"
            f"**Rekening Tujuan:**\n"
            f"🏦 BCA - 1234567890\n"
            f"👤 NAMA ADMIN",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except ValueError:
        await update.message.reply_text("❌ Jumlah harus angka! Gunakan format: `/topup 50000`", parse_mode='Markdown')

async def show_topup_menu_from_message(update, context):
    """Show topup menu from message"""
    user = update.effective_user
    saldo = database.get_user_saldo(user.id)
    
    topup_text = (
        f"💰 **TOP UP SALDO**\n\n"
        f"💳 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
        f"📋 **Cara Top Up:**\n"
        f"1. Transfer ke rekening berikut:\n"
        f"   🏦 **Bank:** BCA\n"
        f"   🔢 **No.Rek:** 123-456-7890\n"
        f"   👤 **A/N:** NAMA ADMIN\n\n"
        f"2. Setelah transfer, kirim bukti transfer dengan command:\n"
        f"   `/topup <jumlah>`\n"
        f"   Contoh: `/topup 50000`\n\n"
        f"3. Admin akan memverifikasi dan menambahkan saldo\n\n"
        f"💡 **Informasi:**\n"
        f"• Minimal topup: Rp 10,000\n"
        f"• Maksimal topup: Rp 5,000,000\n"
        f"• Proses verifikasi: 1-15 menit"
    )
    
    keyboard = [
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="check_balance")],
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="buy_product")],
        [InlineKeyboardButton("⬅️ MENU UTAMA", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        topup_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle image upload for topup proof"""
    user = update.effective_user
    
    if 'pending_topup' not in context.user_data:
        await update.message.reply_text(
            "❌ Silakan gunakan command `/topup <jumlah>` terlebih dahulu\n"
            "Contoh: `/topup 50000`",
            parse_mode='Markdown'
        )
        return
    
    topup_data = context.user_data['pending_topup']
    
    if update.message.photo:
        # Get the largest photo
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        
        # Simpan informasi topup ke database (dalam implementasi nyata)
        # Untuk sekarang, kita beri konfirmasi saja
        
        keyboard = [
            [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="buy_product")],
            [InlineKeyboardButton("💳 CEK SALDO", callback_data="check_balance")],
            [InlineKeyboardButton("⬅️ MENU UTAMA", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **Bukti transfer diterima!**\n\n"
            f"💰 **Jumlah:** Rp {topup_data['amount']:,.0f}\n"
            f"👤 **User:** {user.full_name}\n\n"
            f"⏳ **Status:** Menunggu verifikasi admin\n"
            f"📞 Admin akan memverifikasi dalam 1-15 menit.\n\n"
            f"Terima kasih!",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # Clear pending topup
        del context.user_data['pending_topup']
        
    else:
        await update.message.reply_text("❌ Silakan kirim bukti transfer dalam format gambar/foto")

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel pending topup"""
    if 'pending_topup' in context.user_data:
        del context.user_data['pending_topup']
        
        keyboard = [
            [InlineKeyboardButton("💰 TOP UP SALDO", callback_data="topup_menu")],
            [InlineKeyboardButton("⬅️ MENU UTAMA", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ Topup request dibatalkan.",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("❌ Tidak ada topup request yang aktif.")

# ============================
# CALLBACK QUERY HANDLERS - DIPERBAIKI DENGAN TOMBOL LENGKAP
# ============================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline keyboards"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    if data == "buy_product":
        await start_order_from_callback(query, context)
    elif data == "topup_menu":
        await show_topup_menu(query, context)
    elif data == "check_balance":
        await show_user_balance(query, context)
    elif data == "transaction_history":
        await show_transaction_history(query, context)
    elif data == "show_help":
        await show_help(query, context)
    elif data == "admin_menu":
        if is_admin(user):
            await show_admin_menu(query, context)
        else:
            await query.edit_message_text("❌ Anda bukan admin.")
    elif data == "back_to_menu":
        await show_main_menu(query, context)
    elif data == "cancel_topup":
        await cancel_topup_callback(query, context)
    elif data == "start_order_command":
        await start_order_command_callback(query, context)

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
    
    try:
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
            keyboard = [
                [InlineKeyboardButton("🔄 UPDATE PRODUK", callback_data="admin_update")],
                [InlineKeyboardButton("⬅️ MENU UTAMA", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ **Produk Belum Tersedia**\n\n"
                "Silakan minta admin untuk update produk terlebih dahulu\n\n"
                "💰 **Saldo Anda:** Rp {saldo:,.0f}".format(saldo=saldo),
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        
        # Format product list message
        msg = (
            f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
            "🎮 **PRODUK TERSEDIA:**\n\n"
        )
        
        for code, name, price in produk_list:
            msg += f"▪️ **{name}**\n   Kode: `{code}` - Rp {price:,.0f}\n\n"
        
        msg += "**Klik tombol di bawah untuk mulai order:**"
        
        keyboard = [
            [InlineKeyboardButton("🛒 ORDER SEKARANG", callback_data="start_order_command")],
            [InlineKeyboardButton("💰 TOP UP SALDO", callback_data="topup_menu")],
            [InlineKeyboardButton("💳 CEK SALDO", callback_data="check_balance")],
            [InlineKeyboardButton("⬅️ KEMBALI", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            msg,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in start_order_from_callback: {e}")
        
        keyboard = [
            [InlineKeyboardButton("🔄 COBA LAGI", callback_data="buy_product")],
            [InlineKeyboardButton("⬅️ MENU UTAMA", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "❌ **Terjadi kesalahan saat mengambil data produk.**\n\n"
            "Silakan coba lagi atau hubungi admin.",
            reply_markup=reply_markup
        )

async def start_order_command_callback(query, context):
    """Start order command from callback"""
    user = query.from_user
    
    # Kirim pesan untuk memulai order
    await query.edit_message_text(
        "🛒 **MEMULAI ORDER**\n\n"
        "Ketik /order untuk memulai proses pembelian produk\n\n"
        "Atau klik tombol di bawah untuk kembali:",
        parse_mode='Markdown'
    )
    
    # Panggil order_start function
    from order_handler import order_start
    await order_start(Update(update_id=query.update_id, message=query.message), context)

async def show_topup_menu(query, context):
    """Show topup menu in callback"""
    user = query.from_user
    saldo = database.get_user_saldo(user.id)
    
    topup_text = (
        f"💰 **TOP UP SALDO**\n\n"
        f"💳 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
        f"📋 **Cara Top Up:**\n"
        f"1. Transfer ke rekening berikut:\n"
        f"   🏦 **Bank:** BCA\n"
        f"   🔢 **No.Rek:** 123-456-7890\n"
        f"   👤 **A/N:** NAMA ADMIN\n\n"
        f"2. Setelah transfer, kirim bukti transfer dengan command:\n"
        f"   `/topup <jumlah>`\n"
        f"   Contoh: `/topup 50000`\n\n"
        f"3. Admin akan memverifikasi dan menambahkan saldo\n\n"
        f"💡 **Informasi:**\n"
        f"• Minimal topup: Rp 10,000\n"
        f"• Maksimal topup: Rp 5,000,000\n"
        f"• Proses verifikasi: 1-15 menit"
    )
    
    keyboard = [
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="check_balance")],
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="buy_product")],
        [InlineKeyboardButton("⬅️ MENU UTAMA", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        topup_text,
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
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="buy_product")],
        [InlineKeyboardButton("💰 TOP UP SALDO", callback_data="topup_menu")],
        [InlineKeyboardButton("⬅️ MENU UTAMA", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        balance_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_transaction_history(query, context):
    """Show transaction history"""
    user = query.from_user
    
    history_text = (
        f"📋 **RIWAYAT TRANSAKSI**\n\n"
        f"👤 **User:** {user.full_name}\n\n"
        f"📊 **Fitur riwayat transaksi sedang dalam pengembangan.**\n\n"
        f"💡 **Fitur yang akan datang:**\n"
        f"• Riwayat top up\n"
        f"• Riwayat pembelian\n"
        f"• Filter berdasarkan tanggal\n"
        f"• Export data transaksi"
    )
    
    keyboard = [
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="buy_product")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="check_balance")],
        [InlineKeyboardButton("⬅️ MENU UTAMA", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        history_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_help(query, context):
    """Show help in callback"""
    help_text = (
        "🆘 **BANTUAN & CARA PENGGUNAAN**\n\n"
        "🛒 **Cara Beli Produk:**\n"
        "1. Klik '🛒 BELI PRODUK' di menu\n"
        "2. Pilih produk dari daftar yang tersedia\n"
        "3. Masukkan nomor tujuan\n"
        "4. Konfirmasi pembelian\n"
        "5. Produk akan dikirim otomatis\n\n"
        "💰 **Cara Top Up Saldo:**\n"
        "1. Klik '💰 TOP UP SALDO' di menu\n"
        "2. Transfer ke rekening yang tertera\n"
        "3. Kirim bukti transfer dengan command `/topup <jumlah>`\n"
        "4. Tunggu konfirmasi admin (1-15 menit)\n\n"
        "💳 **Cek Saldo:**\n"
        "Gunakan menu '💳 CEK SALDO' atau command /balance\n\n"
        "📞 **Bantuan Admin:**\n"
        "Jika mengalami kendala, hubungi admin langsung."
    )
    
    keyboard = [
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="buy_product")],
        [InlineKeyboardButton("💰 TOP UP SALDO", callback_data="topup_menu")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="check_balance")],
        [InlineKeyboardButton("⬅️ MENU UTAMA", callback_data="back_to_menu")]
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
        [InlineKeyboardButton("📦 KELOLA PRODUK", callback_data="admin_products")],
        [InlineKeyboardButton("💳 KELOLA TOPUP", callback_data="admin_topup")],
        [InlineKeyboardButton("📊 STATISTIK", callback_data="admin_stats")],
        [InlineKeyboardButton("⬅️ MENU UTAMA", callback_data="back_to_menu")]
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
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="buy_product")],
        [InlineKeyboardButton("💰 TOP UP SALDO", callback_data="topup_menu")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="check_balance")],
        [InlineKeyboardButton("📋 RIWAYAT TRANSAKSI", callback_data="transaction_history")],
        [InlineKeyboardButton("🆘 BANTUAN", callback_data="show_help")],
    ]
    
    if is_admin(user):
        keyboard.append([InlineKeyboardButton("👑 MENU ADMIN", callback_data="admin_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📱 **MENU UTAMA**\n\nPilih opsi yang diinginkan:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def cancel_topup_callback(query, context):
    """Cancel topup from callback"""
    if 'pending_topup' in context.user_data:
        del context.user_data['pending_topup']
    
    keyboard = [
        [InlineKeyboardButton("💰 TOP UP SALDO", callback_data="topup_menu")],
        [InlineKeyboardButton("⬅️ MENU UTAMA", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "❌ Topup request dibatalkan.",
        reply_markup=reply_markup
    )

# ============================
# ORDER COMMAND HANDLER
# ============================

async def order_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct order command handler"""
    user = update.effective_user
    
    # Create user in database if not exists
    database.create_user(user.id, user.username, user.full_name)
    
    # Get user balance
    saldo = database.get_user_saldo(user.id)
    
    # Get available products
    import sqlite3
    DB_PATH = "bot_topup.db"
    
    try:
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
            keyboard = [
                [InlineKeyboardButton("🔄 UPDATE PRODUK", callback_data="admin_update")],
                [InlineKeyboardButton("⬅️ MENU UTAMA", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "❌ **Produk Belum Tersedia**\n\n"
                "Silakan minta admin untuk update produk terlebih dahulu\n\n"
                "💰 **Saldo Anda:** Rp {saldo:,.0f}".format(saldo=saldo),
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        
        # Format product list message
        msg = (
            f"💰 **Saldo Anda:** Rp {saldo:,.0f}\n\n"
            "🎮 **PRODUK TERSEDIA:**\n\n"
        )
        
        for code, name, price in produk_list:
            msg += f"▪️ **{name}**\n   Kode: `{code}` - Rp {price:,.0f}\n\n"
        
        msg += "**Untuk memesan, ketik kode produk yang diinginkan**"
        
        keyboard = [
            [InlineKeyboardButton("💰 TOP UP SALDO", callback_data="topup_menu")],
            [InlineKeyboardButton("💳 CEK SALDO", callback_data="check_balance")],
            [InlineKeyboardButton("⬅️ MENU UTAMA", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            msg,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in order_command: {e}")
        
        keyboard = [
            [InlineKeyboardButton("🔄 COBA LAGI", callback_data="buy_product")],
            [InlineKeyboardButton("⬅️ MENU UTAMA", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ **Terjadi kesalahan saat mengambil data produk.**\n\n"
            "Silakan coba lagi atau hubungi admin.",
            reply_markup=reply_markup
        )

# ============================
# ECHO HANDLER (Fallback)
# ============================

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Echo the user message with menu suggestion."""
    keyboard = [
        [InlineKeyboardButton("🛒 BELI PRODUK", callback_data="buy_product")],
        [InlineKeyboardButton("💰 TOP UP SALDO", callback_data="topup_menu")],
        [InlineKeyboardButton("💳 CEK SALDO", callback_data="check_balance")],
        [InlineKeyboardButton("🆘 BANTUAN", callback_data="show_help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 Saya adalah bot pembelian produk.\n\n"
        "Gunakan tombol di bawah untuk navigasi:",
        reply_markup=reply_markup
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
    application.add_handler(CommandHandler("order", order_command))
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
    print("💰 Top Up System: READY")
    print("💳 Balance System: READY")
    print("📋 Transaction History: READY")
    print("👑 Admin Menu: READY")
    print("🔧 Bot is now running...")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

from order_handler import order_handler

def main():
    application = Application.builder().token(config.TOKEN).build()
    
    # Add order handler
    application.add_handler(order_handler.get_conversation_handler())
    application.add_handler(order_handler.get_callback_handler())
    
    # ... other handlers
    
    application.run_polling()

if __name__ == "__main__":
    main()
