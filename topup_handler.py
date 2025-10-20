# topup_handler.py - Disesuaikan dengan struktur asli
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
    return f"Rp {amount:,}".replace(',', '.')

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
    Generate QRIS payment menggunakan API.
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
                        if qris_base64 and len(qris_base64) > 100:
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
# (Tidak ada perubahan di bagian ini, sama seperti kode asli)
async def topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start topup process"""
    try:
        user_id = str(update.effective_user.id)
        
        database.get_or_create_user(
            user_id,
            update.effective_user.username,
            update.effective_user.full_name
        )
        
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
        if update.message:
            await update.message.reply_text(error_msg)
        elif update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        return ConversationHandler.END

# (Fungsi-fungsi menu tidak diubah)
async def show_topup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu topup utama"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(str(user.id))
        
        # Asumsi database memiliki fungsi get_pending_topups_by_user
        try:
            pending_topups = database.get_pending_topups_by_user(str(user.id))
        except AttributeError:
            # Fallback jika fungsi spesifik user tidak ada, gunakan yang general
            all_pending = database.get_pending_topups()
            pending_topups = [t for t in all_pending if t['user_id'] == str(user.id)]

        
        keyboard = [
            [InlineKeyboardButton("💳 Topup Sekarang", callback_data="topup_start")],
            [InlineKeyboardButton("📋 Riwayat Topup", callback_data="topup_history")],
        ]
        
        if pending_topups:
            keyboard.insert(1, [InlineKeyboardButton("⏳ Topup Pending", callback_data="topup_pending")])
        
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = f"""
💰 **MENU TOPUP SALDO**

💳 **Saldo Anda:** {format_currency(saldo)}
📊 **Topup Pending:** {len(pending_topups)}

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
        await update.callback_query.message.reply_text("❌ Error memuat menu topup.")

async def show_topup_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's topup history"""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = str(query.from_user.id)
        topups = database.get_user_topups(user_id)
        
        if not topups:
            await query.edit_message_text(
                "📋 **RIWAYAT TOPUP**\n\n"
                "Belum ada riwayat topup.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Topup Sekarang", callback_data="topup_start")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
                ])
            )
            return
        
        history_text = "📋 **RIWAYAT TOPUP**\n\n"
        
        for topup in topups[:10]:
            status_emoji = "✅" if topup['status'] == 'completed' else "⏳" if topup['status'] == 'pending' else "❌"
            status_text = "Selesai" if topup['status'] == 'completed' else "Pending" if topup['status'] == 'pending' else "Ditolak"
            
            history_text += (
                f"💰 **{format_currency(topup['amount'])}**\n"
                f"├ Status: {status_emoji} {status_text}\n"
                f"├ Waktu: {topup['created_at'].strftime('%d/%m/%Y %H:%M')}\n"
                f"└ ID: `{topup['id']}`\n\n"
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
        await update.callback_query.message.reply_text("❌ Error memuat riwayat topup.")

# ==================== NOMINAL PROCESSING ====================
async def topup_nominal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process nominal topup dengan validation lengkap"""
    try:
        nominal_input = update.message.text.strip()
        user = update.message.from_user
        
        if nominal_input.lower() == '/cancel':
            await update.message.reply_text("❌ **Top Up Dibatalkan**")
            return ConversationHandler.END
            
        if not nominal_input.isdigit():
            await update.message.reply_text(
                "❌ **Format salah!**\n\n"
                "Masukkan angka saja (tanpa titik/koma):\n"
                "✅ Contoh: `50000` untuk Rp 50.000\n\n"
                "Silakan coba lagi:"
            )
            return ASK_TOPUP_NOMINAL
        
        base_amount = int(nominal_input)
        
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
        
        unique_amount, unique_digits = generate_unique_amount(base_amount)
        
        context.user_data['topup_data'] = {
            'base_amount': base_amount,
            'unique_amount': unique_amount,
            'unique_digits': unique_digits,
            'user_id': str(user.id),
            'username': user.username,
            'full_name': user.full_name,
            'payment_method': None # FIX: Tambahkan ini untuk konsistensi
        }
        
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
    await query.answer()
    
    data = query.data
    topup_data = context.user_data.get('topup_data')
    
    if not topup_data:
        await query.edit_message_text("❌ Data topup tidak ditemukan. Silakan mulai ulang.")
        return ConversationHandler.END
    
    user_id = topup_data['user_id']
    unique_amount = topup_data['unique_amount']
    
    try:
        if data == "payment_qris":
            topup_data['payment_method'] = 'qris' # FIX: Set payment method
            loading_msg = await query.edit_message_text("🔄 **Membuat QRIS Payment...** Mohon tunggu...")
            
            qris_base64, _, error = await generate_qris_payment(unique_amount)
            
            if error:
                logger.error(f"QRIS generation failed: {error}")
                keyboard = [
                    [InlineKeyboardButton("🏦 Lanjut dengan Transfer Bank", callback_data="payment_bank")],
                    [InlineKeyboardButton("❌ Batalkan", callback_data="cancel_topup")]
                ]
                await loading_msg.edit_text(
                    f"❌ **QRIS Gagal:** {error}\n\nAnda masih bisa melakukan transfer manual:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return CONFIRM_TOPUP
            
            transaction_id = database.add_pending_topup(
                user_id=user_id,
                amount=unique_amount,
                proof_text=f"QRIS Topup - {topup_data['base_amount']} + {topup_data['unique_digits']}",
                payment_method="qris"
            )
            
            # Kirim foto QRIS
            qris_bytes = base64.b64decode(qris_base64)
            caption = create_qris_instructions(unique_amount, topup_data['unique_digits'])
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=BytesIO(qris_bytes),
                caption=caption,
                parse_mode='Markdown'
            )
            
            # Beri konfirmasi akhir dan selesaikan percakapan
            await loading_msg.edit_text(
                f"✅ **QRIS Berhasil Dibuat!**\n\n"
                f"Silakan scan QR code yang telah dikirim. Saldo akan masuk otomatis setelah pembayaran.\n\n"
                f"ID Transaksi: `{transaction_id}`",
                 parse_mode='Markdown'
            )
            
            context.user_data.clear() # Hapus data sesi
            return ConversationHandler.END # FIX: Akhiri percakapan di sini untuk alur QRIS

        elif data == "payment_bank":
            topup_data['payment_method'] = 'bank_transfer' # FIX: Set payment method
            await show_bank_instructions(query, context, topup_data)
            return UPLOAD_PROOF # FIX: Lanjutkan ke state upload bukti
            
        elif data == "cancel_topup":
            await query.edit_message_text("❌ **Top Up Dibatalkan**")
            context.user_data.clear()
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Error in handle_payment_method: {e}")
        await query.edit_message_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

# (Fungsi-fungsi pembantu tidak diubah)
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

**BRI** 📤 No. Rekening: `1234-5678-9012`
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
    
    await query.edit_message_text(
        instructions,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ==================== PROOF UPLOAD HANDLER ====================
# (Tidak ada perubahan di bagian ini, sama seperti kode asli)
async def handle_proof_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bukti pembayaran upload"""
    try:
        query = update.callback_query
        if query:
            await query.answer()
            await query.edit_message_text(
                "📎 **UPLOAD BUKTI PEMBAYARAN**\n\n"
                "Silakan kirim screenshot/foto bukti pembayaran Anda.\n\n"
                "Pastikan terbaca dengan jelas.\n\n"
                "❌ **Ketik /cancel untuk membatalkan**"
            )
        else:
            # Fallback jika fungsi ini dipanggil dari non-callback
            await update.message.reply_text(
                "📎 **UPLOAD BUKTI PEMBAYARAN**\n\n"
                "Silakan kirim screenshot/foto bukti pembayaran Anda."
            )
        
        return UPLOAD_PROOF
        
    except Exception as e:
        logger.error(f"Error in handle_proof_upload: {e}")
        error_msg = "❌ Terjadi error. Silakan coba lagi."
        if query:
            await query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        return ConversationHandler.END

async def process_proof_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process uploaded payment proof"""
    try:
        topup_data = context.user_data.get('topup_data')
        if not topup_data:
            await update.message.reply_text("❌ Data topup tidak ditemukan. Silakan mulai ulang.")
            return ConversationHandler.END
        
        transaction_id = topup_data.get('transaction_id')
        user_id = topup_data['user_id']
        unique_amount = topup_data['unique_amount']
        
        if not update.message.photo and not update.message.document:
            await update.message.reply_text(
                "❌ File tidak valid. Silakan kirim gambar/screenshot bukti pembayaran."
            )
            return UPLOAD_PROOF
        
        file_id = update.message.photo[-1].file_id if update.message.photo else update.message.document.file_id
        file = await context.bot.get_file(file_id)
        
        create_proofs_directory()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"proof_{user_id}_{transaction_id}_{timestamp}.jpg"
        file_path = f"proofs/{filename}"
        
        await file.download_to_drive(file_path)
        
        database.update_topup_proof(transaction_id, file_path)
        
        if ADMIN_CHAT_ID:
            admin_message = (
                f"🔔 **TOPUP BARU - BUTUH KONFIRMASI**\n\n"
                f"👤 **User:** {topup_data['full_name']} (@{topup_data['username']})\n"
                f"🆔 **User ID:** `{user_id}`\n"
                f"💰 **Amount:** {format_currency(unique_amount)}\n"
                f"📊 **Transaction ID:** `{transaction_id}`\n"
                f"📦 **Metode:** {topup_data.get('payment_method', 'bank_transfer')}\n\n" # Sedikit perbaikan di sini
                f"⚠️ **Silakan verifikasi pembayaran!**"
            )
            
            try:
                with open(file_path, 'rb') as proof_file:
                    await context.bot.send_photo(
                        chat_id=ADMIN_CHAT_ID,
                        photo=proof_file,
                        caption=admin_message,
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.error(f"Error notifying admin: {e}")
        
        keyboard = [
            [InlineKeyboardButton("🔍 Cek Status Topup", callback_data="topup_pending")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
        ]
        
        await update.message.reply_text(
            f"✅ **Bukti Pembayaran Diterima!**\n\n"
            f"📊 **Detail Transaksi:**\n"
            f"├ ID: `{transaction_id}`\n"
            f"├ Nominal: {format_currency(unique_amount)}\n"
            f"├ Status: Menunggu Verifikasi Admin\n"
            f"└ Estimasi: 1-24 jam\n\n"
            f"📞 **Info:** Admin akan memverifikasi pembayaran Anda. "
            f"Anda akan mendapat notifikasi ketika saldo sudah ditambahkan.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        context.user_data.clear()
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in process_proof_upload: {e}")
        await update.message.reply_text("❌ Error mengupload bukti. Silakan coba lagi.")
        return UPLOAD_PROOF

# (Fungsi-fungsi lain tidak diubah)
async def show_pending_topups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's pending topups"""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = str(query.from_user.id)
        # Asumsi get_pending_topups ada di database
        pending_topups = database.get_pending_topups()
        user_pending = [t for t in pending_topups if t['user_id'] == user_id]
        
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
        
        for topup in user_pending[:5]:
            method_emoji = "📱" if topup.get('payment_method') == 'qris' else "🏦"
            method_text = "QRIS" if topup.get('payment_method') == 'qris' else "Transfer Bank"
            
            pending_text += (
                f"💰 **{format_currency(topup['amount'])}**\n"
                f"├ Metode: {method_emoji} {method_text}\n"
                f"├ Waktu: {topup['created_at'].strftime('%d/%m/%Y %H:%M')}\n"
                f"├ ID: `{topup['id']}`\n"
                f"└ Status: **Menunggu Verifikasi**\n\n"
            )
        
        keyboard = [
            [InlineKeyboardButton("💳 Topup Lagi", callback_data="topup_start")],
            [InlineKeyboardButton("📋 Riwayat Topup", callback_data="topup_history")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            pending_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error in show_pending_topups: {e}")
        await update.callback_query.message.reply_text("❌ Error memuat data pending topup.")

async def cancel_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel topup process"""
    try:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("❌ **Top Up Dibatalkan**")
        else:
            await update.message.reply_text("❌ **Top Up Dibatalkan**")
        
        context.user_data.clear()
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in cancel_topup: {e}")
        return ConversationHandler.END

# ==================== CONVERSATION HANDLER SETUP ====================
# (Tidak ada perubahan di bagian ini, sama seperti kode asli)
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
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, process_proof_upload),
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
# (Tidak ada perubahan di bagian ini, sama seperti kode asli)
def get_topup_handlers():
    """Return all topup-related handlers"""
    return [
        get_topup_conversation_handler(),
        CallbackQueryHandler(show_topup_menu, pattern="^topup_menu$"),
        CallbackQueryHandler(show_topup_history, pattern="^topup_history$"),
        CallbackQueryHandler(show_pending_topups, pattern="^topup_pending$"),
        CallbackQueryHandler(handle_proof_upload, pattern="^upload_proof$"), # Handler ini ada di kode asli
    ]
