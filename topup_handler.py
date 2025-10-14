import config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
import database
import logging

logger = logging.getLogger(__name__)

# States untuk conversation
ASK_TOPUP_NOMINAL = 1

async def topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mulai proses topup"""
    try:
        # Handle both command and callback
        if update.callback_query:
            query = update.callback_query
            user = query.from_user
            await query.answer()
            message_func = query.edit_message_text
        else:
            user = update.message.from_user
            message_func = update.message.reply_text
        
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        
        await message_func(
            "💳 **TOP UP SALDO**\n\n"
            "Masukkan nominal top up (angka saja):\n"
            "✅ Contoh: `100000` untuk Rp 100.000\n\n"
            "💰 **PENTING:** Nominal akan ditambahkan kode unik untuk memudahkan verifikasi.\n\n"
            "❌ Ketik /cancel untuk membatalkan",
            parse_mode='Markdown'
        )
        return ASK_TOPUP_NOMINAL
        
    except Exception as e:
        logger.error(f"Error in topup_start: {str(e)}")
        if update.callback_query:
            await update.callback_query.message.reply_text("❌ Terjadi error, silakan coba lagi.")
        else:
            await update.message.reply_text("❌ Terjadi error, silakan coba lagi.")
        return ConversationHandler.END

async def topup_nominal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process nominal topup"""
    try:
        user = update.message.from_user
        nominal_input = update.message.text.strip()
        
        # Cek jika user ingin cancel
        if nominal_input.lower() == '/cancel':
            await topup_cancel(update, context)
            return ConversationHandler.END
            
        # Validasi input
        if not nominal_input.isdigit() or int(nominal_input) <= 0:
            await update.message.reply_text(
                "❌ **Format tidak valid!**\n\n"
                "Masukkan hanya angka dan lebih dari 0.\n"
                "✅ Contoh: `50000` untuk Rp 50.000\n\n"
                "Silakan masukkan lagi:",
                parse_mode='Markdown'
            )
            return ASK_TOPUP_NOMINAL
        
        base_amount = int(nominal_input)
        
        # Validasi minimum amount
        if base_amount < 10000:
            await update.message.reply_text(
                "❌ **Nominal terlalu kecil!**\n\n"
                "Minimum top up adalah Rp 10.000\n\n"
                "Silakan masukkan nominal yang valid:",
                parse_mode='Markdown'
            )
            return ASK_TOPUP_NOMINAL
        
        # Generate nominal unik (sederhana dulu)
        import random
        unique_digits = random.randint(1, 999)
        unique_amount = base_amount + unique_digits
        
        # Simpan ke database
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        request_id = database.create_topup_request(
            user_id, 
            base_amount,
            unique_amount,
            unique_digits,
            "MANUAL"  # Untuk sementara tanpa QRIS
        )
        
        # Kirim konfirmasi ke user
        await update.message.reply_text(
            f"💰 **TOP UP DITERIMA**\n\n"
            f"👤 **User:** {user.full_name}\n"
            f"📊 **Nominal Dasar:** Rp {base_amount:,}\n"
            f"🔢 **Kode Unik:** {unique_digits:03d}\n"
            f"💵 **Total Transfer:** Rp {unique_amount:,}\n"
            f"📋 **ID Request:** `{request_id}`\n\n"
            f"⚠️ **SILAKAN TRANSFER KE:**\n"
            f"🏦 Bank: BCA\n"
            f"📛 Nama: AMIFI STORE\n"
            f"🔢 Rekening: 1234567890\n"
            f"💵 **Jumlah:** Rp {unique_amount:,}\n\n"
            f"Saldo akan ditambahkan setelah admin verifikasi.",
            parse_mode='Markdown'
        )
        
        # Kirim notifikasi ke admin
        await send_admin_notification(context, request_id, user, base_amount, unique_amount, unique_digits)
        
    except Exception as e:
        logger.error(f"Error in topup_nominal: {str(e)}")
        await update.message.reply_text(
            f"❌ **Error System**\n\n"
            f"Terjadi kesalahan: {str(e)}\n\n"
            f"Silakan coba lagi nanti.",
            parse_mode='Markdown'
        )
    
    return ConversationHandler.END

async def send_admin_notification(context: ContextTypes.DEFAULT_TYPE, request_id, user, base_amount, unique_amount, unique_digits):
    """Kirim notifikasi ke admin"""
    try:
        notification_text = (
            f"🔔 **PERMINTAAN TOP UP BARU**\n\n"
            f"👤 **User:** {user.full_name}\n"
            f"📛 **Username:** @{user.username if user.username else 'N/A'}\n"
            f"💰 **Nominal Dasar:** Rp {base_amount:,}\n"
            f"🔢 **Kode Unik:** {unique_digits:03d}\n"
            f"💵 **Total Transfer:** Rp {unique_amount:,}\n"
            f"📋 **ID Request:** `{request_id}`\n\n"
            f"Gunakan `/approve_topup {request_id}` untuk approve."
        )
        
        # Kirim ke semua admin
        for admin_id in config.ADMIN_TELEGRAM_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=notification_text,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Gagal kirim notifikasi ke admin {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error in send_admin_notification: {str(e)}")

async def topup_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Batalkan topup"""
    try:
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            message_func = query.edit_message_text
        else:
            message_func = update.message.reply_text
            
        await message_func(
            "❌ **Top Up Dibatalkan**\n\n"
            "Ketik `/topup` atau gunakan menu untuk memulai kembali.",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in topup_cancel: {str(e)}")
    
    return ConversationHandler.END

# Handler untuk menu topup
async def show_topup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu topup utama"""
    try:
        query = update.callback_query
        await query.answer()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Topup Manual", callback_data="topup_manual")],
            [InlineKeyboardButton("📋 Riwayat Topup", callback_data="topup_history")],
            [InlineKeyboardButton("🔙 Kembali", callback_data="menu_main")]
        ])
        
        await query.edit_message_text(
            "💰 **Menu Topup**\n\n"
            "Pilih jenis topup:\n\n"
            "💳 **Topup Manual** - Transfer manual ke rekening\n"
            "📋 **Riwayat** - Lihat history topup\n\n"
            "Pilih opsi di bawah:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in show_topup_menu: {str(e)}")
        await query.message.reply_text("❌ Terjadi error, silakan coba lagi.")

async def show_manage_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu kelola topup"""
    try:
        query = update.callback_query
        await query.answer("Fitur kelola topup untuk admin akan segera hadir!")
        
    except Exception as e:
        logger.error(f"Error in show_manage_topup: {str(e)}")

async def handle_topup_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memulai topup manual"""
    try:
        query = update.callback_query
        await query.answer()
        await topup_start(update, context)
    except Exception as e:
        logger.error(f"Error in handle_topup_manual: {str(e)}")

async def handle_topup_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk riwayat topup"""
    try:
        query = update.callback_query
        await query.answer("Fitur riwayat topup akan segera hadir!")
    except Exception as e:
        logger.error(f"Error in handle_topup_history: {str(e)}")

# Conversation handler untuk topup
topup_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler('topup', topup_start),
        CallbackQueryHandler(handle_topup_manual, pattern='^topup_manual$')
    ],
    states={
        ASK_TOPUP_NOMINAL: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, topup_nominal)
        ]
    },
    fallbacks=[CommandHandler('cancel', topup_cancel)],
    allow_reentry=True
)
