import config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
import requests
import base64
from io import BytesIO
import database
import random
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# States untuk conversation
ASK_TOPUP_NOMINAL = 1

def generate_unique_amount(base_amount):
    """Generate nominal unik dengan menambahkan 3 digit random"""
    base_amount = int(base_amount)
    unique_digits = random.randint(1, 999)
    unique_amount = base_amount + unique_digits
    return unique_amount, unique_digits

async def topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            "Contoh: `10000` untuk Rp 10.000\n\n"
            "💰 **Nominal akan ditambahkan kode unik** untuk memudahkan verifikasi.\n\n"
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
                "Contoh: `50000` untuk Rp 50.000\n\n"
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
        
        # Generate nominal unik
        unique_amount, unique_digits = generate_unique_amount(base_amount)
        
        # Simpan data di context
        context.user_data['topup_data'] = {
            'user_id': str(user.id),
            'user_name': user.full_name,
            'username': user.username,
            'base_amount': base_amount,
            'unique_amount': unique_amount,
            'unique_digits': unique_digits
        }
        
        # Konfirmasi ke user
        await update.message.reply_text(
            f"💰 **KONFIRMASI TOP UP**\n\n"
            f"👤 **User:** {user.full_name}\n"
            f"📊 **Nominal Dasar:** Rp {base_amount:,}\n"
            f"🔢 **Kode Unik:** {unique_digits:03d}\n"
            f"💵 **Total Transfer:** Rp {unique_amount:,}\n\n"
            f"**Silakan transfer tepat Rp {unique_amount:,}**\n"
            f"QRIS akan segera digenerate...",
            parse_mode='Markdown'
        )
        
        # Generate QRIS
        payload = {
            "amount": str(unique_amount),
            "qris_statis": config.QRIS_STATIS
        }
        
        logger.info(f"Mengirim request QRIS dengan payload: {payload}")
        
        resp = requests.post("https://qrisku.my.id/api", json=payload, timeout=30)
        result = resp.json()
        
        logger.info(f"Response QRIS: {result}")
        
        if result.get("status") == "success" and "qris_base64" in result:
            qris_base64 = result["qris_base64"]
            qris_bytes = base64.b64decode(qris_base64)
            bio = BytesIO(qris_bytes)
            bio.name = 'qris.png'
            
            # Simpan ke database
            user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
            request_id = database.create_topup_request(
                user_id, 
                base_amount,
                unique_amount,
                unique_digits,
                qris_base64
            )
            
            # Simpan request_id di context
            context.user_data['topup_data']['request_id'] = request_id
            
            # Kirim QRIS ke user
            await update.message.reply_photo(
                photo=bio,
                caption=f"📱 **QRIS TOP UP**\n\n"
                       f"💰 **Total Transfer:** Rp {unique_amount:,}\n"
                       f"🔢 **Kode Unik:** {unique_digits:03d}\n\n"
                       f"⚠️ **Transfer tepat Rp {unique_amount:,}**\n"
                       f"Saldo akan otomatis bertambah setelah admin verifikasi.\n\n"
                       f"📋 **ID Request:** `{request_id}`",
                parse_mode='Markdown'
            )
            
            # Kirim notifikasi ke admin
            await send_admin_notification(context, request_id)
            
        else:
            error_msg = result.get('message', 'Unknown error')
            logger.error(f"QRIS generation failed: {error_msg}")
            await update.message.reply_text(
                f"❌ **Gagal generate QRIS**\n\n"
                f"Error: {error_msg}\n\n"
                f"Silakan coba lagi atau hubungi admin.",
                parse_mode='Markdown'
            )
            
    except requests.exceptions.Timeout:
        logger.error("QRIS request timeout")
        await update.message.reply_text(
            "❌ **Timeout**\n\n"
            "Server QRIS sedang sibuk. Silakan coba lagi dalam beberapa menit.",
            parse_mode='Markdown'
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"QRIS request error: {e}")
        await update.message.reply_text(
            "❌ **Error Koneksi**\n\n"
            "Gagal terhubung ke server QRIS. Silakan coba lagi.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in topup_nominal: {str(e)}")
        await update.message.reply_text(
            f"❌ **Error System**\n\n"
            f"Terjadi kesalahan: {str(e)}\n\n"
            f"Silakan coba lagi nanti.",
            parse_mode='Markdown'
        )
    
    return ConversationHandler.END

async def send_admin_notification(context: ContextTypes.DEFAULT_TYPE, request_id):
    """Kirim notifikasi ke semua admin"""
    try:
        topup_data = context.user_data.get('topup_data', {})
        
        if not topup_data:
            logger.error("No topup_data found for admin notification")
            return
        
        user_name = topup_data.get('user_name', 'Unknown')
        username = topup_data.get('username', 'Unknown')
        base_amount = topup_data.get('base_amount', 0)
        unique_amount = topup_data.get('unique_amount', 0)
        unique_digits = topup_data.get('unique_digits', 0)
        
        notification_text = (
            f"🔔 **PERMINTAAN TOP UP BARU**\n\n"
            f"👤 **User:** {user_name}\n"
            f"📛 **Username:** @{username}\n"
            f"💰 **Nominal Dasar:** Rp {base_amount:,}\n"
            f"🔢 **Kode Unik:** {unique_digits:03d}\n"
            f"💵 **Total Transfer:** Rp {unique_amount:,}\n"
            f"📋 **ID Request:** `{request_id}`\n"
            f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}\n\n"
            f"Gunakan `/approve_topup {request_id}` untuk approve atau `/cancel_topup {request_id}` untuk cancel."
        )
        
        # Kirim ke semua admin
        for admin_id in config.ADMIN_TELEGRAM_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=notification_text,
                    parse_mode='Markdown'
                )
                logger.info(f"Notifikasi terkirim ke admin {admin_id}")
            except Exception as e:
                logger.error(f"Gagal kirim notifikasi ke admin {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error in send_admin_notification: {str(e)}")

async def topup_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        
        # Clear user data
        context.user_data.clear()
        
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
            [InlineKeyboardButton("⚙️ Kelola Topup", callback_data="manage_topup")],
            [InlineKeyboardButton("🔙 Kembali", callback_data="menu_main")]
        ])
        
        await query.edit_message_text(
            "💰 **Menu Topup**\n\n"
            "Pilih jenis topup yang tersedia:",
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
        await query.answer("Fitur kelola topup akan segera hadir!")
        
        # Untuk sementara, kembali ke menu topup
        await show_topup_menu(update, context)
        
    except Exception as e:
        logger.error(f"Error in show_manage_topup: {str(e)}")
        await query.message.reply_text("❌ Terjadi error, silakan coba lagi.")

# Handler untuk sub-menu topup
async def handle_topup_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memulai topup manual"""
    try:
        query = update.callback_query
        await query.answer()
        await topup_start(update, context)
    except Exception as e:
        logger.error(f"Error in handle_topup_manual: {str(e)}")
        await query.message.reply_text("❌ Terjadi error, silakan coba lagi.")

async def handle_topup_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Fitur riwayat topup akan segera hadir!")

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
