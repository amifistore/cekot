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
        logger.info(f"📦 [QRIS] Payload: {payload}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                QRIS_API_URL,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            ) as resp:
                
                response_text = await resp.text()
                logger.info(f"📥 [QRIS] Response status: {resp.status}")
                logger.info(f"📥 [QRIS] Response: {response_text}")
                
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

def format_topup_instructions(unique_amount: int, unique_digits: int, payment_method: str = "QRIS") -> str:
    """Format instruksi pembayaran yang jelas"""
    
    bank_instructions = """
🏦 **INSTRUKSI TRANSFER BANK:**
➖➖➖➖➖➖➖➖➖➖
📤 **Transfer Ke Bank:**
• Bank: BCA / BRI / BNI / Mandiri
• Rekening: 123-456-7890
• Atas Nama: BOT STORE

💰 **Nominal Transfer:**
• **Rp {amount:,}** 
• (Termasuk kode unik **{unique_digits:03d}**)

📝 **Catatan:**
• Transfer sesuai nominal di atas
• Kode unik WAJIB untuk verifikasi
• Simpan bukti transfer
➖➖➖➖➖➖➖➖➖➖
""".format(amount=unique_amount, unique_digits=unique_digits)

    qris_instructions = """
📱 **INSTRUKSI QRIS:**
➖➖➖➖➖➖➖➖➖➖
1. Buka aplikasi mobile banking/e-wallet
2. Pilih fitur QRIS/Scan QR
3. Scan kode QR di bawah
4. Pastikan nominal: **Rp {amount:,}**
5. Konfirmasi pembayaran
6. Simpan bukti bayar

💡 **Supported Apps:**
• GoPay, OVO, Dana, LinkAja
• Mobile Banking (BCA, BRI, BNI, Mandiri, dll)
• E-wallet lainnya yang support QRIS
➖➖➖➖➖➖➖➖➖➖
""".format(amount=unique_amount)

    instructions = qris_instructions if payment_method == "QRIS" else bank_instructions
    
    return f"""
💳 **TOPUP SALDO - KONFIRMASI**

💰 **Detail Pembayaran:**
├ Nominal: **Rp {unique_amount:,}**
├ Kode Unik: **{unique_digits:03d}**
├ Metode: **{payment_method}**
└ Status: **Menunggu Pembayaran**

{instructions}
⏰ **Penting:**
• Saldo akan ditambahkan setelah pembayaran dikonfirmasi
• Proses verifikasi 1-10 menit
• Hubungi admin jika ada kendala
"""

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
            f"• Minimal: Rp {MIN_TOPUP_AMOUNT:,}\n"
            f"• Maksimal: Rp {MAX_TOPUP_AMOUNT:,}\n"
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
            [InlineKeyboardButton("💳 Topup Sekarang", callback_data="topup_manual")],
            [InlineKeyboardButton("📋 Riwayat Topup", callback_data="topup_history")],
        ]
        
        if user_pending:
            keyboard.insert(0, [InlineKeyboardButton("⏳ Topup Pending", callback_data="topup_pending")])
        
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = f"""
💰 **MENU TOPUP SALDO**

💳 **Saldo Anda:** Rp {saldo:,.0f}
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

async def handle_topup_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manual topup callback"""
    try:
        query = update.callback_query
        await query.answer()
        
        # Start topup process
        return await topup_start(update, context)
        
    except Exception as e:
        logger.error(f"Error in handle_topup_manual: {e}")
        await update.callback_query.message.reply_text("❌ Error memulai topup.")
        return ConversationHandler.END

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
                f"❌ **Minimum top up Rp {MIN_TOPUP_AMOUNT:,}**\n\n"
                f"Nominal yang Anda masukkan: Rp {base_amount:,}\n"
                "Silakan masukkan nominal yang lebih besar:"
            )
            return ASK_TOPUP_NOMINAL
        
        if base_amount > MAX_TOPUP_AMOUNT:
            await update.message.reply_text(
                f"❌ **Maximum top up Rp {MAX_TOPUP_AMOUNT:,}**\n\n"
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
                InlineKeyboardButton("📱 QRIS", callback_data="payment_qris"),
                InlineKeyboardButton("🏦 Transfer Bank", callback_data="payment_bank")
            ],
            [InlineKeyboardButton("❌ Batalkan", callback_data="cancel_topup")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"💳 **KONFIRMASI TOPUP**\n\n"
            f"📊 **Detail Topup:**\n"
            f"├ Nominal: Rp {base_amount:,}\n"
            f"├ Kode Unik: {unique_digits:03d}\n"
            f"├ Total Transfer: **Rp {unique_amount:,}**\n"
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
                await loading_msg.edit_text(
                    f"❌ **Gagal generate QRIS:** {error}\n\n"
                    "Silakan pilih metode transfer bank atau hubungi admin."
                )
                # Tetap beri opsi untuk lanjut dengan upload bukti manual
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
                proof_text=f"QRIS Topup - {base_amount} + {unique_digits}"
            )
            
            topup_data['transaction_id'] = transaction_id
            context.user_data['topup_data'] = topup_data
            
            # Send QRIS image
            try:
                # Decode base64 image
                qris_bytes = base64.b64decode(qris_image)
                
                # Send QRIS image with caption
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=BytesIO(qris_bytes),
                    caption=format_topup_instructions(unique_amount, unique_digits, "QRIS"),
                    parse_mode='Markdown'
                )
                
                # Edit loading message to show success
                success_message = (
                    f"✅ **QRIS Berhasil Digenerate!**\n\n"
                    f"📊 **Detail Transaksi:**\n"
                    f"├ ID: `{transaction_id}`\n"
                    f"├ Nominal: Rp {unique_amount:,}\n"
                    f"├ Kode Unik: {unique_digits:03d}\n"
                    f"└ Status: Menunggu Pembayaran\n\n"
                    f"💡 **Instruksi:**\n"
                    f"• Scan QR code di atas\n"
                    f"• Bayar tepat **Rp {unique_amount:,}**\n"
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
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        "💡 Jika sudah bayar tapi saldo belum masuk, Anda bisa upload bukti bayar:",
        reply_markup=reply_markup
    )
    
    return UPLOAD_PROOF

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
        proof_text=f"Bank Transfer - {base_amount} + {unique_digits}"
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
        f"├ Nominal Topup: Rp {base_amount:,}\n"
        f"├ Kode Unik: {unique_digits:03d}\n"
        f"├ Total Transfer: **Rp {unique_amount:,}**\n"
        f"└ Status: Menunggu Pembayaran\n\n"
        f"{bank_info}\n"
        f"💡 **Instruksi:**\n"
        f"1. Transfer ke salah satu rekening di atas\n"
        f"2. Transfer tepat **Rp {unique_amount:,}**\n"
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
                "📎 **Upload Bukti Pembayaran**\n\n"
                "Silakan upload bukti pembayaran (foto/screenshot):\n\n"
                "📸 **Format yang diterima:**\n"
                "• Foto bukti transfer\n"
                "• Screenshot pembayaran\n"
                "• File gambar (JPEG, PNG)\n\n"
                "Ketik /cancel untuk membatalkan."
            )
            return UPLOAD_PROOF
    
    topup_data = context.user_data.get('topup_data')
    
    if not topup_data:
        await update.message.reply_text("❌ Data topup tidak ditemukan. Silakan mulai ulang.")
        return ConversationHandler.END
    
    transaction_id = topup_data.get('transaction_id')
    unique_amount = topup_data['unique_amount']
    
    # Check if message contains photo or document
    if update.message.photo:
        # Photo proof
        photo_file = await update.message.photo[-1].get_file()
        proof_type = "photo"
        proof_info = "Bukti transfer (foto)"
    elif update.message.document:
        # Document proof
        document = update.message.document
        if document.file_size > 10 * 1024 * 1024:  # 10MB limit
            await update.message.reply_text("❌ File terlalu besar. Maksimal 10MB.")
            return UPLOAD_PROOF
        photo_file = await document.get_file()
        proof_type = "document"
        proof_info = f"Bukti transfer ({document.file_name})"
    else:
        await update.message.reply_text(
            "❌ Silakan upload bukti transfer dalam bentuk foto atau document.\n\n"
            "📎 **Format yang diterima:**\n"
            "• Foto/screenshot bukti transfer\n"
            "• PDF/file document\n\n"
            "Silakan upload bukti transfer:"
        )
        return UPLOAD_PROOF
    
    try:
        # Notify admin about pending topup
        await notify_admin_pending_topup(context, topup_data, transaction_id, proof_type)
        
        # Send confirmation to user
        keyboard = [
            [InlineKeyboardButton("📋 Status Topup", callback_data="topup_pending")],
            [InlineKeyboardButton("💰 Cek Saldo", callback_data="menu_saldo")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **Bukti Transfer Diterima!**\n\n"
            f"📊 **Detail Transaksi:**\n"
            f"├ ID: `{transaction_id}`\n"
            f"├ Nominal: Rp {unique_amount:,}\n"
            f"├ Status: Menunggu Konfirmasi\n"
            f"└ Admin: Akan memverifikasi\n\n"
            f"⏰ **Proses verifikasi 1-10 menit.**\n"
            f"Anda akan mendapat notifikasi ketika saldo ditambahkan.\n\n"
            f"📞 **Butuh bantuan?** Hubungi admin.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # Clean up context
        if 'topup_data' in context.user_data:
            del context.user_data['topup_data']
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error handling payment proof: {e}")
        await update.message.reply_text("❌ Gagal mengupload bukti. Silakan coba lagi.")
        return UPLOAD_PROOF

async def notify_admin_pending_topup(context, topup_data, transaction_id, proof_type):
    """Notify admin about pending topup"""
    try:
        admin_ids = getattr(config, 'ADMIN_TELEGRAM_IDS', [])
        
        for admin_id in admin_ids:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"🆕 **TOPUP BARU - MENUNGGU KONFIRMASI**\n\n"
                        f"👤 **User:** {topup_data['full_name']} (@{topup_data['username']})\n"
                        f"🆔 **User ID:** `{topup_data['user_id']}`\n"
                        f"💰 **Amount:** Rp {topup_data['unique_amount']:,}\n"
                        f"📝 **Kode Unik:** {topup_data['unique_digits']:03d}\n"
                        f"🆔 **Transaksi ID:** {transaction_id}\n"
                        f"📎 **Proof Type:** {proof_type}\n\n"
                        f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}"
                    ),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error in notify_admin_pending_topup: {e}")

# ==================== OTHER TOPUP HANDLERS ====================
async def handle_topup_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show topup history"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📋 **RIWAYAT TOPUP**\n\n"
        "Fitur ini sedang dalam pengembangan.\n\n"
        "Segera hadir! ⚡",
        parse_mode='Markdown'
    )

async def show_manage_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show manage topup menu - alias untuk show_topup_menu"""
    await show_topup_menu(update, context)

async def handle_topup_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle topup history callback"""
    query = update.callback_query
    await query.answer()
    await handle_topup_history(update, context)

async def topup_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel topup process"""
    await update.message.reply_text("❌ Topup dibatalkan.")
    return ConversationHandler.END

# ==================== CONVERSATION HANDLER ====================
topup_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(handle_topup_manual, pattern='^topup_manual$'),
        CommandHandler('topup', topup_start)
    ],
    states={
        ASK_TOPUP_NOMINAL: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, topup_nominal)
        ],
        CONFIRM_TOPUP: [
            CallbackQueryHandler(handle_payment_method, pattern='^(payment_qris|payment_bank|cancel_topup)$')
        ],
        UPLOAD_PROOF: [
            CallbackQueryHandler(handle_payment_proof, pattern='^upload_proof$'),
            MessageHandler(filters.PHOTO | filters.Document.ALL, handle_payment_proof)
        ],
    },
    fallbacks=[CommandHandler('cancel', topup_cancel)]
)

# Export functions untuk kompatibilitas
async def show_topup_menu_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wrapper untuk show_topup_menu"""
    return await show_topup_menu(update, context)

show_manage_topup = show_topup_menu_wrapper
handle_topup_manual = handle_topup_manual
handle_topup_history = handle_topup_history_callback
