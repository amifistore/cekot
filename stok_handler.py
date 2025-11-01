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
    """Process real-time stock data dari API dengan grouping yang lebih baik"""
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
            
            # Skip jika code kosong
            if not code:
                continue
            
            # Convert price to integer
            try:
                price = int(price)
            except (ValueError, TypeError):
                price = 0
            
            # Determine stock status
            if kosong == 1:
                stock_text = "HABIS"
                stock_emoji = "🔴"
                is_available = False
                status = "empty"
            elif gangguan == 1:
                stock_text = "GANGGUAN"
                stock_emoji = "🚧"
                is_available = False
                status = "problem"
            else:
                stock_text = "TERSEDIA"
                stock_emoji = "🟢"
                is_available = True
                status = "active"
            
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
        
        # Sort setiap kategori berdasarkan nama produk
        for category in categorized_products:
            categorized_products[category].sort(key=lambda x: x['name'])
        
        logger.info(f"📊 Processed {len(stock_info)} products into {len(categorized_products)} categories")
        return {
            'stock_info': stock_info,
            'categorized_products': categorized_products,
            'total_products': len(stock_info),
            'available_products': sum(1 for p in stock_info.values() if p['is_available'])
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing stock data: {e}")
        return {}

def determine_detailed_category(code, name, provider):
    """Determine category dengan grouping yang lebih detail dan rapi"""
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
    elif code_upper.startswith('XLA'):
        return "XL AKSES"
    elif code_upper.startswith('XLB'):
        return "XL BASIC"
    elif 'SUPERMINI' in name_upper or 'MINI' in name_upper or 'BIG' in name_upper or 'JUMBO' in name_upper or 'MEGABIG' in name_upper:
        return "XL PAKET SPECIAL"
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
    """Handler untuk cek stok produk dengan tampilan yang rapi"""
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
        
        # Format message dengan tampilan yang rapi
        message = format_clean_stock_message(processed_data)
        
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
                f"✅ **Data langsung dari provider**\n"
                f"📦 Total produk: **{total_products}**\n"
                f"✅ Tersedia: **{available_products}**\n"
                f"❌ Habis/Gangguan: **{total_products - available_products}**\n"
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

# ==================== CLEAN MESSAGE FORMATTING ====================

def format_clean_stock_message(processed_data):
    """Format stock message dengan tampilan yang rapi dan terkelompok"""
    try:
        categorized_products = processed_data['categorized_products']
        total_products = processed_data['total_products']
        available_products = processed_data['available_products']
        
        message = "📊 **STOK PRODUK**\n\n"
        message += "✅ **DATA REAL-TIME**\n"
        message += f"🔄 Update: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
        
        # Urutkan kategori berdasarkan prioritas tampilan
        category_priority = [
            "BONUS AKRAB L", "BONUS AKRAB XL", "BONUS AKRAB XXL",
            "FLEXMAX", "PAKET REGULER", 
            "XL AKSES", "XL BASIC", "XL PAKET SPECIAL",
            "AXIS", "TELKOMSEL", "INDOSAT", "SMARTFREN", "THREE", "LAINNYA"
        ]
        
        # Filter hanya kategori yang ada produknya
        existing_categories = [cat for cat in category_priority if cat in categorized_products]
        
        for category in existing_categories:
            products = categorized_products[category]
            category_count = len(products)
            category_available = sum(1 for p in products if p['is_available'])
            
            # Header kategori
            message += f"**{category}:**\n"
            
            # Tampilkan produk dalam kategori
            for product in products:
                # Format yang rapi: 🟢 Nama Produk - Rp 10.000 | TERSEDIA
                message += f"{product['stock_emoji']} {product['name']} - Rp {product['price']:,} | {product['stock_text']}\n"
            
            # Summary per kategori
            message += f"*Tersedia: {category_available}/{category_count} produk*\n\n"
        
        # Overall Summary
        message += f"**📈 SUMMARY:**\n"
        message += f"• Total Produk: `{total_products}`\n"
        message += f"• Tersedia: `{available_products}`\n"
        message += f"• Habis/Gangguan: `{total_products - available_products}`\n"
        message += f"• Status: ✅ LIVE\n"
        
        return message
        
    except Exception as e:
        logger.error(f"❌ Error in format_clean_stock_message: {e}")
        return "❌ Error formatting stock message"

# ==================== COMPACT MESSAGE FORMATTING ====================

def format_compact_stock_message(processed_data):
    """Format yang lebih compact untuk kategori dengan banyak produk"""
    try:
        categorized_products = processed_data['categorized_products']
        total_products = processed_data['total_products']
        available_products = processed_data['available_products']
        
        message = "📊 **STOK PRODUK**\n\n"
        message += "✅ **DATA REAL-TIME**\n"
        message += f"🔄 Update: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
        
        category_priority = [
            "BONUS AKRAB L", "BONUS AKRAB XL", "BONUS AKRAB XXL",
            "FLEXMAX", "PAKET REGULER", 
            "XL AKSES", "XL BASIC", "XL PAKET SPECIAL",
            "AXIS", "TELKOMSEL", "INDOSAT", "SMARTFREN", "THREE", "LAINNYA"
        ]
        
        existing_categories = [cat for cat in category_priority if cat in categorized_products]
        
        for category in existing_categories:
            products = categorized_products[category]
            category_count = len(products)
            category_available = sum(1 for p in products if p['is_available'])
            
            # Untuk kategori dengan banyak produk, tampilkan summary saja
            if category_count > 8:
                message += f"**{category}:** {category_available}/{category_count} produk tersedia\n"
            else:
                message += f"**{category}:**\n"
                for product in products:
                    message += f"{product['stock_emoji']} {product['name']} - Rp {product['price']:,}\n"
                message += f"*Tersedia: {category_available}/{category_count}*\n\n"
        
        message += f"\n**📈 SUMMARY:** Total: {total_products} | Tersedia: {available_products} | Gangguan: {total_products - available_products}\n"
        message += f"• Status: ✅ LIVE\n"
        
        return message
        
    except Exception as e:
        logger.error(f"❌ Error in format_compact_stock_message: {e}")
        return format_clean_stock_message(processed_data)

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
                        logger.info(f"🔍 Background stock: {processed['total_products']} total, {processed['available_products']} available")
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
