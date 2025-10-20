import logging
import random
import json
import aiohttp
import asyncio
from datetime import datetime
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    LabeledPrice
)
from telegram.ext import (
    ContextTypes, 
    ConversationHandler, 
    CommandHandler, 
    MessageHandler, 
    filters,
    CallbackQueryHandler
)
import database
import config

# ==================== LOGGING ====================
logger = logging.getLogger(__name__)

# ==================== CONVERSATION STATES ====================
SELECT_CATEGORY, SELECT_PRODUCT, INPUT_NUMBER, CONFIRM_ORDER, PAYMENT = range(5)

# ==================== GLOBAL VARIABLES ====================
QRIS_API_URL = "https://qrisku.my.id/api"
QRIS_STATIS = getattr(config, 'QRIS_STATIS', 'XXXE3353COM.GO-JEK.WWWVDXXX44553463.CO.QRIS.WWXXXX4664XX.MERCHANT ENTE, XX65646XXXXTY5YY')

# ==================== HELPER FUNCTIONS ====================
def generate_unique_amount(amount: int) -> int:
    """Generate nominal unik dengan menambahkan random 2 digit"""
    unique_code = random.randint(1, 99)
    return amount + unique_code

def format_currency(amount: int) -> str:
    """Format currency dengan pemisah ribuan"""
    return f"Rp {amount:,.0f}"

async def generate_qris_payment(amount: int, unique_amount: int) -> dict:
    """Generate QRIS payment menggunakan API"""
    try:
        payload = {
            "amount": str(unique_amount),
            "qris_statis": QRIS_STATIS
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(QRIS_API_URL, json=payload, timeout=30) as response:
                if response.status == 200:
                    result = await response.json()
                    return result
                else:
                    logger.error(f"QRIS API error: {response.status}")
                    return {"status": "error", "message": f"HTTP {response.status}"}
                    
    except Exception as e:
        logger.error(f"Error generating QRIS: {e}")
        return {"status": "error", "message": str(e)}

# ==================== ORDER HANDLERS ====================
async def order_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /order"""
    return await show_categories(update, context)

async def order_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menu order dari callback"""
    query = update.callback_query
    await query.answer()
    return await show_categories(update, context)

async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan kategori produk"""
    try:
        # Clear previous data
        context.user_data.clear()
        
        categories = database.get_categories()
        if not categories:
            await update.callback_query.message.reply_text(
                "❌ Tidak ada kategori produk yang tersedia saat ini."
            ) if hasattr(update, 'callback_query') else await update.message.reply_text(
                "❌ Tidak ada kategori produk yang tersedia saat ini."
            )
            return ConversationHandler.END
        
        keyboard = []
        for category in categories:
            keyboard.append([
                InlineKeyboardButton(
                    f"📁 {category['name']}", 
                    callback_data=f"order_category_{category['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 KEMBALI", callback_data="main_menu_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            "🛒 **BELI PRODUK**\n\n"
            "Pilih kategori produk yang ingin Anda beli:"
        )
        
        if hasattr(update, 'callback_query'):
            await update.callback_query.edit_message_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        
        return SELECT_CATEGORY
        
    except Exception as e:
        logger.error(f"Error showing categories: {e}")
        error_msg = "❌ Terjadi error saat memuat kategori. Silakan coba lagi."
        if hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        return ConversationHandler.END

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pemilihan kategori"""
    query = update.callback_query
    await query.answer()
    
    category_id = int(query.data.split('_')[2])
    context.user_data['category_id'] = category_id
    
    return await show_products(update, context)

async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan produk dalam kategori"""
    try:
        category_id = context.user_data['category_id']
        products = database.get_products_by_category(category_id)
        
        if not products:
            await update.callback_query.message.reply_text(
                "❌ Tidak ada produk yang tersedia dalam kategori ini."
            )
            return SELECT_CATEGORY
        
        keyboard = []
        for product in products:
            status = "✅ TERSEDIA" if product['stock'] > 0 else "❌ HABIS"
            keyboard.append([
                InlineKeyboardButton(
                    f"{product['name']} - {format_currency(product['price'])} ({status})",
                    callback_data=f"order_product_{product['id']}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("🔙 KEMBALI KE KATEGORI", callback_data="order_back_categories")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        category_name = database.get_category_name(category_id)
        
        await update.callback_query.edit_message_text(
            f"📦 **PRODUK {category_name.upper()}**\n\n"
            f"Pilih produk yang ingin dibeli:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return SELECT_PRODUCT
        
    except Exception as e:
        logger.error(f"Error showing products: {e}")
        await update.callback_query.message.reply_text("❌ Error memuat produk.")
        return SELECT_CATEGORY

async def select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pemilihan produk"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[2])
    product = database.get_product(product_id)
    
    if not product:
        await query.message.reply_text("❌ Produk tidak ditemukan.")
        return SELECT_PRODUCT
    
    # Cek stok
    if product['stock'] <= 0:
        await query.answer("❌ Stok produk habis!", show_alert=True)
        return SELECT_PRODUCT
    
    context.user_data['product_id'] = product_id
    context.user_data['product'] = product
    
    await query.edit_message_text(
        f"📝 **INPUT NOMOR TUJUAN**\n\n"
        f"Produk: **{product['name']}**\n"
        f"Harga: **{format_currency(product['price'])}**\n\n"
        f"Silakan masukkan nomor tujuan untuk pengiriman produk:\n"
        f"Contoh: 081234567890",
        parse_mode='Markdown'
    )
    
    return INPUT_NUMBER

async def input_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle input nomor tujuan"""
    phone_number = update.message.text.strip()
    
    # Validasi nomor telepon
    if not phone_number.isdigit() or len(phone_number) < 10 or len(phone_number) > 15:
        await update.message.reply_text(
            "❌ Format nomor tidak valid! Harap masukkan nomor yang benar.\n"
            "Contoh: 081234567890"
        )
        return INPUT_NUMBER
    
    context.user_data['phone_number'] = phone_number
    product = context.user_data['product']
    
    # Generate unique amount
    unique_amount = generate_unique_amount(product['price'])
    context.user_data['unique_amount'] = unique_amount
    
    keyboard = [
        [
            InlineKeyboardButton("✅ KONFIRMASI", callback_data="order_confirm"),
            InlineKeyboardButton("❌ BATAL", callback_data="order_cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📋 **KONFIRMASI PESANAN**\n\n"
        f"📦 Produk: **{product['name']}**\n"
        f"💰 Harga: **{format_currency(product['price'])}**\n"
        f"🔢 Kode Unik: **{format_currency(unique_amount - product['price'])}**\n"
        f"💳 Total Bayar: **{format_currency(unique_amount)}**\n"
        f"📱 Nomor Tujuan: **{phone_number}**\n\n"
        f"Apakah data sudah benar?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    return CONFIRM_ORDER

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle konfirmasi pesanan"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    product = context.user_data['product']
    phone_number = context.user_data['phone_number']
    unique_amount = context.user_data['unique_amount']
    
    # Cek saldo user
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    saldo = database.get_user_saldo(user_id)
    
    if saldo >= unique_amount:
        # Bayar menggunakan saldo
        return await process_payment_saldo(update, context, user_id, product, phone_number, unique_amount)
    else:
        # Tampilkan metode pembayaran QRIS
        return await show_qris_payment(update, context, product, phone_number, unique_amount)

async def process_payment_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, product: dict, phone_number: str, unique_amount: int):
    """Proses pembayaran menggunakan saldo"""
    query = update.callback_query
    
    # Kurangi saldo user
    if database.deduct_saldo(user_id, unique_amount):
        # Buat order
        order_id = database.create_order(
            user_id=user_id,
            product_id=product['id'],
            phone_number=phone_number,
            amount=product['price'],
            unique_amount=unique_amount,
            payment_method="SALDO",
            status="SUCCESS"
        )
        
        # Kurangi stok produk
        database.update_product_stock(product['id'], -1)
        
        # Update saldo admin (tambahkan revenue)
        admin_user_id = database.get_or_create_user("admin", "admin", "Admin Bot")
        database.add_saldo(admin_user_id, product['price'])
        
        await query.edit_message_text(
            f"🎉 **PEMBAYARAN BERHASIL!**\n\n"
            f"📦 Produk: **{product['name']}**\n"
            f"💰 Harga: **{format_currency(product['price'])}**\n"
            f"🔢 Kode Unik: **{format_currency(unique_amount - product['price'])}**\n"
            f"💳 Total Bayar: **{format_currency(unique_amount)}**\n"
            f"📱 Nomor Tujuan: **{phone_number}**\n"
            f"📋 Order ID: **#{order_id}**\n\n"
            f"Pesanan Anda sedang diproses. Terima kasih!",
            parse_mode='Markdown'
        )
        
        # Kirim notifikasi ke admin
        await notify_admin_order(context, order_id, product, user, phone_number, unique_amount)
        
    else:
        await query.edit_message_text(
            "❌ **PEMBAYARAN GAGAL!**\n\n"
            "Saldo tidak cukup atau terjadi kesalahan sistem.",
            parse_mode='Markdown'
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def show_qris_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, product: dict, phone_number: str, unique_amount: int):
    """Tampilkan pembayaran QRIS"""
    query = update.callback_query
    
    # Tampilkan pesan loading
    await query.edit_message_text(
        "⏳ **MEMBUAT PEMBAYARAN QRIS...**\n\n"
        "Sedang generate kode QRIS untuk pembayaran...",
        parse_mode='Markdown'
    )
    
    # Generate QRIS
    qris_result = await generate_qris_payment(product['price'], unique_amount)
    
    if qris_result.get('status') == 'success':
        qris_base64 = qris_result.get('qris_base64')
        
        # Simpan data order sementara
        user = query.from_user
        user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
        
        order_id = database.create_order(
            user_id=user_id,
            product_id=product['id'],
            phone_number=phone_number,
            amount=product['price'],
            unique_amount=unique_amount,
            payment_method="QRIS",
            status="PENDING"
        )
        
        context.user_data['pending_order_id'] = order_id
        
        # Kirim gambar QRIS
        try:
            # Decode base64 dan kirim sebagai photo
            import base64
            from io import BytesIO
            
            qris_image_data = base64.b64decode(qris_base64)
            qris_image = BytesIO(qris_image_data)
            qris_image.name = 'qris_payment.png'
            
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=qris_image,
                caption=(
                    f"💰 **PEMBAYARAN QRIS**\n\n"
                    f"📦 Produk: **{product['name']}**\n"
                    f"💳 Total Bayar: **{format_currency(unique_amount)}**\n"
                    f"📱 Nomor Tujuan: **{phone_number}**\n"
                    f"📋 Order ID: **#{order_id}**\n\n"
                    f"**Instruksi Pembayaran:**\n"
                    f"1. Scan QRIS di atas menggunakan aplikasi e-wallet atau mobile banking\n"
                    f"2. Pastikan nominal tepat **{format_currency(unique_amount)}**\n"
                    f"3. Setelah bayar, tunggu konfirmasi otomatis\n"
                    f"4. Pesanan akan diproses setelah pembayaran berhasil\n\n"
                    f"⏳ QRIS berlaku 15 menit"
                ),
                parse_mode='Markdown'
            )
            
            # Hapus pesan loading
            await query.message.delete()
            
        except Exception as e:
            logger.error(f"Error sending QRIS image: {e}")
            await query.edit_message_text(
                f"❌ **GAGAL MEMUAT QRIS**\n\n"
                f"Silakan coba lagi atau gunakan metode pembayaran lain.\n\n"
                f"Detail Order:\n"
                f"📦 Produk: {product['name']}\n"
                f"💳 Total Bayar: {format_currency(unique_amount)}\n"
                f"📱 Nomor Tujuan: {phone_number}",
                parse_mode='Markdown'
            )
        
    else:
        await query.edit_message_text(
            f"❌ **GAGAL MEMBUAT PEMBAYARAN**\n\n"
            f"Error: {qris_result.get('message', 'Unknown error')}\n\n"
            f"Silakan coba lagi atau hubungi admin.",
            parse_mode='Markdown'
        )
    
    return ConversationHandler.END

async def notify_admin_order(context: ContextTypes.DEFAULT_TYPE, order_id: int, product: dict, user, phone_number: str, amount: int):
    """Kirim notifikasi order ke admin"""
    try:
        admin_ids = getattr(config, 'ADMIN_TELEGRAM_IDS', [])
        
        message = (
            f"🛎️ **ORDER BARU**\n\n"
            f"📋 Order ID: #{order_id}\n"
            f"👤 User: {user.full_name} (@{user.username})\n"
            f"📦 Produk: {product['name']}\n"
            f"💰 Total: {format_currency(amount)}\n"
            f"📱 Nomor: {phone_number}\n"
            f"⏰ Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        for admin_id in admin_ids:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error in notify_admin_order: {e}")

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Batalkan pesanan"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    
    await query.edit_message_text(
        "❌ **PESANAN DIBATALKAN**\n\n"
        "Pesanan Anda telah dibatalkan.",
        parse_mode='Markdown'
    )
    
    return ConversationHandler.END

async def back_to_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kembali ke menu kategori"""
    query = update.callback_query
    await query.answer()
    
    return await show_categories(update, context)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation dari command /cancel"""
    context.user_data.clear()
    
    if update.message:
        await update.message.reply_text(
            "❌ **PEMESANAN DIBATALKAN**\n\n"
            "Anda telah membatalkan proses pemesanan.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 MENU UTAMA", callback_data="main_menu_main")]
            ])
        )
    
    return ConversationHandler.END

# ==================== CONVERSATION HANDLER ====================
def get_conversation_handler():
    """Return conversation handler untuk order"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(order_menu_handler, pattern="^main_menu_order$"),
            CommandHandler("order", order_command)
        ],
        states={
            SELECT_CATEGORY: [
                CallbackQueryHandler(select_category, pattern="^order_category_"),
                CallbackQueryHandler(back_to_categories, pattern="^order_back_categories$"),
                CallbackQueryHandler(cancel_order, pattern="^order_cancel$"),
            ],
            SELECT_PRODUCT: [
                CallbackQueryHandler(select_product, pattern="^order_product_"),
                CallbackQueryHandler(back_to_categories, pattern="^order_back_categories$"),
                CallbackQueryHandler(cancel_order, pattern="^order_cancel$"),
            ],
            INPUT_NUMBER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, input_number),
                CommandHandler("cancel", cancel_conversation),
            ],
            CONFIRM_ORDER: [
                CallbackQueryHandler(confirm_order, pattern="^order_confirm$"),
                CallbackQueryHandler(cancel_order, pattern="^order_cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            CallbackQueryHandler(cancel_order, pattern="^order_cancel$"),
        ],
        allow_reentry=True
    )

def get_order_handlers():
    """Return additional order handlers"""
    return [
        CallbackQueryHandler(back_to_categories, pattern="^order_back_categories$"),
        CallbackQueryHandler(cancel_order, pattern="^order_cancel$"),
    ]

# Handler untuk menu callback
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menu order"""
    return await order_menu_handler(update, context)
