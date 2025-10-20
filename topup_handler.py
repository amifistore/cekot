#!/usr/bin/env python3
"""
Topup Handler untuk Bot Telegram - FIXED & READY TO USE
Fitur: Topup saldo dengan nominal unik, QRIS generator, dan konfirmasi admin
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
    """
    Generate nominal unik dengan menambahkan 3 digit random di akhir
    Returns: (nominal_unik, kode_unik)
    """
    unique_code = random.randint(1, 999)
    unique_amount = base_amount + unique_code
    return unique_amount, unique_code

async def generate_qris_code(amount: int) -> Dict[str, Any]:
    """
    Generate QRIS code menggunakan API - SESUAI DOKUMENTASI
    Format payload: {"amount": "10000", "qris_statis": "STATIC_CODE"}
    """
    # Convert amount to string as required by API documentation
    payload = {
        "amount": str(amount),
        "qris_statis": QRIS_STATIC_CODE
    }
    
    headers = {
        'Content-Type': 'application/json'
    }
    
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
                    return {
                        "status": "error", 
                        "message": f"Invalid JSON response from QRIS API"
                    }
                
                # Check API response according to documentation
                if result.get('status') == 'success' and result.get('qris_base64'):
                    qris_base64 = result['qris_base64']
                    
                    # Validasi base64 - FIXED VERSION
                    try:
                        # Clean base64
                        clean_base64 = qris_base64
                        if "base64," in qris_base64:
                            clean_base64 = qris_base64.split("base64,")[1]
                        
                        # Test decode dengan padding yang benar
                        padding = 4 - (len(clean_base64) % 4)
                        if padding != 4:
                            clean_base64 += "=" * padding
                            
                        test_decode = base64.b64decode(clean_base64)
                        logger.info(f"✅ Base64 validation passed, decoded size: {len(test_decode)} bytes")
                        
                        # Validasi ukuran gambar (minimum 500 bytes untuk QRIS)
                        if len(test_decode) < 500:
                            logger.error(f"❌ Decoded image too small: {len(test_decode)} bytes")
                            return {
                                "status": "error", 
                                "message": f"QRIS image too small: {len(test_decode)} bytes"
                            }
                        
                        # Return cleaned base64
                        result['qris_base64'] = clean_base64
                        return result
                        
                    except Exception as base64_error:
                        logger.error(f"❌ Base64 validation failed: {base64_error}")
                        return {
                            "status": "error", 
                            "message": f"Invalid base64 data from QRIS API: {str(base64_error)}"
                        }
                else:
                    error_msg = result.get('message', 'Unknown error from QRIS API')
                    logger.error(f"❌ QRIS API Error: {error_msg}")
                    return {"status": "error", "message": error_msg}
                    
    except asyncio.TimeoutError:
        logger.error("⏰ QRIS API request timeout")
        return {"status": "error", "message": "QRIS API timeout - please try again later"}
    except aiohttp.ClientError as e:
        logger.error(f"🔌 QRIS API connection error: {e}")
        return {"status": "error", "message": f"Connection error: {str(e)}"}
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
    """Menampilkan menu topup utama"""
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
            
        logger.info("✅ show_topup_menu completed successfully")
        return SELECTING_AMOUNT
            
    except Exception as e:
        logger.error(f"❌ Error in show_topup_menu: {e}", exc_info=True)
        error_msg = "❌ Terjadi error saat menampilkan menu topup."
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.reply_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        return ConversationHandler.END

async def topup_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memilih nominal topup"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    logger.info(f"🎯 topup_amount_handler called with data: {data}")
    
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
            
        elif data == "topup_history":
            await show_topup_history(update, context)
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"❌ Error in topup_amount_handler: {e}", exc_info=True)
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def handle_custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk input manual nominal"""
    try:
        amount_text = update.message.text.strip()
        
        # Hapus karakter non-digit
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
        
        # Kirim konfirmasi
        await update.message.reply_text(
            f"✅ **Nominal Diterima:** Rp {amount:,}\n\n"
            f"Silakan tunggu, mengarahkan ke metode pembayaran...",
            parse_mode='Markdown'
        )
        
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
        logger.error(f"❌ Error in handle_custom_amount: {e}", exc_info=True)
        await update.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def show_payment_methods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan pilihan metode pembayaran"""
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
        
        # Determine message source
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        elif hasattr(update, 'message') and update.message:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            # Fallback - create new message
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"❌ Error in show_payment_methods: {e}", exc_info=True)
        error_msg = "❌ Terjadi error saat memilih metode pembayaran."
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=error_msg
        )

async def handle_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memilih metode pembayaran"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    logger.info(f"🎯 handle_payment_method called with: {data}")
    
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
        logger.error(f"❌ Error in handle_payment_method: {e}", exc_info=True)
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def process_qris_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Proses pembayaran dengan QRIS - COMPLETELY FIXED VERSION"""
    try:
        query = update.callback_query
        user = query.from_user
        amount = context.user_data.get('topup_amount', 0)
        unique_amount = context.user_data.get('unique_amount', 0)
        unique_code = context.user_data.get('unique_code', 0)
        
        # Tampilkan pesan sedang memproses
        await query.edit_message_text(
            "🔄 **Membuat QRIS...**\n\n"
            f"• Nominal: Rp {unique_amount:,}\n"
            f"• Sedang menghubungi server QRIS...",
            parse_mode='Markdown'
        )
        
        logger.info(f"🔗 Processing QRIS payment for amount: {unique_amount}")
        
        # Generate QRIS dengan timeout
        try:
            qris_result = await asyncio.wait_for(
                generate_qris_code(unique_amount), 
                timeout=30
            )
        except asyncio.TimeoutError:
            logger.error("⏰ QRIS generation timeout")
            await query.edit_message_text(
                "❌ **Timeout membuat QRIS**\n\n"
                "Server QRIS tidak merespons dalam waktu yang ditentukan.\n\n"
                "Silakan coba lagi atau gunakan metode transfer manual.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Coba Lagi", callback_data="topup_menu")],
                    [InlineKeyboardButton("🏦 Transfer Manual", callback_data="payment_transfer")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ])
            )
            return ConversationHandler.END
        
        logger.info(f"📊 QRIS Result Status: {qris_result.get('status')}")
        
        if qris_result.get('status') == 'success':
            qris_base64 = qris_result.get('qris_base64', '')
            
            # Validasi base64 string - FIXED
            if not qris_base64 or len(qris_base64) < 100:
                logger.error(f"❌ Invalid QRIS base64 data length: {len(qris_base64)}")
                await query.edit_message_text(
                    "❌ **Gagal membuat QRIS**\n\n"
                    "Data QRIS yang diterima tidak valid.\n\n"
                    "Silakan gunakan metode transfer manual.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🏦 Transfer Manual", callback_data="payment_transfer")],
                        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                    ])
                )
                return ConversationHandler.END
            
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
            
            logger.info(f"💾 Topup saved to database: ID {topup_id}")
            
            # Text untuk caption
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
                f"⚠️ **Pastikan nominal tepat: Rp {unique_amount:,}**\n"
                f"⏰ QRIS berlaku 24 jam"
            )
            
            # Method: Save to temporary file and send - FIXED VERSION
            try:
                # Clean base64 string
                clean_base64 = qris_base64
                if "base64," in qris_base64:
                    clean_base64 = qris_base64.split("base64,")[1]
                
                logger.info(f"🔧 Base64 length: {len(clean_base64)}")
                
                # Validasi base64 dengan mencoba decode - FIXED
                try:
                    # Tambahkan padding jika diperlukan
                    padding = 4 - (len(clean_base64) % 4)
                    if padding != 4:
                        clean_base64 += "=" * padding
                    
                    image_data = base64.b64decode(clean_base64)
                    logger.info(f"🔧 Decoded image size: {len(image_data)} bytes")
                    
                    # Validasi ukuran gambar - FIXED THRESHOLD (500 bytes minimum)
                    if len(image_data) < 500:
                        logger.error(f"❌ Decoded image too small: {len(image_data)} bytes")
                        raise ValueError("Decoded image too small")
                    
                    # Use temp file for sending
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                        tmp_file.write(image_data)
                        tmp_file.flush()
                        
                        with open(tmp_file.name, "rb") as photo:
                            await context.bot.send_photo(
                                chat_id=user.id,
                                photo=photo,
                                caption=text,
                                parse_mode='Markdown'
                            )
                    
                    # Clean up temp file
                    os.unlink(tmp_file.name)
                    
                    # Success message
                    success_text = (
                        f"✅ **TOP UP DIBUAT**\n\n"
                        f"📊 **Detail Transaksi:**\n"
                        f"• ID: `{topup_id}`\n"
                        f"• Nominal: Rp {amount:,}\n"
                        f"• Total Bayar: Rp {unique_amount:,}\n"
                        f"• Metode: QRIS\n\n"
                        f"✅ QRIS telah dikirim. Silakan scan dan bayar.\n\n"
                        f"💰 Saldo akan otomatis bertambah setelah pembayaran terverifikasi."
                    )
                    
                    await query.edit_message_text(
                        success_text,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("📋 Lihat Riwayat", callback_data="topup_history")],
                            [InlineKeyboardButton("💸 Top Up Lagi", callback_data="topup_menu")],
                            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                        ]),
                        parse_mode='Markdown'
                    )
                    
                    # Notify admin
                    await notify_admin_about_topup(context, topup_id, user, amount, unique_amount, "QRIS")
                    
                except Exception as base64_error:
                    logger.error(f"❌ Base64 decode error: {base64_error}")
                    await query.edit_message_text(
                        "❌ **Error QRIS**\n\n"
                        "Gagal memproses gambar QRIS. Data base64 tidak valid.\n\n"
                        "Silakan coba lagi atau gunakan metode transfer manual.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔄 Coba Lagi", callback_data="topup_menu")],
                            [InlineKeyboardButton("🏦 Transfer Manual", callback_data="payment_transfer")],
                            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                        ])
                    )
                    return ConversationHandler.END
                    
            except Exception as e:
                logger.error(f"❌ Error sending QRIS photo: {e}")
                await query.edit_message_text(
                    "❌ **Error Mengirim QRIS**\n\n"
                    "Gagal mengirim gambar QRIS.\n\n"
                    "Silakan coba lagi atau gunakan metode transfer manual.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Coba Lagi", callback_data="topup_menu")],
                        [InlineKeyboardButton("🏦 Transfer Manual", callback_data="payment_transfer")],
                        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                    ])
                )
                return ConversationHandler.END
                
        else:
            # QRIS generation failed
            error_message = qris_result.get('message', 'Unknown error')
            logger.error(f"❌ QRIS generation failed: {error_message}")
            
            await query.edit_message_text(
                f"❌ **Gagal Membuat QRIS**\n\n"
                f"**Error:** {error_message}\n\n"
                f"Silakan coba lagi atau gunakan metode transfer manual.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Coba Lagi", callback_data="topup_menu")],
                    [InlineKeyboardButton("🏦 Transfer Manual", callback_data="payment_transfer")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ]),
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"💥 Unexpected error in process_qris_payment: {e}", exc_info=True)
        await query.edit_message_text(
            "❌ **Terjadi Error Tidak Terduga**\n\n"
            "Silakan coba lagi atau gunakan metode transfer manual.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Coba Lagi", callback_data="topup_menu")],
                [InlineKeyboardButton("🏦 Transfer Manual", callback_data="payment_transfer")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ])
        )
    
    return ConversationHandler.END

async def process_transfer_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Proses pembayaran dengan transfer manual"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    amount = context.user_data.get('topup_amount', 0)
    unique_amount = context.user_data.get('unique_amount', 0)
    unique_code = context.user_data.get('unique_code', 0)
    
    try:
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
        
        # Informasi rekening bank
        bank_info = """
🏦 **TRANSFER MANUAL**

**Detail Pembayaran:**
• Nominal: Rp {amount:,}
• Kode Unik: +{unique_code}
• **Total Transfer: Rp {total_amount:,}**
• ID Transaksi: `{topup_id}`

**Rekening Tujuan:**
