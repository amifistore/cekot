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
    Generate QRIS payment menggunakan API.
    Returns: (qris_base64, qr_content, error_message)
    """
    try:
        if not QRIS_API_URL or not QRIS_STATIS:
            return None, None, "Konfigurasi API QRIS tidak lengkap."
            
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
        error_msg = "API QRIS timeout setelah 30 detik"
        logger.error(f"❌ [QRIS] {error_msg}")
        return None, None, error_msg
        
    except Exception as e:
        error_msg = f"Gagal membuat QRIS: {str(e)}"
        logger.error(f"❌ [QRIS] {error_msg}")
        return None, None, error_msg

# ==================== TOPUP START & MENU ====================
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
            await update.callback_query.answer()
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
        database.get_or_create_user(str(user.id), user.username, user.full_name)
        saldo = database.get_user_saldo(str(user.id))
        
        pending_topups = database.get_pending_topups_by_user(str(user.id))
        
        keyboard = [
            [InlineKeyboardButton("💳 Topup Sekarang", callback_data="topup_start")],
            [InlineKeyboardButton("📋 Riwayat Topup", callback_data="topup_history")],
        ]
        
        if pending_topups:
            keyboard.insert(1, [InlineKeyboardButton(f"⏳ Topup Pending ({len(pending_topups)})", callback_data="topup_pending")])
        
        keyboard.append([InlineKeyboardButton("🏠 Kembali ke Menu Utama", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = (
            f"💰 **MENU TOPUP SALDO**\n\n"
            f"💳 **Saldo Anda:** {format_currency(saldo)}\n"
            f"📊 **Topup Pending:** {len(pending_topups)} transaksi\n\n"
            "Pilih salah satu opsi di bawah ini:"
        )
        
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
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Topup Lagi", callback_data="topup_start")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="topup_menu")]
        ])

        if not topups:
            await query.edit_message_text(
                "📋 **RIWAYAT TOPUP**\n\nAnda belum memiliki riwayat topup.",
                reply_markup=keyboard
            )
            return
        
        history_text = "📋 **RIWAYAT TOPUP ANDA**\n\n"
        
        for topup in topups[:10]:  # Show last 10 topups
            status_map = {
                'completed': ('✅', 'Selesai'),
                'pending': ('⏳', 'Pending'),
                'rejected': ('❌', 'Ditolak')
            }
            status_emoji, status_text = status_map.get(topup['status'], ('❓', 'Tidak Diketahui'))
            
            history_text += (
                f"💰 **{format_currency(topup['amount'])}**\n"
                f"├ Status: {status_emoji} {status_text}\n"
                f"├ Waktu: {topup['created_at'].strftime('%d/%m/%Y %H:%M')}\n"
                f"└ ID: `{topup['id']}`\n\n"
            )
        
        await query.edit_message_text(
            history_text,
            parse_mode='Markdown',
            reply_markup=keyboard
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
        
        if not nominal_input.isdigit():
            await update.message.reply_text(
                "❌ **Format salah!**\nMasukkan angka saja (contoh: `50000`).\nSilakan coba lagi:"
            )
            return ASK_TOPUP_NOMINAL
        
        base_amount = int(nominal_input)
        
        if not (MIN_TOPUP_AMOUNT <= base_amount <= MAX_TOPUP_AMOUNT):
            await update.message.reply_text(
                f"❌ **Nominal tidak valid!**\n"
                f"Minimal: {format_currency(MIN_TOPUP_AMOUNT)}\n"
                f"Maksimal: {format_currency(MAX_TOPUP_AMOUNT)}\n"
                "Silakan masukkan nominal yang sesuai:"
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
            'payment_method': None # IMPROVEMENT: Initialize payment_method
        }
        
        keyboard = [
            [
                InlineKeyboardButton("📱 QRIS (Otomatis)", callback_data="payment_qris"),
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
            f"├ **Total Transfer: {format_currency(unique_amount)}**\n\n"
            f"Silakan pilih metode pembayaran:",
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
    
    method = query.data
    topup_data = context.user_data.get('topup_data')
    
    if not topup_data:
        await query.edit_message_text("❌ Sesi topup berakhir. Silakan mulai ulang dengan /topup.")
        return ConversationHandler.END

    unique_amount = topup_data['unique_amount']
    
    try:
        if method == "payment_qris":
            topup_data['payment_method'] = 'qris' # IMPROVEMENT
            loading_msg = await query.edit_message_text("🔄 Sedang membuat kode QRIS, mohon tunggu...")
            
            qris_b64, _, error = await generate_qris_payment(unique_amount)
            
            await loading_msg.delete() # IMPROVEMENT: Clean up loading message

            if error:
                keyboard = [
                    [InlineKeyboardButton("🏦 Coba Transfer Bank", callback_data="payment_bank")],
                    [InlineKeyboardButton("❌ Batalkan", callback_data="cancel_topup")]
                ]
                await query.message.reply_text(
                    f"❌ **Gagal membuat QRIS:** {error}\n\nSilakan coba metode lain atau batalkan.",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return CONFIRM_TOPUP
            
            transaction_id = database.add_pending_topup(
                user_id=topup_data['user_id'],
                amount=unique_amount,
                proof_text=f"QRIS Topup",
                payment_method="qris"
            )
            topup_data['transaction_id'] = transaction_id
            
            caption = create_qris_instructions(unique_amount, transaction_id)
            qris_bytes = base64.b64decode(qris_b64)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Kembali ke Menu Utama", callback_data="main_menu")]
            ])

            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=BytesIO(qris_bytes),
                caption=caption,
                parse_mode='Markdown',
                reply_markup=keyboard # IMPROVEMENT: Add button for navigation
            )
            
            context.user_data.clear()
            return ConversationHandler.END # FIX: End conversation for QRIS path

        elif method == "payment_bank":
            topup_data['payment_method'] = 'bank_transfer' # IMPROVEMENT
            await show_bank_instructions(query, context, topup_data)
            return UPLOAD_PROOF
            
        elif method == "cancel_topup":
            await query.edit_message_text("❌ **Top Up Dibatalkan**")
            context.user_data.clear()
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Error in handle_payment_method: {e}")
        await query.edit_message_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

def create_qris_instructions(unique_amount: int, transaction_id: str) -> str:
    """Create QRIS payment instructions"""
    return (
        f"📱 **PEMBAYARAN VIA QRIS**\n\n"
        f"Silakan scan QR Code di atas menggunakan aplikasi E-Wallet atau M-Banking Anda.\n\n"
        f"📊 **Detail Transaksi:**\n"
        f"├ ID Transaksi: `{transaction_id}`\n"
        f"├ **Total Bayar: {format_currency(unique_amount)}**\n"
        f"└ Metode: **QRIS (Otomatis)**\n\n"
        f"⏰ **PENTING:**\n"
        f"• Pastikan nominal transfer **SESUAI PERSIS**.\n"
        f"• Saldo akan bertambah otomatis dalam 1-10 menit setelah pembayaran berhasil.\n"
        f"• Tidak perlu upload bukti bayar."
    )

async def show_bank_instructions(query, context, topup_data):
    """Show bank transfer instructions"""
    transaction_id = database.add_pending_topup(
        user_id=topup_data['user_id'],
        amount=topup_data['unique_amount'],
        proof_text=f"Bank Transfer",
        payment_method="bank_transfer"
    )
    
    topup_data['transaction_id'] = transaction_id
    
    bank_info = (
        "🏦 **INFORMASI REKENING:**\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "**BCA:** `1234567890` (a.n. Admin)\n"
        "**BRI:** `0987654321` (a.n. Admin)\n"
        "**Mandiri:** `1122334455` (a.n. Admin)\n"
        "➖➖➖➖➖➖➖➖➖➖"
    )
    
    instructions = (
        f"🏦 **TRANSFER BANK MANUAL**\n\n"
        f"Silakan lakukan transfer ke salah satu rekening di bawah ini.\n\n"
        f"📊 **Detail Transfer:**\n"
        f"├ ID Transaksi: `{transaction_id}`\n"
        f"├ **Total Transfer: {format_currency(topup_data['unique_amount'])}**\n"
        f"└ Kode Unik: {topup_data['unique_digits']:03d}\n\n"
        f"{bank_info}\n\n"
        f"✅ **Langkah Selanjutnya:**\n"
        f"Setelah transfer, klik tombol di bawah untuk **mengirim bukti pembayaran**."
    )
    
    keyboard = [
        [InlineKeyboardButton("📎 Upload Bukti Transfer", callback_data="upload_proof_prompt")],
        [InlineKeyboardButton("❌ Batalkan Topup", callback_data="cancel_topup")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        instructions,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ==================== PROOF UPLOAD HANDLER ====================
async def prompt_proof_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask user to send their payment proof."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📎 **UPLOAD BUKTI PEMBAYARAN**\n\n"
        "Kirimkan screenshot atau foto bukti transfer Anda sebagai gambar.\n\n"
        "Pastikan nominal dan tujuan transfer terlihat jelas."
    )
    return UPLOAD_PROOF

async def process_proof_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process uploaded payment proof"""
    try:
        topup_data = context.user_data.get('topup_data')
        if not topup_data or not topup_data.get('transaction_id'):
            await update.message.reply_text("❌ Sesi topup berakhir. Silakan mulai dari awal dengan /topup.")
            return ConversationHandler.END
        
        transaction_id = topup_data['transaction_id']
        user_id = topup_data['user_id']
        
        if not update.message.photo:
            await update.message.reply_text(
                "❌ File tidak valid. Harap kirim bukti transfer dalam format **gambar/foto**."
            )
            return UPLOAD_PROOF
        
        file = await update.message.photo[-1].get_file()
        
        create_proofs_directory()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = f"proofs/proof_{user_id}_{transaction_id}_{timestamp}.jpg"
        
        await file.download_to_drive(file_path)
        
        database.update_topup_proof(transaction_id, file_path)
        
        if ADMIN_CHAT_ID:
            try:
                admin_message = (
                    f"🔔 **TOPUP MANUAL BARU**\n\n"
                    f"👤 **User:** {topup_data['full_name']} (@{topup_data['username']})\n"
                    f"🆔 **User ID:** `{user_id}`\n"
                    f"💰 **Amount:** {format_currency(topup_data['unique_amount'])}\n"
                    f"📊 **Transaction ID:** `{transaction_id}`\n\n"
                    f"⚠️ **Mohon segera verifikasi pembayaran ini.**"
                )
                await context.bot.send_photo(
                    chat_id=ADMIN_CHAT_ID,
                    photo=open(file_path, 'rb'),
                    caption=admin_message,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error notifying admin: {e}")
        
        keyboard = [
            [InlineKeyboardButton("🏠 Kembali ke Menu Utama", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **Bukti Pembayaran Diterima!**\n\n"
            f"Terima kasih. Kami akan segera memverifikasi pembayaran Anda (biasanya dalam 1-60 menit).\n\n"
            f"Anda akan menerima notifikasi setelah saldo berhasil ditambahkan.\n\n"
            f"**ID Transaksi Anda:** `{transaction_id}`",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        context.user_data.clear()
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in process_proof_upload: {e}")
        await update.message.reply_text("❌ Terjadi error saat mengupload bukti. Silakan coba lagi.")
        return UPLOAD_PROOF

# ==================== PENDING TOPUPS HANDLER ====================
async def show_pending_topups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's pending topups"""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = str(query.from_user.id)
        user_pending = database.get_pending_topups_by_user(user_id)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Topup Lagi", callback_data="topup_start")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="topup_menu")]
        ])

        if not user_pending:
            await query.edit_message_text(
                "⏳ **TOPUP PENDING**\n\nTidak ada topup yang sedang menunggu verifikasi.",
                reply_markup=keyboard
            )
            return
        
        pending_text = "⏳ **TOPUP PENDING ANDA**\n\n"
        
        for topup in user_pending[:5]:
            method_map = {'qris': '📱 QRIS', 'bank_transfer': '🏦 Transfer Bank'}
            method_text = method_map.get(topup['payment_method'], 'Lainnya')
            
            pending_text += (
                f"💰 **{format_currency(topup['amount'])}**\n"
                f"├ Metode: {method_text}\n"
                f"├ Waktu: {topup['created_at'].strftime('%d/%m/%Y %H:%M')}\n"
                f"└ ID: `{topup['id']}`\n\n"
            )
        
        await query.edit_message_text(
            pending_text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error in show_pending_topups: {e}")
        await update.callback_query.message.reply_text("❌ Error memuat data pending topup.")

# ==================== CANCEL HANDLER ====================
async def cancel_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel topup process"""
    message_text = "❌ **Proses top up telah dibatalkan.**"
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message_text)
    else:
        await update.message.reply_text(message_text)
        
    context.user_data.clear()
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
                MessageHandler(filters.TEXT & ~filters.COMMAND, topup_nominal)
            ],
            CONFIRM_TOPUP: [
                CallbackQueryHandler(handle_payment_method, pattern="^payment_"),
            ],
            UPLOAD_PROOF: [
                MessageHandler(filters.PHOTO, process_proof_upload),
                # FIX: Handle non-photo messages in this state
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text("Harap kirim bukti dalam bentuk gambar/foto.")),
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
    """Return all topup-related handlers, including the conversation handler"""
    return [
        get_topup_conversation_handler(),
        CallbackQueryHandler(show_topup_menu, pattern="^topup_menu$"),
        CallbackQueryHandler(show_topup_history, pattern="^topup_history$"),
        CallbackQueryHandler(show_pending_topups, pattern="^topup_pending$"),
        # FIX: The button now calls a prompt function within the conversation
        CallbackQueryHandler(prompt_proof_upload, pattern="^upload_proof_prompt$")
    ]
