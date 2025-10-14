import config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
import requests
import base64
from io import BytesIO
import database
import random
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

async def generate_qris(unique_amount):
    """Generate QRIS menggunakan API"""
    try:
        logger.info(f"🔧 [QRIS] Generating QRIS untuk amount: {unique_amount}")
        
        # Payload untuk API QRIS
        payload = {
            "amount": str(unique_amount),
            "qris_statis": config.QRIS_STATIS
        }
        
        logger.info(f"🔧 [QRIS] Payload: {payload}")
        
        # Kirim request ke API QRIS
        response = requests.post(
            "https://qrisku.my.id/api",
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        logger.info(f"🔧 [QRIS] Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"🔧 [QRIS] API Response: {result}")
            
            if result.get("status") == "success" and "qris_base64" in result:
                qris_base64 = result["qris_base64"]
                logger.info("✅ [QRIS] QRIS berhasil digenerate")
                return qris_base64, None
            else:
                error_msg = result.get('message', 'Unknown error from QRIS API')
                logger.error(f"❌ [QRIS] API Error: {error_msg}")
                return None, error_msg
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ [QRIS] HTTP Error: {error_msg}")
            return None, error_msg
            
    except requests.exceptions.Timeout:
        error_msg = "Timeout: Server QRIS tidak merespons"
        logger.error(f"❌ [QRIS] {error_msg}")
        return None, error_msg
    except requests.exceptions.ConnectionError:
        error_msg = "Connection Error: Tidak dapat terhubung ke server QRIS"
        logger.error(f"❌ [QRIS] {error_msg}")
        return None, error_msg
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"❌ [QRIS] {error_msg}")
        return None, error_msg

async def topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mulai proses topup"""
    try:
        logger.info("🔧 [TOPUP_START] Dipanggil")
        
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
        logger.info(f"🔧 [TOPUP_START] User: {user.id}, User ID: {user_id}")
        
        await message_func(
            "💳 **TOP UP SALDO**\n\n"
            "Masukkan nominal top up (angka saja):\n"
            "✅ Contoh: `100000` untuk Rp 100.000\n\n"
            "💰 **PENTING:** Nominal akan ditambahkan kode unik untuk memudahkan verifikasi.\n\n"
            "❌ Ketik /cancel untuk membatalkan",
            parse_mode='Markdown'
        )
        
        logger.info(f"🔧 [TOPUP_START] Selesai, menunggu input nominal dari user {user.id}")
        return ASK_TOPUP_NOMINAL
        
    except Exception as e:
        logger.error(f"❌ [TOPUP_START] Error: {str(e)}")
        if update.callback_query:
            await update.callback_query.message.reply_text("❌ Terjadi error, silakan coba lagi.")
        else:
            await update.message.reply_text("❌ Terjadi error, silakan coba lagi.")
        return ConversationHandler.END

async def topup_nominal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process nominal topup dengan QRIS"""
    try:
        user = update.message.from_user
        nominal_input = update.message.text.strip()
        
        logger.info(f"🔧 [TOPUP_NOMINAL] Dipanggil - User: {user.id}, Input: {nominal_input}")
        
        # Cek jika user ingin cancel
        if nominal_input.lower() == '/cancel':
            logger.info(f"🔧 [TOPUP_NOMINAL] User {user.id} membatalkan")
            await topup_cancel(update, context)
            return ConversationHandler.END
            
        # Validasi input
        if not nominal_input.isdigit() or int(nominal_input) <= 0:
            logger.warning(f"🔧 [TOPUP_NOMINAL] Input tidak valid: {nominal_input}")
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
            logger.warning(f"🔧 [TOPUP_NOMINAL] Nominal terlalu kecil: {base_amount}")
            await update.message.reply_text(
                "❌ **Nominal terlalu kecil!**\n\n"
                "Minimum top up adalah Rp 10.000\n\n"
                "Silakan masukkan nominal yang valid:",
                parse_mode='Markdown'
            )
            return ASK_TOPUP_NOMINAL
        
        # Generate nominal unik
        unique_digits = random.randint(1, 999)
        unique_amount = base_amount + unique_digits
        
        logger.info(f"🔧 [TOPUP_NOMINAL] Generated: Base={base_amount}, Unique={unique_amount}, Digits={unique_digits}")
        
        # Kirim pesan sedang memproses
        processing_msg = await update.message.reply_text(
            "🔄 **Membuat QRIS...**\n\n"
            "Sedang generate kode QRIS untuk pembayaran Anda...",
            parse_mode='Markdown'
        )
        
        # Generate QRIS
        qris_base64, qris_error = await generate_qris(unique_amount)
        
        # Simpan ke database
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        logger.info(f"🔧 [TOPUP_NOMINAL] User ID dari database: {user_id}")
        
        if qris_base64:
            # Jika QRIS berhasil digenerate
            request_id = database.create_topup_request(
                user_id, 
                base_amount,
                unique_amount,
                unique_digits,
                qris_base64
            )
            
            if request_id is None:
                logger.error("❌ [TOPUP_NOMINAL] Gagal membuat topup request di database")
                raise Exception("Gagal membuat request topup di database")
            
            logger.info(f"✅ [TOPUP_NOMINAL] Topup request dengan QRIS dibuat: ID {request_id}")
            
            # Hapus pesan processing
            await processing_msg.delete()
            
            # Convert base64 to image
            qris_bytes = base64.b64decode(qris_base64)
            bio = BytesIO(qris_bytes)
            bio.name = 'qris.png'
            
            # Kirim QRIS ke user
            await update.message.reply_photo(
                photo=bio,
                caption=f"📱 **QRIS TOP UP**\n\n"
                       f"💰 **Total Transfer:** Rp {unique_amount:,}\n"
                       f"🔢 **Kode Unik:** {unique_digits:03d}\n"
                       f"📋 **ID Request:** `{request_id}`\n\n"
                       f"⚠️ **Transfer tepat Rp {unique_amount:,}**\n"
                       f"Saldo akan otomatis bertambah setelah admin verifikasi.\n\n"
                       f"⏰ **QRIS berlaku 24 jam**",
                parse_mode='Markdown'
            )
            
        else:
            # Fallback ke transfer manual jika QRIS gagal
            request_id = database.create_topup_request(
                user_id, 
                base_amount,
                unique_amount,
                unique_digits,
                None  # No QRIS
            )
            
            if request_id is None:
                logger.error("❌ [TOPUP_NOMINAL] Gagal membuat topup request di database")
                raise Exception("Gagal membuat request topup di database")
            
            logger.info(f"✅ [TOPUP_NOMINAL] Topup request manual dibuat: ID {request_id}")
            
            # Hapus pesan processing
            await processing_msg.delete()
            
            # Kirim instruksi transfer manual
            await update.message.reply_text(
                f"💰 **TOP UP DITERIMA**\n\n"
                f"👤 **User:** {user.full_name}\n"
                f"📊 **Nominal Dasar:** Rp {base_amount:,}\n"
                f"🔢 **Kode Unik:** {unique_digits:03d}\n"
                f"💵 **Total Transfer:** Rp {unique_amount:,}\n"
                f"📋 **ID Request:** `{request_id}`\n\n"
                f"❌ **QRIS Gagal:** {qris_error}\n\n"
                f"⚠️ **SILAKAN TRANSFER MANUAL KE:**\n"
                f"🏦 Bank: BCA\n"
                f"📛 Nama: AMIFI STORE\n"
                f"🔢 Rekening: 1234567890\n"
                f"💵 **Jumlah:** Rp {unique_amount:,}\n\n"
                f"Saldo akan ditambahkan setelah admin verifikasi.",
                parse_mode='Markdown'
            )
        
        # Kirim notifikasi ke admin
        await send_admin_notification(context, request_id, user, base_amount, unique_amount, unique_digits, qris_base64 is not None)
        
        logger.info(f"✅ [TOPUP_NOMINAL] Proses selesai untuk user {user.id}")
        
    except Exception as e:
        logger.error(f"❌ [TOPUP_NOMINAL] Error: {str(e)}", exc_info=True)
        await update.message.reply_text(
            f"❌ **Error System**\n\n"
            f"Terjadi kesalahan: {str(e)}\n\n"
            f"Silakan coba lagi nanti.",
            parse_mode='Markdown'
        )
    
    return ConversationHandler.END

async def send_admin_notification(context: ContextTypes.DEFAULT_TYPE, request_id, user, base_amount, unique_amount, unique_digits, has_qris=True):
    """Kirim notifikasi ke admin"""
    try:
        method = "QRIS" if has_qris else "MANUAL"
        
        notification_text = (
            f"🔔 **PERMINTAAN TOP UP BARU**\n\n"
            f"👤 **User:** {user.full_name}\n"
            f"📛 **Username:** @{user.username if user.username else 'N/A'}\n"
            f"💰 **Nominal Dasar:** Rp {base_amount:,}\n"
            f"🔢 **Kode Unik:** {unique_digits:03d}\n"
            f"💵 **Total Transfer:** Rp {unique_amount:,}\n"
            f"📋 **ID Request:** `{request_id}`\n"
            f"📱 **Metode:** {method}\n\n"
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
                logger.info(f"✅ Notifikasi terkirim ke admin {admin_id}")
            except Exception as e:
                logger.error(f"❌ Gagal kirim notifikasi ke admin {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"❌ Error in send_admin_notification: {str(e)}")

async def topup_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Batalkan topup"""
    try:
        logger.info("🔧 [TOPUP_CANCEL] Dipanggil")
        
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
        logger.error(f"❌ [TOPUP_CANCEL] Error: {str(e)}")
    
    return ConversationHandler.END

# Handler untuk menu topup
async def show_topup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu topup utama"""
    try:
        query = update.callback_query
        await query.answer()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Topup QRIS", callback_data="topup_manual")],
            [InlineKeyboardButton("📋 Riwayat Topup", callback_data="topup_history")],
            [InlineKeyboardButton("🔙 Kembali", callback_data="menu_main")]
        ])
        
        await query.edit_message_text(
            "💰 **Menu Topup**\n\n"
            "Pilih jenis topup:\n\n"
            "💳 **Topup QRIS** - Bayar dengan scan QRIS\n"
            "📋 **Riwayat** - Lihat history topup\n\n"
            "Pilih opsi di bawah:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"❌ Error in show_topup_menu: {str(e)}")
        await query.message.reply_text("❌ Terjadi error, silakan coba lagi.")

async def show_manage_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu kelola topup"""
    try:
        query = update.callback_query
        await query.answer("Fitur kelola topup untuk admin akan segera hadir!")
        
    except Exception as e:
        logger.error(f"❌ Error in show_manage_topup: {str(e)}")

async def handle_topup_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memulai topup QRIS"""
    try:
        logger.info("🔧 [HANDLE_TOPUP_MANUAL] Dipanggil")
        query = update.callback_query
        await query.answer()
        await topup_start(update, context)
    except Exception as e:
        logger.error(f"❌ [HANDLE_TOPUP_MANUAL] Error: {str(e)}")
        await update.callback_query.message.reply_text("❌ Terjadi error, silakan coba lagi.")

async def handle_topup_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk riwayat topup"""
    try:
        query = update.callback_query
        await query.answer("Fitur riwayat topup akan segera hadir!")
    except Exception as e:
        logger.error(f"❌ Error in handle_topup_history: {str(e)}")

# ... (import statements dan kode lainnya) ...

# Conversation handler untuk topup - INI HARUS DI AKHIR FILE
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
