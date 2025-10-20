#!/usr/bin/env python3
"""
Topup Handler untuk Bot Telegram - FIXED VERSION
Fitur: Topup saldo dengan nominal unik, QRIS generator, dan konfirmasi admin
"""

import logging
import random
import asyncio
import aiohttp
import json
from datetime import datetime
from typing import Dict, Any, List, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)

import config
import database

# ==================== LOGGING ====================
logger = logging.getLogger(__name__)

# ==================== CONVERSATION STATES ====================
SELECTING_AMOUNT, CONFIRMING_TOPUP, UPLOADING_PROOF, SELECTING_PAYMENT_METHOD = range(4)

# ==================== CONFIGURATION ====================
QRIS_API_URL = "https://qrisku.my.id/api"
QRIS_STATIC_CODE = getattr(config, 'QRIS_STATIC_CODE', '00020101021126690014COM.GO-JEK.WWW0118936009140319946531021520000005240000153033605802ID5914GOJEK INDONESIA6007JAKARTA61051234062130111QRIS Ref62280124A0123B4567C8901D234E6304')

# Nominal yang tersedia untuk topup
AVAILABLE_AMOUNTS = [
    10000, 20000, 50000, 100000, 150000, 200000, 250000, 300000, 
    500000, 750000, 1000000, 1500000, 2000000
]

# ==================== UTILITY FUNCTIONS ====================
def generate_unique_amount(base_amount: int) -> Tuple[int, int]:
    """
    Generate nominal unik dengan menambahkan 3 digit random di akhir
    Returns: (nominal_unik, kode_unik)
    """
    unique_code = random.randint(1, 999)
    unique_amount = base_amount + unique_code
    return unique_amount, unique_code

async def generate_qris_code(amount: int, session: aiohttp.ClientSession = None) -> Dict[str, Any]:
    """
    Generate QRIS code menggunakan API
    """
    payload = {
        "amount": str(amount),
        "qris_statis": QRIS_STATIC_CODE
    }
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    try:
        if session:
            async with session.post(QRIS_API_URL, json=payload, headers=headers) as response:
                result = await response.json()
        else:
            async with aiohttp.ClientSession() as session:
                async with session.post(QRIS_API_URL, json=payload, headers=headers) as response:
                    result = await response.json()
        
        logger.info(f"QRIS API Response: {result}")
        return result
    except Exception as e:
        logger.error(f"Error generating QRIS: {e}")
        return {"status": "error", "message": str(e)}

def get_payment_methods() -> List[List[InlineKeyboardButton]]:
    """Daftar metode pembayaran yang tersedia"""
    return [
        [InlineKeyboardButton("💳 QRIS (Otomatis)", callback_data="payment_qris")],
        [InlineKeyboardButton("🏦 Transfer Bank (Manual)", callback_data="payment_transfer")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="topup_cancel")]
    ]

# ==================== TOPUP MENU & CONVERSATION ====================
async def show_topup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan menu topup utama - FIXED VERSION"""
    try:
        logger.info("show_topup_menu called")
        
        # Reset user data
        context.user_data.clear()
        
        # Determine message source
        if hasattr(update, 'callback_query') and update.callback_query:
            query = update.callback_query
            await query.answer()
            message = query.message
            user = query.from_user
            edit_message = True
        else:
            message = update.message
            user = update.message.from_user
            edit_message = False

        # Get user data
        user_id = database.get_or_create_user(str(user.id), user.username or "", user.full_name)
        saldo = database.get_user_saldo(user_id)
        
        # Keyboard dengan nominal yang tersedia
        keyboard = []
        for i in range(0, len(AVAILABLE_AMOUNTS), 3):
            row = []
            for amount in AVAILABLE_AMOUNTS[i:i+3]:
                row.append(InlineKeyboardButton(f"Rp {amount:,}", callback_data=f"topup_amount_{amount}"))
            keyboard.append(row)
        
        # Tambahkan opsi input manual dan lainnya
        keyboard.extend([
            [InlineKeyboardButton("✏️ Input Manual", callback_data="topup_custom")],
            [InlineKeyboardButton("📋 Riwayat Topup", callback_data="topup_history")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            f"💸 **TOP UP SALDO**\n\n"
            f"💰 **Saldo Anda:** Rp {saldo:,}\n\n"
            f"Pilih nominal top up atau gunakan input manual:\n"
            f"➖ Minimal: Rp 10.000\n"
            f"➖ Maksimal: Rp 2.000.000\n\n"
            f"⚠️ **FITUR NOMINAL UNIK:**\n"
            f"Setiap top up akan memiliki nominal unik 3 digit untuk memudahkan verifikasi."
        )
        
        if edit_message:
            try:
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            except Exception as e:
                logger.warning(f"Could not edit message, sending new: {e}")
                await query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        logger.info("show_topup_menu completed successfully")
            
    except Exception as e:
        logger.error(f"Error in show_topup_menu: {e}", exc_info=True)
        error_msg = "❌ Terjadi error saat menampilkan menu topup."
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.reply_text(error_msg)
        else:
            await update.message.reply_text(error_msg)

async def topup_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memilih nominal topup - FIXED VERSION"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    logger.info(f"topup_amount_handler called with data: {data}")
    
    try:
        if data == "topup_custom":
            # Minta input manual
            await query.edit_message_text(
                "✏️ **INPUT MANUAL**\n\n"
                "Silakan masukkan nominal top up:\n"
                "➖ Minimal: Rp 10.000\n"
                "➖ Maksimal: Rp 2.000.000\n\n"
                "Contoh: `75000`",
                parse_mode='Markdown'
            )
            return SELECTING_AMOUNT
            
        elif data.startswith("topup_amount_"):
            # Nominal dari button
            amount = int(data.split("_")[2])
            context.user_data['topup_amount'] = amount
            await show_payment_methods(update, context)
            return SELECTING_PAYMENT_METHOD
            
    except Exception as e:
        logger.error(f"Error in topup_amount_handler: {e}", exc_info=True)
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def handle_custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk input manual nominal - FIXED VERSION"""
    try:
        amount_text = update.message.text.strip()
        
        # Hapus karakter non-digit kecuali koma dan titik
        amount_text = ''.join(c for c in amount_text if c.isdigit())
        
        # Validasi input
        if not amount_text:
            await update.message.reply_text(
                "❌ Format nominal tidak valid. Harap masukkan angka saja.\n"
                "Contoh: `75000`",
                parse_mode='Markdown'
            )
            return SELECTING_AMOUNT
        
        amount = int(amount_text)
        
        # Validasi range nominal
        if amount < 10000:
            await update.message.reply_text(
                "❌ Nominal terlalu kecil. Minimal top up adalah Rp 10.000"
            )
            return SELECTING_AMOUNT
            
        if amount > 2000000:
            await update.message.reply_text(
                "❌ Nominal terlalu besar. Maksimal top up adalah Rp 2.000.000"
            )
            return SELECTING_AMOUNT
        
        context.user_data['topup_amount'] = amount
        
        # Edit pesan sebelumnya untuk menghapus input manual
        await update.message.delete()
        
        await show_payment_methods(update, context)
        return SELECTING_PAYMENT_METHOD
        
    except ValueError:
        await update.message.reply_text(
            "❌ Format nominal tidak valid. Harap masukkan angka saja.\n"
            "Contoh: `75000`",
            parse_mode='Markdown'
        )
        return SELECTING_AMOUNT
    except Exception as e:
        logger.error(f"Error in handle_custom_amount: {e}", exc_info=True)
        await update.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def show_payment_methods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan pilihan metode pembayaran - FIXED VERSION"""
    try:
        amount = context.user_data.get('topup_amount', 0)
        
        # Generate nominal unik
        unique_amount, unique_code = generate_unique_amount(amount)
        context.user_data['unique_amount'] = unique_amount
        context.user_data['unique_code'] = unique_code
        
        text = (
            f"💸 **KONFIRMASI TOP UP**\n\n"
            f"📊 **Detail Transaksi:**\n"
            f"• Nominal Request: Rp {amount:,}\n"
            f"• Kode Unik: +{unique_code}\n"
            f"• **Total Bayar: Rp {unique_amount:,}**\n\n"
            f"Pilih metode pembayaran:"
        )
        
        reply_markup = InlineKeyboardMarkup(get_payment_methods())
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error in show_payment_methods: {e}", exc_info=True)
        error_msg = "❌ Terjadi error saat memilih metode pembayaran."
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.reply_text(error_msg)
        else:
            await update.message.reply_text(error_msg)

async def handle_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memilih metode pembayaran - FIXED VERSION"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    logger.info(f"handle_payment_method called with: {data}")
    
    try:
        if data == "payment_qris":
            await process_qris_payment(update, context)
            return ConversationHandler.END
            
        elif data == "payment_transfer":
            await process_transfer_payment(update, context)
            return ConversationHandler.END
            
        elif data == "topup_cancel":
            await query.edit_message_text(
                "❌ Top up dibatalkan.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💸 Top Up Lagi", callback_data="topup_menu")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ])
            )
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Error in handle_payment_method: {e}", exc_info=True)
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def process_qris_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Proses pembayaran dengan QRIS - FIXED VERSION"""
    try:
        query = update.callback_query
        user = query.from_user
        amount = context.user_data.get('topup_amount', 0)
        unique_amount = context.user_data.get('unique_amount', 0)
        unique_code = context.user_data.get('unique_code', 0)
        
        # Tampilkan pesan sedang memproses
        await query.edit_message_text(
            "🔄 **Membuat QRIS...**\n\n"
            "Silakan tunggu sebentar...",
            parse_mode='Markdown'
        )
        
        # Generate QRIS
        qris_result = await generate_qris_code(unique_amount)
        
        if qris_result.get('status') == 'success':
            qris_base64 = qris_result.get('qris_base64', '')
            
            # Simpan topup ke database
            user_id = database.get_or_create_user(str(user.id), user.username or "", user.full_name)
            topup_id = database.create_topup(
                user_id=user_id,
                amount=amount,
                unique_code=unique_code,
                total_amount=unique_amount,
                method='qris',
                status='pending'
            )
            
            # Kirim QRIS ke user
            text = (
                f"✅ **QRIS BERHASIL DIBUAT**\n\n"
                f"📊 **Detail Pembayaran:**\n"
                f"• Nominal: Rp {amount:,}\n"
                f"• Kode Unik: +{unique_code}\n"
                f"• **Total: Rp {unique_amount:,}**\n"
                f"• ID Transaksi: `{topup_id}`\n\n"
                f"**CARA BAYAR:**\n"
                f"1. Scan QRIS di bawah ini\n"
                f"2. Bayar tepat sesuai nominal\n"
                f"3. Pembayaran akan diverifikasi otomatis\n\n"
                f"⚠️ **Pastikan nominal tepat: Rp {unique_amount:,}**"
            )
            
            # Kirim gambar QRIS
            await query.message.reply_photo(
                photo=f"data:image/png;base64,{qris_base64}",
                caption=text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Cek Status", callback_data=f"check_topup_{topup_id}")],
                    [InlineKeyboardButton("💸 Top Up Lagi", callback_data="topup_menu")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ])
            )
            
            # Notifikasi admin
            await notify_admin_new_topup(context, topup_id, user, amount, unique_amount, 'qris')
            
        else:
            error_msg = qris_result.get('message', 'Unknown error')
            await query.edit_message_text(
                f"❌ **GAGAL MEMBUAT QRIS**\n\n"
                f"Error: {error_msg}\n\n"
                f"Silakan coba metode pembayaran lain.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Coba Lagi", callback_data="topup_menu")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ]),
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error in process_qris_payment: {e}", exc_info=True)
        await query.edit_message_text(
            "❌ Terjadi error saat membuat QRIS. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Coba Lagi", callback_data="topup_menu")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ])
        )

async def process_transfer_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Proses pembayaran dengan transfer manual - FIXED VERSION"""
    try:
        query = update.callback_query
        user = query.from_user
        amount = context.user_data.get('topup_amount', 0)
        unique_amount = context.user_data.get('unique_amount', 0)
        unique_code = context.user_data.get('unique_code', 0)
        
        # Simpan topup ke database
        user_id = database.get_or_create_user(str(user.id), user.username or "", user.full_name)
        topup_id = database.create_topup(
            user_id=user_id,
            amount=amount,
            unique_code=unique_code,
            total_amount=unique_amount,
            method='transfer',
            status='pending'
        )
        
        # Informasi rekening (dari config)
        bank_info = getattr(config, 'BANK_ACCOUNTS', [{
            'bank': 'BCA',
            'number': '1234567890',
            'name': 'Nama Pemilik Rekening'
        }])
        
        bank_text = "\n".join([f"• {acc['bank']}: `{acc['number']}` a.n {acc['name']}" for acc in bank_info])
        
        text = (
            f"🏦 **TRANSFER MANUAL**\n\n"
            f"📊 **Detail Pembayaran:**\n"
            f"• Nominal: Rp {amount:,}\n"
            f"• Kode Unik: +{unique_code}\n"
            f"• **Total: Rp {unique_amount:,}**\n"
            f"• ID Transaksi: `{topup_id}`\n\n"
            f"**REKENING TUJUAN:**\n"
            f"{bank_text}\n\n"
            f"**INSTRUKSI:**\n"
            f"1. Transfer tepat **Rp {unique_amount:,}** ke rekening di atas\n"
            f"2. Screenshot/simpan bukti transfer\n"
            f"3. Upload bukti transfer dengan tombol di bawah\n\n"
            f"⚠️ **Pastikan nominal transfer tepat!**"
        )
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📎 Upload Bukti Transfer", callback_data=f"upload_proof_{topup_id}")],
                [InlineKeyboardButton("💸 Top Up Lagi", callback_data="topup_menu")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ])
        )
        
        # Notifikasi admin
        await notify_admin_new_topup(context, topup_id, user, amount, unique_amount, 'transfer')
        
    except Exception as e:
        logger.error(f"Error in process_transfer_payment: {e}", exc_info=True)
        await query.edit_message_text(
            "❌ Terjadi error. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Coba Lagi", callback_data="topup_menu")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ])
        )

async def handle_proof_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk upload bukti transfer - FIXED VERSION"""
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        topup_id = int(data.split("_")[2])
        
        context.user_data['upload_topup_id'] = topup_id
        
        await query.edit_message_text(
            "📎 **UPLOAD BUKTI TRANSFER**\n\n"
            "Silakan upload screenshot/foto bukti transfer Anda.\n\n"
            "⚠️ Pastikan bukti transfer jelas terbaca:\n"
            "• Nominal transfer\n"
            "• Nama pengirim\n"
            "• Waktu transfer\n\n"
            "Kirim foto sebagai file (bukan sebagai gambar yang dikompres).",
            parse_mode='Markdown'
        )
        
        return UPLOADING_PROOF
        
    except Exception as e:
        logger.error(f"Error in handle_proof_upload: {e}", exc_info=True)
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def handle_proof_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menerima foto bukti transfer - FIXED VERSION"""
    try:
        user = update.message.from_user
        topup_id = context.user_data.get('upload_topup_id')
        
        if not topup_id:
            await update.message.reply_text("❌ Sesi upload tidak valid. Silakan mulai ulang.")
            return ConversationHandler.END
        
        # Dapatkan file photo (gunakan photo terbesar)
        if update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
        elif update.message.document:
            photo_file = await update.message.document.get_file()
        else:
            await update.message.reply_text("❌ Format tidak didukung. Silakan kirim foto atau file gambar.")
            return UPLOADING_PROOF
        
        # Simpan informasi bukti transfer
        proof_filename = f"proof_{topup_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        
        # Update database
        success = database.update_topup_proof(topup_id, proof_filename)
        
        if success:
            # Update status menunggu verifikasi
            database.update_topup_status(topup_id, 'waiting_approval')
            
            await update.message.reply_text(
                "✅ **BUKTI TRANSFER DITERIMA**\n\n"
                "Bukti transfer Anda telah berhasil diupload dan sedang menunggu verifikasi admin.\n\n"
                "Biasanya proses verifikasi memakan waktu 1-15 menit.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Cek Status", callback_data=f"check_topup_{topup_id}")],
                    [InlineKeyboardButton("💸 Top Up Lagi", callback_data="topup_menu")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ]),
                parse_mode='Markdown'
            )
            
            # Notifikasi admin tentang bukti transfer
            await notify_admin_proof_uploaded(context, topup_id, user, photo_file)
            
        else:
            await update.message.reply_text(
                "❌ Gagal menyimpan bukti transfer. Silakan hubungi admin.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Coba Lagi", callback_data="topup_menu")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ])
            )
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in handle_proof_photo: {e}", exc_info=True)
        await update.message.reply_text("❌ Terjadi error saat mengupload bukti. Silakan coba lagi.")
        return UPLOADING_PROOF

# ==================== TOPUP HISTORY ====================
async def show_topup_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan riwayat topup user - FIXED VERSION"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        user_id = database.get_or_create_user(str(user.id), user.username or "", user.full_name)
        
        # Dapatkan riwayat topup
        history = database.get_user_topups(user_id, limit=10)
        
        if not history:
            text = "📋 **RIWAYAT TOP UP**\n\n" \
                   "Anda belum melakukan top up."
        else:
            text = "📋 **RIWAYAT TOP UP**\n\n"
            for topup in history:
                status_emoji = {
                    'pending': '⏳',
                    'waiting_approval': '📋', 
                    'completed': '✅',
                    'cancelled': '❌'
                }.get(topup['status'], '❓')
                
                status_text = {
                    'pending': 'Menunggu Pembayaran',
                    'waiting_approval': 'Menunggu Verifikasi',
                    'completed': 'Berhasil',
                    'cancelled': 'Dibatalkan'
                }.get(topup['status'], topup['status'])
                
                text += (
                    f"{status_emoji} **Rp {topup['amount']:,}** "
                    f"(+{topup['unique_code']}) → "
                    f"**Rp {topup['total_amount']:,}**\n"
                    f"   Method: {topup['method'].upper()} | "
                    f"Status: {status_text}\n"
                    f"   Waktu: {topup['created_at']}\n\n"
                )
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💸 Top Up Baru", callback_data="topup_menu")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="topup_history")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error in show_topup_history: {e}", exc_info=True)
        await query.message.reply_text("❌ Terjadi error saat mengambil riwayat.")

async def show_pending_topups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan topup yang pending untuk admin - FIXED VERSION"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        
        # Cek apakah admin
        ADMIN_IDS = getattr(config, 'ADMIN_TELEGRAM_IDS', [])
        if str(user.id) not in ADMIN_IDS:
            await query.answer("❌ Anda bukan admin!", show_alert=True)
            return
        
        # Dapatkan topup pending
        pending_topups = database.get_pending_topups()
        
        if not pending_topups:
            text = "📋 **TOPUP MENUNGGU VERIFIKASI**\n\nTidak ada topup yang menunggu verifikasi."
        else:
            text = "📋 **TOPUP MENUNGGU VERIFIKASI**\n\n"
            for topup in pending_topups:
                user_info = database.get_user_by_id(topup['user_id'])
                status_text = "Menunggu Bukti" if topup['status'] == 'pending' and topup['method'] == 'transfer' else "Menunggu Pembayaran"
                
                text += (
                    f"🔔 **ID: {topup['id']}**\n"
                    f"👤 User: {user_info['full_name']} (@{user_info['username']})\n"
                    f"💰 Amount: Rp {topup['amount']:,} (+{topup['unique_code']})\n"
                    f"💳 Total: Rp {topup['total_amount']:,}\n"
                    f"📦 Method: {topup['method']}\n"
                    f"⏰ Waktu: {topup['created_at']}\n"
                    f"📝 Status: {status_text}\n\n"
                )
        
        keyboard = []
        for topup in pending_topups:
            keyboard.append([
                InlineKeyboardButton(
                    f"✅ Verifikasi #{topup['id']}", 
                    callback_data=f"admin_approve_topup_{topup['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="topup_pending_list")])
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")])
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error in show_pending_topups: {e}", exc_info=True)
        await query.message.reply_text("❌ Terjadi error saat mengambil data pending topup.")

# ==================== ADMIN NOTIFICATION ====================
async def notify_admin_new_topup(context: ContextTypes.DEFAULT_TYPE, topup_id: int, user, amount: int, total_amount: int, method: str):
    """Notify admin tentang topup baru - FIXED VERSION"""
    try:
        ADMIN_IDS = getattr(config, 'ADMIN_TELEGRAM_IDS', [])
        
        method_text = "QRIS" if method == 'qris' else "Transfer Bank"
        
        text = (
            f"🔔 **TOPUP BARU**\n\n"
            f"**ID:** #{topup_id}\n"
            f"**User:** {user.full_name} (@{user.username})\n"
            f"**Nominal:** Rp {amount:,}\n"
            f"**Total Bayar:** Rp {total_amount:,}\n"
            f"**Method:** {method_text}\n"
            f"**Waktu:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Verifikasi", callback_data=f"admin_approve_topup_{topup_id}")],
                        [InlineKeyboardButton("📋 Lihat Pending", callback_data="topup_pending_list")]
                    ])
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error in notify_admin_new_topup: {e}")

async def notify_admin_proof_uploaded(context: ContextTypes.DEFAULT_TYPE, topup_id: int, user, photo_file=None):
    """Notify admin tentang bukti transfer yang diupload - FIXED VERSION"""
    try:
        ADMIN_IDS = getattr(config, 'ADMIN_TELEGRAM_IDS', [])
        
        text = (
            f"📎 **BUKTI TRANSFER DIUPLOAD**\n\n"
            f"**ID Topup:** #{topup_id}\n"
            f"**User:** {user.full_name} (@{user.username})\n"
            f"**Waktu:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        for admin_id in ADMIN_IDS:
            try:
                if photo_file:
                    # Forward foto ke admin
                    await context.bot.send_photo(
                        chat_id=admin_id,
                        photo=photo_file.file_id,
                        caption=text,
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("✅ Verifikasi", callback_data=f"admin_approve_topup_{topup_id}")],
                            [InlineKeyboardButton("📋 Lihat Pending", callback_data="topup_pending_list")]
                        ])
                    )
                else:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=text,
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("✅ Verifikasi", callback_data=f"admin_approve_topup_{topup_id}")],
                            [InlineKeyboardButton("📋 Lihat Pending", callback_data="topup_pending_list")]
                        ])
                    )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error in notify_admin_proof_uploaded: {e}")

# ==================== CANCEL HANDLER ====================
async def cancel_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel topup conversation - FIXED VERSION"""
    try:
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(
                "❌ Top up dibatalkan.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💸 Top Up Lagi", callback_data="topup_menu")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ])
            )
        elif hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.reply_text(
                "❌ Top up dibatalkan.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💸 Top Up Lagi", callback_data="topup_menu")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ])
            )
    except Exception as e:
        logger.error(f"Error in cancel_topup: {e}")
    
    return ConversationHandler.END

# ==================== CONVERSATION HANDLER ====================
def get_topup_conversation_handler():
    """Mengembalikan conversation handler untuk topup - FIXED VERSION"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(topup_amount_handler, pattern="^topup_amount_"),
            CallbackQueryHandler(topup_amount_handler, pattern="^topup_custom$")
        ],
        states={
            SELECTING_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_amount)
            ],
            SELECTING_PAYMENT_METHOD: [
                CallbackQueryHandler(handle_payment_method, pattern="^payment_"),
                CallbackQueryHandler(handle_payment_method, pattern="^topup_cancel$")
            ],
            UPLOADING_PROOF: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_proof_photo)
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_topup, pattern="^topup_cancel$"),
            CommandHandler("cancel", cancel_topup),
            CommandHandler("start", cancel_topup)
        ],
        allow_reentry=True
    )

def get_topup_handlers():
    """Mengembalikan list of handlers untuk topup - FIXED VERSION"""
    return [
        CallbackQueryHandler(show_topup_menu, pattern="^topup_menu$"),
        CallbackQueryHandler(show_topup_history, pattern="^topup_history$"),
        CallbackQueryHandler(show_pending_topups, pattern="^topup_pending_list$"),
        CallbackQueryHandler(handle_proof_upload, pattern="^upload_proof_"),
        CallbackQueryHandler(show_topup_menu, pattern="^check_topup_"),  # Fallback untuk cek status
    ]

# ==================== EXPORT FUNCTIONS ====================
__all__ = [
    'get_topup_conversation_handler',
    'show_topup_menu', 
    'show_topup_history',
    'show_pending_topups',
    'handle_proof_upload',
    'get_topup_handlers'
]
