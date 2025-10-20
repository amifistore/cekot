"""
topup_handler.py - Complete Topup System (Release-ready)

Deskripsi:
- Handler conversation untuk topup saldo dengan integrasi QRIS & transfer manual.
- Tetap mempertahankan struktur dan fungsi seperti yang diminta.

Perbaikan & catatan rilis:
- Perbaikan akses chat id -> gunakan `query.message.chat.id`.
- Menyimpan `payment_method` ke dalam `topup_data` saat user memilih metode.
- Penanganan upload file diperkuat (cek mime_type untuk dokumen).
- Penggunaan `filters.Document.ALL` untuk menerima dokumen gambar (lalu disaring manual).
- Penambahan validasi defensif untuk `update.callback_query` vs `update.message`.
- Directory `proofs/` dibuat jika belum ada.
- Logging ditambahkan di bagian atas.

Pra-syarat:
- config.py : harus mendefinisikan MIN_TOPUP_AMOUNT, MAX_TOPUP_AMOUNT, QRIS_API_URL, QRIS_STATIS, ADMIN_CHAT_ID
- database.py : harus menyediakan fungsi yang digunakan di dalam (get_or_create_user, get_user_saldo, get_user_topups,
  get_pending_topups, add_pending_topup, update_topup_proof)
- python-telegram-bot v20+ direkomendasikan.

Cara pakai singkat (contoh):
- Import get_topup_handlers() dan daftarkan ke Application() Anda.

"""

import logging
import random
import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from datetime import datetime
import base64
from io import BytesIO
import json
import os
from pathlib import Path
import config
import database

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ==================== CONVERSATION STATES ====================
ASK_TOPUP_NOMINAL, CONFIRM_TOPUP, UPLOAD_PROOF = range(3)

# ==================== CONFIGURATION ====================
MIN_TOPUP_AMOUNT = getattr(config, 'MIN_TOPUP_AMOUNT', 10000)
MAX_TOPUP_AMOUNT = getattr(config, 'MAX_TOPUP_AMOUNT', 1000000)
QRIS_API_URL = getattr(config, 'QRIS_API_URL', '')
QRIS_STATIS = getattr(config, 'QRIS_STATIS', '')
ADMIN_CHAT_ID = getattr(config, 'ADMIN_CHAT_ID', None)

# ==================== UTILITY FUNCTIONS ====================

def format_currency(amount: int) -> str:
    """Format currency dengan titik sebagai pemisah ribuan"""
    try:
        return f"Rp {int(amount):,}".replace(',', '.')
    except Exception:
        return f"Rp {amount}"


def generate_unique_amount(base_amount: int) -> tuple:
    """Generate nominal unik dengan 3 digit random"""
    try:
        base_amount = int(base_amount)
        unique_digits = random.randint(1, 999)
        unique_amount = base_amount + unique_digits
        return unique_amount, unique_digits
    except Exception as e:
        logger.error(f"Error generating unique amount: {e}")
        return base_amount, 0


def create_proofs_directory():
    """Create directory untuk menyimpan bukti pembayaran"""
    Path("proofs").mkdir(exist_ok=True)

# ==================== QRIS INTEGRATION ====================
async def generate_qris_payment(unique_amount: int) -> tuple:
    """
    Generate QRIS payment menggunakan API QRISku.my.id atau endpoint lain.
    Returns: (qris_base64, qr_content, error_message)
    """
    try:
        if not QRIS_API_URL:
            return None, None, "QRIS API URL not configured"

        if not QRIS_STATIS:
            return None, None, "QRIS static data not configured"

        logger.info(f"🔧 [QRIS] Generating QRIS untuk amount: {unique_amount}")

        payload = {
            "amount": str(unique_amount),
            "qris_statis": QRIS_STATIS
        }

        logger.info(f"📤 [QRIS] Sending request to: {QRIS_API_URL}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                QRIS_API_URL,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            ) as resp:

                response_text = await resp.text()
                logger.info(f"📥 [QRIS] Response status: {resp.status}")

                if resp.status == 200:
                    result = await resp.json()

                    if result.get("status") == "success" and "qris_base64" in result:
                        qris_base64 = result["qris_base64"]
                        if qris_base64 and len(qris_base64) > 20:
                            logger.info("✅ [QRIS] QRIS berhasil digenerate")
                            return qris_base64, result.get("qr_content", ""), None

                    error_msg = result.get('message', 'Unknown error from QRIS API')
                    logger.error(f"❌ [QRIS] API error: {error_msg}")
                    return None, None, error_msg

                else:
                    error_msg = f"HTTP {resp.status}: {response_text}"
                    logger.error(f"❌ [QRIS] HTTP error: {error_msg}")
                    return None, None, error_msg

    except asyncio.TimeoutError:
        error_msg = "QRIS API timeout setelah 30 detik"
        logger.error(f"❌ [QRIS] {error_msg}")
        return None, None, error_msg

    except Exception as e:
        error_msg = f"QRIS generation error: {str(e)}"
        logger.error(f"❌ [QRIS] {error_msg}")
        return None, None, error_msg

# ==================== TOPUP START & MENU ====================
async def topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start topup process"""
    try:
        # Accept both callback_query or command/message trigger
        user = update.effective_user
        if user is None:
            logger.warning("topup_start called without user")
            return ConversationHandler.END

        # Get or create user
        user_id = database.get_or_create_user(
            str(user.id),
            user.username or '',
            user.full_name or ''
        )

        # Clear any existing context
        context.user_data.clear()

        message_text = (
            "💳 **TOP UP SALDO**\n\n"
            "Masukkan nominal top up (angka saja):\n"
            "✅ **Contoh:** `50000` untuk Rp 50.000\n\n"
            f"💰 **Ketentuan:**\n"
            f"• Minimal: {format_currency(MIN_TOPUP_AMOUNT)}\n"
            f"• Maksimal: {format_currency(MAX_TOPUP_AMOUNT)}\n"
            f"• Kode unik otomatis ditambahkan\n"
            f"• Pilih metode pembayaran setelahnya\n\n"
            "❌ **Ketik /cancel untuk membatalkan**"
        )

        if update.message:
            await update.message.reply_text(message_text, parse_mode='Markdown')
        elif update.callback_query:
            await update.callback_query.edit_message_text(message_text, parse_mode='Markdown')

        return ASK_TOPUP_NOMINAL

    except Exception as e:
        logger.error(f"Error in topup_start: {e}")
        error_msg = "❌ Terjadi error. Silakan coba lagi nanti."
        if update and getattr(update, 'message', None):
            await update.message.reply_text(error_msg)
        elif update and getattr(update, 'callback_query', None):
            await update.callback_query.edit_message_text(error_msg)
        return ConversationHandler.END

async def show_topup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu topup utama"""
    try:
        query = update.callback_query
        if not query:
            return
        await query.answer()

        user = query.from_user
        user_id = database.get_or_create_user(str(user.id), user.username or '', user.full_name or '')
        saldo = database.get_user_saldo(str(user.id)) or 0

        pending_topups = database.get_pending_topups() or []
        user_pending = [t for t in pending_topups if t.get('user_id') == str(user.id)]

        keyboard = [
            [InlineKeyboardButton("💳 Topup Sekarang", callback_data="topup_start")],
            [InlineKeyboardButton("📋 Riwayat Topup", callback_data="topup_history")],
        ]

        if user_pending:
            keyboard.insert(0, [InlineKeyboardButton("⏳ Topup Pending", callback_data="topup_pending")])

        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        message = f"""
💰 **MENU TOPUP SALDO**

💳 **Saldo Anda:** {format_currency(saldo)}
📊 **Topup Pending:** {len(user_pending)}

**Pilihan:**
• 💳 Topup Sekarang - Tambah saldo sekarang
• 📋 Riwayat Topup - Lihat history topup
• ⏳ Topup Pending - Cek status topup
"""

        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error in show_topup_menu: {e}")
        if update and getattr(update, 'callback_query', None) and update.callback_query.message:
            await update.callback_query.message.reply_text("❌ Error memuat menu topup.")

async def show_topup_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's topup history"""
    try:
        query = update.callback_query
        if not query:
            return
        await query.answer()

        user_id = str(query.from_user.id)
        topups = database.get_user_topups(user_id) or []

        if not topups:
            await query.edit_message_text(
                "📋 **RIWAYAT TOPUP**\n\n" "Belum ada riwayat topup.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Topup Sekarang", callback_data="topup_start")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
                ])
            )
            return

        history_text = "📋 **RIWAYAT TOPUP**\n\n"

        for topup in topups[:10]:  # Show last 10 topups
            status_emoji = "✅" if topup.get('status') == 'completed' else "⏳" if topup.get('status') == 'pending' else "❌"
            status_text = "Selesai" if topup.get('status') == 'completed' else "Pending" if topup.get('status') == 'pending' else "Ditolak"
            created_at = topup.get('created_at')
            time_str = created_at.strftime('%d/%m/%Y %H:%M') if hasattr(created_at, 'strftime') else str(created_at)

            history_text += (
                f"💰 **{format_currency(topup.get('amount', 0))}**\n"
                f"├ Status: {status_emoji} {status_text}\n"
                f"├ Waktu: {time_str}\n"
                f"└ ID: `{topup.get('id')}`\n\n"
            )

        await query.edit_message_text(
            history_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Topup Lagi", callback_data="topup_start")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ])
        )

    except Exception as e:
        logger.error(f"Error in show_topup_history: {e}")
        if update and getattr(update, 'callback_query', None) and update.callback_query.message:
            await update.callback_query.message.reply_text("❌ Error memuat riwayat topup.")

# ==================== NOMINAL PROCESSING ====================
async def topup_nominal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process nominal topup dengan validation lengkap"""
    try:
        if not update.message:
            return ConversationHandler.END

        nominal_input = update.message.text.strip()
        user = update.message.from_user

        # Handle cancellation
        if nominal_input.lower() == '/cancel':
            await update.message.reply_text("❌ **Top Up Dibatalkan**")
            return ConversationHandler.END

        # Validation
        if not nominal_input.isdigit():
            await update.message.reply_text(
                "❌ **Format salah!**\n\n"
                "Masukkan angka saja (tanpa titik/koma):\n"
                "✅ Contoh: `50000` untuk Rp 50.000\n\n"
                "Silakan coba lagi:"
            )
            return ASK_TOPUP_NOMINAL

        base_amount = int(nominal_input)

        # Amount validation
        if base_amount < MIN_TOPUP_AMOUNT:
            await update.message.reply_text(
                f"❌ **Minimum top up {format_currency(MIN_TOPUP_AMOUNT)}**\n\n"
                f"Nominal yang Anda masukkan: {format_currency(base_amount)}\n"
                "Silakan masukkan nominal yang lebih besar:"
            )
            return ASK_TOPUP_NOMINAL

        if base_amount > MAX_TOPUP_AMOUNT:
            await update.message.reply_text(
                f"❌ **Maximum top up {format_currency(MAX_TOPUP_AMOUNT)}**\n\n"
                "Untuk topup lebih dari 1 juta, silakan hubungi admin.\n"
                "Silakan masukkan nominal yang lebih kecil:"
            )
            return ASK_TOPUP_NOMINAL

        # Generate unique amount
        unique_amount, unique_digits = generate_unique_amount(base_amount)

        # Store in context
        context.user_data['topup_data'] = {
            'base_amount': base_amount,
            'unique_amount': unique_amount,
            'unique_digits': unique_digits,
            'user_id': str(user.id),
            'username': user.username or '',
            'full_name': user.full_name or ''
        }

        # Show payment method selection
        keyboard = [
            [
                InlineKeyboardButton("📱 QRIS (Auto)", callback_data="payment_qris"),
                InlineKeyboardButton("🏦 Transfer Bank", callback_data="payment_bank")
            ],
            [InlineKeyboardButton("❌ Batalkan", callback_data="cancel_topup")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"💳 **KONFIRMASI TOPUP**\n\n"
            f"📊 **Detail Topup:**\n"
            f"├ Nominal: {format_currency(base_amount)}\n"
            f"├ Kode Unik: {unique_digits:03d}\n"
            f"├ Total Transfer: **{format_currency(unique_amount)}**\n"
            f"└ Metode: Pilih di bawah\n\n"
            f"**Pilih metode pembayaran:**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        return CONFIRM_TOPUP

    except Exception as e:
        logger.error(f"Error in topup_nominal: {e}")
        await update.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

# ==================== PAYMENT METHOD HANDLERS ====================
async def handle_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment method selection"""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()

    data = query.data
    topup_data = context.user_data.get('topup_data')

    if not topup_data:
        await query.edit_message_text("❌ Data topup tidak ditemukan. Silakan mulai ulang.")
        return ConversationHandler.END

    user_id = topup_data['user_id']
    unique_amount = topup_data['unique_amount']
    unique_digits = topup_data['unique_digits']
    base_amount = topup_data['base_amount']

    try:
        if data == "payment_qris":
            # Simpan metode pembayaran
            topup_data['payment_method'] = 'qris'
            context.user_data['topup_data'] = topup_data

            loading_msg = await query.edit_message_text(
                "🔄 **Membuat QRIS Payment...**\n\n" "Mohon tunggu sebentar..."
            )

            qris_image, qr_content, error = await generate_qris_payment(unique_amount)

            if error:
                logger.error(f"QRIS generation failed: {error}")
                keyboard = [
                    [InlineKeyboardButton("🏦 Lanjut dengan Transfer Bank", callback_data="payment_bank")],
                    [InlineKeyboardButton("❌ Batalkan", callback_data="cancel_topup")]
                ]
                await loading_msg.edit_text(
                    f"❌ **QRIS Gagal:** {error}\n\n"
                    "Anda masih bisa melakukan transfer manual:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return CONFIRM_TOPUP

            # Create transaction record
            transaction_id = database.add_pending_topup(
                user_id=user_id,
                amount=unique_amount,
                proof_text=f"QRIS Topup - {base_amount} + {unique_digits}",
                payment_method="qris"
            )

            topup_data['transaction_id'] = transaction_id
            context.user_data['topup_data'] = topup_data

            # Send QRIS image
            try:
                qris_bytes = base64.b64decode(qris_image)
                instructions = create_qris_instructions(unique_amount, unique_digits)

                await context.bot.send_photo(
                    chat_id=query.message.chat.id,
                    photo=BytesIO(qris_bytes),
                    caption=instructions,
                    parse_mode='Markdown'
                )

                success_message = (
                    f"✅ **QRIS Berhasil Digenerate!**\n\n"
                    f"📊 **Detail Transaksi:**\n"
                    f"├ ID: `{transaction_id}`\n"
                    f"├ Nominal: {format_currency(unique_amount)}\n"
                    f"├ Kode Unik: {unique_digits:03d}\n"
                    f"└ Status: Menunggu Pembayaran\n\n"
                    f"💡 **Instruksi:**\n"
                    f"• Scan QR code di atas\n"
                    f"• Bayar tepat **{format_currency(unique_amount)}**\n"
                    f"• Simpan bukti bayar\n"
                    f"• Saldo otomatis ditambahkan setelah pembayaran\n\n"
                    f"⏰ **Pembayaran otomatis terdeteksi dalam 1-10 menit**"
                )

                await loading_msg.edit_text(success_message, parse_mode='Markdown')

            except Exception as e:
                logger.error(f"Error sending QRIS image: {e}")
                await loading_msg.edit_text(
                    f"❌ Gagal mengirim QRIS. Silakan hubungi admin.\nError: {str(e)}"
                )
                return ConversationHandler.END

        elif data == "payment_bank":
            topup_data['payment_method'] = 'bank_transfer'
            context.user_data['topup_data'] = topup_data
            await show_bank_instructions(query, context, topup_data)
            return UPLOAD_PROOF

        elif data == "cancel_topup":
            await query.edit_message_text("❌ **Top Up Dibatalkan**")
            return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in handle_payment_method: {e}")
        try:
            await query.edit_message_text("❌ Terjadi error. Silakan coba lagi.")
        except Exception:
            pass
        return ConversationHandler.END

    # For QRIS, wait for payment automatically (user doesn't need to upload proof)
    keyboard = [
        [InlineKeyboardButton("📎 Upload Bukti Bayar", callback_data="upload_proof")],
        [InlineKeyboardButton("🔍 Cek Status", callback_data="topup_pending")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
    ]

    try:
        await query.message.reply_text(
            "💡 Jika sudah bayar tapi saldo belum masuk, Anda bisa upload bukti bayar:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        pass

    return UPLOAD_PROOF


def create_qris_instructions(unique_amount: int, unique_digits: int) -> str:
    """Create QRIS payment instructions"""
    return f"""
📱 **INSTRUKSI QRIS:**
➖➖➖➖➖➖➖➖➖➖
1. Buka aplikasi mobile banking/e-wallet
2. Pilih fitur QRIS/Scan QR
3. Scan kode QR di bawah
4. Pastikan nominal: **{format_currency(unique_amount)}**
5. Konfirmasi pembayaran
6. Simpan bukti bayar

💡 **Supported Apps:**
• GoPay, OVO, Dana, LinkAja
• Mobile Banking (BCA, BRI, BNI, Mandiri, dll)
• E-wallet lainnya yang support QRIS
➖➖➖➖➖➖➖➖➖➖

💳 **TOPUP SALDO - KONFIRMASI**

💰 **Detail Pembayaran:**
├ Nominal: **{format_currency(unique_amount)}**
├ Kode Unik: **{unique_digits:03d}**
├ Metode: **QRIS**
└ Status: **Menunggu Pembayaran**

⏰ **Penting:**
• Saldo akan ditambahkan setelah pembayaran dikonfirmasi
• Proses verifikasi 1-10 menit
• Hubungi admin jika ada kendala
"""

async def show_bank_instructions(query, context, topup_data):
    """Show bank transfer instructions"""
    user_id = topup_data['user_id']
    unique_amount = topup_data['unique_amount']
    unique_digits = topup_data['unique_digits']
    base_amount = topup_data['base_amount']

    # Create transaction record for bank transfer
    transaction_id = database.add_pending_topup(
        user_id=user_id,
        amount=unique_amount,
        proof_text=f"Bank Transfer - {base_amount} + {unique_digits}",
        payment_method="bank_transfer"
    )

    topup_data['transaction_id'] = transaction_id
    context.user_data['topup_data'] = topup_data

    bank_info = """
🏦 **INFORMASI REKENING:**
➖➖➖➖➖➖➖➖➖➖
**BCA**
📤 No. Rekening: `1234-5678-9012`
👤 Atas Nama: **BOT STORE**

**BRI** 
📤 No. Rekening: `1234-5678-9012`
👤 Atas Nama: **BOT STORE**

**BNI**
📤 No. Rekening: `1234-5678-9012`  
👤 Atas Nama: **BOT STORE**

**Mandiri**
📤 No. Rekening: `1234-5678-9012`
👤 Atas Nama: **BOT STORE**
➖➖➖➖➖➖➖➖➖➖
"""

    instructions = (
        f"🏦 **TRANSFER BANK MANUAL**\n\n"
        f"💰 **Detail Pembayaran:**\n"
        f"├ Nominal: {format_currency(base_amount)}\n"
        f"├ Kode Unik: {unique_digits:03d}\n"
        f"├ Total Transfer: **{format_currency(unique_amount)}**\n"
        f"├ ID Transaksi: `{transaction_id}`\n"
        f"└ Metode: **Transfer Bank**\n\n"
        f"{bank_info}\n"
        f"📋 **INSTRUKSI:**\n"
        f"1. Transfer tepat **{format_currency(unique_amount)}**\n"
        f"2. Ke salah satu rekening di atas\n"
        f"3. Screenshot/simpan bukti transfer\n"
        f"4. Upload bukti transfer di langkah berikutnya\n\n"
        f"⏰ **Konfirmasi manual oleh admin 1-24 jam**"
    )

    keyboard = [
        [InlineKeyboardButton("📎 Upload Bukti Transfer", callback_data="upload_proof")],
        [InlineKeyboardButton("❌ Batalkan Topup", callback_data="cancel_topup")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(
            instructions,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error editing message for bank instructions: {e}")

# ==================== PROOF UPLOAD HANDLER ====================
async def handle_proof_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt user to upload proof or start upload flow"""
    try:
        query = update.callback_query
        if query:
            await query.answer()
            await query.edit_message_text(
                "📎 **UPLOAD BUKTI PEMBAYARAN**\n\n"
                "Silakan kirim screenshot/foto bukti pembayaran Anda.\n\n"
                "✅ **Format yang diterima:**\n"
                "• Foto/Gambar (JPEG, PNG)\n"
                "• Screenshot bukti transfer\n"
                "• Pastikan terbaca dengan jelas\n\n"
                "❌ **Ketik /cancel untuk membatalkan**"
            )
        else:
            if update.message:
                await update.message.reply_text(
                    "📎 **UPLOAD BUKTI PEMBAYARAN**\n\n"
                    "Silakan kirim screenshot/foto bukti pembayaran Anda."
                )

        return UPLOAD_PROOF

    except Exception as e:
        logger.error(f"Error in handle_proof_upload: {e}")
        if query:
            await query.edit_message_text("❌ Terjadi error. Silakan coba lagi.")
        elif update.message:
            await update.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def process_proof_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process uploaded payment proof"""
    try:
        if not update.message:
            return ConversationHandler.END

        topup_data = context.user_data.get('topup_data')
        if not topup_data:
            await update.message.reply_text("❌ Data topup tidak ditemukan. Silakan mulai ulang.")
            return ConversationHandler.END

        transaction_id = topup_data.get('transaction_id')
        user_id = topup_data['user_id']
        unique_amount = topup_data['unique_amount']

        # Validate file presence & type
        if not update.message.photo and not update.message.document:
            await update.message.reply_text(
                "❌ File tidak valid. Silakan kirim gambar/screenshot bukti pembayaran."
            )
            return UPLOAD_PROOF

        # If document, ensure it's an image mime type
        if update.message.document:
            mime_type = getattr(update.message.document, 'mime_type', '') or getattr(update.message.document, 'mimeType', '')
            if not mime_type.startswith('image/'):
                await update.message.reply_text(
                    "❌ File tidak valid. Silakan kirim gambar (JPEG/PNG) atau foto bukti pembayaran."
                )
                return UPLOAD_PROOF

        # Get the file id
        file_id = update.message.photo[-1].file_id if update.message.photo else update.message.document.file_id

        # Download file
        file = await context.bot.get_file(file_id)

        create_proofs_directory()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_trans_id = transaction_id if transaction_id is not None else 'noid'
        filename = f"proof_{user_id}_{safe_trans_id}_{timestamp}.jpg"
        file_path = os.path.join('proofs', filename)

        await file.download_to_drive(file_path)

        # Update database with proof path
        database.update_topup_proof(transaction_id, file_path)

        # Notify admin
        if ADMIN_CHAT_ID:
            admin_message = (
                f"🔔 **TOPUP BARU - BUTUH KONFIRMASI**\n\n"
                f"👤 **User:** {topup_data.get('full_name','')} (@{topup_data.get('username','')})\n"
                f"🆔 **User ID:** `{user_id}`\n"
                f"💰 **Amount:** {format_currency(unique_amount)}\n"
                f"📊 **Transaction ID:** `{transaction_id}`\n"
                f"📦 **Metode:** {topup_data.get('payment_method', 'unknown')}\n\n"
                f"⚠️ **Silakan verifikasi pembayaran!**"
            )

            try:
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=admin_message,
                    parse_mode='Markdown'
                )

                with open(file_path, 'rb') as proof_file:
                    await context.bot.send_photo(
                        chat_id=ADMIN_CHAT_ID,
                        photo=proof_file,
                        caption=f"Bukti transfer untuk Transaction ID: {transaction_id}"
                    )
            except Exception as e:
                logger.error(f"Error notifying admin: {e}")

        # Confirm to user
        keyboard = [
            [InlineKeyboardButton("🔍 Cek Status Topup", callback_data="topup_pending")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ **Bukti Pembayaran Diterima!**\n\n"
            f"📊 **Detail Transaksi:**\n"
            f"├ ID: `{transaction_id}`\n"
            f"├ Nominal: {format_currency(unique_amount)}\n"
            f"├ Status: Menunggu Verifikasi Admin\n"
            f"└ Estimasi: 1-24 jam\n\n"
            f"📞 **Info:** Admin akan memverifikasi pembayaran Anda.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        # Clear conversation data
        context.user_data.clear()

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in process_proof_upload: {e}")
        try:
            await update.message.reply_text("❌ Error mengupload bukti. Silakan coba lagi.")
        except Exception:
            pass
        return UPLOAD_PROOF

# ==================== PENDING TOPUPS HANDLER ====================
async def show_pending_topups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's pending topups"""
    try:
        query = update.callback_query
        if not query:
            return
        await query.answer()

        user_id = str(query.from_user.id)
        pending_topups = database.get_pending_topups() or []
        user_pending = [t for t in pending_topups if t.get('user_id') == user_id]

        if not user_pending:
            await query.edit_message_text(
                "⏳ **TOPUP PENDING**\n\n"
                "Tidak ada topup yang sedang menunggu verifikasi.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Topup Sekarang", callback_data="topup_start")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
                ])
            )
            return

        pending_text = "⏳ **TOPUP PENDING**\n\n"

        for topup in user_pending[:5]:  # Show last 5 pending topups
            method_emoji = "📱" if topup.get('payment_method') == 'qris' else "🏦"
            method_text = "QRIS" if topup.get('payment_method') == 'qris' else "Transfer Bank"
            created_at = topup.get('created_at')
            time_str = created_at.strftime('%d/%m/%Y %H:%M') if hasattr(created_at, 'strftime') else str(created_at)

            pending_text += (
                f"💰 **{format_currency(topup.get('amount',0))}**\n"
                f"├ Metode: {method_emoji} {method_text}\n"
                f"├ Waktu: {time_str}\n"
                f"├ ID: `{topup.get('id')}`\n"
                f"└ Status: **Menunggu Verifikasi**\n\n"
            )

        keyboard = [
            [InlineKeyboardButton("💳 Topup Lagi", callback_data="topup_start")],
            [InlineKeyboardButton("📋 Riwayat Topup", callback_data="topup_history")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            pending_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Error in show_pending_topups: {e}")
        if update and getattr(update, 'callback_query', None) and update.callback_query.message:
            await update.callback_query.message.reply_text("❌ Error memuat data pending topup.")

# ==================== CANCEL HANDLER ====================
async def cancel_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel topup process"""
    try:
        query = update.callback_query
        if query:
            await query.answer()
            await query.edit_message_text("❌ **Top Up Dibatalkan**")
        elif update.message:
            await update.message.reply_text("❌ **Top Up Dibatalkan**")

        # Clear user data
        context.user_data.clear()

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in cancel_topup: {e}")
        return ConversationHandler.END

# ==================== CONVERSATION HANDLER SETUP ====================
def get_topup_conversation_handler():
    """Return configured conversation handler for topup"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(topup_start, pattern="^topup_start$"),
            CommandHandler('topup', topup_start)
        ],
        states={
            ASK_TOPUP_NOMINAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, topup_nominal),
                CommandHandler('cancel', cancel_topup)
            ],
            CONFIRM_TOPUP: [
                CallbackQueryHandler(handle_payment_method, pattern="^payment_"),
                CallbackQueryHandler(cancel_topup, pattern="^cancel_topup$")
            ],
            UPLOAD_PROOF: [
                CallbackQueryHandler(handle_proof_upload, pattern="^upload_proof$"),
                MessageHandler((filters.PHOTO | filters.Document.ALL), process_proof_upload),
                CommandHandler('cancel', cancel_topup)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel_topup),
            CallbackQueryHandler(cancel_topup, pattern="^cancel_topup$")
        ],
        allow_reentry=True
    )

# ==================== OTHER HANDLERS ====================
def get_topup_handlers():
    """Return all topup-related handlers (conversation + quick callbacks)"""
    return [
        get_topup_conversation_handler(),
        CallbackQueryHandler(show_topup_menu, pattern="^topup_menu$"),
        CallbackQueryHandler(show_topup_history, pattern="^topup_history$"),
        CallbackQueryHandler(show_pending_topups, pattern="^topup_pending$"),
        CallbackQueryHandler(handle_proof_upload, pattern="^upload_proof$")
    ]


# Optional: contoh sederhana untuk menjalankan bot (jangan sertakan token di file ini untuk release)
if __name__ == '__main__':
    # Contoh penggunaan: register handlers ke Application yang sudah dibuat di project Anda
    print("Module topup_handler ready. Import get_topup_handlers() ke main bot application Anda.")
