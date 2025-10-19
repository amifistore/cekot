# stok_handler.py - Complete Stock Management System
import logging
import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from datetime import datetime
import config
from database import db

logger = logging.getLogger(__name__)

# ==================== STOCK UTILITIES ====================
def format_stock_akrab(data: Dict) -> str:
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
                    
        elif isinstance(stocks, list):
            for i, product in enumerate(stocks, 1):
                if isinstance(product, dict):
                    product_name = product.get('nama', product.get('product_name', product.get('name', f'Produk {i}')))
                    stock = product.get('stock', product.get('stok', product.get('quantity', 0)))
                    price = product.get('harga', product.get('price', 'N/A'))
                else:
                    product_name = f'Produk {i}'
                    stock = product
                    price = 'N/A'
                    
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
        
        if isinstance(data, dict) and 'timestamp' in data:
            message += f"└ Update: {data['timestamp']}"
        else:
            message += f"└ Update: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
            
        return message
        
    except Exception as e:
        logger.error(f"Error formatting stock data: {str(e)}")
        logger.error(f"Data that caused error: {data}")
        return f"❌ Error memformat data stok: {str(e)}"

def format_local_stock(products: List[Dict]) -> str:
    """Format stok dari database lokal"""
    try:
        if not products:
            return "📭 Tidak ada produk aktif di database."
        
        # Group by category
        products_by_category = {}
        for product in products:
            category = product['category'] or 'Umum'
            if category not in products_by_category:
                products_by_category[category] = []
            products_by_category[category].append(product)
        
        message = "📊 **STOK PRODUK (DATABASE)**\n\n"
        total_products = 0
        available_products = 0
        
        for category, products_list in products_by_category.items():
            message += f"**{category}**\n"
            for product in products_list:
                status_icon = "✅" if product.get('stock', 0) > 0 else "❌"
                stock_info = f"Stok: {product.get('stock', 'N/A')}"
                price_info = f"Rp {product['price']:,}"
                
                message += f"{status_icon} {product['name']} - {price_info} - {stock_info}\n"
                total_products += 1
                if product.get('stock', 0) > 0:
                    available_products += 1
            message += "\n"
        
        message += f"📈 **Ringkasan:**\n"
        message += f"├ Total Produk: {total_products}\n"
        message += f"├ Tersedia: {available_products}\n"
        message += f"├ Habis: {total_products - available_products}\n"
        message += f"└ Update: {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        
        return message
        
    except Exception as e:
        logger.error(f"Error formatting local stock: {e}")
        return f"❌ Error memformat stok lokal: {str(e)}"

# ==================== STOCK CHECKING HANDLERS ====================
async def stock_akrab_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menampilkan stok produk dari provider"""
    query = getattr(update, "callback_query", None)
    user_id = query.from_user.id if query else update.effective_user.id

    try:
        if query:
            await query.answer()
            msg_func = query.edit_message_text
        else:
            msg_func = update.message.reply_text

        # Show loading message
        loading_msg = "🔄 Memuat data stok dari provider..."
        if query:
            await query.edit_message_text(loading_msg)
        else:
            loading_message = await update.message.reply_text(loading_msg)

        # Fetch stock data from provider
        url = config.STOCK_API_URL
        params = {"api_key": config.API_KEY_PROVIDER}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=15) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"HTTP {resp.status}: {error_text}")
                data = await resp.json()
                logger.info(f"Raw API response: {data}")

        # Format and send stock data
        msg = format_stock_akrab(data)

    except aiohttp.ClientError as e:
        msg = f"🌐 **Error Koneksi**: Gagal terhubung ke server provider.\n\nDetail: {str(e)}"
        logger.error(f"Network error: {e}")
    except asyncio.TimeoutError:
        msg = "⏰ **Timeout**: Provider tidak merespons dalam waktu yang ditentukan.\nSilakan coba lagi nanti."
        logger.error("Stock API timeout")
    except Exception as e:
        msg = f"❌ **Gagal mengambil data stok:**\n\n{str(e)}"
        logger.error(f"Error mengambil stok: {e}", exc_info=True)

    # Create keyboard
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Stok", callback_data="menu_stock")],
        [InlineKeyboardButton("📊 Stok Database", callback_data="stock_local")],
        [InlineKeyboardButton("🛒 Beli Produk", callback_data="menu_order")],
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
        error_msg = "❌ Error menampilkan stok. Silakan coba lagi."
        if query:
            await query.edit_message_text(error_msg, reply_markup=reply_markup)
        else:
            await update.effective_chat.send_message(error_msg, reply_markup=reply_markup)

async def stock_local_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menampilkan stok dari database lokal"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Show loading
        await query.edit_message_text("🔄 Memuat data stok dari database...")
        
        # Get products from database
        products = db.get_active_products()
        
        # Format and send stock data
        msg = format_local_stock(products)
        
        # Create keyboard
        keyboard = [
            [InlineKeyboardButton("🔄 Stok Provider", callback_data="menu_stock")],
            [InlineKeyboardButton("📦 Update Produk", callback_data="admin_update")],
            [InlineKeyboardButton("🛒 Beli Produk", callback_data="menu_order")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
        ]
        
        # Add admin button if user is admin
        if str(query.from_user.id) in [str(admin_id) for admin_id in config.ADMIN_TELEGRAM_IDS]:
            keyboard.insert(1, [InlineKeyboardButton("👑 Admin Panel", callback_data="menu_admin")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in stock_local_callback: {e}")
        await query.edit_message_text(
            f"❌ Gagal memuat stok dari database: {str(e)}",
            parse_mode="Markdown"
        )

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /stock"""
    await stock_akrab_callback(update, context)

async def stock_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menu stock dari callback"""
    query = update.callback_query
    await query.answer()
    
    # Show stock source selection
    keyboard = [
        [InlineKeyboardButton("🌐 Stok Provider", callback_data="menu_stock")],
        [InlineKeyboardButton("💾 Stok Database", callback_data="stock_local")],
        [InlineKeyboardButton("🛒 Beli Produk", callback_data="menu_order")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ]
    
    # Add admin button if user is admin
    if str(query.from_user.id) in [str(admin_id) for admin_id in config.ADMIN_TELEGRAM_IDS]:
        keyboard.insert(2, [InlineKeyboardButton("👑 Admin Panel", callback_data="menu_admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📊 **CEK STOK PRODUK**\n\n"
        "Pilih sumber data stok:\n"
        "• 🌐 **Stok Provider** - Data real-time dari provider\n"
        "• 💾 **Stok Database** - Data dari database lokal\n\n"
        "💡 **Tips:** Gunakan stok provider untuk data terbaru, "
        "stok database untuk data yang sudah disinkronisasi.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ==================== STOCK MANAGEMENT (ADMIN) ====================
async def update_stock_from_provider(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Update stock data from provider (Admin only)"""
    from admin_handler import admin_check, log_admin_action
    
    if not await admin_check(update, context):
        return
    
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        await query.edit_message_text("🔄 Memperbarui data stok dari provider...")
        
        # Fetch stock data from provider
        url = config.STOCK_API_URL
        params = {"api_key": config.API_KEY_PROVIDER}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=15) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}: {await resp.text()}")
                data = await resp.json()
        
        if not data.get("ok", True):
            raise Exception(data.get("message", "Unknown error from provider"))
        
        stocks = data.get("data", {})
        
        # Update products stock in database
        updated_count = 0
        if isinstance(stocks, dict):
            for product_name, stock_info in stocks.items():
                try:
                    # Find product by name (this is simplified - in reality you might need better matching)
                    products = db.get_active_products()
                    matching_products = [p for p in products if p['name'].lower() == product_name.lower()]
                    
                    if matching_products:
                        product = matching_products[0]
                        stock = stock_info.get("stock", stock_info.get("stok", 0)) if isinstance(stock_info, dict) else stock_info
                        
                        # Update product stock
                        db.update_product(product['code'], stock=stock)
                        updated_count += 1
                        
                except Exception as e:
                    logger.error(f"Error updating stock for {product_name}: {e}")
                    continue
        
        await log_admin_action(user_id, "UPDATE_STOCK", f"Updated: {updated_count} products")
        
        keyboard = [
            [InlineKeyboardButton("📊 Lihat Stok", callback_data="stock_local")],
            [InlineKeyboardButton("🔄 Update Lagi", callback_data="update_stock")],
            [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ **Update Stok Berhasil**\n\n"
            f"📊 **Statistik:**\n"
            f"├ Produk diupdate: {updated_count}\n"
            f"⏰ **Update Terakhir:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error updating stock: {e}")
        await query.edit_message_text(
            f"❌ **Gagal update stok:** {str(e)}",
            parse_mode='Markdown'
        )

def get_stock_handlers():
    """Return list of stock handlers for registration"""
    return [
        CallbackQueryHandler(stock_akrab_callback, pattern="^menu_stock$"),
        CallbackQueryHandler(stock_local_callback, pattern="^stock_local$"),
        CallbackQueryHandler(stock_menu_handler, pattern="^stock_menu$"),
        CallbackQueryHandler(update_stock_from_provider, pattern="^update_stock$"),
        CommandHandler("stock", stock_command)
                ]
