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
        """Get real-time stock from KhfyPay API dengan quantity"""
        try:
            logger.info("🔄 Fetching REAL-TIME stock with quantities from KhfyPay...")
            
            products = await self._get_products_v2()
            if products:
                logger.info(f"✅ Successfully got {len(products)} products from API v2")
                return products
            else:
                logger.warning("⚠️ API v2 failed")
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
                async with session.get(url, params=params, timeout=20) as response:
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, list):
                            return data
                        elif isinstance(data, dict) and 'data' in data:
                            return data['data']
                    return None
        except Exception as e:
            logger.error(f"❌ Error in _get_products_v2: {e}")
            return None

# ==================== STOCK PROCESSING ====================

def process_real_time_stock(products_data):
    """Process real-time stock data dengan quantity"""
    try:
        if not products_data or not isinstance(products_data, list):
            return {}
        
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
            
            # Cari field yang mengandung informasi stok/quantity
            # Beberapa provider mungkin menggunakan field berbeda untuk stok
            stock_quantity = find_stock_quantity(product)
            
            # Skip jika code kosong
            if not code:
                continue
            
            # Convert price to integer
            try:
                price = int(price)
            except (ValueError, TypeError):
                price = 0
            
            # Determine stock status dan quantity text
            if kosong == 1:
                stock_text = "STOK: 0"
                stock_emoji = "🔴"
                is_available = False
                status = "empty"
                stock_number = 0
            elif gangguan == 1:
                stock_text = "GANGGUAN"
                stock_emoji = "🚧"
                is_available = False
                status = "problem"
                stock_number = 0
            else:
                # Jika ada quantity, tampilkan jumlah stok
                if stock_quantity > 0:
                    stock_text = f"STOK: {stock_quantity}"
                    stock_emoji = "🟢"
                    is_available = True
                    status = "active"
                    stock_number = stock_quantity
                else:
                    # Default untuk produk tersedia tanpa quantity
                    stock_text = "TERSEDIA"
                    stock_emoji = "🟢"
                    is_available = True
                    status = "active"
                    stock_number = 100  # Default quantity untuk produk tersedia
            
            # Tentukan kategori dengan grouping yang lebih spesifik
            category = determine_detailed_category(code, name, provider)
            
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
                'stock_quantity': stock_number,
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
                'provider': provider,
                'stock_quantity': stock_number
            })
        
        # Sort setiap kategori berdasarkan nama produk
        for category in categorized_products:
            categorized_products[category].sort(key=lambda x: x['name'])
        
        logger.info(f"📊 Processed {len(stock_info)} products with quantities")
        return {
            'stock_info': stock_info,
            'categorized_products': categorized_products,
            'total_products': len(stock_info),
            'available_products': sum(1 for p in stock_info.values() if p['is_available']),
            'total_stock': sum(p['stock_quantity'] for p in stock_info.values() if p['is_available'])
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing stock data: {e}")
        return {}

def find_stock_quantity(product):
    """Cari field yang mengandung informasi quantity/stok"""
    # Coba berbagai kemungkinan field untuk stok
    possible_stock_fields = [
        'stok', 'stock', 'quantity', 'qty', 'jumlah', 'sisa',
        'available', 'tersedia', 'kuantitas'
    ]
    
    for field in possible_stock_fields:
        if field in product and product[field] is not None:
            try:
                return int(product[field])
            except (ValueError, TypeError):
                continue
    
    # Jika tidak ada field stok, coba infer dari status
    gangguan = product.get('gangguan', 0)
    kosong = product.get('kosong', 0)
    
    if kosong == 1:
        return 0
    elif gangguan == 1:
        return 0
    else:
        # Untuk produk aktif tanpa quantity, return default
        return 100  # Default quantity

def determine_detailed_category(code, name, provider):
    """Determine category dengan grouping yang lebih detail"""
    code_upper = code.upper()
    name_upper = name.upper()
    
    # Grouping berdasarkan jenis produk yang spesifik
    if 'BONUS AKRAB L' in name_upper or 'BPAL' in code_upper:
        return "BONUS AKRAB L"
    elif 'BONUS AKRAB XL' in name_upper or 'BPAXL' in code_upper:
        return "BONUS AKRAB XL" 
    elif 'BONUS AKRAB XXL' in name_upper or 'BPAXXL' in code_upper:
        return "BONUS AKRAB XXL"
    elif 'FLEXMAX' in name_upper:
        return "FLEXMAX"
    elif 'REGULER' in name_upper or 'GB REGULER' in name_upper:
        return "PAKET REGULER"
    elif 'SUPERMINI' in name_upper:
        return "XL SUPERMINI"
    elif 'MINI' in name_upper and 'SUPERMINI' not in name_upper:
        return "XL MINI"
    elif 'BIG' in name_upper:
        return "XL BIG"
    elif 'JUMBO' in name_upper:
        return "XL JUMBO"
    elif 'MEGABIG' in name_upper:
        return "XL MEGABIG"
    elif code_upper.startswith('XLA'):
        return "XL AKSES"
    elif code_upper.startswith('XLB'):
        return "XL BASIC"
    elif 'AXIS' in name_upper or code_upper.startswith('AXIS'):
        return "AXIS"
    elif 'TELKOMSEL' in name_upper or 'TSEL' in code_upper:
        return "TELKOMSEL"
    elif 'INDOSAT' in name_upper or 'IM' in code_upper:
        return "INDOSAT"
    elif 'SMARTFREN' in name_upper:
        return "SMARTFREN"
    elif 'THREE' in name_upper or '3' in code_upper:
        return "THREE"
    else:
        return "LAINNYA"

# ==================== TELEGRAM STOCK HANDLERS ====================

async def stock_akrab_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk cek stok produk dengan quantity real-time"""
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
        
        # Format message dengan quantity
        message = format_stock_with_quantity_message(processed_data)
        
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

# ==================== QUANTITY STOCK MESSAGE FORMATTING ====================

def format_stock_with_quantity_message(processed_data):
    """Format stock message dengan quantity real-time"""
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
            "BONUS AKRAB L", "BONUS AKRAB XL", "BONUS AKRAB XXL",
            "FLEXMAX", "PAKET REGULER", 
            "XL SUPERMINI", "XL MINI", "XL BIG", "XL JUMBO", "XL MEGABIG",
            "XL AKSES", "XL BASIC",
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
            
            # Tampilkan produk dengan quantity
            for product in products:
                if product['is_available']:
                    # Format: 🟢 Nama Produk - Rp 10.000 | STOK: 15
                    message += f"{product['stock_emoji']} {product['name']} - Rp {product['price']:,} | {product['stock_text']}\n"
                else:
                    # Format: 🔴 Nama Produk - Rp 10.000 | STOK: 0
                    message += f"{product['stock_emoji']} {product['name']} - Rp {product['price']:,} | {product['stock_text']}\n"
            
            # Summary per kategori dengan total stok
            if category_available > 0:
                message += f"*📦 Total Stok: {category_total_stock} | Tersedia: {category_available}/{category_count} produk*\n\n"
            else:
                message += f"*❌ Stok Habis: {category_available}/{category_count} produk*\n\n"
        
        # Overall Summary dengan total stok
        message += f"**📈 SUMMARY REAL-TIME:**\n"
        message += f"• Total Produk: `{total_products}`\n"
        message += f"• Produk Tersedia: `{available_products}`\n"
        message += f"• Total Stok: `{total_stock}`\n"
        message += f"• Produk Gangguan: `{total_products - available_products}`\n"
        message += f"• Status: ✅ LIVE\n"
        
        return message
        
    except Exception as e:
        logger.error(f"❌ Error in format_stock_with_quantity_message: {e}")
        return "❌ Error formatting stock message"

def format_compact_quantity_message(processed_data):
    """Format compact untuk kategori dengan banyak produk"""
    try:
        categorized_products = processed_data['categorized_products']
        total_products = processed_data['total_products']
        available_products = processed_data['available_products']
        total_stock = processed_data['total_stock']
        
        message = "📊 **STOK PRODUK REAL-TIME**\n\n"
        message += "✅ **DATA REAL-TIME DARI PROVIDER**\n"
        message += f"🔄 Update: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
        
        category_priority = [
            "BONUS AKRAB L", "BONUS AKRAB XL", "BONUS AKRAB XXL",
            "FLEXMAX", "PAKET REGULER", 
            "XL SUPERMINI", "XL MINI", "XL BIG", "XL JUMBO", "XL MEGABIG",
            "XL AKSES", "XL BASIC",
            "AXIS", "TELKOMSEL", "INDOSAT", "SMARTFREN", "THREE", "LAINNYA"
        ]
        
        existing_categories = [cat for cat in category_priority if cat in categorized_products]
        
        for category in existing_categories:
            products = categorized_products[category]
            category_count = len(products)
            category_available = sum(1 for p in products if p['is_available'])
            category_total_stock = sum(p['stock_quantity'] for p in products if p['is_available'])
            
            # Untuk kategori dengan banyak produk, tampilkan summary saja
            if category_count > 6:
                if category_available > 0:
                    message += f"**{category}:** {category_available}/{category_count} produk | Total Stok: {category_total_stock}\n"
                else:
                    message += f"**{category}:** ❌ {category_available}/{category_count} produk\n"
            else:
                message += f"**{category}:**\n"
                for product in products:
                    message += f"{product['stock_emoji']} {product['name']} - Rp {product['price']:,} | {product['stock_text']}\n"
                if category_available > 0:
                    message += f"*Total Stok: {category_total_stock} | {category_available}/{category_count} produk*\n\n"
                else:
                    message += f"*{category_available}/{category_count} produk*\n\n"
        
        message += f"\n**📈 SUMMARY:** Produk: {total_products} | Tersedia: {available_products} | Total Stok: {total_stock}\n"
        message += f"• Status: ✅ LIVE\n"
        
        return message
        
    except Exception as e:
        logger.error(f"❌ Error in format_compact_quantity_message: {e}")
        return format_stock_with_quantity_message(processed_data)

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
    """Background task untuk monitoring stok"""
    while True:
        try:
            await asyncio.sleep(300)
            api_key = getattr(config, 'KHFYPAY_API_KEY', '')
            if api_key:
                stock_api = KhfyPayStockAPI(api_key)
                real_time_data = await stock_api.get_real_time_stock()
                if real_time_data:
                    processed = process_real_time_stock(real_time_data)
                    if processed:
                        logger.info(f"🔍 Background stock: {processed['total_products']} produk, {processed['available_products']} tersedia, {processed['total_stock']} total stok")
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
