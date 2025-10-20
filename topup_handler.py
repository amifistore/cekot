#!/usr/bin/env python3
"""
Order Handler untuk Bot Telegram - FIXED & READY TO USE
Fitur: Pembuatan order, pemilihan item, pembayaran dengan nominal unik
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
SELECTING_CATEGORY, SELECTING_ITEM, SELECTING_QUANTITY, CONFIRMING_ORDER, SELECTING_PAYMENT_METHOD = range(5)

# ==================== CONFIGURATION ====================
QRIS_API_URL = getattr(config, 'QRIS_API_URL', "https://qrisku.my.id/api")
QRIS_STATIC_CODE = getattr(config, 'QRIS_STATIC_CODE', '00020101021126690014COM.GO-JEK.WWW0118936009140319946531021520000005240000153033605802ID5914GOJEK INDONESIA6007JAKARTA61051234062130111QRIS Ref62280124A0123B4567C8901D234E6304')

# ==================== PRODUCT DATA ====================
PRODUCT_CATEGORIES = [
    {
        'id': 'voucher',
        'name': '🛒 Voucher & Topup Game',
        'items': [
            {'id': 'voucher_1', 'name': 'Voucher Google Play $10', 'price': 150000},
            {'id': 'voucher_2', 'name': 'Voucher Steam Wallet $5', 'price': 75000},
            {'id': 'voucher_3', 'name': 'Voucher Mobile Legends 100 Diamond', 'price': 28000},
            {'id': 'voucher_4', 'name': 'Voucher Free Fire 100 Diamond', 'price': 25000},
            {'id': 'voucher_5', 'name': 'Voucher PUBG Mobile 100 UC', 'price': 30000},
        ]
    },
    {
        'id': 'digital',
        'name': '📱 Produk Digital',
        'items': [
            {'id': 'digital_1', 'name': 'Paket Internet 10GB 30 Hari', 'price': 50000},
            {'id': 'digital_2', 'name': 'Paket Streaming 15GB 30 Hari', 'price': 65000},
            {'id': 'digital_3', 'name': 'e-Book Premium Programming', 'price': 120000},
            {'id': 'digital_4', 'name': 'Software License Key', 'price': 200000},
        ]
    },
    {
        'id': 'physical',
        'name': '📦 Produk Fisik',
        'items': [
            {'id': 'physical_1', 'name': 'T-Shirt Premium', 'price': 150000},
            {'id': 'physical_2', 'name': 'Mouse Gaming', 'price': 250000},
            {'id': 'physical_3', 'name': 'Keyboard Mechanical', 'price': 450000},
        ]
    }
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
    Generate QRIS code menggunakan API
    """
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
                
                if result.get('status') == 'success' and result.get('qris_base64'):
                    qris_base64 = result['qris_base64']
                    
                    # Validasi base64
                    try:
                        clean_base64 = qris_base64
                        if "base64," in qris_base64:
                            clean_base64 = qris_base64.split("base64,")[1]
                        
                        padding = 4 - (len(clean_base64) % 4)
                        if padding != 4:
                            clean_base64 += "=" * padding
                            
                        test_decode = base64.b64decode(clean_base64)
                        logger.info(f"✅ Base64 validation passed, decoded size: {len(test_decode)} bytes")
                        
                        result['qris_base64'] = clean_base64
                        return result
                        
                    except Exception as base64_error:
                        logger.error(f"❌ Base64 validation failed: {base64_error}")
                        return {
                            "status": "error", 
                            "message": f"Invalid base64 data from QRIS API"
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
        [InlineKeyboardButton("💳 QRIS (Otomatis)", callback_data="order_payment_qris")],
        [InlineKeyboardButton("🏦 Transfer Bank (Manual)", callback_data="order_payment_transfer")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="order_cancel")]
    ]

def find_product_by_id(product_id: str) -> Dict[str, Any]:
    """Mencari produk berdasarkan ID"""
    for category in PRODUCT_CATEGORIES:
        for item in category['items']:
            if item['id'] == product_id:
                return item
    return None

# ==================== ORDER MENU & CONVERSATION ====================
async def show_order_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan menu order utama"""
    try:
        logger.info("🎯 show_order_menu called")
        
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
        
        # Keyboard dengan kategori produk
        keyboard = []
        for category in PRODUCT_CATEGORIES:
            keyboard.append([InlineKeyboardButton(category['name'], callback_data=f"order_category_{category['id']}")])
        
        # Tambahkan opsi lainnya
        keyboard.extend([
            [InlineKeyboardButton("📋 Riwayat Order", callback_data="order_history")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            f"🛒 **ORDER PRODUK**\n\n"
            f"💰 **Saldo Anda:** Rp {saldo:,}\n\n"
            f"Pilih kategori produk yang ingin dibeli:\n\n"
            f"📦 **Tersedia:**\n"
            f"• Voucher & Topup Game\n"
            f"• Produk Digital\n"
            f"• Produk Fisik\n\n"
            f"⚠️ **FITUR NOMINAL UNIK:**\n"
            f"Setiap order akan memiliki nominal unik 3 digit untuk memudahkan verifikasi."
        )
        
        if edit_message:
            try:
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            except Exception as e:
                logger.warning(f"Could not edit message, sending new: {e}")
                await query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        logger.info("✅ show_order_menu completed successfully")
        return SELECTING_CATEGORY
            
    except Exception as e:
        logger.error(f"❌ Error in show_order_menu: {e}", exc_info=True)
        error_msg = "❌ Terjadi error saat menampilkan menu order."
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.reply_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        return ConversationHandler.END

async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memilih kategori"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    logger.info(f"🎯 handle_category_selection called with data: {data}")
    
    try:
        if data.startswith("order_category_"):
            category_id = data.split("_")[2]
            
            # Cari kategori
            selected_category = None
            for category in PRODUCT_CATEGORIES:
                if category['id'] == category_id:
                    selected_category = category
                    break
            
            if not selected_category:
                await query.edit_message_text("❌ Kategori tidak ditemukan.")
                return SELECTING_CATEGORY
            
            context.user_data['selected_category'] = selected_category
            
            # Tampilkan produk dalam kategori
            keyboard = []
            for item in selected_category['items']:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{item['name']} - Rp {item['price']:,}", 
                        callback_data=f"order_item_{item['id']}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("🔙 Kembali", callback_data="order_menu")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"🛍️ **{selected_category['name']}**\n\n"
                f"Pilih produk yang ingin dibeli:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return SELECTING_ITEM
            
        elif data == "order_history":
            await show_order_history(update, context)
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"❌ Error in handle_category_selection: {e}", exc_info=True)
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def handle_item_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memilih item"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    logger.info(f"🎯 handle_item_selection called with data: {data}")
    
    try:
        if data.startswith("order_item_"):
            item_id = data.split("_")[2]
            
            # Cari item
            selected_item = find_product_by_id(item_id)
            if not selected_item:
                await query.edit_message_text("❌ Produk tidak ditemukan.")
                return SELECTING_ITEM
            
            context.user_data['selected_item'] = selected_item
            
            # Untuk sekarang, langsung set quantity = 1
            # Bisa dikembangkan untuk memilih quantity
            context.user_data['quantity'] = 1
            
            total_amount = selected_item['price'] * 1
            
            await query.edit_message_text(
                f"📦 **KONFIRMASI PRODUK**\n\n"
                f"**Produk:** {selected_item['name']}\n"
                f"**Harga:** Rp {selected_item['price']:,}\n"
                f"**Jumlah:** 1\n"
                f"**Total:** Rp {total_amount:,}\n\n"
                f"Apakah Anda ingin melanjutkan pembelian?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Ya, Lanjutkan", callback_data="order_confirm_yes")],
                    [InlineKeyboardButton("❌ Batalkan", callback_data="order_menu")]
                ]),
                parse_mode='Markdown'
            )
            return CONFIRMING_ORDER
            
    except Exception as e:
        logger.error(f"❌ Error in handle_item_selection: {e}", exc_info=True)
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def handle_order_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk konfirmasi order"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    logger.info(f"🎯 handle_order_confirmation called with data: {data}")
    
    try:
        if data == "order_confirm_yes":
            selected_item = context.user_data.get('selected_item')
            quantity = context.user_data.get('quantity', 1)
            
            if not selected_item:
                await query.edit_message_text("❌ Data produk tidak ditemukan.")
                return SELECTING_CATEGORY
            
            base_amount = selected_item['price'] * quantity
            
            # Generate nominal unik
            unique_amount, unique_code = generate_unique_amount(base_amount)
            context.user_data['unique_amount'] = unique_amount
            context.user_data['unique_code'] = unique_code
            context.user_data['base_amount'] = base_amount
            
            text = (
                f"💰 **KONFIRMASI ORDER**\n\n"
                f"📊 **Detail Order:**\n"
                f"• Produk: {selected_item['name']}\n"
                f"• Harga: Rp {selected_item['price']:,}\n"
                f"• Jumlah: {quantity}\n"
                f"• Subtotal: Rp {base_amount:,}\n"
                f"• Kode Unik: +{unique_code}\n"
                f"• **Total Bayar: Rp {unique_amount:,}**\n\n"
                f"Pilih metode pembayaran:"
            )
            
            reply_markup = InlineKeyboardMarkup(get_payment_methods())
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return SELECTING_PAYMENT_METHOD
            
        elif data == "order_menu":
            await show_order_menu(update, context)
            return SELECTING_CATEGORY
            
    except Exception as e:
        logger.error(f"❌ Error in handle_order_confirmation: {e}", exc_info=True)
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def handle_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memilih metode pembayaran"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    logger.info(f"🎯 handle_payment_method called with: {data}")
    
    try:
        if data == "order_payment_qris":
            await process_order_qris_payment(update, context)
            return ConversationHandler.END
            
        elif data == "order_payment_transfer":
            await process_order_transfer_payment(update, context)
            return ConversationHandler.END
            
        elif data == "order_cancel":
            await query.edit_message_text(
                "❌ Order dibatalkan.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛒 Order Lagi", callback_data="order_menu")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ])
            )
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"❌ Error in handle_payment_method: {e}", exc_info=True)
        await query.message.reply_text("❌ Terjadi error. Silakan coba lagi.")
        return ConversationHandler.END

async def process_order_qris_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Proses pembayaran order dengan QRIS"""
    try:
        query = update.callback_query
        user = query.from_user
        selected_item = context.user_data.get('selected_item')
        quantity = context.user_data.get('quantity', 1)
        unique_amount = context.user_data.get('unique_amount', 0)
        unique_code = context.user_data.get('unique_code', 0)
        base_amount = context.user_data.get('base_amount', 0)
        
        # Tampilkan pesan sedang memproses
        await query.edit_message_text(
            "🔄 **Membuat QRIS...**\n\n"
            f"• Produk: {selected_item['name']}\n"
            f"• Total: Rp {unique_amount:,}\n"
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
                    [InlineKeyboardButton("🔄 Coba Lagi", callback_data="order_menu")],
                    [InlineKeyboardButton("🏦 Transfer Manual", callback_data="order_payment_transfer")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ])
            )
            return ConversationHandler.END
        
        logger.info(f"📊 QRIS Result Status: {qris_result.get('status')}")
        
        if qris_result.get('status') == 'success':
            qris_base64 = qris_result.get('qris_base64', '')
            
            # Validasi base64 string
            if not qris_base64 or len(qris_base64) < 100:
                logger.error(f"❌ Invalid QRIS base64 data length: {len(qris_base64)}")
                await query.edit_message_text(
                    "❌ **Gagal membuat QRIS**\n\n"
                    "Data QRIS yang diterima tidak valid.\n\n"
                    "Silakan gunakan metode transfer manual.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🏦 Transfer Manual", callback_data="order_payment_transfer")],
                        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                    ])
                )
                return ConversationHandler.END
            
            # Simpan order ke database
            user_id = database.get_or_create_user(str(user.id), user.username or "", user.full_name)
            order_id = database.create_order(
                user_id=user_id,
                product_id=selected_item['id'],
                product_name=selected_item['name'],
                quantity=quantity,
                base_amount=base_amount,
                unique_code=unique_code,
                total_amount=unique_amount,
                method='qris',
                status='pending'
            )
            
            logger.info(f"💾 Order saved to database: ID {order_id}")
            
            # Text untuk caption
            text = (
                f"✅ **QRIS BERHASIL DIBUAT**\n\n"
                f"📊 **Detail Order:**\n"
                f"• Produk: {selected_item['name']}\n"
                f"• Jumlah: {quantity}\n"
                f"• Subtotal: Rp {base_amount:,}\n"
                f"• Kode Unik: +{unique_code}\n"
                f"• **Total: Rp {unique_amount:,}**\n"
                f"• ID Order: `{order_id}`\n\n"
                f"**CARA BAYAR:**\n"
                f"1. Scan QRIS di bawah ini\n"
                f"2. Bayar tepat sesuai nominal\n"
                f"3. Order akan diproses otomatis\n\n"
                f"⚠️ **Pastikan nominal tepat: Rp {unique_amount:,}**\n"
                f"⏰ QRIS berlaku 24 jam"
            )
            
            # Method: Save to temporary file and send
            try:
                # Clean base64 string
                clean_base64 = qris_base64
                if "base64," in qris_base64:
                    clean_base64 = qris_base64.split("base64,")[1]
                
                logger.info(f"🔧 Base64 length: {len(clean_base64)}")
                
                # Validasi base64 dengan mencoba decode
                try:
                    # Tambahkan padding jika diperlukan
                    padding = 4 - (len(clean_base64) % 4)
                    if padding != 4:
                        clean_base64 += "=" * padding
                    
                    image_data = base64.b64decode(clean_base64)
                    logger.info(f"🔧 Decoded image size: {len(image_data)} bytes")
                    
                    if len(image_data) < 1000:
                        raise ValueError("Decoded image data too small")
                    
                    # Simpan ke file temporary
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                        temp_file.write(image_data)
                        temp_file_path = temp_file.name
                    
                    # Kirim gambar QRIS
                    with open(temp_file_path, 'rb') as photo:
                        await context.bot.send_photo(
                            chat_id=user.id,
                            photo=photo,
                            caption=text,
                            parse_mode='Markdown',
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("🔄 Cek Status", callback_data=f"check_order_{order_id}")],
                                [InlineKeyboardButton("🛒 Order Lagi", callback_data="order_menu")],
                                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                            ])
                        )
                    
                    # Hapus file temporary
                    os.unlink(temp_file_path)
                    
                    logger.info(f"✅ QRIS image sent successfully for order ID: {order_id}")
                    
                except Exception as img_error:
                    logger.error(f"❌ Error processing QRIS image: {img_error}")
                    await query.edit_message_text(
                        "❌ **Gagal memproses gambar QRIS**\n\n"
                        "Data QRIS tidak valid. Silakan gunakan metode transfer manual.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🏦 Transfer Manual", callback_data="order_payment_transfer")],
                            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                        ])
                    )
                    return ConversationHandler.END
                    
            except Exception as e:
                logger.error(f"❌ Error in QRIS image processing: {e}")
                await query.edit_message_text(
                    "❌ **Gagal membuat QRIS**\n\n"
                    "Terjadi error saat memproses QRIS. Silakan gunakan metode transfer manual.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🏦 Transfer Manual", callback_data="order_payment_transfer")],
                        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                    ])
                )
                return ConversationHandler.END
                
        else:
            # QRIS API returned error
            error_message = qris_result.get('message', 'Unknown error')
            await query.edit_message_text(
                f"❌ **Gagal membuat QRIS**\n\n"
                f"Error: {error_message}\n\n"
                f"Silakan gunakan metode transfer manual.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏦 Transfer Manual", callback_data="order_payment_transfer")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ])
            )
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"❌ Error in process_order_qris_payment: {e}", exc_info=True)
        await query.edit_message_text(
            "❌ **Terjadi error saat memproses QRIS**\n\n"
            "Silakan coba lagi atau gunakan metode transfer manual.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Coba Lagi", callback_data="order_menu")],
                [InlineKeyboardButton("🏦 Transfer Manual", callback_data="order_payment_transfer")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ])
        )
        return ConversationHandler.END

async def process_order_transfer_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Proses pembayaran order dengan transfer manual"""
    try:
        query = update.callback_query
        user = query.from_user
        selected_item = context.user_data.get('selected_item')
        quantity = context.user_data.get('quantity', 1)
        unique_amount = context.user_data.get('unique_amount', 0)
        unique_code = context.user_data.get('unique_code', 0)
        base_amount = context.user_data.get('base_amount', 0)
        
        # Simpan order ke database
        user_id = database.get_or_create_user(str(user.id), user.username or "", user.full_name)
        order_id = database.create_order(
            user_id=user_id,
            product_id=selected_item['id'],
            product_name=selected_item['name'],
            quantity=quantity,
            base_amount=base_amount,
            unique_code=unique_code,
            total_amount=unique_amount,
            method='transfer',
            status='pending'
        )
        
        # Dapatkan info rekening dari config
        bank_accounts = getattr(config, 'BANK_ACCOUNTS', [])
        if not bank_accounts:
            bank_accounts = [{
                'bank_name': 'BANK EXAMPLE',
                'account_number': '1234567890',
                'account_name': 'YOUR NAME'
            }]
        
        bank_info = ""
        for i, account in enumerate(bank_accounts, 1):
            bank_info += (
                f"🏦 **{account.get('bank_name', 'BANK')}**\n"
                f"📋 No. Rekening: `{account.get('account_number', '')}`\n"
                f"👤 Atas Nama: {account.get('account_name', '')}\n"
            )
            if i < len(bank_accounts):
                bank_info += "\n"
        
        text = (
            f"🏦 **TRANSFER MANUAL**\n\n"
            f"📊 **Detail Order:**\n"
            f"• Produk: {selected_item['name']}\n"
            f"• Jumlah: {quantity}\n"
            f"• Subtotal: Rp {base_amount:,}\n"
            f"• Kode Unik: +{unique_code}\n"
            f"• **Total Transfer: Rp {unique_amount:,}**\n"
            f"• ID Order: `{order_id}`\n\n"
            f"**REKENING TUJUAN:**\n"
            f"{bank_info}\n"
            f"**INSTRUKSI:**\n"
            f"1. Transfer tepat **Rp {unique_amount:,}** ke salah satu rekening di atas\n"
            f"2. Screenshot/simpan bukti transfer\n"
            f"3. Klik tombol **📤 Upload Bukti** di bawah untuk mengirim bukti transfer\n\n"
            f"⚠️ **Pastikan nominal transfer tepat: Rp {unique_amount:,}**\n"
            f"⏰ Batas upload bukti: 24 jam"
        )
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Upload Bukti Transfer", callback_data=f"upload_order_proof_{order_id}")],
                [InlineKeyboardButton("🛒 Order Lagi", callback_data="order_menu")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ])
        )
        
        logger.info(f"✅ Transfer payment info sent for order ID: {order_id}")
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"❌ Error in process_order_transfer_payment: {e}", exc_info=True)
        await query.edit_message_text(
            "❌ Terjadi error saat memproses transfer manual.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Coba Lagi", callback_data="order_menu")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ])
        )
        return ConversationHandler.END

async def show_order_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan riwayat order user"""
    try:
        query = update.callback_query
        await query.answer()
        user = query.from_user
        
        user_id = database.get_or_create_user(str(user.id), user.username or "", user.full_name)
        history = database.get_user_order_history(user_id, limit=10)
        
        if not history:
            text = "📋 **RIWAYAT ORDER**\n\n" \
                   "Belum ada riwayat order."
        else:
            text = "📋 **RIWAYAT ORDER**\n\n"
            for i, order in enumerate(history, 1):
                status_emoji = {
                    'pending': '🟡',
                    'success': '🟢', 
                    'failed': '🔴',
                    'expired': '⚫',
                    'processing': '🟠'
                }.get(order['status'], '⚪')
                
                method_emoji = {
                    'qris': '💳',
                    'transfer': '🏦'
                }.get(order['method'], '🛒')
                
                text += (
                    f"{i}. {status_emoji} {method_emoji} {order['product_name']}\n"
                    f"   💰 Total: Rp {order['total_amount']:,}\n"
                    f"   🆔 ID: `{order['id']}`\n"
                    f"   📅 {order['created_at'].strftime('%d/%m/%Y %H:%M')}\n"
                    f"   📊 Status: {order['status'].upper()}\n\n"
                )
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 Order Baru", callback_data="order_menu")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ])
        )
        
    except Exception as e:
        logger.error(f"❌ Error in show_order_history: {e}", exc_info=True)
        await query.edit_message_text(
            "❌ Terjadi error saat mengambil riwayat order.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Coba Lagi", callback_data="order_history")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ])
        )

# ==================== CONVERSATION HANDLER SETUP ====================
def get_order_conversation_handler():
    """Mengembalikan ConversationHandler untuk order"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(show_order_menu, pattern="^order_menu$"),
            CommandHandler("order", show_order_menu)
        ],
        states={
            SELECTING_CATEGORY: [
                CallbackQueryHandler(handle_category_selection, pattern="^order_category_|order_history$")
            ],
            SELECTING_ITEM: [
                CallbackQueryHandler(handle_item_selection, pattern="^order_item_"),
                CallbackQueryHandler(show_order_menu, pattern="^order_menu$")
            ],
            CONFIRMING_ORDER: [
                CallbackQueryHandler(handle_order_confirmation, pattern="^order_confirm_|order_menu$")
            ],
            SELECTING_PAYMENT_METHOD: [
                CallbackQueryHandler(handle_payment_method, pattern="^order_payment_|order_cancel$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(show_order_menu, pattern="^order_menu$"),
            CommandHandler("cancel", show_order_menu)
        ],
        allow_reentry=True
    )

# ==================== REGISTER HANDLERS ====================
def register_handlers(application):
    """Mendaftarkan semua handler order"""
    application.add_handler(get_order_conversation_handler())
    
    # Additional handlers
    application.add_handler(CallbackQueryHandler(show_order_history, pattern="^order_history$"))
    application.add_handler(CallbackQueryHandler(show_order_menu, pattern="^order_menu$"))

# ==================== MAIN FOR TESTING ====================
if __name__ == "__main__":
    print("✅ Order Handler Module - Fixed & Ready to Use")
    print("Available categories:")
    for category in PRODUCT_CATEGORIES:
        print(f"- {category['name']}: {len(category['items'])} items")
