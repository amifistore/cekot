#!/usr/bin/env python3
"""
Topup Handler untuk Bot Telegram - FIXED VERSION
"""

import logging
import random
import asyncio
import aiohttp
import json
import tempfile
import base64
import os
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
SELECTING_AMOUNT, SELECTING_PAYMENT_METHOD, UPLOADING_PROOF = range(3)

# ==================== CONFIGURATION ====================
QRIS_API_URL = getattr(config, 'QRIS_API_URL', "https://qrisku.my.id/api")
QRIS_STATIC_CODE = getattr(config, 'QRIS_STATIC_CODE', '00020101021126690014COM.GO-JEK.WWW0118936009140319946531021520000005240000153033605802ID5914GOJEK INDONESIA6007JAKARTA61051234062130111QRIS Ref62280124A0123B4567C8901D234E6304')

# Nominal yang tersedia untuk topup
AVAILABLE_AMOUNTS = [
    10000, 20000, 50000, 100000, 150000, 200000, 250000, 300000, 
    500000, 750000, 1000000, 1500000, 2000000
]

# ==================== UTILITY FUNCTIONS ====================
def generate_unique_amount(base_amount: int) -> Tuple[int, int]:
    """Generate nominal unik dengan 3 digit random"""
    unique_code = random.randint(1, 999)
    unique_amount = base_amount + unique_code
    return unique_amount, unique_code

async def generate_qris_code(amount: int) -> Dict[str, Any]:
    """Generate QRIS code menggunakan API"""
    payload = {"amount": str(amount), "qris_statis": QRIS_STATIC_CODE}
    headers = {'Content-Type': 'application/json'}
    
    logger.info(f"🔗 Calling QRIS API for amount: {amount}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(QRIS_API_URL, json=payload, headers=headers, timeout=30) as response:
                response_text = await response.text()
                logger.info(f"📡 QRIS API Response status: {response.status}")
                
                try:
                    result = json.loads(response_text)
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON decode error: {e}")
                    return {"status": "error", "message": "Invalid JSON response"}
                
                if result.get('status') == 'success' and result.get('qris_base64'):
                    qris_base64 = result['qris_base64']
                    try:
                        # Clean base64
                        clean_base64 = qris_base64
                        if "base64," in qris_base64:
                            clean_base64 = qris_base64.split("base64,")[1]
                        
                        # Test decode
                        padding = 4 - (len(clean_base64) % 4)
                        if padding != 4:
                            clean_base64 += "=" * padding
                            
                        test_decode = base64.b64decode(clean_base64)
                        logger.info(f"✅ Base64 validation passed")
                        
                        result['qris_base64'] = clean_base64
                        return result
                        
                    except Exception as base64_error:
                        logger.error(f"❌ Base64 validation failed: {base64_error}")
                        return {"status": "error", "message": "Invalid base64 data"}
                else:
                    error_msg = result.get('message', 'Unknown error')
                    logger.error(f"❌ QRIS API Error: {error_msg}")
                    return {"status": "error", "message": error_msg}
                    
    except asyncio.TimeoutError:
        logger.error("⏰ QRIS API request timeout")
        return {"status": "error", "message": "QRIS API timeout"}
    except Exception as e:
        logger.error(f"💥 Unexpected error generating QRIS: {e}")
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}

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
        logger.info("🎯 show_topup_menu called")
        
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
            
        return SELECTING_AMOUNT
            
    except Exception as e:
        logger.error(f"❌ Error in show_topup_menu: {e}")
        error_msg = "❌ Terjadi error saat menampilkan menu topup."
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.reply_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        return ConversationHandler.END

async def topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /topup"""
    await show_topup_menu(update, context)

async def topup_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memilih nominal topup"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    try:
        if data == "topup_custom":
            await query.edit_message_text(
                "✏️ **INPUT MANUAL**\n\nSilakan masukkan nominal top up:\n➖ Minimal: Rp 10.000\n➖ Maksimal: Rp 2.000.000\n\nContoh: `75000`",
                parse_mode='Markdown'
            )
            return SELECTING_AMOUNT
            
        elif data.startswith("topup_amount_"):
            amount = int(data.split("_")[2])
            context.user_data['topup_amount'] = amount
            await show_payment_methods(update, context)
            return SELECTING_PAYMENT_METHOD
            
        elif data == "topup_history":
            await show_topup_history(update, context)
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"❌ Error in topup_amount_handler: {e}")
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def handle_custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk input manual nominal"""
    try:
        amount_text = update.message.text.strip()
        amount_text = ''.join(c for c in amount_text if c.isdigit())
        
        if not amount_text:
            await update.message.reply_text("❌ Format nominal tidak valid. Contoh: `75000`", parse_mode='Markdown')
            return SELECTING_AMOUNT
        
        amount = int(amount_text)
        
        if amount < 10000:
            await update.message.reply_text("❌ Nominal terlalu kecil. Minimal Rp 10.000")
            return SELECTING_AMOUNT
            
        if amount > 2000000:
            await update.message.reply_text("❌ Nominal terlalu besar. Maksimal Rp 2.000.000")
            return SELECTING_AMOUNT
        
        context.user_data['topup_amount'] = amount
        await update.message.reply_text(f"✅ **Nominal Diterima:** Rp {amount:,}", parse_mode='Markdown')
        await show_payment_methods(update, context)
        return SELECTING_PAYMENT_METHOD
        
    except ValueError:
        await update.message.reply_text("❌ Format nominal tidak valid. Contoh: `75000`", parse_mode='Markdown')
        return SELECTING_AMOUNT
    except Exception as e:
        logger.error(f"❌ Error in handle_custom_amount: {e}")
        await update.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def show_payment_methods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan pilihan metode pembayaran"""
    try:
        amount = context.user_data.get('topup_amount', 0)
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
        elif hasattr(update, 'message') and update.message:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"❌ Error in show_payment_methods: {e}")
        error_msg = "❌ Terjadi error saat memilih metode pembayaran."
        await context.bot.send_message(chat_id=update.effective_chat.id, text=error_msg)

async def handle_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memilih metode pembayaran"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
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
        logger.error(f"❌ Error in handle_payment_method: {e}")
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def process_qris_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Proses pembayaran dengan QRIS - SIMPLIFIED VERSION"""
    try:
        query = update.callback_query
        user = query.from_user
        amount = context.user_data.get('topup_amount', 0)
        unique_amount = context.user_data.get('unique_amount', 0)
        unique_code = context.user_data.get('unique_code', 0)
        
        await query.edit_message_text("🔄 **Membuat QRIS...**\n\nSedang menghubungi server QRIS...", parse_mode='Markdown')
        
        # Generate QRIS
        qris_result = await generate_qris_code(unique_amount)
        
        if qris_result.get('status') == 'success':
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
            
            text = (
                f"✅ **QRIS BERHASIL DIBUAT**\n\n"
                f"📊 **Detail Pembayaran:**\n"
                f"• Nominal: Rp {amount:,}\n"
                f"• Kode Unik: +{unique_code}\n"
                f"• **Total: Rp {unique_amount:,}**\n"
                f"• ID Transaksi: `{topup_id}`\n\n"
                f"**CARA BAYAR:**\n"
                f"1. Scan QRIS di aplikasi bank/e-wallet\n"
                f"2. Bayar tepat sesuai nominal\n"
                f"3. Pembayaran akan diverifikasi otomatis\n\n"
                f"⚠️ **Pastikan nominal tepat: Rp {unique_amount:,}**"
            )
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Cek Status", callback_data=f"check_topup_{topup_id}")],
                    [InlineKeyboardButton("💸 Top Up Lagi", callback_data="topup_menu")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ])
            )
        else:
            error_message = qris_result.get('message', 'Unknown error')
            await query.edit_message_text(
                f"❌ **Gagal membuat QRIS**\n\nError: {error_message}\n\nSilakan coba lagi atau gunakan transfer manual.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Coba Lagi", callback_data="topup_menu")],
                    [InlineKeyboardButton("🏦 Transfer Manual", callback_data="payment_transfer")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ])
            )
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"❌ Error in process_qris_payment: {e}")
        await query.edit_message_text("❌ Terjadi error yang tidak terduga. Silakan coba lagi.")
        return ConversationHandler.END

async def process_transfer_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Proses pembayaran dengan transfer manual"""
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
        
        text = (
            f"🏦 **TRANSFER MANUAL**\n\n"
            f"📊 **Detail Pembayaran:**\n"
            f"• Nominal: Rp {amount:,}\n"
            f"• Kode Unik: +{unique_code}\n"
            f"• **Total Transfer: Rp {unique_amount:,}**\n"
            f"• ID Transaksi: `{topup_id}`\n\n"
            f"**REKENING TUJUAN:**\n"
            f"```\nBank: BCA\nNomor: 1234567890\nAtas Nama: JOHN DOE\n```\n\n"
            f"**INSTRUKSI:**\n"
            f"1. Transfer tepat Rp {unique_amount:,}\n"
            f"2. Screenshot bukti transfer\n"
            f"3. Kirim bukti transfer ke admin\n\n"
            f"⚠️ **Pastikan nominal transfer tepat!**"
        )
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Konfirmasi ke Admin", url=f"https://t.me/{config.ADMIN_USERNAME}")],
                [InlineKeyboardButton("💸 Top Up Lagi", callback_data="topup_menu")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ])
        )
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"❌ Error in process_transfer_payment: {e}")
        await query.edit_message_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def show_topup_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan riwayat topup user"""
    try:
        query = update.callback_query
        await query.answer()
        user = query.from_user
        
        user_id = database.get_or_create_user(str(user.id), user.username or "", user.full_name)
        history = database.get_user_topup_history(user_id, limit=10)
        
        if not history:
            text = "📋 **RIWAYAT TOP UP**\n\nBelum ada transaksi top up."
        else:
            text = "📋 **RIWAYAT TOP UP TERAKHIR**\n\n"
            for topup in history:
                status_emoji = "✅" if topup['status'] == 'completed' else "⏳" if topup['status'] == 'pending' else "❌"
                text += (
                    f"**{status_emoji} ID: {topup['id']}**\n"
                    f"• Tanggal: {topup['created_at'].strftime('%d/%m/%Y %H:%M')}\n"
                    f"• Nominal: Rp {topup['amount']:,}\n"
                    f"• Total: Rp {topup['total_amount']:,}\n"
                    f"• Metode: {topup['method'].upper()}\n"
                    f"• Status: {topup['status'].title()}\n\n"
                )
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💸 Top Up Baru", callback_data="topup_menu")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ])
        )
        
    except Exception as e:
        logger.error(f"❌ Error in show_topup_history: {e}")
        await query.edit_message_text("❌ Terjadi error saat mengambil riwayat.")

async def check_topup_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cek status topup tertentu"""
    try:
        query = update.callback_query
        await query.answer()
        
        topup_id = int(query.data.split("_")[2])
        topup = database.get_topup_by_id(topup_id)
        
        if not topup:
            await query.edit_message_text("❌ Topup tidak ditemukan.")
            return
        
        status_emoji = {"pending": "⏳", "completed": "✅", "rejected": "❌", "expired": "⌛"}.get(topup['status'], '❓')
        status_text = {"pending": "Menunggu Pembayaran", "completed": "Berhasil", "rejected": "Ditolak", "expired": "Kadaluarsa"}.get(topup['status'], 'Tidak Diketahui')
        
        text = (
            f"📊 **STATUS TOP UP**\n\n"
            f"**ID Transaksi:** `{topup_id}`\n"
            f"**Status:** {status_emoji} {status_text}\n"
            f"**Tanggal:** {topup['created_at'].strftime('%d/%m/%Y %H:%M')}\n"
            f"**Nominal:** Rp {topup['amount']:,}\n"
            f"**Kode Unik:** +{topup['unique_code']}\n"
            f"**Total:** Rp {topup['total_amount']:,}\n"
            f"**Metode:** {topup['method'].upper()}\n\n"
        )
        
        if topup['status'] == 'pending':
            if topup['method'] == 'qris':
                text += "🔄 Pembayaran QRIS masih menunggu. Pastikan Anda sudah scan dan bayar."
            else:
                text += "🔄 Menunggu verifikasi admin. Biasanya 1-2 jam."
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data=f"check_topup_{topup_id}")],
                [InlineKeyboardButton("💸 Top Up Lagi", callback_data="topup_menu")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ])
        )
        
    except Exception as e:
        logger.error(f"❌ Error in check_topup_status: {e}")
        await query.edit_message_text("❌ Terjadi error saat cek status.")

async def cancel_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel topup process"""
    await update.message.reply_text(
        "❌ Top up dibatalkan.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💸 Top Up Lagi", callback_data="topup_menu")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
        ])
    )
    return ConversationHandler.END

def get_topup_conversation_handler() -> ConversationHandler:
    """Mengembalikan ConversationHandler untuk topup"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(show_topup_menu, pattern="^topup_menu$"),
            CommandHandler("topup", topup_command)
        ],
        states={
            SELECTING_AMOUNT: [
                CallbackQueryHandler(topup_amount_handler, pattern="^topup_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_amount)
            ],
            SELECTING_PAYMENT_METHOD: [
                CallbackQueryHandler(handle_payment_method, pattern="^payment_|^topup_cancel$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(show_topup_menu, pattern="^topup_menu$"),
            CommandHandler("cancel", cancel_topup),
            CommandHandler("start", cancel_topup)
        ],
        allow_reentry=True
    )

def get_topup_handlers():
    """Return list of topup callback handlers"""
    return [
        CallbackQueryHandler(check_topup_status, pattern="^check_topup_"),
        CallbackQueryHandler(show_topup_history, pattern="^topup_history$")
    ]

# Untuk admin functions (jika diperlukan)
async def show_pending_topups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pending topups for admin"""
    try:
        pending_topups = database.get_pending_topups()
        
        if not pending_topups:
            text = "📋 **PENDING TOPUPS**\n\nTidak ada topup yang pending."
        else:
            text = "📋 **PENDING TOPUPS**\n\n"
            for topup in pending_topups:
                user_info = database.get_user_by_id(topup['user_id'])
                text += (
                    f"**ID: {topup['id']}**\n"
                    f"• User: {user_info['full_name']} (@{user_info['username']})\n"
                    f"• Nominal: Rp {topup['amount']:,}\n"
                    f"• Total: Rp {topup['total_amount']:,}\n"
                    f"• Metode: {topup['method']}\n"
                    f"• Tanggal: {topup['created_at'].strftime('%d/%m/%Y %H:%M')}\n\n"
                )
        
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"❌ Error in show_pending_topups: {e}")
        await update.message.reply_text("❌ Terjadi error saat mengambil data topup.")

async def handle_proof_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle proof upload - placeholder"""
    await update.message.reply_text("📤 Silakan kirim bukti transfer sebagai photo.")

if __name__ == "__main__":
    print("✅ Topup Handler Module Loaded")
