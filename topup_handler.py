from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
import config
import requests
import base64
from io import BytesIO
import database
import random
import logging
import sqlite3
from datetime import datetime
import aiohttp
import asyncio

logger = logging.getLogger(__name__)

# States untuk conversation
ASK_TOPUP_NOMINAL = 1

def generate_unique_amount(base_amount):
    """Generate nominal unik dengan menambahkan 3 digit random"""
    try:
        base_amount = int(base_amount)
        unique_digits = random.randint(1, 999)
        unique_amount = base_amount + unique_digits
        return unique_amount, unique_digits
    except Exception as e:
        logger.error(f"Error generating unique amount: {e}")
        return base_amount, 0

async def generate_qris(unique_amount):
    """Generate QRIS menggunakan API"""
    try:
        logger.info(f"🔧 [QRIS] Generating QRIS untuk amount: {unique_amount}")
        
        payload = {
            "amount": str(unique_amount),
            "qris_statis": getattr(config, 'QRIS_STATIS', '')
        }
        
        response = requests.post(
            "https://qrisku.my.id/api",
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success" and "qris_base64" in result:
                qris_base64 = result["qris_base64"]
                if qris_base64 and len(qris_base64) > 100:
                    return qris_base64, None
                else:
                    return None, "QRIS base64 tidak valid"
            else:
                return None, result.get('message', 'Unknown error from QRIS API')
        else:
            return None, f"HTTP {response.status_code}"
            
    except Exception as e:
        return None, f"Error: {str(e)}"

async def topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mulai proses topup"""
    try:
        if update.callback_query:
            query = update.callback_query
            user = query.from_user
            await query.answer()
            await query.edit_message_text(
                "💳 **TOP UP SALDO**\n\n"
                "Masukkan nominal top up (angka saja):\n"
                "✅ Contoh: `100000` untuk Rp 100.000\n\n"
                "💰 **PENTING:** Nominal akan ditambahkan kode unik\n\n"
                "❌ Ketik /cancel untuk membatalkan",
                parse_mode='Markdown'
            )
        else:
            user = update.message.from_user
            await update.message.reply_text(
                "💳 **TOP UP SALDO**\n\n"
                "Masukkan nominal top up (angka saja):\n"
                "✅ Contoh: `100000` untuk Rp 100.000\n\n"
                "💰 **PENTING:** Nominal akan ditambahkan kode unik\n\n"
                "❌ Ketik /cancel untuk membatalkan",
                parse_mode='Markdown'
            )
        
        return ASK_TOPUP_NOMINAL
        
    except Exception as e:
        logger.error(f"Error in topup_start: {e}")
        return ConversationHandler.END

async def topup_nominal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process nominal topup"""
    try:
        nominal_input = update.message.text.strip()
        
        if nominal_input.lower() == '/cancel':
            await update.message.reply_text("❌ **Top Up Dibatalkan**")
            return ConversationHandler.END
            
        if not nominal_input.isdigit():
            await update.message.reply_text("❌ Masukkan angka saja!")
            return ASK_TOPUP_NOMINAL
        
        base_amount = int(nominal_input)
        
        if base_amount < 10000:
            await update.message.reply_text("❌ Minimum top up Rp 10.000")
            return ASK_TOPUP_NOMINAL
        
        unique_amount, unique_digits = generate_unique_amount(base_amount)
        
        await update.message.reply_text(
            f"💰 **TOP UP DITERIMA**\n\n"
            f"💵 **Total Transfer:** Rp {unique_amount:,}\n"
            f"🔢 **Kode Unik:** {unique_digits:03d}\n\n"
            f"Silakan transfer ke rekening admin dan kirim bukti transfer.",
            parse_mode='Markdown'
        )
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in topup_nominal: {e}")
        await update.message.reply_text("❌ Terjadi error")
        return ConversationHandler.END

async def topup_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Batalkan topup"""
    await update.message.reply_text("❌ **Top Up Dibatalkan**")
    return ConversationHandler.END

async def show_topup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu topup"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("💳 Topup Manual", callback_data="topup_manual")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="menu_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "💰 **Menu Topup**\n\nPilih jenis topup:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_topup_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk topup manual"""
    return await topup_start(update, context)

async def handle_topup_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk riwayat"""
    query = update.callback_query
    await query.answer("Fitur coming soon!")

async def show_manage_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage topup"""
    query = update.callback_query
    await query.answer("Fitur admin coming soon!")

# Conversation handler
topup_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler('topup', topup_start),
        CallbackQueryHandler(handle_topup_manual, pattern='^topup_manual$')
    ],
    states={
        ASK_TOPUP_NOMINAL: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, topup_nominal),
            CommandHandler('cancel', topup_cancel)
        ]
    },
    fallbacks=[CommandHandler('cancel', topup_cancel)]
)
