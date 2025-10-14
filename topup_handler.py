import config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
import requests
import base64
from io import BytesIO
import database
import random
from datetime import datetime

ASK_TOPUP_NOMINAL = 1

def generate_unique_amount(base_amount):
    """Generate nominal unik dengan menambahkan 3 digit random"""
    base_amount = int(base_amount)
    unique_digits = random.randint(1, 999)
    unique_amount = base_amount + unique_digits
    return unique_amount, unique_digits

async def topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle both command and callback
    if hasattr(update, 'callback_query') and update.callback_query:
        user = update.callback_query.from_user
        message_func = update.callback_query.edit_message_text
    else:
        user = update.message.from_user
        message_func = update.message.reply_text
    
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    
    await message_func(
        "💳 **TOP UP SALDO**\n\n"
        "Masukkan nominal top up (angka saja):\n"
        "Contoh: `10000` untuk Rp 10.000\n\n"
        "💰 **Nominal akan ditambahkan kode unik** untuk memudahkan verifikasi.",
        parse_mode='Markdown'
    )
    return ASK_TOPUP_NOMINAL

async def topup_nominal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    nominal_input = update.message.text.strip()
    
    # Validasi input
    if not nominal_input.isdigit() or int(nominal_input) <= 0:
        await update.message.reply_text(
            "❌ **Format tidak valid!**\n\n"
            "Masukkan hanya angka dan lebih dari 0.\n"
            "Contoh: `50000` untuk Rp 50.000\n\n"
            "Silakan masukkan lagi:",
            parse_mode='Markdown'
        )
        return ASK_TOPUP_NOMINAL
    
    base_amount = int(nominal_input)
    
    # Generate nominal unik
    unique_amount, unique_digits = generate_unique_amount(base_amount)
    
    # Simpan data di context untuk notifikasi admin
    context.user_data['topup_data'] = {
        'user_id': user_id,
        'user_name': user.full_name,
        'username': user.username,
        'base_amount': base_amount,
        'unique_amount': unique_amount,
        'unique_digits': unique_digits
    }
    
    # Konfirmasi ke user
    await update.message.reply_text(
        f"💰 **KONFIRMASI TOP UP**\n\n"
        f"👤 **User:** {user.full_name}\n"
        f"📊 **Nominal Dasar:** Rp {base_amount:,}\n"
        f"🔢 **Kode Unik:** {unique_digits:03d}\n"
        f"💵 **Total Transfer:** Rp {unique_amount:,}\n\n"
        f"**Silakan transfer tepat Rp {unique_amount:,}**\n"
        f"QRIS akan segera digenerate...",
        parse_mode='Markdown'
    )
    
    # Generate QRIS
    payload = {
        "amount": str(unique_amount),  # Kirim nominal unik
        "qris_statis": config.QRIS_STATIS
    }
    
    try:
        resp = requests.post("https://qrisku.my.id/api", json=payload, timeout=15)
        result = resp.json()
        
        if result.get("status") == "success" and "qris_base64" in result:
            qris_base64 = result["qris_base64"]
            qris_bytes = base64.b64decode(qris_base64)
            bio = BytesIO(qris_bytes)
            bio.name = 'qris.png'
            
            # Simpan ke database
            request_id = database.create_topup_request(
                user_id, 
                base_amount,  # Simpan nominal dasar
                unique_amount,  # Simpan nominal unik
                unique_digits,  # Simpan kode unik
                qris_base64
            )
            
            # Simpan request_id di context untuk notifikasi admin
            context.user_data['topup_data']['request_id'] = request_id
            
            # Kirim QRIS ke user
            await update.message.reply_photo(
                photo=bio,
                caption=f"📱 **QRIS TOP UP**\n\n"
                       f"💰 **Total Transfer:** Rp {unique_amount:,}\n"
                       f"🔢 **Kode Unik:** {unique_digits:03d}\n\n"
                       f"⚠️ **Transfer tepat Rp {unique_amount:,}**\n"
                       f"Saldo akan otomatis bertambah setelah admin verifikasi.\n\n"
                       f"📋 **ID Request:** `{request_id}`",
                parse_mode='Markdown'
            )
            
            # Kirim notifikasi ke admin
            await send_admin_notification(update, context, request_id)
            
        else:
            await update.message.reply_text(
                f"❌ **Gagal generate QRIS**\n\n"
                f"Error: {result.get('message', 'Unknown error')}\n\n"
                f"Silakan coba lagi atau hubungi admin.",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        await update.message.reply_text(
            f"❌ **Error System**\n\n"
            f"Terjadi kesalahan: {str(e)}\n\n"
            f"Silakan coba lagi nanti.",
            parse_mode='Markdown'
        )
    
    return ConversationHandler.END

async def send_admin_notification(update: Update, context: ContextTypes.DEFAULT_TYPE, request_id):
    """Kirim notifikasi ke semua admin"""
    topup_data = context.user_data.get('topup_data', {})
    
    if not topup_data:
        return
    
    user_name = topup_data.get('user_name', 'Unknown')
    username = topup_data.get('username', 'Unknown')
    base_amount = topup_data.get('base_amount', 0)
    unique_amount = topup_data.get('unique_amount', 0)
    unique_digits = topup_data.get('unique_digits', 0)
    
    notification_text = (
        f"🔔 **PERMINTAAN TOP UP BARU**\n\n"
        f"👤 **User:** {user_name}\n"
        f"📛 **Username:** @{username}\n"
        f"💰 **Nominal Dasar:** Rp {base_amount:,}\n"
        f"🔢 **Kode Unik:** {unique_digits:03d}\n"
        f"💵 **Total Transfer:** Rp {unique_amount:,}\n"
        f"📋 **ID Request:** `{request_id}`\n"
        f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}\n\n"
        f"Gunakan `/approve_topup {request_id}` untuk approve atau `/cancel_topup {request_id}` untuk cancel."
    )
    
    # Kirim ke semua admin
    for admin_id in config.ADMIN_TELEGRAM_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=notification_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Gagal kirim notifikasi ke admin {admin_id}: {e}")

async def topup_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query') and update.callback_query:
        message_func = update.callback_query.edit_message_text
    else:
        message_func = update.message.reply_text
        
    await message_func(
        "❌ **Top Up Dibatalkan**\n\n"
        "Ketik `/topup` atau gunakan menu untuk memulai kembali.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

# Conversation handler untuk topup
topup_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler('topup', topup_start),
        CallbackQueryHandler(topup_start, pattern='^menu_topup$')
    ],
    states={
        ASK_TOPUP_NOMINAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, topup_nominal)]
    },
    fallbacks=[CommandHandler('cancel', topup_cancel)]
        )
