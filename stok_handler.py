import logging
import aiohttp
import asyncio
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config

logger = logging.getLogger(__name__)

# ==================== KHFYPAY STOCK API ====================

class KhfyPayStockAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://panel.khfy-store.com/api_v2"
    
    async def get_real_time_stock(self):
        """Get real-time stock from KhfyPay API v2 - REAL TIME langsung dari provider"""
        try:
            logger.info("🔄 Fetching REAL-TIME stock from KhfyPay API v2...")
            
            products = await self._get_products_v2()
            if products:
                logger.info(f"✅ Got REAL-TIME stock from API v2: {len(products)} products")
                return products
            else:
                logger.error("❌ Failed to get products from API v2")
                return None
            
        except Exception as e:
            logger.error(f"❌ Error getting REAL-TIME stock: {e}")
            return None
    
    async def _get_products_v2(self):
        """Get products from API v2 - sesuai dokumentasi resmi"""
        try:
            url = f"{self.base_url}/list_product"
            params = {"api_key": self.api_key}
            
            logger.info(f"🔍 Calling API v2: {url}")
            logger.info(f"🔍 Using API Key: {self.api_key[:8]}...")  # Log partial API key for security
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=15) as response:
                    logger.info(f"🔍 API v2 Response status: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"🔍 API v2 Response type: {type(data)}")
                        
                        # Validasi response format
                        if isinstance(data, list):
                            logger.info(f"✅ API v2 returned list with {len(data)} items")
                            if len(data) > 0:
                                first_item = data[0]
                                if isinstance(first_item, dict):
                                    logger.info(f"✅ First item keys: {list(first_item.keys())}")
                                    # Check required fields
                                    required_fields = ['code', 'name', 'price', 'status']
                                    missing_fields = [field for field in required_fields if field not in first_item]
                                    if missing_fields:
                                        logger.warning(f"⚠️ Missing fields in first item: {missing_fields}")
                                    else:
                                        logger.info("✅ All required fields present")
                            return data
                        else:
                            logger.error(f"❌ API v2 returned non-list data: {type(data)}")
                            logger.error(f"❌ Response content: {data}")
                            return None
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ API v2 returned status {response.status}: {error_text}")
                        return None
        except asyncio.TimeoutError:
            logger.error("❌ API v2 timeout")
            return None
        except Exception as e:
            logger.error(f"❌ Error in _get_products_v2: {e}")
            return None

# ==================== STOCK PROCESSING ====================

def process_real_time_stock(products_data):
    """Process real-time stock data dari API v2"""
    try:
        if not products_data or not isinstance(products_data, list):
            return {}
        
        stock_info = {}
        categorized_products = {}
        
        for product in products_data:
            if not isinstance(product, dict):
                continue
                
            code = product.get('code', '').strip()
            name = product.get('name', 'Unknown Product')
            price = product.get('price', 0)
            status = product.get('status', '').lower()
            category = product.get('category', 'Umum')
            
            # Skip jika code kosong
            if not code:
                continue
            
            # Convert price to integer
            try:
                price = int(price)
            except (ValueError, TypeError):
                price = 0
            
            # Determine stock status berdasarkan status field
            if status == 'active':
                stock_text = "Tersedia"
                stock_emoji = "🟢"
                is_available = True
            elif status == 'empty':
                stock_text = "Habis" 
                stock_emoji = "🔴"
                is_available = False
            elif status == 'problem':
                stock_text = "Gangguan"
                stock_emoji = "🚧"
                is_available = False
            elif status == 'inactive':
                stock_text = "Nonaktif"
                stock_emoji = "⚫"
                is_available = False
            else:
                stock_text = "Unknown"
                stock_emoji = "⚫"
                is_available = False
            
            # Simpan info produk
            stock_info[code] = {
                'name': name,
                'price': price,
                'stock_text': stock_text,
                'stock_emoji': stock_emoji,
                'category': category,
                'status': status,
                'is_available': is_available,
                'real_time': True
            }
            
            # Kategorikan produk
            if category not in categorized_products:
                categorized_products[category] = []
            
            categorized_products[category].append({
                'code': code,
                'name': name,
                'price': price,
                'stock_text': stock_text,
                'stock_emoji': stock_emoji,
                'status': status,
                'is_available': is_available
            })
        
        logger.info(f"📊 Processed {len(stock_info)} products into {len(categorized_products)} categories")
        return {
            'stock_info': stock_info,
            'categorized_products': categorized_products,
            'total_products': len(stock_info),
            'available_products': sum(1 for p in stock_info.values() if p['is_available'])
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing real-time stock: {e}")
        return {}

# ==================== TELEGRAM STOCK HANDLERS ====================

async def stock_akrab_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk cek stok produk dengan data REAL-TIME langsung dari provider"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Show processing message
        processing_msg = await query.edit_message_text(
            "🔄 **Mengambil data stok REAL-TIME dari provider...**\n\n"
            "⏳ Mohon tunggu sebentar...",
            parse_mode='Markdown'
        )
        
        # Get REAL-TIME stock directly from provider
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            await show_error_message(update, "❌ API key tidak ditemukan di config")
            return
        
        stock_api = KhfyPayStockAPI(api_key)
        real_time_data = await stock_api.get_real_time_stock()
        
        if not real_time_data:
            await show_error_message(update, "❌ Gagal mengambil data stok dari provider")
            return
        
        # Process the real-time data
        processed_data = process_real_time_stock(real_time_data)
        
        if not processed_data or not processed_data['categorized_products']:
            await show_no_products_message(update)
            return
        
        # Format message dengan data REAL-TIME
        message = format_stock_message(processed_data)
        
        # Create keyboard
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Stok REAL-TIME", callback_data="main_menu_stock")],
            [InlineKeyboardButton("🛒 Beli Produk", callback_data="main_menu_order")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"❌ Error in stock_akrab_callback: {e}")
        await show_error_message(update, f"❌ Error: {str(e)}")

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /stock dengan data REAL-TIME"""
    try:
        # Show processing message
        processing_msg = await update.message.reply_text(
            "🔄 Mengambil data stok REAL-TIME...",
            parse_mode='Markdown'
        )
        
        # Get REAL-TIME stock directly from provider
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            await update.message.reply_text("❌ API key tidak ditemukan")
            return
        
        stock_api = KhfyPayStockAPI(api_key)
        real_time_data = await stock_api.get_real_time_stock()
        
        if not real_time_data:
            await update.message.reply_text("❌ Gagal mengambil data stok REAL-TIME")
            return
        
        # Process the real-time data
        processed_data = process_real_time_stock(real_time_data)
        
        if processed_data:
            total_products = processed_data['total_products']
            available_products = processed_data['available_products']
            
            message = (
                "📊 **STOK PRODUK REAL-TIME**\n\n"
                f"🔄 **Data langsung dari provider**\n"
                f"📦 Total produk: **{total_products}**\n"
                f"✅ Tersedia: **{available_products}**\n"
                f"❌ Habis: **{total_products - available_products}**\n"
                f"⏰ Update: **{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}**\n\n"
                "✨ **Fitur REAL-TIME:**\n"
                "• 📡 Data langsung dari server provider\n"
                "• ⚡ Update real-time setiap akses\n"
                "• 🚀 Tidak melalui cache/database\n"
                "• 💯 Akurat dan ter-update\n\n"
                "Klik tombol di bawah untuk melihat detail stok:"
            )
        else:
            message = (
                "📊 **STOK PRODUK REAL-TIME**\n\n"
                "❌ Gagal memproses data stok\n\n"
                "Silakan coba lagi atau hubungi admin."
            )
        
        keyboard = [
            [InlineKeyboardButton("📋 Lihat Detail Stok REAL-TIME", callback_data="main_menu_stock")],
            [InlineKeyboardButton("🛒 Beli Sekarang", callback_data="main_menu_order")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"❌ Error in stock_command: {e}")
        await update.message.reply_text(
            "❌ Gagal memuat data stok REAL-TIME.\nSilakan coba lagi nanti."
        )

# ==================== MESSAGE FORMATTING ====================

def format_stock_message(processed_data):
    """Format stock message dengan data REAL-TIME"""
    try:
        categorized_products = processed_data['categorized_products']
        total_products = processed_data['total_products']
        available_products = processed_data['available_products']
        
        message = "📊 **STOK PRODUK REAL-TIME**\n\n"
        message += f"🔄 **Update:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        message += f"📡 **Sumber:** Data langsung dari provider\n\n"
        
        # Sort categories alphabetically
        sorted_categories = sorted(categorized_products.keys())
        
        for category in sorted_categories:
            products = categorized_products[category]
            message += f"**{category.upper()}:**\n"
            
            category_count = len(products)
            category_available = sum(1 for p in products if p['is_available'])
            
            for product in products:
                message += f"{product['stock_emoji']} {product['name']} - Rp {product['price']:,.0f} | {product['stock_text']}\n"
            
            message += f"*Tersedia: {category_available}/{category_count} produk*\n\n"
        
        # Summary
        message += f"**📈 SUMMARY REAL-TIME:**\n"
        message += f"• Total Produk: {total_products}\n"
        message += f"• Tersedia: {available_products}\n"
        message += f"• Habis: {total_products - available_products}\n"
        message += f"• Sumber: 📡 KhfyPay API v2\n"
        message += f"• Status: ✅ LIVE\n"
        
        return message
        
    except Exception as e:
        logger.error(f"❌ Error in format_stock_message: {e}")
        return "❌ Error formatting stock message"

# ==================== ERROR HANDLING ====================

async def show_error_message(update, error_text):
    """Show error message"""
    keyboard = [
        [InlineKeyboardButton("🔄 Coba Lagi", callback_data="main_menu_stock")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(
            f"❌ **Gagal memuat data stok REAL-TIME**\n\n{error_text}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"❌ Gagal memuat data stok REAL-TIME\n\n{error_text}",
            reply_markup=reply_markup
        )

async def show_no_products_message(update):
    """Show no products available message"""
    keyboard = [
        [InlineKeyboardButton("🔄 Coba Lagi", callback_data="main_menu_stock")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(
            "📭 **Tidak ada produk aktif**\n\n"
            "Tidak ada produk yang tersedia saat ini dari provider.\n"
            "Silakan coba lagi nanti atau hubungi admin.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "📭 Tidak ada produk aktif saat ini.\nSilakan coba lagi nanti.",
            reply_markup=reply_markup
        )

# ==================== QUICK STOCK CHECK ====================

async def quick_stock_check(product_code):
    """Quick stock check for specific product - REAL-TIME"""
    try:
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            return None
        
        stock_api = KhfyPayStockAPI(api_key)
        real_time_data = await stock_api.get_real_time_stock()
        
        if real_time_data:
            for product in real_time_data:
                if isinstance(product, dict) and product.get('code') == product_code:
                    status = product.get('status', '').lower()
                    is_available = status == 'active'
                    
                    return {
                        'name': product.get('name', 'Unknown'),
                        'price': product.get('price', 0),
                        'status': status,
                        'is_available': is_available,
                        'stock_text': "Tersedia" if is_available else "Habis",
                        'stock_emoji': "🟢" if is_available else "🔴",
                        'real_time': True
                    }
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Error in quick_stock_check: {e}")
        return None

# ==================== BACKGROUND STOCK SYNC ====================

async def background_stock_sync():
    """Background task untuk monitoring stok (optional)"""
    while True:
        try:
            await asyncio.sleep(300)  # Check every 5 minutes
            api_key = getattr(config, 'KHFYPAY_API_KEY', '')
            if api_key:
                stock_api = KhfyPayStockAPI(api_key)
                real_time_data = await stock_api.get_real_time_stock()
                if real_time_data:
                    processed = process_real_time_stock(real_time_data)
                    if processed:
                        logger.info(f"🔍 Background stock check: {processed['total_products']} total, {processed['available_products']} available")
        except Exception as e:
            logger.error(f"❌ Background stock sync error: {e}")
            await asyncio.sleep(60)

def initialize_stock_sync():
    """Initialize background stock monitoring"""
    try:
        asyncio.create_task(background_stock_sync())
        logger.info("✅ Background REAL-TIME stock monitoring initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize background stock monitoring: {e}")

# Import datetime
from datetime import datetime
