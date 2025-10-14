import config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
import database
import random
import logging

logger = logging.getLogger(__name__)

# States untuk conversation
ASK_TOPUP_NOMINAL = 1

def generate_unique_amount(base_amount):
    """Generate nominal unik dengan menambahkan 3 digit random"""
    try:
        base_amount = int(base_amount)
        unique_digits = random.randint(1, 999)
        unique_amount = base_amount + unique_digits
        return unique_amount, unique_digits
    except ValueError as e:
        logger.error(f"❌ Error in generate_unique_amount: {str(e)}")
        raise  # Lempar error agar bisa ditangani di atas

async def topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mulai proses topup"""
    try:
        logger.info("🔧 topup_start dipanggil")
        
        if update.callback_query:
            query = update.callback_query
            user = query.from_user
            await query.answer()
            message_func = query.edit_message_text
            chat_id = query.message.chat_id
        else:
            user = update.message.from_user
            message_func = update.message.reply_text
            chat_id = update.message.chat_id
        
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        
        context.user_data['topup_chat_id'] = chat_id
        context.user_data['topup_user_id'] = str(user.id)
        
        await message_func(
            "💳 **TOP UP SALDO**\n\n"
            "Masukkan nominal top up (angka saja):\n"
            "✅ Contoh: `100000` untuk Rp 100.000\n\n"
            "💰 **PENTING:** Nominal akan ditambahkan kode unik untuk memudahkan verifikasi.\n\n"
            "❌ Ketik /cancel untuk membatalkan",
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ topup_start selesai, menunggu input nominal dari user {user.id}")
        return ASK_TOPUP_NOMINAL
        
    except Exception as e:
        logger.error(f"❌ Error in topup_start: {str(e)}")
        if update.callback_query:
            await update.callback_query.message.reply_text("❌ Terjadi error, silakan coba lagi.")
        else:
            await update.message.reply_text("❌ Terjadi error, silakan coba lagi.")
        return ConversationHandler.END

async def topup_nominal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process nominal topup"""
    try:
        logger.info(f"🔧 topup_nominal dipanggil dengan pesan: {update.message.text if update.message else 'No message'}")
        
        if not update.message:  # Pengecekan tambahan untuk keamanan
            logger.error("❌ No message found in update")
            await context.bot.send_message(chat_id=context.user_data.get('topup_chat_id'), text="❌ Error: Pesan tidak ditemukan.")
            return ConversationHandler.END
        
        user = update.message.from_user
        nominal_input = update.message.text.strip()
        
        logger.info(f"📥 User {user.id} mengirim: {nominal_input}")
        logger.info(f"📊 Context user_data: {context.user_data}")
        
        if nominal_input.lower() == '/cancel':
            await topup_cancel(update, context)
            return ConversationHandler.END
            
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
        
        if base_amount < 10000:
            await update.message.reply_text(
                "❌ **Nominal terlalu kecil!**\n\n"
                "Minimum top up adalah Rp 10.000\n\n"
                "Silakan masukkan nominal yang valid:",
                parse_mode='Markdown'
            )
            return ASK_TOPUP_NOMINAL
        
        # Tambahkan batas maksimum, misalnya Rp 1.000.000 untuk keamanan
        if base_amount > 1000000:
            await update.message.reply_text(
                "❌ **Nominal terlalu besar!**\n\n"
                "Maksimum top up adalah Rp 1.000.000. Silakan masukkan nominal yang valid.",
                parse_mode='Markdown'
            )
            return ASK_TOPUP_NOMINAL
        
        unique_amount, unique_digits = generate_unique_amount(base_amount)
        
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        request_id = database.create_topup_request(
            user_id, 
            base_amount,
            unique_amount,
            unique_digits,
            "MANUAL"
        )
        
        logger.info(f"✅ Topup request dibuat: ID {request_id} untuk user {user.id}")
        
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
        
        await send_admin_notification(context, request_id, user, base_amount, unique_amount, unique_digits)
        
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"❌ Error in topup_nominal: {str(e)}")
        await update.message.reply_text(
            f"❌ **Error System**\n\n"
            f"Terjadi kesalahan: {str(e)}\n\n"
            f"Silakan coba lagi nanti.",
            parse_mode='Markdown'
        )
    
    return ConversationHandler.END

# Sisanya dari kode Anda sudah baik, jadi saya hanya copy-paste dengan sedikit penyesuaian jika diperlukan.

async def send_admin_notification(context: ContextTypes.DEFAULT_TYPE, request_id, user, base_amount, unique_amount, unique_digits):
    """Kirim notifikasi ke admin"""
    try:
        if not config.ADMIN_TELEGRAM_IDS:  # Pengecekan jika list admin kosong
            logger.warning("❌ Daftar admin kosong, notifikasi tidak dikirim.")
            return
        
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
        
        for admin_id in config.ADMIN_TELEGRAM_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=notification_text,
                    parse_mode='Markdown'
                )
                logger.info(f"✅ Notifikasi terkirim ke admin {admin_id}")
            except Exception as e:
                logger.error(f"❌ Gagal kirim notifikasi ke admin {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"❌ Error in send_admin_notification: {str(e)}")

# Fungsi lainnya (topup_cancel, show_topup_menu, dll.) sudah baik, jadi tidak saya ubah.

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
    allow_reentry=True,
    per_message=False
)
