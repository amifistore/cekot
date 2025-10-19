# order_handler.py - Complete Product Ordering System
import logging
import aiohttp
import asyncio
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, 
    ConversationHandler, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters
)
from datetime import datetime
from typing import Dict, List, Optional
import config
from database import db

logger = logging.getLogger(__name__)

# ==================== CONVERSATION STATES ====================
SELECT_CATEGORY, SELECT_PRODUCT, INPUT_CUSTOMER_DATA, CONFIRM_ORDER, PROCESS_ORDER = range(5)

# ==================== ORDER UTILITIES ====================
def format_products_message(products: List[Dict], category: str = "All") -> str:
    """Format daftar produk menjadi message yang rapi"""
    if not products:
        return f"📭 Tidak ada produk aktif dalam kategori {category}."
    
    message = f"📦 **PRODUK {category.upper()}**\n\n"
    
    for product in products:
        status_icon = "✅" if product.get('stock', 0) > 0 else "⚠️"
        message += (
            f"{status_icon} **{product['name']}**\n"
            f"├ Kode: `{product['code']}`\n"
            f"├ Harga: Rp {product['price']:,.0f}\n"
            f"├ Stok: {product.get('stock', 'N/A')}\n"
            f"└ {product.get('description', 'Tidak ada deskripsi')[:50]}...\n\n"
        )
    
    return message

def format_order_confirmation(order_data: Dict) -> str:
    """Format konfirmasi pesanan"""
    return f"""
🛒 **KONFIRMASI PEMESANAN**

📦 **Produk:** {order_data['product_name']}
💰 **Harga:** Rp {order_data['price']:,.0f}
👤 **Data:** {order_data['customer_input']}
📝 **Kode:** `{order_data['product_code']}`

💳 **Saldo Anda:** Rp {order_data['user_balance']:,.0f}
💵 **Saldo Setelah:** Rp {order_data['user_balance'] - order_data['price']:,.0f}

⚠️ **Pastikan data sudah benar!**
Saldo akan dikurangi setelah konfirmasi.
"""

def format_order_result(order_data: Dict, api_response: Dict) -> str:
    """Format hasil pemesanan"""
    status_icon = "✅" if api_response.get('success') else "❌"
    status_text = "BERHASIL" if api_response.get('success') else "GAGAL"
    
    message = f"""
{status_icon} **PEMESANAN {status_text}**

📦 **Produk:** {order_data['product_name']}
💰 **Harga:** Rp {order_data['price']:,.0f}
👤 **Data:** {order_data['customer_input']}
🆔 **Order ID:** `{order_data['order_id']}`

"""
    
    if api_response.get('success'):
        message += f"""
🎉 **Pesanan berhasil diproses!**
📋 **Detail:**
{api_response.get('message', 'Pesanan sedang diproses')}

⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}
"""
    else:
        message += f"""
😞 **Pesanan gagal diproses**
📋 **Error:**
{api_response.get('message', 'Terjadi kesalahan')}

💡 **Solusi:**
• Cek kembali data yang dimasukkan
• Pastikan saldo mencukupi
• Hubungi admin jika masalah berlanjut
"""
    
    return message

# ==================== ORDER MENU & CATEGORIES ====================
async def show_order_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu pemesanan dengan kategori"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_id = db.get_or_create_user(str(user.id), user.username, user.full_name)
    saldo = db.get_user_balance(str(user.id))
    
    # Get available categories
    products = db.get_active_products()
    categories = set(product['category'] for product in products if product['category'])
    
    # Create category buttons (2 columns)
    keyboard = []
    category_list = list(categories)
    
    for i in range(0, len(category_list), 2):
        row = []
        if i < len(category_list):
            row.append(InlineKeyboardButton(
                f"📱 {category_list[i]}", 
                callback_data=f"order_category:{category_list[i]}"
            ))
        if i + 1 < len(category_list):
            row.append(InlineKeyboardButton(
                f"📦 {category_list[i+1]}", 
                callback_data=f"order_category:{category_list[i+1]}"
            ))
        keyboard.append(row)
    
    # Add all products and back button
    keyboard.extend([
        [InlineKeyboardButton("📋 Semua Produk", callback_data="order_category:all")],
        [InlineKeyboardButton("📜 Riwayat Pesanan", callback_data="order_history")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🛒 **MENU PEMESANAN**\n\n"
        f"💳 **Saldo Anda:** Rp {saldo:,.0f}\n"
        f"📦 **Total Produk:** {len(products)} produk aktif\n"
        f"📂 **Kategori Tersedia:** {len(categories)}\n\n"
        f"Pilih kategori produk:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_order_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle kategori yang dipilih dan tampilkan produk"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    category = data.split(":")[1]
    
    # Get products based on category
    if category == "all":
        products = db.get_active_products()
        category_name = "Semua Produk"
    else:
        products = db.get_active_products(category)
        category_name = category
    
    if not products:
        keyboard = [
            [InlineKeyboardButton("📂 Kategori Lain", callback_data="menu_order")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📭 Tidak ada produk aktif dalam kategori {category_name}.",
            reply_markup=reply_markup
        )
        return
    
    # Filter hanya produk dengan stok tersedia (jika info stok ada)
    available_products = [
        p for p in products 
        if p.get('stock', 1) > 0 or p.get('stock') is None
    ]
    
    if not available_products:
        keyboard = [
            [InlineKeyboardButton("📂 Kategori Lain", callback_data="menu_order")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"😞 Semua produk dalam kategori {category_name} sedang habis.\n"
            f"Silakan pilih kategori lain atau coba lagi nanti.",
            reply_markup=reply_markup
        )
        return
    
    # Create product selection keyboard dengan pagination
    context.user_data['current_products'] = available_products
    context.user_data['current_category'] = category_name
    context.user_data['current_page'] = 0
    
    await show_products_page(update, context, page=0)

async def show_products_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Show products page dengan pagination"""
    products = context.user_data.get('current_products', [])
    category_name = context.user_data.get('current_category', 'Produk')
    
    if not products:
        await update.callback_query.edit_message_text("❌ Data produk tidak ditemukan.")
        return
    
    items_per_page = 5
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_products = products[start_idx:end_idx]
    
    total_pages = (len(products) + items_per_page - 1) // items_per_page
    
    # Create message
    message = f"📦 **{category_name.upper()}** - Halaman {page + 1}/{total_pages}\n\n"
    
    for product in page_products:
        status_icon = "✅" if product.get('stock', 0) > 0 else "⚠️"
        stock_info = f"Stok: {product.get('stock', 'N/A')}" if product.get('stock') is not None else ""
        
        message += (
            f"{status_icon} **{product['name']}**\n"
            f"├ 💰 Rp {product['price']:,.0f}\n"
            f"├ 📦 `{product['code']}`\n"
            f"├ 📝 {product.get('description', '')[:40]}...\n"
            f"└ {stock_info}\n\n"
        )
    
    # Create keyboard dengan pagination
    keyboard = []
    
    # Product buttons
    for product in page_products:
        btn_text = f"{product['name'][:20]} - Rp {product['price']:,.0f}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"select_product:{product['code']}")])
    
    # Pagination buttons
    pagination_row = []
    if page > 0:
        pagination_row.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data=f"products_page:{page-1}"))
    if end_idx < len(products):
        pagination_row.append(InlineKeyboardButton("Selanjutnya ➡️", callback_data=f"products_page:{page+1}"))
    
    if pagination_row:
        keyboard.append(pagination_row)
    
    # Navigation buttons
    keyboard.extend([
        [InlineKeyboardButton("📂 Kategori Lain", callback_data="menu_order")],
        [InlineKeyboardButton("📜 Riwayat Pesanan", callback_data="order_history")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def handle_products_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pagination untuk products list"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    page = int(data.split(":")[1])
    
    context.user_data['current_page'] = page
    await show_products_page(update, context, page)

# ==================== PRODUCT SELECTION & ORDER PROCESS ====================
async def handle_product_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pemilihan produk untuk dipesan"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    product_code = data.split(":")[1]
    
    # Get product details
    product = db.get_product_by_code(product_code)
    if not product:
        await query.edit_message_text("❌ Produk tidak ditemukan.")
        return
    
    # Check product status
    if product['status'] != 'active':
        await query.edit_message_text("❌ Produk tidak aktif. Silakan pilih produk lain.")
        return
    
    # Check stock
    if product.get('stock', 0) <= 0 and product.get('stock') is not None:
        await query.edit_message_text("❌ Stok produk habis. Silakan pilih produk lain.")
        return
    
    # Check user balance
    user = query.from_user
    user_balance = db.get_user_balance(str(user.id))
    
    if user_balance < product['price']:
        keyboard = [
            [InlineKeyboardButton("💳 Topup Saldo", callback_data="menu_topup")],
            [InlineKeyboardButton("📦 Produk Lain", callback_data="menu_order")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"❌ **Saldo Tidak Mencukupi!**\n\n"
            f"💰 **Harga Produk:** Rp {product['price']:,.0f}\n"
            f"💳 **Saldo Anda:** Rp {user_balance:,.0f}\n"
            f"📊 **Kekurangan:** Rp {product['price'] - user_balance:,.0f}\n\n"
            f"Silakan topup saldo terlebih dahulu.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Store product data in context
    context.user_data['selected_product'] = product
    context.user_data['user_balance'] = user_balance
    
    # Determine what input is needed based on product category
    product_name_lower = product['name'].lower()
    
    if any(x in product_name_lower for x in ['pulsa', 'data', 'internet', 'kuota']):
        input_prompt = (
            f"📱 **PEMESANAN {product['name'].upper()}**\n\n"
            f"💰 **Harga:** Rp {product['price']:,.0f}\n"
            f"💳 **Saldo Anda:** Rp {user_balance:,.0f}\n\n"
            f"📞 **Masukkan nomor handphone:**\n"
            f"✅ Contoh: `081234567890`\n\n"
            f"❌ **Ketik /cancel untuk membatalkan**"
        )
    elif any(x in product_name_lower for x in ['listrik', 'pln']):
        input_prompt = (
            f"⚡ **PEMESANAN {product['name'].upper()}**\n\n"
            f"💰 **Harga:** Rp {product['price']:,.0f}\n"
            f"💳 **Saldo Anda:** Rp {user_balance:,.0f}\n\n"
            f"🏠 **Masukkan nomor meter/listrik:**\n"
            f"✅ Contoh: `123456789012`\n\n"
            f"❌ **Ketik /cancel untuk membatalkan**"
        )
    elif any(x in product_name_lower for x in ['game', 'voucher']):
        input_prompt = (
            f"🎮 **PEMESANAN {product['name'].upper()}**\n\n"
            f"💰 **Harga:** Rp {product['price']:,.0f}\n"
            f"💳 **Saldo Anda:** Rp {user_balance:,.0f}\n\n"
            f"🎯 **Masukkan ID game/username:**\n"
            f"✅ Contoh: `Player123` atau `123456789`\n\n"
            f"❌ **Ketik /cancel untuk membatalkan**"
        )
    else:
        input_prompt = (
            f"📦 **PEMESANAN {product['name'].upper()}**\n\n"
            f"💰 **Harga:** Rp {product['price']:,.0f}\n"
            f"💳 **Saldo Anda:** Rp {user_balance:,.0f}\n\n"
            f"📝 **Masukkan data yang diperlukan:**\n"
            f"✅ Sesuai dengan kebutuhan produk\n\n"
            f"❌ **Ketik /cancel untuk membatalkan**"
        )
    
    await query.edit_message_text(
        input_prompt,
        parse_mode='Markdown'
    )
    
    return INPUT_CUSTOMER_DATA

async def handle_customer_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle input data dari customer"""
    customer_input = update.message.text.strip()
    
    # Handle cancellation
    if customer_input.lower() == '/cancel':
        await update.message.reply_text("❌ **Pemesanan Dibatalkan**")
        return ConversationHandler.END
    
    # Basic validation
    if not customer_input:
        await update.message.reply_text("❌ Data tidak boleh kosong. Silakan masukkan data:")
        return INPUT_CUSTOMER_DATA
    
    if len(customer_input) < 3:
        await update.message.reply_text("❌ Data terlalu pendek. Silakan masukkan data yang valid:")
        return INPUT_CUSTOMER_DATA
    
    # Store customer input
    context.user_data['customer_input'] = customer_input
    
    # Get stored data
    product = context.user_data.get('selected_product')
    user_balance = context.user_data.get('user_balance')
    
    if not product:
        await update.message.reply_text("❌ Data produk tidak ditemukan. Silakan mulai ulang.")
        return ConversationHandler.END
    
    # Show confirmation
    order_data = {
        'product_name': product['name'],
        'product_code': product['code'],
        'price': product['price'],
        'customer_input': customer_input,
        'user_balance': user_balance
    }
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Konfirmasi Pesan", callback_data="confirm_order"),
            InlineKeyboardButton("❌ Batalkan", callback_data="cancel_order")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        format_order_confirmation(order_data),
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    return CONFIRM_ORDER

async def handle_order_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle konfirmasi pesanan"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "confirm_order":
        # Process the order
        await process_order(update, context)
        return PROCESS_ORDER
    elif data == "cancel_order":
        await query.edit_message_text("❌ **Pemesanan Dibatalkan**")
        return ConversationHandler.END

async def process_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process pesanan ke provider API"""
    query = update.callback_query
    user = query.from_user
    
    # Get order data from context
    product = context.user_data.get('selected_product')
    customer_input = context.user_data.get('customer_input')
    user_balance = context.user_data.get('user_balance')
    
    if not all([product, customer_input, user_balance]):
        await query.edit_message_text("❌ Data pesanan tidak lengkap. Silakan mulai ulang.")
        return ConversationHandler.END
    
    # Create order record in database
    order_id = db.create_order(
        user_id=str(user.id),
        product_code=product['code'],
        product_name=product['name'],
        price=product['price'],
        customer_input=customer_input
    )
    
    # Update context dengan order ID
    context.user_data['order_id'] = order_id
    
    # Show processing message
    processing_msg = await query.edit_message_text(
        f"🔄 **Memproses Pesanan...**\n\n"
        f"📦 **Produk:** {product['name']}\n"
        f"💰 **Harga:** Rp {product['price']:,.0f}\n"
        f"👤 **Data:** {customer_input}\n"
        f"🆔 **Order ID:** `{order_id}`\n\n"
        f"Mohon tunggu sebentar...",
        parse_mode='Markdown'
    )
    
    try:
        # Prepare API request
        api_payload = {
            "api_key": config.API_KEY_PROVIDER,
            "code": product['code'],
            "target": customer_input,
            "ref_id": f"ORDER_{order_id}"
        }
        
        # Send request to provider API
        async with aiohttp.ClientSession() as session:
            async with session.post(
                config.ORDER_API_URL,
                json=api_payload,
                timeout=30
            ) as response:
                
                if response.status == 200:
                    api_response = await response.json()
                else:
                    api_response = {
                        "success": False,
                        "message": f"HTTP Error {response.status}",
                        "data": None
                    }
        
    except asyncio.TimeoutError:
        api_response = {
            "success": False,
            "message": "Timeout - Provider tidak merespons",
            "data": None
        }
    except Exception as e:
        logger.error(f"Error processing order {order_id}: {e}")
        api_response = {
            "success": False,
            "message": f"System Error: {str(e)}",
            "data": None
        }
    
    # Update order status in database
    if api_response.get('success'):
        db.update_order_status(
            order_id,
            status='completed',
            provider_order_id=api_response.get('data', {}).get('order_id'),
            response_data=json.dumps(api_response)
        )
        
        # Update user balance (already handled in database method)
    else:
        db.update_order_status(
            order_id,
            status='failed',
            response_data=json.dumps(api_response)
        )
    
    # Prepare order data for result message
    order_data = {
        'product_name': product['name'],
        'price': product['price'],
        'customer_input': customer_input,
        'order_id': order_id,
        'user_balance': user_balance
    }
    
    # Send result message
    keyboard = [
        [InlineKeyboardButton("🛒 Pesan Lagi", callback_data="menu_order")],
        [InlineKeyboardButton("📜 Riwayat Pesanan", callback_data="order_history")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ]
    
    if not api_response.get('success'):
        keyboard.insert(0, [InlineKeyboardButton("🔄 Coba Lagi", callback_data=f"retry_order:{product['code']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await processing_msg.edit_text(
        format_order_result(order_data, api_response),
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    # Clean up context
    for key in ['selected_product', 'customer_input', 'user_balance', 'order_id']:
        context.user_data.pop(key, None)
    
    return ConversationHandler.END

async def handle_order_retry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle retry untuk pesanan yang gagal"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    product_code = data.split(":")[1]
    
    # Get product details
    product = db.get_product_by_code(product_code)
    if not product:
        await query.edit_message_text("❌ Produk tidak ditemukan.")
        return
    
    context.user_data['selected_product'] = product
    context.user_data['user_balance'] = db.get_user_balance(str(query.from_user.id))
    
    # Ask for customer input again
    product_name_lower = product['name'].lower()
    
    if any(x in product_name_lower for x in ['pulsa', 'data', 'internet', 'kuota']):
        input_prompt = f"📞 **Masukkan nomor handphone:**"
    elif any(x in product_name_lower for x in ['listrik', 'pln']):
        input_prompt = f"🏠 **Masukkan nomor meter/listrik:**"
    elif any(x in product_name_lower for x in ['game', 'voucher']):
        input_prompt = f"🎯 **Masukkan ID game/username:**"
    else:
        input_prompt = f"📝 **Masukkan data yang diperlukan:**"
    
    await query.edit_message_text(
        f"🔄 **Mengulang Pesanan**\n\n"
        f"📦 **Produk:** {product['name']}\n"
        f"💰 **Harga:** Rp {product['price']:,.0f}\n\n"
        f"{input_prompt}\n\n"
        f"❌ **Ketik /cancel untuk membatalkan**",
        parse_mode='Markdown'
    )
    
    return INPUT_CUSTOMER_DATA

# ==================== ORDER HISTORY ====================
async def show_order_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan riwayat pesanan user"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_id = db.get_or_create_user(str(user.id), user.username, user.full_name)
    
    # Get user orders
    orders = db.get_user_orders(str(user.id), limit=15)
    
    if not orders:
        keyboard = [
            [InlineKeyboardButton("🛒 Pesan Sekarang", callback_data="menu_order")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📭 **Belum ada riwayat pesanan.**\n\n"
            "Yuk pesan produk pertama Anda! 🛒",
            reply_markup=reply_markup
        )
        return
    
    # Calculate statistics
    total_orders = len(orders)
    completed_orders = len([o for o in orders if o['status'] == 'completed'])
    pending_orders = len([o for o in orders if o['status'] == 'pending'])
    failed_orders = len([o for o in orders if o['status'] == 'failed'])
    total_spent = sum(o['price'] for o in orders if o['status'] == 'completed')
    
    message = (
        f"📜 **RIWAYAT PESANAN**\n\n"
        f"📊 **Statistik:**\n"
        f"├ Total Pesanan: {total_orders}\n"
        f"├ Berhasil: {completed_orders}\n"
        f"├ Gagal: {failed_orders}\n"
        f"├ Pending: {pending_orders}\n"
        f"└ Total Pengeluaran: Rp {total_spent:,}\n\n"
        f"📋 **Pesanan Terbaru:**\n"
    )
    
    # Show recent orders
    for order in orders[:8]:
        status_icon = {
            'completed': '✅',
            'pending': '⏳', 
            'failed': '❌'
        }.get(order['status'], '❓')
        
        status_text = order['status'].title()
        
        # Format time
        created_time = datetime.fromisoformat(order['created_at'].replace('Z', '+00:00'))
        time_str = created_time.strftime('%d/%m %H:%M')
        
        message += (
            f"{status_icon} `{order['id']:04d}` | "
            f"{order['product_name'][:15]:<15} | "
            f"Rp {order['price']:>7,} | "
            f"{status_text:>8} | "
            f"{time_str}\n"
        )
    
    if len(orders) > 8:
        message += f"\n... dan {len(orders) - 8} pesanan sebelumnya"
    
    keyboard = [
        [InlineKeyboardButton("🛒 Pesan Sekarang", callback_data="menu_order")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="order_history")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_order_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed order information"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    order_id = int(data.split(":")[1])
    
    # Get order details from database
    # This would require additional database method to get single order
    # For now, we'll show a placeholder
    await query.edit_message_text(
        f"🔍 **Detail Pesanan #{order_id}**\n\n"
        f"Fitur detail pesanan dalam pengembangan...\n\n"
        f"⏰ Akan segera hadir di update berikutnya!",
        parse_mode='Markdown'
    )

# ==================== CONVERSATION HANDLERS ====================
async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel order process"""
    await update.message.reply_text("❌ **Pemesanan Dibatalkan**")
    
    # Clean up context
    for key in ['selected_product', 'customer_input', 'user_balance', 'current_products', 'current_category']:
        context.user_data.pop(key, None)
    
    return ConversationHandler.END

def get_order_conv_handler():
    """Return order conversation handler"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_order_category, pattern="^order_category:"),
            CallbackQueryHandler(handle_product_selection, pattern="^select_product:"),
            CallbackQueryHandler(handle_order_retry, pattern="^retry_order:")
        ],
        states={
            SELECT_CATEGORY: [
                CallbackQueryHandler(handle_order_category, pattern="^order_category:"),
            ],
            SELECT_PRODUCT: [
                CallbackQueryHandler(handle_product_selection, pattern="^select_product:"),
                CallbackQueryHandler(handle_products_pagination, pattern="^products_page:"),
            ],
            INPUT_CUSTOMER_DATA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_customer_input),
                CommandHandler('cancel', cancel_order)
            ],
            CONFIRM_ORDER: [
                CallbackQueryHandler(handle_order_confirmation, pattern="^(confirm_order|cancel_order)$")
            ],
            PROCESS_ORDER: [
                # Processing state - mostly handled by process_order function
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel_order),
            CallbackQueryHandler(show_order_menu, pattern="^menu_order$")
        ],
        allow_reentry=True
    )

def get_order_handlers():
    """Return all order handlers untuk registration"""
    return [
        get_order_conv_handler(),
        CallbackQueryHandler(show_order_menu, pattern="^menu_order$"),
        CallbackQueryHandler(show_order_history, pattern="^order_history$"),
        CallbackQueryHandler(show_order_details, pattern="^order_detail:"),
        CallbackQueryHandler(handle_products_pagination, pattern="^products_page:"),
    ]

# ==================== COMMAND HANDLERS ====================
async def order_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /order"""
    return await show_order_menu(update, context)

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /history"""
    return await show_order_history(update, context)

# ==================== UTILITY FUNCTIONS ====================
async def get_user_order_stats(user_id: str) -> Dict:
    """Get user order statistics"""
    try:
        orders = db.get_user_orders(user_id, limit=100)
        
        total_orders = len(orders)
        completed_orders = len([o for o in orders if o['status'] == 'completed'])
        pending_orders = len([o for o in orders if o['status'] == 'pending'])
        failed_orders = len([o for o in orders if o['status'] == 'failed'])
        total_spent = sum(o['price'] for o in orders if o['status'] == 'completed')
        
        return {
            'total_orders': total_orders,
            'completed_orders': completed_orders,
            'pending_orders': pending_orders,
            'failed_orders': failed_orders,
            'total_spent': total_spent,
            'success_rate': (completed_orders / total_orders * 100) if total_orders > 0 else 0
        }
    except Exception as e:
        logger.error(f"Error getting user order stats: {e}")
        return {
            'total_orders': 0,
            'completed_orders': 0,
            'pending_orders': 0,
            'failed_orders': 0,
            'total_spent': 0,
            'success_rate': 0
        }
