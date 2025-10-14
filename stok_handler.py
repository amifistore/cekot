import requests
import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, CallbackQueryHandler
import config
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

PROVIDER_STOCK_URL = "https://panel.khfy-store.com/api_v3/cek_stock_akrab"

def format_stock_akrab(data):
    """Format data stok dari provider menjadi pesan yang mudah dibaca"""
    try:
        # Debug: Log struktur data yang diterima
        logger.info(f"Data structure received: {type(data)}")
        if isinstance(data, dict):
            logger.info(f"Data keys: {data.keys()}")
        
        # Handle berbagai format response
        if isinstance(data, list):
            # Jika data adalah list langsung
            stocks = data
            message = "📊 **STOK PRODUK AKRAB**\n\n"
            
            total_stock = 0
            available_products = 0
            
            for i, product in enumerate(stocks, 1):
                if isinstance(product, dict):
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
                    message += f"• {str(product)}\n"
            
            message += f"\n📈 **Ringkasan:**\n"
            message += f"├ Produk Tersedia: {available_products}\n"
            message += f"├ Total Stok: {total_stock} pcs\n"
            message += f"└ Update: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
            
        elif isinstance(data, dict):
            # Jika data adalah dictionary dengan struktur standar
            if not data.get("ok", False):
                error_msg = data.get("message", "Gagal mengambil data stok dari provider.")
                return f"❌ {error_msg}"
            
            stocks = data.get("data", {})
            
            # Handle jika data.data adalah list
            if isinstance(stocks, list):
                message = "📊 **STOK PRODUK AKRAB**\n\n"
                
                total_stock = 0
                available_products = 0
                
                for i, product in enumerate(stocks, 1):
                    if isinstance(product, dict):
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
                        message += f"• {str(product)}\n"
                
                message += f"\n📈 **Ringkasan:**\n"
                message += f"├ Produk Tersedia: {available_products}\n"
                message += f"├ Total Stok: {total_stock} pcs\n"
                message += f"└ Update: {data.get('timestamp', datetime.now().strftime('%d-%m-%Y %H:%M:%S'))}"
                
            else:
                # Format dictionary tradisional
                message = "📊 **STOK PRODUK AKRAB**\n\n"
                
                total_stock = 0
                available_products = 0
                
                for product_name, stock_info in stocks.items():
                    if isinstance(stock_info, dict):
                        stock = stock_info.get("stock", stock_info.get("stok", 0))
                        price = stock_info.get("harga", stock_info.get("price", "N/A"))
                    else:
                        stock = stock_info
                        price = "N/A"
                    
                    status = "✅ TERSEDIA" if stock > 0 else "❌ HABIS"
                    price_text = f" | Rp {price:,}" if price != 'N/A' and isinstance(price, (int, float)) else ""
                    message += f"• **{product_name}**: {stock} pcs{price_text} - {status}\n"
                    
                    total_stock += int(stock)
                    if stock > 0:
                        available_products += 1
                
                message += f"\n📈 **Ringkasan:**\n"
                message += f"├ Produk Tersedia: {available_products}\n"
                message += f"├ Total Stok: {total_stock} pcs\n"
                message += f"└ Update: {data.get('timestamp', datetime.now().strftime('%d-%m-%Y %H:%M:%S'))}"
        
        else:
            return f"❌ Format data tidak dikenali: {type(data)}"
        
        return message
        
    except Exception as e:
        logger.error(f"Error formatting stock data: {str(e)}")
        logger.error(f"Data that caused error: {data}")
        return f"❌ Error memformat data stok: {str(e)}"

async def stock_akrab_callback(update: Update, context: CallbackContext):
    """Handler untuk menampilkan stok produk"""
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id
    
    try:
        # Answer callback query terlebih dahulu
        if query:
            await query.answer()
            msg_func = query.edit_message_text
        else:
            msg_func = update.message.reply_text

        # Tampilkan pesan loading
        loading_msg = "🔄 Memuat data stok..."
        if query:
            await query.edit_message_text(loading_msg)
        else:
            loading_message = await update.message.reply_text(loading_msg)
        
        # Siapkan parameter request
        api_key = getattr(config, 'API_KEY_PROVIDER', '')
        headers = {}
        params = {}
        
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
            params['api_key'] = api_key
            
        # Request data stok dengan timeout
        async with aiohttp.ClientSession() as session:
            async with session.get(
                PROVIDER_STOCK_URL, 
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"HTTP {resp.status}: {error_text}")
                
                data = await resp.json()
                logger.info(f"Raw API response: {data}")

        # Format pesan stok
        msg = format_stock_akrab(data)
        
    except asyncio.TimeoutError:
        msg = "⏰ **Timeout**: Gagal mengambil data stok. Server provider tidak merespons."
        logger.error("Timeout saat mengambil data stok")
        
    except aiohttp.ClientError as e:
        msg = f"🌐 **Error Koneksi**: Gagal terhubung ke server provider.\n\nDetail: {str(e)}"
        logger.error(f"Network error: {e}")
        
    except Exception as e:
        msg = f"❌ **Gagal mengambil data stok:**\n\n{str(e)}"
        logger.error(f"Error mengambil stok: {e}", exc_info=True)

    # Buat keyboard dengan opsi refresh dan kembali
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Stok", callback_data="menu_stock")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Kirim atau edit pesan
    try:
        if query:
            await query.edit_message_text(
                msg,
                parse_mode="Markdown",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        else:
            # Hapus loading message dan kirim yang baru
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
        # Fallback: kirim pesan baru
        await update.effective_chat.send_message(
            "❌ Error menampilkan stok. Silakan coba lagi.",
            reply_markup=reply_markup
        )

async def stock_command(update: Update, context: CallbackContext):
    """Handler untuk command /stock"""
    await stock_akrab_callback(update, context)

def get_stock_handlers():
    """Return list of stock handlers for registration"""
    return [
        CallbackQueryHandler(stock_akrab_callback, pattern="^menu_stock$"),
]
