# topup_handler.py - Complete Topup System with QRIS
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
from database import db

logger = logging.getLogger(__name__)

# ==================== CONVERSATION STATES ====================
ASK_TOPUP_NOMINAL, CONFIRM_TOPUP, UPLOAD_PROOF = range(3)

# ==================== TOPUP UTILITIES ====================
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

async def generate_qris_payment(unique_amount: int, description: str = "Topup Saldo") -> tuple:
    """Generate QRIS payment menggunakan API external"""
    try:
        logger.info(f"🔧 [QRIS] Generating QRIS untuk amount: {unique_amount}")
        
        payload = {
            "amount": str(unique_amount),
            "description": description,
            "qris_statis": getattr(config, 'QRIS_STATIS', '')
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                config.QRIS_API_URL,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if result.get("status") == "success" and "qris_base64" in result:
                        qris_base64 = result["qris_base64"]
                        if qris_base64 and len(qris_base64) > 100:
                            return qris_base64, result.get("qr_content"), None
                    return None, None, result.get('message', 'Unknown error from QRIS API')
                else:
                    return None, None, f"HTTP {resp.status}: {await resp.text()}"
                
    except asyncio.TimeoutError:
        return None, None, "QRIS API timeout"
    except Exception as e:
        logger.error(f"QRIS generation error: {e}")
        return None, None, f"Error: {str(e)}"

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
    """Mulai proses topup - Entry point"""
    try:
        user = update.effective_user
        user_id = db.get_or_create_user(str(user.id), user.username, user.full_name)
        
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            await query.edit_message_text(
                "💳 **TOP UP SALDO**\n\n"
                "Masukkan nominal top up (angka saja):\n"
                "✅ **Contoh:** `50000` untuk Rp 50.000\n\n"
                "💰 **Ketentuan:**
├ Minimal: Rp 10.000
├ Maksimal: Rp 1.000.000
├ Kode unik otomatis ditambahkan
└ Pilih metode pembayaran setelahnya\n\n"
                "❌ **Ketik /cancel untuk membatalkan**",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "💳 **TOP UP SALDO**\n\n"
                "Masukkan nominal top up (angka saja):\n"
                "✅ **Contoh:** `50000` untuk Rp 50.000\n\n"
                "💰 **Ketentuan:**
├ Minimal: Rp 10.000
├ Maksimal: Rp 1.000.000
├ Kode unik otomatis ditambahkan
└ Pilih metode pembayaran setelahnya\n\n"
                "❌ **Ketik /cancel untuk membatalkan**",
                parse_mode='Markdown'
            )
        
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
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_id = db.get_or_create_user(str(user.id), user.username, user.full_name)
    saldo = db.get_user_balance(str(user.id))
    
    # Get pending topups
    user_transactions = db.get_user_transactions(str(user.id), limit=5)
    pending_topups = [t for t in user_transactions if t['status'] == 'pending' and t['type'] == 'topup']
    
    keyboard = [
        [InlineKeyboardButton("💳 Topup Sekarang", callback_data="topup_manual")],
        [InlineKeyboardButton("📋 Riwayat Topup", callback_data="topup_history")],
    ]
    
    if pending_topups:
        keyboard.insert(0, [InlineKeyboardButton("⏳ Topup Pending", callback_data="topup_pending")])
    
    keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = f"""
💰 **MENU TOPUP SALDO**

💳 **Saldo Anda:** Rp {saldo:,.0f}
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

# ==================== NOMINAL PROCESSING ====================
async def topup_nominal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process nominal topup dengan validation lengkap"""
    try:
        nominal_input = update.message.text.strip()
        user = update.message.from_user
        user_id = db.get_or_create_user(str(user.id), user.username, user.full_name)
        
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
        if base_amount < config.MIN_TOPUP_AMOUNT:
            await update.message.reply_text(
                f"❌ **Minimum top up Rp {config.MIN_TOPUP_AMOUNT:,}**\n\n"
                f"Nominal yang Anda masukkan: Rp {base_amount:,}\n"
                "Silakan masukkan nominal yang lebih besar:"
            )
            return ASK_TOPUP_NOMINAL
        
        if base_amount > 1000000:  # Max 1 juta
            await update.message.reply_text(
                "❌ **Maximum top up Rp 1,000,000**\n\n"
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
            
            qris_image, qr_content, error = await generate_qris_payment(
                unique_amount, 
                f"Topup {topup_data['full_name']}"
            )
            
            if error:
                await loading_msg.edit_text(
                    f"❌ **Gagal generate QRIS:** {error}\n\n"
                    "Silakan pilih metode transfer bank."
                )
                # Fallback to bank transfer
                return await show_bank_instructions(query, context, topup_data)
            
            # Create transaction record
            transaction_id = db.add_transaction(
                user_id=user_id,
                trans_type='topup',
                amount=unique_amount,
                status='pending',
                details=f"QRIS Topup - {base_amount} + {unique_digits}",
                unique_code=unique_digits
            )
            
            topup_data['transaction_id'] = transaction_id
            context.user_data['topup_data'] = topup_data
            
            # Send QRIS image
            try:
                qris_bytes = base64.b64decode(qris_image)
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=BytesIO(qris_bytes),
                    caption=format_topup_instructions(unique_amount, unique_digits, "QRIS"),
                    parse_mode='Markdown'
                )
                
                # Edit loading message to show success
                await loading_msg.edit_text(
                    f"✅ **QRIS Berhasil Digenerate!**\n\n"
                    f"📊 **Detail Transaksi:**\n"
                    f"├ ID: `{transaction_id}`\n"
                    f"├ Nominal: Rp {unique_amount:,}\n"
                    f"├ Kode Unik: {unique_digits:03d}\n"
                    f"└ Status: Menunggu Pembayaran\n\n"
                    f"💡 **Instruksi:**\n"
                    f"• Scan QR code di atas\n"
                    f"• Bayar tepat Rp {unique_amount:,}\n"
                    f"• Simpan bukti bayar\n"
                    f"• Saldo otomatis setelah bayar",
                    parse_mode='Markdown'
                )
                
            except Exception as e:
                logger.error(f"Error sending QRIS: {e}")
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
    
    # For QRIS, wait for payment automatically
    return UPLOAD_PROOF

async def show_bank_instructions(query, context, topup_data):
    """Show bank transfer instructions"""
    user_id = topup_data['user_id']
    unique_amount = topup_data['unique_amount']
    unique_digits = topup_data['unique_digits']
    base_amount = topup_data['base_amount']
    
    # Create transaction record for bank transfer
    transaction_id = db.add_transaction(
        user_id=user_id,
        trans_type='topup',
        amount=unique_amount,
        status='pending',
        details=f"Bank Transfer - {base_amount} + {unique_digits}",
        unique_code=unique_digits
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
        # Update transaction with proof info
        db.update_transaction_status(
            transaction_id,
            status='pending',
            details=f"Payment proof uploaded - {proof_info} - Amount: {unique_amount}"
        )
        
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
        admin_ids = config.ADMIN_TELEGRAM_IDS
        
        message = (
            f"🆕 **TOPUP BARU - MENUNGGU KONFIRMASI**\n\n"
            f"👤 **User:** {topup_data['full_name']} (@{topup_data['username']})\n"
            f"🆔 **User ID:** `{topup_data['user_id']}`\n"
            f"💵 **Jumlah:** Rp {topup_data['unique_amount']:,}\n"
            f"🔢 **Kode Unik:** {topup_data['unique_digits']:03d}\n"
            f"🆔 **Transaksi ID:** `{transaction_id}`\n"
            f"📎 **Bukti:** {proof_type}\n"
            f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_topup:{transaction_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_topup:{transaction_id}")
            ],
            [InlineKeyboardButton("📋 List Topup", callback_data="admin_topup")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        for admin_id in admin_ids:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error in notify_admin_pending_topup: {e}")

# ==================== TOPUP STATUS & HISTORY ====================
async def show_topup_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's pending topup status"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_id = db.get_or_create_user(str(user.id), user.username, user.full_name)
    
    # Get pending topups
    user_transactions = db.get_user_transactions(str(user.id), limit=10)
    pending_topups = [t for t in user_transactions if t['status'] == 'pending' and t['type'] == 'topup']
    completed_topups = [t for t in user_transactions if t['status'] == 'completed' and t['type'] == 'topup']
    
    if not pending_topups:
        keyboard = [
            [InlineKeyboardButton("💳 Topup Sekarang", callback_data="topup_manual")],
            [InlineKeyboardButton("📋 Riwayat Topup", callback_data="topup_history")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "✅ **Tidak ada topup pending.**\n\n"
            "Semua topup Anda sudah diproses.",
            reply_markup=reply_markup
        )
        return
    
    message = "⏳ **TOPUP PENDING ANDA**\n\n"
    
    for topup in pending_topups[:5]:  # Show max 5 pending topups
        created_time = datetime.fromisoformat(topup['created_at'].replace('Z', '+00:00'))
        time_diff = datetime.now() - created_time
        hours_pending = int(time_diff.total_seconds() / 3600)
        minutes_pending = int((time_diff.total_seconds() % 3600) / 60)
        
        message += (
            f"🆔 **ID:** `{topup['id']}`\n"
            f"💵 **Jumlah:** Rp {topup['amount']:,}\n"
            f"🔢 **Kode Unik:** {topup['unique_code']:03d}\n"
            f"⏰ **Menunggu:** {hours_pending}h {minutes_pending}m\n"
            f"📝 **Status:** {topup['status'].title()}\n"
            f"────────────────────\n"
        )
    
    if len(pending_topups) > 5:
        message += f"\n... dan {len(pending_topups) - 5} topup pending lainnya\n"
    
    message += f"\n📊 **Total Pending:** {len(pending_topups)} topup"
    message += f"\n✅ **Completed:** {len(completed_topups)} topup"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="topup_pending")],
        [InlineKeyboardButton("💳 Topup Baru", callback_data="topup_manual")],
        [InlineKeyboardButton("📋 Riwayat Lengkap", callback_data="topup_history")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_topup_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's topup history"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_id = db.get_or_create_user(str(user.id), user.username, user.full_name)
    
    # Get topup history
    user_transactions = db.get_user_transactions(str(user.id), limit=15)
    topup_history = [t for t in user_transactions if t['type'] == 'topup']
    
    if not topup_history:
        keyboard = [
            [InlineKeyboardButton("💳 Topup Sekarang", callback_data="topup_manual")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📭 **Belum ada riwayat topup.**\n\n"
            "Lakukan topup pertama Anda!",
            reply_markup=reply_markup
        )
        return
    
    # Calculate statistics
    total_topups = len(topup_history)
    completed_topups = len([t for t in topup_history if t['status'] == 'completed'])
    pending_topups = len([t for t in topup_history if t['status'] == 'pending'])
    total_amount = sum(t['amount'] for t in topup_history if t['status'] == 'completed')
    
    message = (
        f"📋 **RIWAYAT TOPUP**\n\n"
        f"📊 **Statistik:**\n"
        f"├ Total Topup: {total_topups}\n"
        f"├ Berhasil: {completed_topups}\n"
        f"├ Pending: {pending_topups}\n"
        f"└ Total Deposit: Rp {total_amount:,}\n\n"
        f"📜 **Riwayat Terbaru:**\n"
    )
    
    # Show recent topups
    for topup in topup_history[:8]:
        status_icon = "✅" if topup['status'] == 'completed' else "⏳" if topup['status'] == 'pending' else "❌"
        status_text = topup['status'].title()
        
        # Format time
        created_time = datetime.fromisoformat(topup['created_at'].replace('Z', '+00:00'))
        time_str = created_time.strftime('%d/%m %H:%M')
        
        message += (
            f"{status_icon} `{topup['id']:04d}` | "
            f"Rp {topup['amount']:>8,} | "
            f"{status_text:>8} | "
            f"{time_str}\n"
        )
    
    if len(topup_history) > 8:
        message += f"\n... dan {len(topup_history) - 8} topup sebelumnya"
    
    keyboard = [
        [InlineKeyboardButton("💳 Topup Sekarang", callback_data="topup_manual")],
        [InlineKeyboardButton("⏳ Cek Pending", callback_data="topup_pending")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="topup_history")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ==================== COMMAND HANDLERS ====================
async def topup_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel topup process"""
    await update.message.reply_text("❌ **Top Up Dibatalkan**")
    
    # Clean up context
    if 'topup_data' in context.user_data:
        del context.user_data['topup_data']
    
    return ConversationHandler.END

async def handle_topup_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk topup manual dari menu"""
    return await topup_start(update, context)

# ==================== CONVERSATION HANDLER ====================
def get_topup_conv_handler():
    """Return topup conversation handler"""
    return ConversationHandler(
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
                CallbackQueryHandler(handle_payment_method, pattern='^(payment_qris|payment_bank|cancel_topup)$')
            ],
            UPLOAD_PROOF: [
                MessageHandler(filters.PHOTO | filters.DOCUMENT | filters.TEXT, handle_payment_proof),
                CommandHandler('cancel', topup_cancel)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', topup_cancel),
            CommandHandler('topup', topup_start)
        ],
        allow_reentry=True
    )

def get_topup_handlers():
    """Return all topup handlers untuk registration"""
    return [
        get_topup_conv_handler(),
        CallbackQueryHandler(show_topup_menu, pattern='^menu_topup$'),
        CallbackQueryHandler(show_topup_status, pattern='^topup_pending$'),
        CallbackQueryHandler(show_topup_history, pattern='^topup_history$'),
        CallbackQueryHandler(handle_topup_manual, pattern='^topup_manual$')
    ]

# ==================== UTILITY FUNCTIONS ====================
async def get_user_topup_stats(user_id: str) -> dict:
    """Get user topup statistics"""
    try:
        user_transactions = db.get_user_transactions(user_id, limit=100)
        topup_transactions = [t for t in user_transactions if t['type'] == 'topup']
        
        total_topups = len(topup_transactions)
        completed_topups = len([t for t in topup_transactions if t['status'] == 'completed'])
        pending_topups = len([t for t in topup_transactions if t['status'] == 'pending'])
        total_deposited = sum(t['amount'] for t in topup_transactions if t['status'] == 'completed')
        
        return {
            'total_topups': total_topups,
            'completed_topups': completed_topups,
            'pending_topups': pending_topups,
            'total_deposited': total_deposited,
            'success_rate': (completed_topups / total_topups * 100) if total_topups > 0 else 0
        }
    except Exception as e:
        logger.error(f"Error getting user topup stats: {e}")
        return {
            'total_topups': 0,
            'completed_topups': 0,
            'pending_topups': 0,
            'total_deposited': 0,
            'success_rate': 0
        }
