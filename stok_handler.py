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
        """Get real-time stock from KhfyPay API"""
        try:
            logger.info("🔄 Fetching REAL-TIME stock from KhfyPay...")
            
            # Coba API v2 terlebih dahulu
            products = await self._get_products_v2()
            if products:
                logger.info(f"✅ Successfully got {len(products)} products from API v2")
                return products
            else:
                logger.warning("⚠️ API v2 failed, trying fallback...")
                return None
            
        except Exception as e:
            logger.error(f"❌ Error getting REAL-TIME stock: {e}")
            return None
    
    async def _get_products_v2(self):
        """Get products from API v2 dengan error handling yang lebih baik"""
        try:
            url = f"{self.base_url}/list_product"
            params = {"api_key": self.api_key}
            
            logger.info(f"🔍 Calling API v2: {url}")
            logger.info(f"🔍 API Key: {self.api_key[:8]}...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=20) as response:
                    logger.info(f"🔍 API v2 HTTP Status: {response.status}")
                    
                    # Handle different status codes
                    if response.status == 200:
                        content_type = response.headers.get('content-type', '')
                        logger.info(f"🔍 Content-Type: {content_type}")
                        
                        # Try to parse as JSON
                        try:
                            data = await response.json()
                            logger.info(f"🔍 JSON Response type: {type(data)}")
                            
                            if isinstance(data, list):
                                logger.info(f"✅ API v2 returned list with {len(data)} items")
                                if len(data) > 0:
                                    first_item = data[0]
                                    logger.info(f"🔍 First item type: {type(first_item)}")
                                    if isinstance(first_item, dict):
                                        logger.info(f"🔍 First item keys: {list(first_item.keys())}")
                                return data
                            elif isinstance(data, dict):
                                logger.info(f"🔍 API returned dict with keys: {list(data.keys())}")
                                # Check if there's a data key
                                if 'data' in data and isinstance(data['data'], list):
                                    logger.info(f"✅ Found 'data' key with {len(data['data'])} items")
                                    return data['data']
                                else:
                                    logger.error("❌ Unexpected dict structure")
                                    return None
                            else:
                                logger.error(f"❌ Unexpected response type: {type(data)}")
                                return None
                                
                        except json.JSONDecodeError as e:
                            logger.error(f"❌ JSON decode error: {e}")
                            # Try to read as text
                            text_response = await response.text()
                            logger.error(f"❌ Raw response: {text_response[:500]}...")
                            return None
                            
                    elif response.status == 401:
                        logger.error("❌ API v2: Unauthorized (invalid API key)")
                        return None
                    elif response.status == 403:
                        logger.error("❌ API v2: Forbidden")
                        return None
                    elif response.status == 404:
                        logger.error("❌ API v2: Not Found")
                        return None
                    elif response.status == 500:
                        logger.error("❌ API v2: Server Error")
                        return None
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ API v2 returned status {response.status}: {error_text[:200]}...")
                        return None
                        
        except asyncio.TimeoutError:
            logger.error("❌ API v2: Request timeout")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"❌ API v2: Client error - {e}")
            return None
        except Exception as e:
            logger.error(f"❌ API v2: Unexpected error - {e}")
            return None

# ==================== FALLBACK STOCK DATA ====================

def get_fallback_stock_data():
    """Fallback data ketika API tidak tersedia"""
    fallback_products = [
        {
            'kode_produk': 'XLA5',
            'nama_produk': 'XL 5GB - 1 Hari',
            'harga_final': 5000,
            'gangguan': 0,
            'kosong': 0,
            'kode_provider': 'REG'
        },
        {
            'kode_produk': 'XLA10', 
            'nama_produk': 'XL 10GB - 3 Hari',
            'harga_final': 10000,
            'gangguan': 0,
            'kosong': 0,
            'kode_provider': 'REG'
        },
        {
            'kode_produk': 'XLA25',
            'nama_produk': 'XL 25GB - 7 Hari',
            'harga_final': 25000,
            'gangguan': 1,
            'kosong': 0,
            'kode_provider': 'REG'
        },
        {
            'kode_produk': 'AXIS5',
            'nama_produk': 'AXIS 5GB - 1 Hari',
            'harga_final': 5000,
            'gangguan': 0,
            'kosong': 1,
            'kode_provider': 'REG'
        }
    ]
    return fallback_products

# ==================== STOCK PROCESSING ====================

def process_real_time_stock(products_data):
    """Process real-time stock data dari API"""
    try:
        if not products_data or not isinstance(products_data, list):
            logger.warning("⚠️ No products data, using fallback")
            products_data = get_fallback_stock_data()
        
        stock_info = {}
        categorized_products = {}
        
        for product in products_data:
            if not isinstance(product, dict):
                continue
                
            # Gunakan field yang sesuai dengan response API
            code = product.get('kode_produk', '').strip()
            name = product.get('nama_produk', 'Unknown Product')
            price = product.get('harga_final', 0)
            gangguan = product.get('gangguan', 0)
            kosong = product.get('kosong', 0)
            provider = product.get('kode_provider', 'Unknown')
            
            # Skip jika code kosong
            if not code:
                continue
            
            # Convert price to integer
            try:
                price = int(price)
            except (ValueError, TypeError):
                price = 0
            
            # Determine stock status berdasarkan gangguan dan kosong
            if kosong == 1:
                stock_text = "Habis"
                stock_emoji = "🔴"
                is_available = False
                status = "empty"
            elif gangguan == 1:
                stock_text = "Gangguan"
                stock_emoji = "🚧"
                is_available = False
                status = "problem"
            else:
                stock_text = "Tersedia"
                stock_emoji = "🟢"
                is_available = True
                status = "active"
            
            # Tentukan kategori berdasarkan kode produk
            category = determine_category(code, provider)
            
            # Simpan info produk
            stock_info[code] = {
                'name': name,
                'price': price,
                'stock_text': stock_text,
                'stock_emoji': stock_emoji,
                'category': category,
                'status': status,
                'is_available': is_available,
                'provider': provider,
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
                'is_available': is_available,
                'provider': provider
            })
        
        logger.info(f"📊 Processed {len(stock_info)} products into {len(categorized_products)} categories")
        return {
            'stock_info': stock_info,
            'categorized_products': categorized_products,
            'total_products': len(stock_info),
            'available_products': sum(1 for p in stock_info.values() if p['is_available']),
            'is_fallback': products_data == get_fallback_stock_data()
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing stock data: {e}")
        # Return fallback data jika ada error processing
        return process_real_time_stock(get_fallback_stock_data())

def determine_category(code, provider):
    """Determine category based on product code and provider"""
    code_upper = code.upper()
    
    # Kategori berdasarkan prefix kode produk
    if code_upper.startswith('XLA'):
        return "XL A"
    elif code_upper.startswith('XLB'):
        return "XL B"
    elif code_upper.startswith('AXIS'):
        return "AXIS"
    elif code_upper.startswith('TELKOMSEL') or code_upper.startswith('TSEL'):
        return "TELKOMSEL"
    elif code_upper.startswith('INDOSAT') or code_upper.startswith('IM'):
        return "INDOSAT"
    elif code_upper.startswith('SMARTFREN'):
        return "SMARTFREN"
    elif code_upper.startswith('THREE') or code_upper.startswith('3'):
        return "THREE"
    else:
        # Kategori berdasarkan provider
        provider_map = {
            'KUBER': 'Kuota Berbagi',
            'IM': 'Internet Murah',
            'REG': 'Reguler',
            'PROMO': 'Promo'
        }
        return provider_map.get(provider, 'Umum')

# ==================== TELEGRAM STOCK HANDLERS ====================

async def stock_akrab_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk cek stok produk"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Show processing message
        processing_msg = await query.edit_message_text(
            "🔄 **Mengambil data stok dari provider...**\n\n"
            "⏳ Mohon tunggu sebentar...",
            parse_mode='Markdown'
        )
        
        # Get stock data
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            await show_error_message(update, "❌ API key tidak ditemukan di config")
            return
        
        stock_api = KhfyPayStockAPI(api_key)
        real_time_data = await stock_api.get_real_time_stock()
        
        # Process the data (will use fallback if real_time_data is None)
        processed_data = process_real_time_stock(real_time_data)
        
        if not processed_data or not processed_data['categorized_products']:
            await show_no_products_message(update)
            return
        
        # Format message
        message = format_stock_message(processed_data)
        
        # Create keyboard
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Stok", callback_data="main_menu_stock")],
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
    """Handler untuk command /stock"""
    try:
        # Show processing message
        processing_msg = await update.message.reply_text(
            "🔄 Mengambil data stok...",
            parse_mode='Markdown'
        )
        
        # Get stock data
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            await update.message.reply_text("❌ API key tidak ditemukan")
            return
        
        stock_api = KhfyPayStockAPI(api_key)
        real_time_data = await stock_api.get_real_time_stock()
        
        # Process the data
        processed_data = process_real_time_stock(real_time_data)
        
        if processed_data:
            total_products = processed_data['total_products']
            available_products = processed_data['available_products']
            is_fallback = processed_data.get('is_fallback', False)
            
            status_info = "📡 **Data langsung dari provider**" if not is_fallback else "⚠️ **Data fallback** (API sedang gangguan)"
            
            message = (
                "📊 **STOK PRODUK**\n\n"
                f"{status_info}\n"
                f"📦 Total produk: **{total_products}**\n"
                f"✅ Tersedia: **{available_products}**\n"
                f"❌ Habis/Gangguan: **{total_products - available_products}**\n"
                f"⏰ Update: **{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}**\n\n"
            )
            
            if is_fallback:
                message += "🔧 **Info:** Sedang menggunakan data fallback karena API gangguan\n\n"
            
            message += "Klik tombol di bawah untuk melihat detail stok:"
        else:
            message = (
                "📊 **STOK PRODUK**\n\n"
                "❌ Gagal memuat data stok\n\n"
                "Silakan coba lagi atau hubungi admin."
            )
        
        keyboard = [
            [InlineKeyboardButton("📋 Lihat Detail Stok", callback_data="main_menu_stock")],
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
            "❌ Gagal memuat data stok.\nSilakan coba lagi nanti."
        )

# ==================== MESSAGE FORMATTING ====================

def format_stock_message(processed_data):
    """Format stock message"""
    try:
        categorized_products = processed_data['categorized_products']
        total_products = processed_data['total_products']
        available_products = processed_data['available_products']
        is_fallback = processed_data.get('is_fallback', False)
        
        message = "📊 **STOK PRODUK**\n\n"
        
        if is_fallback:
            message += "⚠️ **DATA FALLBACK** (API gangguan)\n"
        else:
            message += "✅ **DATA REAL-TIME**\n"
            
        message += f"🔄 Update: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
        
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
        message += f"**📈 SUMMARY:**\n"
        message += f"• Total Produk: {total_products}\n"
        message += f"• Tersedia: {available_products}\n"
        message += f"• Habis/Gangguan: {total_products - available_products}\n"
        
        if is_fallback:
            message += f"• Status: ⚠️ FALLBACK MODE\n"
        else:
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
            f"❌ **Gagal memuat data stok**\n\n{error_text}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"❌ Gagal memuat data stok\n\n{error_text}",
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

# ==================== BACKGROUND STOCK SYNC ====================

async def background_stock_sync():
    """Background task untuk monitoring stok"""
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
                        status = "FALLBACK" if processed.get('is_fallback') else "LIVE"
                        logger.info(f"🔍 Background stock check: {processed['total_products']} total, {processed['available_products']} available ({status})")
        except Exception as e:
            logger.error(f"❌ Background stock sync error: {e}")
            await asyncio.sleep(60)

def initialize_stock_sync():
    """Initialize background stock monitoring"""
    try:
        asyncio.create_task(background_stock_sync())
        logger.info("✅ Background stock monitoring initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize background stock monitoring: {e}")

# Import datetime
from datetime import datetime
