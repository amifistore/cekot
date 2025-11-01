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
        self.stock_url = "https://panel.khfy-store.com/api_v3/cek_stock_akrab"
    
    async def get_real_time_stock(self):
        """Get real-time stock from KhfyPay API - REAL DATA dari provider"""
        try:
            logger.info("🔄 Fetching REAL-TIME stock from KhfyPay...")
            
            # Priority 1: Try to get stock from API v3 (stock endpoint)
            stock_data = await self._get_stock_v3()
            if stock_data:
                logger.info("✅ Got REAL stock data from API v3")
                return self._parse_stock_data(stock_data)
            
            # Priority 2: Fallback to API v2 (products endpoint)
            products = await self._get_products_v2()
            if products:
                logger.info("✅ Got products data from API v2")
                return self._parse_products_data(products)
            
            logger.error("❌ Both API methods failed")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting REAL-TIME stock: {e}")
            return None
    
    async def _get_stock_v3(self):
        """Get stock data from API v3 - khusus cek stok"""
        try:
            logger.info(f"🔍 Calling Stock API: {self.stock_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.stock_url, timeout=15) as response:
                    logger.info(f"🔍 Stock API Response Status: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"🔍 Stock API Response type: {type(data)}")
                        
                        # Debug log
                        if isinstance(data, dict):
                            logger.info(f"🔍 Stock API Keys: {list(data.keys())}")
                        elif isinstance(data, list):
                            logger.info(f"🔍 Stock API List length: {len(data)}")
                        
                        return data
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Stock API Error: {response.status} - {error_text}")
                        return None
        except Exception as e:
            logger.error(f"❌ Error in _get_stock_v3: {e}")
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
                    return None
        except Exception as e:
            logger.error(f"❌ Error in _get_products_v2: {e}")
            return None
    
    def _parse_stock_data(self, stock_data):
        """Parse stock data dari API v3 format"""
        try:
            products = []
            
            if isinstance(stock_data, dict):
                # Format: {'XLA14': 'SuperMini | 0 unit', 'XLA32': 'Mini | 0 unit', ...}
                for code, info in stock_data.items():
                    if isinstance(info, str):
                        # Parse "SuperMini | 0 unit"
                        parts = info.split('|')
                        name = parts[0].strip() if len(parts) > 0 else code
                        stock_text = parts[1].strip() if len(parts) > 1 else "0 unit"
                        
                        # Extract stock quantity
                        stock_quantity = self._extract_stock_quantity(stock_text)
                        
                        products.append({
                            'kode_produk': code,
                            'nama_produk': name,
                            'stock_text': stock_text,
                            'stock_quantity': stock_quantity,
                            'status': 'active' if stock_quantity > 0 else 'empty'
                        })
            
            elif isinstance(stock_data, list):
                # Format: [{'code': 'XLA14', 'name': 'SuperMini', 'stock': 0}, ...]
                for item in stock_data:
                    if isinstance(item, dict):
                        code = item.get('code', '')
                        name = item.get('name', '')
                        stock = item.get('stock', 0)
                        
                        products.append({
                            'kode_produk': code,
                            'nama_produk': name,
                            'stock_text': f"{stock} unit",
                            'stock_quantity': stock,
                            'status': 'active' if stock > 0 else 'empty'
                        })
            
            logger.info(f"📊 Parsed {len(products)} products from stock API")
            return products
            
        except Exception as e:
            logger.error(f"❌ Error parsing stock data: {e}")
            return []
    
    def _parse_products_data(self, products_data):
        """Parse products data dari API v2"""
        try:
            products = []
            
            if isinstance(products_data, list):
                for product in products_data:
                    if isinstance(product, dict):
                        code = product.get('kode_produk', '').strip()
                        name = product.get('nama_produk', 'Unknown Product')
                        gangguan = product.get('gangguan', 0)
                        kosong = product.get('kosong', 0)
                        
                        # Determine stock status from gangguan/kosong fields
                        if kosong == 1:
                            stock_quantity = 0
                            status = 'empty'
                        elif gangguan == 1:
                            stock_quantity = 0
                            status = 'problem'
                        else:
                            # For active products without quantity, show as available
                            stock_quantity = 1  # Default for available products
                            status = 'active'
                        
                        products.append({
                            'kode_produk': code,
                            'nama_produk': name,
                            'stock_text': f"{stock_quantity} unit",
                            'stock_quantity': stock_quantity,
                            'status': status
                        })
            
            logger.info(f"📊 Parsed {len(products)} products from products API")
            return products
            
        except Exception as e:
            logger.error(f"❌ Error parsing products data: {e}")
            return []
    
    def _extract_stock_quantity(self, stock_text):
        """Extract stock quantity from text like '0 unit'"""
        try:
            # Remove non-digit characters and convert to int
            import re
            numbers = re.findall(r'\d+', stock_text)
            if numbers:
                return int(numbers[0])
            return 0
        except:
            return 0

# ==================== STOCK PROCESSING ====================

def process_real_time_stock(products_data):
    """Process REAL-TIME stock data langsung dari provider"""
    try:
        if not products_data or not isinstance(products_data, list):
            logger.error("❌ No real products data received")
            return {}
        
        stock_info = {}
        categorized_products = {}
        
        for product in products_data:
            if not isinstance(product, dict):
                continue
                
            # Gunakan field REAL dari API response
            code = product.get('kode_produk', '').strip()
            name = product.get('nama_produk', 'Unknown Product')
            stock_quantity = product.get('stock_quantity', 0)
            stock_text = product.get('stock_text', '0 unit')
            status = product.get('status', 'empty')
            
            # Skip jika code kosong
            if not code:
                continue
            
            # Determine stock status dan emoji
            if status == 'empty' or stock_quantity == 0:
                stock_display = "STOK: 0"
                stock_emoji = "🔴"
                is_available = False
            elif status == 'problem':
                stock_display = "GANGGUAN"
                stock_emoji = "🚧"
                is_available = False
            else:
                stock_display = f"STOK: {stock_quantity}"
                stock_emoji = "🟢"
                is_available = True
            
            # Tentukan kategori berdasarkan kode produk
            category = determine_category_from_code(code, name)
            
            # Simpan info produk
            stock_info[code] = {
                'name': name,
                'stock_display': stock_display,
                'stock_emoji': stock_emoji,
                'category': category,
                'status': status,
                'is_available': is_available,
                'stock_quantity': stock_quantity,
                'real_time': True
            }
            
            # Kategorikan produk
            if category not in categorized_products:
                categorized_products[category] = []
            
            categorized_products[category].append({
                'code': code,
                'name': name,
                'stock_display': stock_display,
                'stock_emoji': stock_emoji,
                'status': status,
                'is_available': is_available,
                'stock_quantity': stock_quantity
            })
        
        # Sort setiap kategori berdasarkan nama produk
        for category in categorized_products:
            categorized_products[category].sort(key=lambda x: x['name'])
        
        logger.info(f"📊 Processed {len(stock_info)} REAL products into {len(categorized_products)} categories")
        
        # Calculate totals
        total_products = len(stock_info)
        available_products = sum(1 for p in stock_info.values() if p['is_available'])
        total_stock = sum(p['stock_quantity'] for p in stock_info.values() if p['is_available'])
        
        return {
            'stock_info': stock_info,
            'categorized_products': categorized_products,
            'total_products': total_products,
            'available_products': available_products,
            'total_stock': total_stock
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing REAL stock data: {e}")
        return {}

def determine_category_from_code(code, name):
    """Determine category berdasarkan kode produk seperti contoh"""
    code_upper = code.upper()
    
    # Kategori berdasarkan prefix kode produk (sesuai contoh)
    if code_upper.startswith('XLA'):
        if 'SUPERMINI' in name.upper():
            return "XL SUPERMINI"
        elif 'MINI' in name.upper():
            return "XL MINI"
        elif 'BIG' in name.upper():
            return "XL BIG"
        elif 'JUMBO' in name.upper():
            return "XL JUMBO"
        elif 'MEGABIG' in name.upper():
            return "XL MEGABIG"
        else:
            return "XL AKSES"
    
    elif code_upper.startswith('XLB'):
        return "XL BASIC"
    
    elif code_upper.startswith('XDA'):
        return "PAKET REGULER"
    
    elif code_upper.startswith('AXIS'):
        return "AXIS"
    
    elif code_upper.startswith('TSEL'):
        return "TELKOMSEL"
    
    elif code_upper.startswith('INDOSAT') or code_upper.startswith('IM'):
        return "INDOSAT"
    
    elif code_upper.startswith('SF'):
        return "SMARTFREN"
    
    elif code_upper.startswith('THREE') or code_upper.startswith('3'):
        return "THREE"
    
    else:
        return "LAINNYA"

# ==================== TELEGRAM STOCK HANDLERS ====================

async def stock_akrab_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk cek stok produk dengan data REAL-TIME dari provider"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Show processing message
        await query.edit_message_text(
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
            await show_error_message(update, "❌ Gagal mengambil data stok REAL dari provider")
            return
        
        # Process the real-time data
        processed_data = process_real_time_stock(real_time_data)
        
        if not processed_data or not processed_data['categorized_products']:
            await show_no_products_message(update)
            return
        
        # Format message dengan data REAL
        message = format_real_stock_message(processed_data)
        
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
    """Handler untuk command /stock"""
    try:
        # Get REAL-TIME stock directly from provider
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            await update.message.reply_text("❌ API key tidak ditemukan")
            return
        
        stock_api = KhfyPayStockAPI(api_key)
        real_time_data = await stock_api.get_real_time_stock()
        
        if not real_time_data:
            await update.message.reply_text("❌ Gagal mengambil data stok REAL-TIME dari provider")
            return
        
        # Process the real-time data
        processed_data = process_real_time_stock(real_time_data)
        
        if processed_data:
            total_products = processed_data['total_products']
            available_products = processed_data['available_products']
            total_stock = processed_data['total_stock']
            
            message = (
                "📊 **STOK PRODUK REAL-TIME**\n\n"
                f"✅ **Data REAL dari provider**\n"
                f"📦 Total produk: **{total_products}**\n"
                f"✅ Produk tersedia: **{available_products}**\n"
                f"📊 Total stok: **{total_stock}**\n"
                f"⏰ Update: **{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}**\n\n"
                "Klik tombol di bawah untuk melihat detail stok:"
            )
        else:
            message = (
                "📊 **STOK PRODUK REAL-TIME**\n\n"
                "❌ Gagal memproses data stok\n\n"
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
            "❌ Gagal memuat data stok REAL-TIME.\nSilakan coba lagi nanti."
        )

# ==================== REAL STOCK MESSAGE FORMATTING ====================

def format_real_stock_message(processed_data):
    """Format stock message dengan data REAL dari provider"""
    try:
        categorized_products = processed_data['categorized_products']
        total_products = processed_data['total_products']
        available_products = processed_data['available_products']
        total_stock = processed_data['total_stock']
        
        message = "📊 **STOK PRODUK REAL-TIME**\n\n"
        message += "✅ **DATA REAL-TIME DARI PROVIDER**\n"
        message += f"🔄 Update: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
        
        # Urutkan kategori berdasarkan prioritas tampilan
        category_priority = [
            "XL SUPERMINI", "XL MINI", "XL BIG", "XL JUMBO", "XL MEGABIG",
            "XL AKSES", "XL BASIC",
            "PAKET REGULER",
            "AXIS", "TELKOMSEL", "INDOSAT", "SMARTFREN", "THREE", "LAINNYA"
        ]
        
        # Filter hanya kategori yang ada produknya
        existing_categories = [cat for cat in category_priority if cat in categorized_products]
        
        for category in existing_categories:
            products = categorized_products[category]
            category_count = len(products)
            category_available = sum(1 for p in products if p['is_available'])
            category_total_stock = sum(p['stock_quantity'] for p in products if p['is_available'])
            
            # Header kategori
            message += f"**{category.upper()}:**\n"
            
            # Tampilkan produk dengan stok REAL
            for product in products:
                # Format: 🟢 SuperMini - STOK: 3
                message += f"{product['stock_emoji']} {product['name']} - {product['stock_display']}\n"
            
            # Summary per kategori dengan total stok REAL
            if category_available > 0:
                message += f"📦 Total Stok: {category_total_stock} | Tersedia: {category_available}/{category_count} produk\n\n"
            else:
                message += f"❌ Stok Habis: {category_available}/{category_count} produk\n\n"
        
        # Overall Summary dengan total stok REAL
        message += f"**📈 SUMMARY REAL-TIME:**\n"
        message += f"• Total Produk: {total_products}\n"
        message += f"• Produk Tersedia: {available_products}\n"
        message += f"• Total Stok: {total_stock}\n"
        message += f"• Produk Gangguan: {total_products - available_products}\n"
        message += f"• Status: ✅ LIVE\n"
        
        return message
        
    except Exception as e:
        logger.error(f"❌ Error in format_real_stock_message: {e}")
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

# ==================== BACKGROUND STOCK SYNC ====================

async def background_stock_sync():
    """Background task untuk monitoring stok REAL"""
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
                        logger.info(f"🔍 REAL Background stock: {processed['total_products']} produk, {processed['available_products']} tersedia, {processed['total_stock']} total stok")
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
