import logging
import requests
import aiohttp
import asyncio
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database
import config

logger = logging.getLogger(__name__)

# ==================== KHFYPAY STOCK API ====================

class KhfyPayStockAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://panel.khfy-store.com/api_v2"
        self.stock_url = "https://panel.khfy-store.com/api_v3/cek_stock_akrab"
    
    async def get_real_time_stock(self):
        """Get real-time stock from KhfyPay API"""
        try:
            logger.info("🔄 Fetching real-time stock from KhfyPay...")
            
            # Method 1: Try API v2 list_product first
            products = await self._get_products_v2()
            if products:
                return self._parse_products_v2(products)
            
            # Method 2: Try API v3 cek_stock_akrab
            stock_data = await self._get_stock_v3()
            if stock_data:
                return self._parse_stock_v3(stock_data)
            
            logger.error("❌ Both API methods failed")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting real-time stock: {e}")
            return None
    
    async def _get_products_v2(self):
        """Get products from API v2"""
        try:
            url = f"{self.base_url}/list_product"
            params = {"api_key": self.api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Got {len(data) if isinstance(data, list) else 'unknown'} products from API v2")
                        return data
                    else:
                        logger.error(f"❌ API v2 returned status {response.status}")
                        return None
        except Exception as e:
            logger.error(f"❌ Error in _get_products_v2: {e}")
            return None
    
    async def _get_stock_v3(self):
        """Get stock from API v3"""
        try:
            url = self.stock_url
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Got stock data from API v3")
                        return data
                    else:
                        logger.error(f"❌ API v3 returned status {response.status}")
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
                        
                        # Determine stock status based on status field
                        if status == 'active':
                            stock = 100
                            stock_status = "🟢 TERSEDIA"
                        elif status == 'empty':
                            stock = 0
                            stock_status = "🔴 HABIS"
                        elif status == 'problem':
                            stock = 0
                            stock_status = "🚧 GANGGUAN"
                        elif status == 'inactive':
                            stock = 0
                            stock_status = "⚫ NONAKTIF"
                        else:
                            stock = 0
                            stock_status = "⚫ UNKNOWN"
                        
                        stock_info[code] = {
                            'name': name,
                            'price': price,
                            'stock': stock,
                            'stock_status': stock_status,
                            'category': category,
                            'status': status
                        }
            
            logger.info(f"📊 Parsed {len(stock_info)} products from API v2")
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
                # If it's a dictionary with product codes as keys
                for code, product_info in stock_data.items():
                    if isinstance(product_info, dict):
                        stock_info[code] = {
                            'name': product_info.get('name', code),
                            'price': product_info.get('price', 0),
                            'stock': product_info.get('stock', 0),
                            'stock_status': self._get_stock_status_emoji(product_info.get('stock', 0)),
                            'category': product_info.get('category', 'Umum'),
                            'status': product_info.get('status', 'unknown')
                        }
                # If it's a dictionary with a 'data' key containing products
                elif 'data' in stock_data and isinstance(stock_data['data'], list):
                    for product in stock_data['data']:
                        code = product.get('code', '')
                        if code:
                            stock_info[code] = {
                                'name': product.get('name', code),
                                'price': product.get('price', 0),
                                'stock': product.get('stock', 0),
                                'stock_status': self._get_stock_status_emoji(product.get('stock', 0)),
                                'category': product.get('category', 'Umum'),
                                'status': product.get('status', 'unknown')
                            }
            
            elif isinstance(stock_data, list):
                # If it's a list of products
                for product in stock_data:
                    if isinstance(product, dict):
                        code = product.get('code', '')
                        if code:
                            stock_info[code] = {
                                'name': product.get('name', code),
                                'price': product.get('price', 0),
                                'stock': product.get('stock', 0),
                                'stock_status': self._get_stock_status_emoji(product.get('stock', 0)),
                                'category': product.get('category', 'Umum'),
                                'status': product.get('status', 'unknown')
                            }
            
            logger.info(f"📊 Parsed {len(stock_info)} products from API v3")
            return stock_info
            
        except Exception as e:
            logger.error(f"❌ Error parsing stock v3: {e}")
            return {}
    
    def _get_stock_status_emoji(self, stock):
        """Convert stock number to status emoji"""
        if stock > 20:
            return "🟢 TERSEDIA"
        elif stock > 10:
            return "🟢 TERSEDIA"
        elif stock > 5:
            return "🟡 SEDIKIT"
        elif stock > 0:
            return "🟡 MENIPIS"
        else:
            return "🔴 HABIS"

# ==================== STOCK SYNC SYSTEM ====================

async def sync_stock_with_provider():
    """Sync local database stock with provider's real-time data"""
    try:
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            logger.error("❌ API key tidak tersedia untuk sinkronisasi stok")
            return False
        
        stock_api = KhfyPayStockAPI(api_key)
        real_time_stock = await stock_api.get_real_time_stock()
        
        if not real_time_stock:
            logger.error("❌ Gagal mendapatkan stok real-time dari provider")
            return False
        
        updated_count = 0
        error_count = 0
        
        for product_code, stock_info in real_time_stock.items():
            try:
                # Update product in database
                success = update_product_stock(
                    product_code=product_code,
                    name=stock_info['name'],
                    price=stock_info['price'],
                    stock=stock_info['stock'],
                    category=stock_info['category'],
                    status='active' if stock_info['stock'] > 0 else 'inactive'
                )
                
                if success:
                    updated_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"❌ Error updating product {product_code}: {e}")
                error_count += 1
        
        logger.info(f"✅ Stock sync completed: {updated_count} updated, {error_count} errors")
        return updated_count > 0
        
    except Exception as e:
        logger.error(f"❌ Error in sync_stock_with_provider: {e}")
        return False

def update_product_stock(product_code, name, price, stock, category, status):
    """Update product stock in database"""
    try:
        if hasattr(database, 'update_product_stock'):
            return database.update_product_stock(
                product_code=product_code,
                name=name,
                price=price,
                stock=stock,
                category=category,
                status=status
            )
        else:
            # Fallback to direct database operation
            conn = database.db_manager.conn if hasattr(database.db_manager, 'conn') else None
            if not conn:
                import sqlite3
                conn = sqlite3.connect(database.db_manager.db_path)
            
            c = conn.cursor()
            
            # Check if product exists
            c.execute("SELECT code FROM products WHERE code = ?", (product_code,))
            existing = c.fetchone()
            
            if existing:
                # Update existing product
                c.execute("""
                    UPDATE products 
                    SET name = ?, price = ?, stock = ?, category = ?, status = ?, updated_at = datetime('now')
                    WHERE code = ?
                """, (name, price, stock, category, status, product_code))
            else:
                # Insert new product
                c.execute("""
                    INSERT INTO products (code, name, price, stock, category, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """, (product_code, name, price, stock, category, status))
            
            conn.commit()
            conn.close()
            return True
            
    except Exception as e:
        logger.error(f"❌ Error updating product stock: {e}")
        return False

# ==================== TELEGRAM STOCK HANDLERS ====================

async def stock_akrab_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk cek stok produk dengan real-time data"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Show processing message
        processing_msg = await query.edit_message_text(
            "🔄 **Mengambil data stok terbaru...**\n\n"
            "Mohon tunggu sebentar...",
            parse_mode='Markdown'
        )
        
        # Sync with provider first
        sync_success = await sync_stock_with_provider()
        
        if not sync_success:
            await query.edit_message_text(
                "❌ **Gagal mengambil data stok terbaru**\n\n"
                "Menampilkan data stok lokal...",
                parse_mode='Markdown'
            )
        
        # Get categorized products
        categorized_products = get_categorized_products()
        
        if not categorized_products:
            message = "📊 **STOK PRODUK**\n\n" \
                     "📭 Tidak ada produk aktif saat ini.\n\n" \
                     "ℹ️ Silakan refresh atau coba lagi nanti."
        else:
            message = "📊 **STOK PRODUK REAL-TIME**\n\n"
            message += f"🔄 **Update:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
            
            total_products = 0
            available_products = 0
            
            for category, products in categorized_products.items():
                message += f"**{category.upper()}:**\n"
                
                category_count = 0
                category_available = 0
                
                for product in products:
                    total_products += 1
                    category_count += 1
                    
                    if product['stock'] > 0:
                        available_products += 1
                        category_available += 1
                    
                    stock_emoji = "🟢" if product['stock'] > 10 else "🟡" if product['stock'] > 0 else "🔴"
                    stock_text = f"{product['stock']}+" if product['stock'] > 10 else str(product['stock'])
                    
                    message += f"{stock_emoji} {product['name']} - Rp {product['price']:,.0f} | Stok: {stock_text}\n"
                
                message += f"*Tersedia: {category_available}/{category_count} produk*\n\n"
            
            # Summary
            message += f"**📈 SUMMARY:**\n"
            message += f"• Total Produk: {total_products}\n"
            message += f"• Tersedia: {available_products}\n"
            message += f"• Habis: {total_products - available_products}\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Stok", callback_data="menu_stock")],
            [InlineKeyboardButton("🛒 Beli Produk", callback_data="main_menu_order")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"❌ Error in stock_akrab_callback: {e}")
        await query.edit_message_text(
            "❌ **Gagal memuat data stok**\n\n"
            "Silakan coba lagi nanti atau hubungi admin.",
            parse_mode='Markdown'
        )

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /stock"""
    try:
        # Get quick stats
        active_products = database.get_active_products_count() if hasattr(database, 'get_active_products_count') else 0
        
        message = (
            "📊 **STOK PRODUK REAL-TIME**\n\n"
            f"Total produk aktif: **{active_products}**\n"
            f"🔄 Update otomatis dari provider\n\n"
            "Fitur:\n"
            "• ✅ Stok real-time dari KhfyPay\n"
            "• 📊 Kategori terorganisir\n"
            "• 🔄 Auto-sync setiap akses\n"
            "• 🚀 Data ter-update\n\n"
            "Klik tombol di bawah untuk melihat detail stok:"
        )
        
        keyboard = [
            [InlineKeyboardButton("📋 Lihat Detail Stok", callback_data="menu_stock")],
            [InlineKeyboardButton("🛒 Beli Sekarang", callback_data="main_menu_order")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
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

# ==================== UTILITY FUNCTIONS ====================

def get_categorized_products():
    """Get products grouped by category from database"""
    try:
        conn = database.db_manager.conn if hasattr(database.db_manager, 'conn') else None
        if not conn:
            import sqlite3
            conn = sqlite3.connect(database.db_manager.db_path)
        
        c = conn.cursor()
        c.execute("""
            SELECT code, name, category, price, stock, status 
            FROM products 
            WHERE status = 'active' 
            ORDER BY category, name
        """)
        products = c.fetchall()
        conn.close()
        
        categorized = {}
        for code, name, category, price, stock, status in products:
            if category not in categorized:
                categorized[category] = []
            
            categorized[category].append({
                'code': code,
                'name': name,
                'category': category,
                'price': price,
                'stock': stock,
                'status': status
            })
        
        return categorized
        
    except Exception as e:
        logger.error(f"❌ Error in get_categorized_products: {e}")
        return {}

async def quick_stock_check(update: Update, product_code):
    """Quick stock check for specific product"""
    try:
        api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        if not api_key:
            return None
        
        stock_api = KhfyPayStockAPI(api_key)
        real_time_stock = await stock_api.get_real_time_stock()
        
        if real_time_stock and product_code in real_time_stock:
            return real_time_stock[product_code]
        else:
            # Fallback to database
            conn = database.db_manager.conn if hasattr(database.db_manager, 'conn') else None
            if not conn:
                import sqlite3
                conn = sqlite3.connect(database.db_manager.db_path)
            
            c = conn.cursor()
            c.execute("SELECT name, price, stock FROM products WHERE code = ?", (product_code,))
            product = c.fetchone()
            conn.close()
            
            if product:
                return {
                    'name': product[0],
                    'price': product[1],
                    'stock': product[2],
                    'stock_status': "🟢 TERSEDIA" if product[2] > 0 else "🔴 HABIS"
                }
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Error in quick_stock_check: {e}")
        return None

# ==================== BACKGROUND STOCK SYNC ====================

async def background_stock_sync():
    """Background task to sync stock periodically"""
    while True:
        try:
            await asyncio.sleep(300)  # Sync every 5 minutes
            await sync_stock_with_provider()
        except Exception as e:
            logger.error(f"❌ Background stock sync error: {e}")
            await asyncio.sleep(60)  # Wait 1 minute before retry

# Initialize background sync
def initialize_stock_sync():
    """Initialize background stock synchronization"""
    asyncio.create_task(background_stock_sync())
    logger.info("✅ Background stock sync initialized")

# Import datetime for the stock handler
from datetime import datetime
