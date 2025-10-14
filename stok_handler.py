import requests
import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, CallbackQueryHandler
import config
import logging

logger = logging.getLogger(__name__)

PROVIDER_STOCK_URL = "https://panel.khfy-store.com/api_v3/cek_stock_akrab"

def format_stock_akrab(data):
    """Format data stok dari provider menjadi pesan yang mudah dibaca"""
    if not data.get("ok", False):
        return "❌ Gagal mengambil data stok dari provider."
    
    stocks = data.get("data", {})
    if not stocks:
        return "📭 Tidak ada data stok yang tersedia."
    
    message = "📊 **STOK PRODUK AKRAB**\n\n"
    
    # Hitung total stok tersedia
    total_stock = 0
    available_products = 0
    
    for product_name, stock_info in stocks.items():
        stock = stock_info.get("stock", 0)
        status = "✅ TERSEDIA" if stock > 0 else "❌ HABIS"
        message += f"• **{product_name}**: {stock} pcs - {status}\n"
        
        total_stock += stock
        if stock > 0:
            available_products += 1
    
    message += f"\n📈 **Ringkasan:**\n"
    message += f"├ Produk Tersedia: {available_products}\n"
    message += f"├ Total Stok: {total_stock} pcs\n"
    message += f"└ Update: {data.get('timestamp', 'N/A')}"
    
    return message

async def stock_akrab_callback(update: Update, context: CallbackContext):
    query = update.callback_query if hasattr(update, "callback_query") and update.callback_query else None
    user_id = None
    
    if query:
        user_id = query.from_user.id
        await query.answer()
        msg_func = query.edit_message_text
    else:
        user_id = update.effective_user.id if update.effective_user else None
        msg_func = update.message.reply_text

    try:
        # Tampilkan pesan loading
        loading_msg = "🔄 Memuat data stok..."
        if query:
            await query.edit_message_text(loading_msg)
        else:
            loading_message = await update.message.reply_text(loading_msg)
        
        # Tambahkan API key jika diperlukan
        api_key = getattr(config, 'API_KEY_PROVIDER', '')
        params = {}
        if api_key:
            params['api_key'] = api_key
            
        # Gunakan aiohttp untuk request async
        async with aiohttp.ClientSession() as session:
            async with session.get(PROVIDER_STOCK_URL, params=params, timeout=10) as resp:
                resp.raise_for_status()
                data = await resp.json()
        
        msg = format_stock_akrab(data)
        
    except asyncio.TimeoutError:
        msg = "⏰ **Timeout**: Gagal mengambil data stok. Server provider tidak merespons."
        logger.error("Timeout saat mengambil data stok")
    except Exception as e:
        msg = f"❌ **Gagal mengambil data stok:**\n{str(e)}"
        logger.error(f"Error mengambil stok: {e}")

    # Buat keyboard dengan opsi refresh dan kembali
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Stok", callback_data="menu_stock")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Kirim atau edit pesan
    if query:
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

# Command handler untuk /stock
async def stock_command(update: Update, context: CallbackContext):
    """Handler untuk command /stock"""
    await stock_akrab_callback(update, context)

# Handler untuk callback refresh stok
def get_stock_handlers():
    """Return list of stock handlers for registration"""
    return [
        CallbackQueryHandler(stock_akrab_callback, pattern="^menu_stock$"),
    ]
