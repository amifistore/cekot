# topup_handler.py - Complete Topup System with QRIS Integration
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
    Generate QRIS payment menggunakan API QRISku.my.id
    Returns: (qris_base64, qr_content, error_message)
    """
    try:
        if not QRIS_API_URL:
            return None, None, "QRIS API URL not configured"
            
        if not QRIS_STATIS:
            return None, None, "QRIS static data not configured"

        logger.info(f"🔧 [QRIS] Generating QRIS untuk amount: {unique_amount}")
        
        # Prepare payload sesuai dokumentasi API
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
async def topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start topup process"""
    try:
        user_id = str(update.effective_user.id)
        
        # Get user data menggunakan database yang sudah ada
        user_id = database.get_or_create_user(
            user_id,
            update.effective_user.username,
            update.effective_user.full_name
        )
        
        # Clear any existing context
        context.user_data.clear()
        
        # Send topup instructions
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

async def show_topup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu topup utama"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(str(user.id))
        
        # Get pending topups
        pending_topups = database.get_pending_topups()
        user_pending = [t for t in pending_topups if t['user_id'] == str(user.id)]
        
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
        
        for topup in topups[:10]:  # Show last 10 topups
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
            'username': user.username,
            'full_name': user.full_name
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
            # Generate QRIS
            loading_msg = await query.edit_message_text(
                "🔄 **Membuat QRIS Payment...**\n\n"
                "Mohon tunggu sebentar..."
            )
            
            qris_image, qr_content, error = await generate_qris_payment(unique_amount)
            
            if error:
                logger.error(f"QRIS generation failed: {error}")
                keyboard = [
                    [InlineKeyboardButton("🏦 Lanjut dengan Transfer Bank", callback_data="payment_bank")],
                    [InlineKeyboardButton("❌ Batalkan", callback_data="cancel_topup")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await loading_msg.edit_text(
                    f"❌ **QRIS Gagal:** {error}\n\n"
                    "Anda masih bisa melakukan transfer manual:",
                    reply_markup=reply_markup
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
                # Decode base64 image
                qris_bytes = base64.b64decode(qris_image)
                
                # Create instructions
                instructions = create_qris_instructions(unique_amount, unique_digits)
                
                # Send QRIS image with caption
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=BytesIO(qris_bytes),
                    caption=instructions,
                    parse_mode='Markdown'
                )
                
                # Edit loading message to show success
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
            # Show bank transfer instructions
            await show_bank_instructions(query, context, topup_data)
            return UPLOAD_PROOF
        
        elif data == "cancel_topup":
            await query.edit_message_text("❌ **Top Up Dibatalkan**")
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Error in handle_payment_method: {e}")
        await query.edit_message_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END
    
    # For QRIS, wait for payment automatically (user doesn't need to upload proof)
    # But we still give option to upload proof if needed
    keyboard = [
        [InlineKeyboardButton("📎 Upload Bukti Bayar", callback_data="upload_proof")],
        [InlineKeyboardButton("🔍 Cek Status", callback_data="topup_pending")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        "💡 Jika sudah bayar tapi saldo belum masuk, Anda bisa upload bukti bayar:",
        reply_markup=reply_markup
    )
    
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
    
    await query.edit_message_text(
        f"🏦 **TRANSFER BANK - KONFIRMASI**\n\n"
        f"📊 **Detail Transaksi:**\n"
        f"├ ID Transaksi: `{transaction_id}`\n"
        f"├ Nominal Topup: {format_currency(base_amount)}\n"
        f"├ Kode Unik: {unique_digits:03d}\n"
        f"├ Total Transfer: **{format_currency(unique_amount)}**\n"
        f"└ Status: Menunggu Pembayaran\n\n"
        f"{bank_info}\n"
        f"💡 **Instruksi:**\n"
        f"1. Transfer ke salah satu rekening di atas\n"
        f"2. Transfer tepat **{format_currency(unique_amount)}**\n"
        f"3. Simpan bukti transfer\n"
        f"4. Upload bukti transfer di langkah berikutnya\n\n"
        f"📎 **Silakan upload bukti transfer:**",
        parse_mode='Markdown'
    )

# ==================== PAYMENT PROOF UPLOAD ====================
async def handle_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment proof upload"""
    # Handle callback for upload proof button
    if hasattr(update, 'callback_query') and update.callback_query:
        query = update.callback_query
        await query.answer()
        
        if query.data == "upload_proof":
            await query.edit_message_text(
                "📎 **UPLOAD BUKTI PEMBAYARAN**\n\n"
                "Silakan upload bukti pembayaran (screenshot/photo):\n"
                "• Format: JPEG, PNG, atau JPG\n"
                "• Pastikan bukti transfer jelas terbaca\n"
                "• Tampilkan nominal dan bank pengirim\n\n"
                "❌ **Ketik /cancel untuk membatalkan**"
            )
            return UPLOAD_PROOF
    
    # Handle actual file upload
    elif update.message and (update.message.photo or update.message.document):
        return await process_proof_upload(update, context)
    
    # Handle text messages in UPLOAD_PROOF state
    elif update.message and update.message.text:
        if update.message.text.strip().lower() == '/cancel':
            await update.message.reply_text("❌ **Upload Bukti Dibatalkan**")
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "❌ **Silakan upload bukti pembayaran berupa gambar**\n\n"
                "Upload screenshot/photo bukti transfer Anda.\n"
                "❌ **Ketik /cancel untuk membatalkan**"
            )
            return UPLOAD_PROOF
    
    return UPLOAD_PROOF

async def process_proof_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the uploaded payment proof"""
    try:
        topup_data = context.user_data.get('topup_data')
        if not topup_data:
            await update.message.reply_text("❌ Data topup tidak ditemukan. Silakan mulai ulang.")
            return ConversationHandler.END

        # Get the file
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
        elif update.message.document:
            if not update.message.document.mime_type.startswith('image/'):
                await update.message.reply_text(
                    "❌ **Format file tidak didukung!**\n"
                    "Silakan upload file gambar (JPEG, PNG, JPG)"
                )
                return UPLOAD_PROOF
            file_id = update.message.document.file_id
        else:
            await update.message.reply_text("❌ Silakan upload bukti pembayaran berupa gambar.")
            return UPLOAD_PROOF

        # Create proofs directory
        create_proofs_directory()
        
        # Get file info and download
        file = await context.bot.get_file(file_id)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path = f"proofs/{topup_data['transaction_id']}_{timestamp}.jpg"
        
        # Update database with proof
        database.update_topup_proof(
            topup_data['transaction_id'],
            file_path,
            "pending"
        )

        # Download file
        try:
            await file.download_to_drive(file_path)
        except Exception as e:
            logger.warning(f"Could not save proof file: {e}")

        # Notify admin
        await notify_admin_proof_upload(context, topup_data, file_id)
        
        # Confirm to user
        keyboard = [
            [InlineKeyboardButton("🔍 Cek Status Topup", callback_data="topup_pending")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **Bukti Pembayaran Diterima!**\n\n"
            f"📊 **Detail Transaksi:**\n"
            f"├ ID: `{topup_data['transaction_id']}`\n"
            f"├ Nominal: {format_currency(topup_data['unique_amount'])}\n"
            f"├ Kode Unik: {topup_data['unique_digits']:03d}\n"
            f"└ Status: **Menunggu Verifikasi Admin**\n\n"
            f"⏰ **Proses verifikasi 1-10 menit**\n"
            f"• Admin akan memverifikasi pembayaran Anda\n"
            f"• Saldo otomatis ditambahkan setelah diverifikasi\n"
            f"• Anda akan mendapat notifikasi ketika selesai",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in process_proof_upload: {e}")
        await update.message.reply_text("❌ Terjadi error saat mengupload bukti. Silakan coba lagi.")
        return UPLOAD_PROOF

async def notify_admin_proof_upload(context: ContextTypes.DEFAULT_TYPE, topup_data: dict, file_id: str):
    """Notify admin about proof upload"""
    if not ADMIN_CHAT_ID:
        logger.warning("ADMIN_CHAT_ID not configured, skipping admin notification")
        return
        
    try:
        admin_notification = (
            f"🔔 **BUKTI PEMBAYARAN BARU**\n\n"
            f"👤 **User:** {topup_data['full_name']} (@{topup_data['username']})\n"
            f"🆔 **User ID:** {topup_data['user_id']}\n"
            f"💳 **Transaksi ID:** `{topup_data['transaction_id']}`\n"
            f"💰 **Nominal:** {format_currency(topup_data['unique_amount'])}\n"
            f"🔢 **Kode Unik:** {topup_data['unique_digits']:03d}\n"
            f"⏰ **Waktu:** {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )

        await context.bot.send_photo(
            chat_id=ADMIN_CHAT_ID,
            photo=file_id,
            caption=admin_notification,
            parse_mode='Markdown'
        )
        
        # Add quick action buttons for admin
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{topup_data['transaction_id']}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{topup_data['transaction_id']}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text="**Tindakan Cepat:**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

# ==================== PENDING TOPUPS ====================
async def show_pending_topups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's pending topups"""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = str(query.from_user.id)
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
        
        for topup in user_pending[:5]:  # Show last 5 pending
            method = "QRIS" if topup.get('payment_method') == 'qris' else "Transfer Bank"
            
            pending_text += (
                f"💰 **{format_currency(topup['amount'])}**\n"
                f"├ Metode: {method}\n"
                f"├ Waktu: {topup['created_at'].strftime('%d/%m/%Y %H:%M')}\n"
                f"└ ID: `{topup['id']}`\n\n"
            )
        
        pending_text += "⏰ **Status:** Menunggu verifikasi admin"
        
        await query.edit_message_text(
            pending_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="topup_pending")],
                [InlineKeyboardButton("💳 Topup Lagi", callback_data="topup_start")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error in show_pending_topups: {e}")
        await update.callback_query.message.reply_text("❌ Error memuat data pending topup.")

# ==================== CANCEL HANDLER ====================
async def cancel_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the topup process"""
    try:
        context.user_data.clear()
        
        if update.message:
            await update.message.reply_text(
                "❌ **Top Up Dibatalkan**\n\n"
                "Kembali ke menu utama.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
                ])
            )
        elif update.callback_query:
            await update.callback_query.edit_message_text(
                "❌ **Top Up Dibatalkan**\n\n"
                "Kembali ke menu utama.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
                ])
            )
            
    except Exception as e:
        logger.error(f"Error in cancel_topup: {e}")
        
    return ConversationHandler.END

# ==================== ERROR HANDLER ====================
async def topup_error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in topup conversation"""
    logger.error(f"Exception in topup handler: {context.error}", exc_info=context.error)
    
    try:
        if update and update.message:
            await update.message.reply_text(
                "❌ **Terjadi error yang tidak terduga**\n\n"
                "Silakan coba lagi atau hubungi admin.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
                ])
            )
        context.user_data.clear()
    except Exception as e:
        logger.error(f"Error in error handler: {e}")
    
    return ConversationHandler.END

# ==================== CONVERSATION HANDLER SETUP ====================
def get_topup_conversation_handler():
    """Return the topup conversation handler"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(topup_start, pattern="^topup_start$"),
            CallbackQueryHandler(topup_start, pattern="^topup_manual$"),
            CommandHandler("topup", topup_start)
        ],
        states={
            ASK_TOPUP_NOMINAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, topup_nominal)
            ],
            CONFIRM_TOPUP: [
                CallbackQueryHandler(handle_payment_method, pattern="^payment_"),
                CallbackQueryHandler(cancel_topup, pattern="^cancel_topup$")
            ],
            UPLOAD_PROOF: [
                CallbackQueryHandler(handle_payment_proof, pattern="^upload_proof$"),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, process_proof_upload),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_payment_proof)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_topup),
            CallbackQueryHandler(cancel_topup, pattern="^cancel_topup$")
        ],
        allow_reentry=True
    )

# ==================== HANDLER REGISTRATION ====================
def register_topup_handlers(application):
    """Register all topup-related handlers"""
    
    # Register conversation handler
    application.add_handler(get_topup_conversation_handler())
    
    # Register callback handlers for topup menu
    application.add_handler(CallbackQueryHandler(show_topup_menu, pattern="^topup_menu$"))
    application.add_handler(CallbackQueryHandler(show_topup_history, pattern="^topup_history$"))
    application.add_handler(CallbackQueryHandler(show_pending_topups, pattern="^topup_pending$"))
    
    # Register error handler
    application.add_error_handler(topup_error_handler)
    
    logger.info("✅ Topup handlers registered successfully")

# ==================== MAIN MENU HANDLER ====================
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu callback"""
    try:
        query = update.callback_query
        await query.answer()
        
        # You can redirect to your existing main menu handler
        from main_handler import show_main_menu  # Adjust import as needed
        await show_main_menu(update, context)
        
    except ImportError:
        # Fallback if main handler is not available
        await query.edit_message_text(
            "🏠 **Menu Utama**\n\n"
            "Silakan pilih menu yang tersedia:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Topup Saldo", callback_data="topup_menu")],
                [InlineKeyboardButton("🛍️ Beli Produk", callback_data="product_menu")],
                [InlineKeyboardButton("📞 Bantuan", callback_data="help_menu")]
            ])
        )
    except Exception as e:
        logger.error(f"Error in main_menu: {e}")
        await update.callback_query.message.reply_text("❌ Error memuat menu utama.")
