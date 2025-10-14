import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import config

PROVIDER_STOCK_URL = "https://panel.khfy-store.com/api_v3/cek_stock_akrab"

def format_stock_akrab(data):
    """Format data stok dari provider menjadi pesan yang mudah dibaca"""
    if not data.get("ok", False):
        return "❌ Gagal mengambil data stok dari provider."
    
    stocks = data.get("data", {})
    if not stocks:
        return "📭 Tidak ada data stok yang tersedia."
    
    message = "📊 **STOK PRODUK AKRAB**\n\n"
    
    for product_name, stock_info in stocks.items():
        stock = stock_info.get("stock", 0)
        status = "✅ TERSEDIA" if stock > 0 else "❌ HABIS"
        message += f"• **{product_name}**: {stock} pcs - {status}\n"
    
    message += f"\n⏰ Terakhir diperbarui: {data.get('timestamp', 'N/A')}"
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
        # Tambahkan API key jika diperlukan
        api_key = getattr(config, 'API_KEY_PROVIDER', '')
        params = {}
        if api_key:
            params['api_key'] = api_key
            
        resp = requests.get(PROVIDER_STOCK_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        msg = format_stock_akrab(data)
    except Exception as e:
        msg = f"❌ **Gagal mengambil data stok:**\n{str(e)}"

    # Buat keyboard untuk kembali ke menu utama
    keyboard = [[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await msg_func(
        msg,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
