import logging
import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config

logger = logging.getLogger(__name__)

# ==================== KHFYPAY STOCK API ====================

class KhfyPayStockAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://panel.khfy-store.com/api_v2"
        self.stock_url = "https://panel.khfy-store.com/api_v3/cek_stock_akrab"
    
    async def get_real_time_stock(self):
        """Get real-time stock from KhfyPay API - REAL TIME langsung dari provider"""
        try:
            logger.info("🔄 Fetching REAL-TIME stock from KhfyPay...")
            
            # Priority 1: Try API v3 cek_stock_akrab (lebih update)
            stock_data = await self._get_stock_v3()
            if stock_data:
                logger.info("✅ Got REAL-TIME stock from API v3")
                return self._parse_stock_v3(stock_data)
            
            # Priority 2: Try API v2 list_product
            products = await self._get_products_v2()
            if products:
                logger.info("✅ Got REAL-TIME stock from API v2")
                return self._parse_products_v2(products)
            
            logger.error("❌ Both API methods failed")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting REAL-TIME stock: {e}")
            return None
    
    async def _get_products_v2(self):
        """Get products from API v2"""
        try:
            url = f"{self.base_url}/list_product"
            params = {"api_key": self.api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        logger.error(f"❌ API v2 returned status {response.status}")
                        return None
        except asyncio.TimeoutError:
            logger.error("❌ API v2 timeout")
            return None
        except Exception as e:
            logger.error(f"❌ Error in _get_products_v2: {e}")
            return None
    
    async def _get_stock_v3(self):
        """Get stock from API v3"""
        try:
            url = self.stock_url
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        logger.error(f"❌ API v3 returned status {response.status}")
                        return None
        except asyncio.TimeoutError:
            logger.error("❌ API v3 timeout")
            return None
        except Exception as e:
            logger.error(f"❌ Error in _get_stock_v3: {e}")
            return None
    
    def _parse_products_v2(self, products_data):
        """Parse products from API v2 response"""
        try:
            stock_info = {}
            
            if isinstance(products_data, list):
                for product in products_data:
                    if isinstance(product, dict):
                        code = product.get('code', '').strip()
                        name = product.get('name', '')
                        price = product.get('price', 0)
                        status = product.get('status', '').lower()
                        category = product.get('category', 'Umum')
                        
                        # REAL-TIME status dari provider
                        if status == 'active':
                            stock = "Tersedia"
                            stock_emoji = "🟢"
                        elif status == 'empty':
                            stock = "Habis"
                            stock_emoji = "🔴"
                        elif status == 'problem':
                            stock = "Gangguan"
                            stock_emoji = "🚧"
                        elif status == 'inactive':
                            stock = "Nonaktif"
                            stock_emoji = "⚫"
                        else:
                            stock = "Unknown"
                            stock_emoji = "⚫"
                        
                        stock_info[code] = {
                            'name': name,
                            'price': price,
                            'stock_text': stock,
                            'stock_emoji': stock_emoji,
                            'category': category,
                            'status': status,
                            'real_time': True
                        }
            
            logger.info(f"📊 Parsed {len(stock_info)} products from API v2 (REAL-TIME)")
            return stock_info
            
        except Exception as e:
            logger.error(f"❌ Error parsing products v2: {e}")
            return {}
    
    def _parse_stock_v3(self, stock_data):
        """Parse stock from API v3 response"""
        try:
            stock_info = {}
            
            # Handle different possible formats from API v3
            if isinstance(stock_data, dict):
                # Jika format: {'product_code': {'name': '...', 'stock': 100, ...}}
                for code, product_info in stock_data.items():
                    if isinstance(product_info, dict):
                        stock = product_info.get('stock', 0)
                        stock_info[code] = {
                            'name': product_info.get('name', code),
                            'price': product_info.get('price', 0),
                            'stock': stock,
                            'stock_text': self._get_stock_status_text(stock),
                            'stock_emoji': self._get_stock_status_emoji(stock),
                            'category': product_info.get('category', 'Umum'),
                            'status': 'active' if stock > 0 else 'empty',
                            'real_time': True
                        }
                
                # Jika format: {'data': [{'code': '...', 'name': '...', ...}]}
                if 'data' in stock_data and isinstance(stock_data['data'], list):
                    for product in stock_data['data']:
                        code = product.get('code', '')
                        if code:
                            stock = product.get('stock', 0)
                            stock_info[code] = {
                                'name': product.get('name', code),
                                'price': product.get('price', 0),
                                'stock': stock,
                                'stock_text': self._get_stock_status_text(stock),
                                'stock_emoji': self._get_stock_status_emoji(stock),
                                'category': product.get('category', 'Umum'),
                                'status': 'active' if stock > 0 else 'empty',
                                'real_time': True
                            }
            
            elif isinstance(stock_data, list):
                # Jika format: [{'code': '...', 'name': '...', ...}]
                for product in stock_data:
                    if isinstance(product, dict):
                        code = product.get('code', '')
                        if code:
                            stock = product.get('stock', 0)
                            stock_info[code] = {
                                'name': product.get('name', code),
                                'price': product.get('price', 0),
                                'stock': stock,
                                'stock_text': self._get_stock_status_text(stock),
                                'stock_emoji': self._get_stock_status_emoji(stock),
                                'category': product.get('category', 'Umum'),
                                'status': 'active' if stock > 0 else 'empty',
                                'real_time': True
                            }
            
            logger.info(f"📊 Parsed {len(stock_info)} products from API v3 (REAL-TIME)")
            return stock_info
            
        except Exception as e:
            logger.error(f"❌ Error parsing stock v3: {e}")
            return {}
    
    def _get_stock_status_emoji(self, stock):
        """Convert stock number to status emoji"""
        if isinstance(stock, str):
            return "⚫"
        elif stock > 20:
            return "🟢"
        elif stock > 10:
            return "🟢"
        elif stock > 5:
            return "🟡"
        elif stock > 0:
            return "🟡"
        else:
            return "🔴"
    
    def _get_stock_status_text(self, stock):
        """Convert stock number to status text"""
        if isinstance(stock, str):
            return stock
        elif stock > 20:
            return "Tersedia"
        elif stock > 10:
            return "Tersedia"
        elif stock > 5:
            return "Sedikit"
        elif stock > 0:
            return "Menipis"
        else:
            return "Habis"

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
            await show_error_message(update, "API key tidak ditemukan di config")
            return
        
        stock_api = KhfyPayStockAPI(api_key)
        real_time_stock = await stock_api.get_real_time_stock()
        
        if not real_time_stock:
            await show_error_message(update, "Gagal mengambil data stok dari provider")
            return
        
        # Categorize products
        categorized_products = categorize_products(real_time_stock)
        
        if not categorized_products:
            await show_no_products_message(update)
            return
        
        # Format message dengan data REAL-TIME
        message = format_stock_message(categorized_products, real_time_stock)
        
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
        await show_error_message(update, f"Error: {str(e)}")

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /stock dengan data REAL-TIME"""
    try:
        # Get quick REAL-TIME stats
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            await update.message.reply_text("❌ API key tidak ditemukan")
            return
        
        stock_api = KhfyPayStockAPI(api_key)
        real_time_stock = await stock_api.get_real_time_stock()
        
        if real_time_stock:
            total_products = len(real_time_stock)
            available_products = sum(1 for p in real_time_stock.values() 
                                   if p.get('status') == 'active' or p.get('stock', 0) > 0)
        else:
            total_products = 0
            available_products = 0
        
        message = (
            "📊 **STOK PRODUK REAL-TIME**\n\n"
            f"🔄 **Data langsung dari provider**\n"
            f"📦 Total produk: **{total_products}**\n"
            f"✅ Tersedia: **{available_products}**\n"
            f"⏰ Update: **{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}**\n\n"
            "✨ **Fitur REAL-TIME:**\n"
            "• 📡 Data langsung dari server provider\n"
            "• ⚡ Update real-time setiap akses\n"
            "• 🚀 Tidak melalui cache/database\n"
            "• 💯 Akurat dan ter-update\n\n"
            "Klik tombol di bawah untuk melihat detail stok:"
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

# ==================== UTILITY FUNCTIONS ====================

def categorize_products(real_time_stock):
    """Categorize products from REAL-TIME data"""
    try:
        categorized = {}
        
        for product_code, product_info in real_time_stock.items():
            category = product_info.get('category', 'Umum')
            
            if category not in categorized:
                categorized[category] = []
            
            categorized[category].append({
                'code': product_code,
                'name': product_info['name'],
                'price': product_info['price'],
                'stock_text': product_info.get('stock_text', 'Unknown'),
                'stock_emoji': product_info.get('stock_emoji', '⚫'),
                'status': product_info.get('status', 'unknown')
            })
        
        return categorized
        
    except Exception as e:
        logger.error(f"❌ Error in categorize_products: {e}")
        return {}

def format_stock_message(categorized_products, real_time_stock):
    """Format stock message dengan data REAL-TIME"""
    try:
        message = "📊 **STOK PRODUK REAL-TIME**\n\n"
        message += f"🔄 **Update:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        message += f"📡 **Sumber:** Data langsung dari provider\n\n"
        
        total_products = len(real_time_stock)
        available_products = sum(1 for p in real_time_stock.values() 
                               if p.get('status') == 'active' or p.get('stock', 0) > 0)
        
        for category, products in categorized_products.items():
            message += f"**{category.upper()}:**\n"
            
            category_count = len(products)
            category_available = sum(1 for p in products 
                                   if p['status'] == 'active' or 'stock_text' in p and 'Habis' not in p['stock_text'])
            
            for product in products:
                message += f"{product['stock_emoji']} {product['name']} - Rp {product['price']:,.0f} | {product['stock_text']}\n"
            
            message += f"*Tersedia: {category_available}/{category_count} produk*\n\n"
        
        # Summary
        message += f"**📈 SUMMARY REAL-TIME:**\n"
        message += f"• Total Produk: {total_products}\n"
        message += f"• Tersedia: {available_products}\n"
        message += f"• Habis: {total_products - available_products}\n"
        message += f"• Sumber: 📡 KhfyPay API\n"
        
        return message
        
    except Exception as e:
        logger.error(f"❌ Error in format_stock_message: {e}")
        return "❌ Error formatting stock message"

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
            "Tidak ada produk yang tersedia saat ini.\n"
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
        real_time_stock = await stock_api.get_real_time_stock()
        
        if real_time_stock and product_code in real_time_stock:
            product_info = real_time_stock[product_code]
            return {
                'name': product_info['name'],
                'price': product_info['price'],
                'stock': product_info.get('stock', 0),
                'stock_text': product_info.get('stock_text', 'Unknown'),
                'stock_emoji': product_info.get('stock_emoji', '⚫'),
                'status': product_info.get('status', 'unknown'),
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
                real_time_stock = await stock_api.get_real_time_stock()
                if real_time_stock:
                    logger.info(f"🔍 Background stock check: {len(real_time_stock)} products available")
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
