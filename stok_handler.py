import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
import config
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def format_stock_akrab(data):
    """Format data stok dari provider menjadi pesan yang mudah dibaca"""
    try:
        if isinstance(data, dict) and not data.get("ok", True):
            error_msg = data.get("message", "Gagal mengambil data stok dari provider.")
            return f"❌ {error_msg}"
        stocks = data.get("data", {}) if isinstance(data, dict) else data
        message = "📊 **STOK PRODUK AKRAB**\n\n"
        total_stock = 0
        available_products = 0

        if isinstance(stocks, dict):
            for product_name, stock_info in stocks.items():
                stock = stock_info.get("stock", stock_info.get("stok", 0)) if isinstance(stock_info, dict) else stock_info
                price = stock_info.get("harga", stock_info.get("price", "N/A")) if isinstance(stock_info, dict) else "N/A"
                status = "✅ TERSEDIA" if stock > 0 else "❌ HABIS"
                price_text = f" | Rp {price:,}" if price != 'N/A' and isinstance(price, (int, float)) else ""
                message += f"• **{product_name}**: {stock} pcs{price_text} - {status}\n"
                total_stock += int(stock)
                if stock > 0:
                    available_products += 1
        elif isinstance(stocks, list):
            for i, product in enumerate(stocks, 1):
                product_name = product.get('nama', product.get('product_name', product.get('name', f'Produk {i}')))
                stock = product.get('stock', product.get('stok', product.get('quantity', 0)))
                price = product.get('harga', product.get('price', 'N/A'))
                status = "✅ TERSEDIA" if stock > 0 else "❌ HABIS"
                price_text = f" | Rp {price:,}" if price != 'N/A' and isinstance(price, (int, float)) else ""
                message += f"• **{product_name}**: {stock} pcs{price_text} - {status}\n"
                total_stock += int(stock)
                if stock > 0:
                    available_products += 1
        else:
            return f"❌ Format data tidak dikenali: {type(data)}"

        message += f"\n📈 **Ringkasan:**\n"
        message += f"├ Produk Tersedia: {available_products}\n"
        message += f"├ Total Stok: {total_stock} pcs\n"
        message += f"└ Update: {data.get('timestamp', datetime.now().strftime('%d-%m-%Y %H:%M:%S'))}" if isinstance(data, dict) else f"└ Update: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
        return message
    except Exception as e:
        logger.error(f"Error formatting stock data: {str(e)}")
        logger.error(f"Data that caused error: {data}")
        return f"❌ Error memformat data stok: {str(e)}"

async def stock_akrab_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menampilkan stok produk"""
    query = getattr(update, "callback_query", None)
    user_id = query.from_user.id if query else update.effective_user.id

    try:
        if query:
            await query.answer()
            msg_func = query.edit_message_text
        else:
            msg_func = update.message.reply_text

        loading_msg = "🔄 Memuat data stok..."
        if query:
            await query.edit_message_text(loading_msg)
        else:
            loading_message = await update.message.reply_text(loading_msg)

        url = "https://panel.khfy-store.com/api_v3/cek_stock_akrab"
        params = {"api_key": config.API_KEY_PROVIDER}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=15) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"HTTP {resp.status}: {error_text}")
                data = await resp.json()
                logger.info(f"Raw API response: {data}")

        msg = format_stock_akrab(data)

    except aiohttp.ClientError as e:
        msg = f"🌐 **Error Koneksi**: Gagal terhubung ke server provider.\n\nDetail: {str(e)}"
        logger.error(f"Network error: {e}")
    except Exception as e:
        msg = f"❌ **Gagal mengambil data stok:**\n\n{str(e)}"
        logger.error(f"Error mengambil stok: {e}", exc_info=True)

    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Stok", callback_data="menu_stock")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if query:
            await query.edit_message_text(
                msg,
                parse_mode="Markdown",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        else:
            if 'loading_message' in locals():
                await loading_message.delete()
            await update.message.reply_text(
                msg,
                parse_mode="Markdown",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        await update.effective_chat.send_message(
            "❌ Error menampilkan stok. Silakan coba lagi.",
            reply_markup=reply_markup
        )

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /stock"""
    await stock_akrab_callback(update, context)

def get_stock_handlers():
    """Return list of stock handlers for registration"""
    return [
        CallbackQueryHandler(stock_akrab_callback, pattern="^menu_stock$"),
    ]
