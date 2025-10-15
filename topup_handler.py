import config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
import requests
import base64
from io import BytesIO
import database
import random
import logging
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

# States untuk conversation
ASK_TOPUP_NOMINAL, CONFIRM_TOPUP = range(2)

def generate_unique_amount(base_amount):
    """Generate nominal unik dengan menambahkan 3 digit random"""
    try:
        base_amount = int(base_amount)
        unique_digits = random.randint(1, 999)
        unique_amount = base_amount + unique_digits
        return unique_amount, unique_digits
    except Exception as e:
        logger.error(f"Error generating unique amount: {e}")
        return base_amount, 0

async def generate_qris(unique_amount):
    """Generate QRIS menggunakan API dengan error handling"""
    try:
        logger.info(f"🔧 [QRIS] Generating QRIS untuk amount: {unique_amount}")
        
        # Payload untuk API QRIS
        payload = {
            "amount": str(unique_amount),
            "qris_statis": getattr(config, 'QRIS_STATIS', '')
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
    """Mulai proses topup - FIXED VERSION"""
    try:
        logger.info("🔧 [TOPUP_START] Dipanggil")
        
        # Handle both command and callback
        if update.callback_query:
            query = update.callback_query
            user = query.from_user
            await query.answer()
            # Use reply_text for callback queries to avoid edit issues
            await query.message.reply_text(
                "💳 **TOP UP SALDO**\n\n"
                "Masukkan nominal top up (angka saja):\n"
                "✅ Contoh: `100000` untuk Rp 100.000\n\n"
                "💰 **PENTING:** Nominal akan ditambahkan kode unik untuk memudahkan verifikasi.\n\n"
                "❌ Ketik /cancel untuk membatalkan",
                parse_mode='Markdown'
            )
        else:
            user = update.message.from_user
            await update.message.reply_text(
                "💳 **TOP UP SALDO**\n\n"
                "Masukkan nominal top up (angka saja):\n"
                "✅ Contoh: `100000` untuk Rp 100.000\n\n"
                "💰 **PENTING:** Nominal akan ditambahkan kode unik untuk memudahkan verifikasi.\n\n"
                "❌ Ketik /cancel untuk membatalkan",
                parse_mode='Markdown'
            )
        
        # Create or get user
        user_id = database.get_or_create_user(str(user.id), user.username or "", user.full_name or "")
        logger.info(f"🔧 [TOPUP_START] User: {user.id}, User ID: {user_id}")
        
        logger.info(f"✅ [TOPUP_START] Conversation state ASK_TOPUP_NOMINAL dimulai untuk user {user.id}")
        return ASK_TOPUP_NOMINAL
        
    except Exception as e:
        logger.error(f"❌ [TOPUP_START] Error: {str(e)}", exc_info=True)
        error_message = "❌ Terjadi error, silakan coba lagi."
        if update.callback_query:
            await update.callback_query.message.reply_text(error_message)
        else:
            await update.message.reply_text(error_message)
        return ConversationHandler.END

async def topup_nominal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process nominal topup dengan QRIS - FIXED VERSION"""
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
        
        # Validasi maksimum amount
        if base_amount > 10000000:  # 10 juta
            logger.warning(f"🔧 [TOPUP_NOMINAL] Nominal terlalu besar: {base_amount}")
            await update.message.reply_text(
                "❌ **Nominal terlalu besar!**\n\n"
                "Maksimum top up adalah Rp 10.000.000\n\n"
                "Silakan masukkan nominal yang lebih kecil:",
                parse_mode='Markdown'
            )
            return ASK_TOPUP_NOMINAL
        
        # Generate nominal unik
        unique_amount, unique_digits = generate_unique_amount(base_amount)
        
        logger.info(f"🔧 [TOPUP_NOMINAL] Generated: Base={base_amount}, Unique={unique_amount}, Digits={unique_digits}")
        
        # Simpan ke context untuk konfirmasi
        context.user_data['topup_data'] = {
            'base_amount': base_amount,
            'unique_amount': unique_amount,
            'unique_digits': unique_digits,
            'user_id': str(user.id)
        }
        
        # Konfirmasi nominal
        keyboard = [
            [
                InlineKeyboardButton("✅ Lanjutkan", callback_data="confirm_topup"),
                InlineKeyboardButton("❌ Batalkan", callback_data="cancel_topup")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"💰 **KONFIRMASI TOP UP**\n\n"
            f"Nominal dasar: Rp {base_amount:,}\n"
            f"Kode unik: {unique_digits:03d}\n"
            f"**Total transfer: Rp {unique_amount:,}**\n\n"
            f"Apakah Anda ingin melanjutkan?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return CONFIRM_TOPUP
        
    except Exception as e:
        logger.error(f"❌ [TOPUP_NOMINAL] Error: {str(e)}", exc_info=True)
        await update.message.reply_text(
            f"❌ **Error System**\n\n"
            f"Terjadi kesalahan: {str(e)}\n\n"
            f"Silakan coba lagi nanti.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

async def handle_topup_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle konfirmasi topup dari user"""
    try:
        query = update.callback_query
        await query.answer()
        data = query.data
        
        if data == "cancel_topup":
            await query.edit_message_text("❌ **Top Up Dibatalkan**")
            return ConversationHandler.END
        
        # Ambil data dari context
        topup_data = context.user_data.get('topup_data', {})
        if not topup_data:
            await query.edit_message_text("❌ **Data tidak ditemukan. Silakan mulai ulang.**")
            return ConversationHandler.END
        
        base_amount = topup_data['base_amount']
        unique_amount = topup_data['unique_amount']
        unique_digits = topup_data['unique_digits']
        user_id = topup_data['user_id']
        
        # Kirim pesan sedang memproses
        processing_msg = await query.message.reply_text(
            "🔄 **Membuat QRIS...**\n\n"
            "Sedang generate kode QRIS untuk pembayaran Anda...",
            parse_mode='Markdown'
        )
        
        # Generate QRIS
        qris_base64, qris_error = await generate_qris(unique_amount)
        
        if qris_base64:
            # Jika QRIS berhasil digenerate
            request_id = create_topup_request_compatible(
                user_id, 
                base_amount,
                unique_amount,
                unique_digits,
                qris_base64
            )
            
            if request_id is None:
                logger.error("❌ [TOPUP_CONFIRM] Gagal membuat topup request di database")
                await processing_msg.delete()
                await query.message.reply_text(
                    "❌ **Gagal membuat request topup.**\n\nSilakan coba lagi nanti.",
                    parse_mode='Markdown'
                )
                return ConversationHandler.END
            
            logger.info(f"✅ [TOPUP_CONFIRM] Topup request dengan QRIS dibuat: ID {request_id}")
            
            # Hapus pesan processing
            await processing_msg.delete()
            
            # Convert base64 to image
            try:
                qris_bytes = base64.b64decode(qris_base64)
                bio = BytesIO(qris_bytes)
                bio.name = 'qris.png'
                
                # Kirim QRIS ke user
                await query.message.reply_photo(
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
                
            except Exception as e:
                logger.error(f"❌ [TOPUP_CONFIRM] Error processing QRIS image: {e}")
                await query.message.reply_text(
                    f"📱 **TOP UP DITERIMA**\n\n"
                    f"💰 **Total Transfer:** Rp {unique_amount:,}\n"
                    f"🔢 **Kode Unik:** {unique_digits:03d}\n"
                    f"📋 **ID Request:** `{request_id}`\n\n"
                    f"⚠️ **Transfer tepat Rp {unique_amount:,}**\n"
                    f"Saldo akan otomatis bertambah setelah admin verifikasi.\n\n"
                    f"❌ QRIS gagal ditampilkan, silakan hubungi admin.",
                    parse_mode='Markdown'
                )
            
        else:
            # Fallback ke transfer manual jika QRIS gagal
            request_id = create_topup_request_compatible(
                user_id, 
                base_amount,
                unique_amount,
                unique_digits,
                None  # No QRIS
            )
            
            if request_id is None:
                logger.error("❌ [TOPUP_CONFIRM] Gagal membuat topup request di database")
                await processing_msg.delete()
                await query.message.reply_text(
                    "❌ **Gagal membuat request topup.**\n\nSilakan coba lagi nanti.",
                    parse_mode='Markdown'
                )
                return ConversationHandler.END
            
            logger.info(f"✅ [TOPUP_CONFIRM] Topup request manual dibuat: ID {request_id}")
            
            # Hapus pesan processing
            await processing_msg.delete()
            
            # Kirim instruksi transfer manual
            await query.message.reply_text(
                f"💰 **TOP UP DITERIMA**\n\n"
                f"👤 **User ID:** {user_id}\n"
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
        user = query.from_user
        await send_admin_notification(context, request_id, user, base_amount, unique_amount, unique_digits, qris_base64 is not None)
        
        # Hapus data dari context
        context.user_data.pop('topup_data', None)
        
        logger.info(f"✅ [TOPUP_CONFIRM] Proses selesai untuk user {user.id}")
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"❌ [TOPUP_CONFIRM] Error: {str(e)}", exc_info=True)
        await query.message.reply_text(
            "❌ Terjadi error saat memproses topup. Silakan coba lagi.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

def create_topup_request_compatible(user_id, base_amount, unique_amount, unique_digits, qris_base64):
    """Fungsi kompatibilitas untuk membuat topup request sesuai struktur database"""
    try:
        conn = sqlite3.connect(database.DB_PATH)
        c = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Get user info
        c.execute("SELECT username, full_name FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        username = row[0] if row else ""
        full_name = row[1] if row else ""
        
        # Insert dengan struktur yang sesuai
        c.execute("""
            INSERT INTO topup_requests (
                user_id, username, full_name, amount, status, proof_image, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
        """, (user_id, username, full_name, unique_amount, qris_base64, now, now))
        
        request_id = c.lastrowid
        conn.commit()
        conn.close()
        logger.info(f"✅ Topup request created: ID {request_id}")
        return request_id
    except Exception as e:
        logger.error(f"❌ Error create_topup_request_compatible: {e}")
        return None

async def send_admin_notification(context: ContextTypes.DEFAULT_TYPE, request_id, user, base_amount, unique_amount, unique_digits, has_qris=True):
    """Kirim notifikasi ke admin"""
    try:
        method = "QRIS" if has_qris else "MANUAL"
        
        notification_text = (
            f"🔔 **PERMINTAAN TOP UP BARU**\n\n"
            f"👤 **User:** {user.full_name or 'User'}\n"
            f"📛 **Username:** @{user.username if user.username else 'N/A'}\n"
            f"🆔 **User ID:** {user.id}\n"
            f"💰 **Nominal Dasar:** Rp {base_amount:,}\n"
            f"🔢 **Kode Unik:** {unique_digits:03d}\n"
            f"💵 **Total Transfer:** Rp {unique_amount:,}\n"
            f"📋 **ID Request:** `{request_id}`\n"
            f"📱 **Metode:** {method}\n\n"
            f"Gunakan `/approve_topup {request_id}` untuk approve."
        )
        
        # Kirim ke semua admin
        admin_ids = getattr(config, 'ADMIN_TELEGRAM_IDS', [])
        for admin_id in admin_ids:
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
        
        # Hapus data dari context
        context.user_data.pop('topup_data', None)
        
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            await query.edit_message_text("❌ **Top Up Dibatalkan**")
        else:
            await update.message.reply_text("❌ **Top Up Dibatalkan**")
        
    except Exception as e:
        logger.error(f"❌ [TOPUP_CANCEL] Error: {str(e)}")
    
    return ConversationHandler.END

async def show_topup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu topup utama"""
    try:
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("💳 Topup QRIS", callback_data="topup_manual")],
            [InlineKeyboardButton("📋 Riwayat Topup", callback_data="topup_history")],
            [InlineKeyboardButton("🔙 Kembali", callback_data="menu_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "💰 **Menu Topup**\n\n"
            "Pilih jenis topup:\n\n"
            "💳 **Topup QRIS** - Bayar dengan scan QRIS\n"
            "📋 **Riwayat** - Lihat history topup\n\n"
            "Pilih opsi di bawah:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"❌ Error in show_topup_menu: {str(e)}")
        if update.callback_query:
            await update.callback_query.message.reply_text("❌ Terjadi error, silakan coba lagi.")

async def show_manage_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu kelola topup (untuk admin)"""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = str(query.from_user.id)
        admin_ids = getattr(config, 'ADMIN_TELEGRAM_IDS', [])
        
        if user_id not in admin_ids:
            await query.message.reply_text("❌ Anda tidak memiliki akses ke menu ini.")
            return
        
        # Ambil pending topup requests
        try:
            conn = sqlite3.connect(database.DB_PATH)
            c = conn.cursor()
            c.execute('''
                SELECT tr.id, tr.user_id, u.username, tr.amount, tr.status, tr.created_at 
                FROM topup_requests tr
                JOIN users u ON tr.user_id = u.user_id
                WHERE tr.status = 'pending'
                ORDER BY tr.created_at DESC
                LIMIT 10
            ''')
            pending_requests = c.fetchall()
            conn.close()
        except Exception as e:
            logger.error(f"Error getting pending requests: {e}")
            pending_requests = []
        
        if pending_requests:
            message = "⏳ **TOPUP MENUNGGU VERIFIKASI**\n\n"
            for req in pending_requests:
                req_id, user_id, username, amount, status, created_at = req
                message += f"📋 **ID:** `{req_id}`\n"
                message += f"👤 **User:** {username or 'N/A'}\n"
                message += f"💰 **Amount:** Rp {amount:,}\n"
                message += f"⏰ **Waktu:** {created_at}\n"
                message += f"✅ **Approve:** `/approve_topup {req_id}`\n"
                message += f"❌ **Tolak:** `/cancel_topup {req_id}`\n\n"
        else:
            message = "✅ **Tidak ada topup yang menunggu verifikasi**\n\n"
        
        message += "**Perintah Admin:**\n"
        message += "• `/approve_topup <id>` - Approve topup\n"
        message += "• `/cancel_topup <id>` - Batalkan topup\n"
        message += "• `/topup_history` - Lihat riwayat semua user"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="manage_topup")],
            [InlineKeyboardButton("🔙 Kembali", callback_data="menu_admin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"❌ Error in show_manage_topup: {str(e)}")
        await query.message.reply_text("❌ Terjadi error, silakan coba lagi.")

async def handle_topup_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memulai topup QRIS"""
    try:
        logger.info("🔧 [HANDLE_TOPUP_MANUAL] Dipanggil")
        query = update.callback_query
        await query.answer()
        return await topup_start(update, context)
    except Exception as e:
        logger.error(f"❌ [HANDLE_TOPUP_MANUAL] Error: {str(e)}")
        await update.callback_query.message.reply_text("❌ Terjadi error, silakan coba lagi.")
        return ConversationHandler.END

async def handle_topup_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk riwayat topup user"""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = str(query.from_user.id)
        
        # Ambil riwayat topup user
        try:
            conn = sqlite3.connect(database.DB_PATH)
            c = conn.cursor()
            c.execute('''
                SELECT amount, status, created_at 
                FROM topup_requests 
                WHERE user_id = ?
                ORDER BY created_at DESC 
                LIMIT 10
            ''', (user_id,))
            history = c.fetchall()
            conn.close()
        except Exception as e:
            logger.error(f"Error getting topup history: {e}")
            history = []
        
        if history:
            message = "📋 **RIWAYAT TOP UP**\n\n"
            for amount, status, created_at in history:
                status_icon = "✅" if status == "approved" else "⏳" if status == "pending" else "❌"
                status_text = "DITERIMA" if status == "approved" else "MENUNGGU" if status == "pending" else "DITOLAK"
                message += f"{status_icon} **Rp {amount:,}**\n"
                message += f"📅 {created_at} - {status_text}\n\n"
        else:
            message = "📭 **Belum ada riwayat top up**\n\n"
        
        message += "Gunakan menu Top Up untuk menambah saldo."
        
        keyboard = [
            [InlineKeyboardButton("💳 Top Up Sekarang", callback_data="topup_manual")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="topup_history")],
            [InlineKeyboardButton("🔙 Kembali", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"❌ Error in handle_topup_history: {str(e)}")
        await query.message.reply_text("❌ Terjadi error, silakan coba lagi.")

# Conversation handler untuk topup - IMPROVED VERSION
topup_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler('topup', topup_start),
        CallbackQueryHandler(handle_topup_manual, pattern='^topup_manual$')
    ],
    states={
        ASK_TOPUP_NOMINAL: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, topup_nominal),
            CommandHandler('cancel', topup_cancel)
        ],
        CONFIRM_TOPUP: [
            CallbackQueryHandler(handle_topup_confirmation, pattern='^(confirm_topup|cancel_topup)$'),
            CommandHandler('cancel', topup_cancel)
        ]
    },
    fallbacks=[
        CommandHandler('cancel', topup_cancel),
        CommandHandler('start', topup_cancel)  # Fallback ke cancel jika user ketik start
    ],
    allow_reentry=True,
    per_chat=True,
    per_user=True,
    per_message=False
)
