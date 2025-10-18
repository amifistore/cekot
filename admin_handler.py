# admin_handler.py - Complete Admin Features dengan Approve Topup
import logging
import aiohttp
import asyncio
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import config
from database import db

logger = logging.getLogger(__name__)

# ==================== CONVERSATION STATES ====================
EDIT_MENU, CHOOSE_PRODUCT, EDIT_HARGA, EDIT_DESKRIPSI, BROADCAST_MESSAGE = range(5)

# ==================== ADMIN UTILITIES ====================
def is_admin(user) -> bool:
    """Check if user is admin"""
    if not user:
        return False
    return str(user.id) in [str(admin_id) for admin_id in config.ADMIN_TELEGRAM_IDS]

async def admin_check(update, context) -> bool:
    """Check admin permissions dengan comprehensive checking"""
    user = update.effective_user
    if not is_admin(user):
        if update.message:
            await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        elif update.callback_query:
            await update.callback_query.answer("❌ Hanya admin yang bisa menggunakan fitur ini.", show_alert=True)
        return False
    return True

async def log_admin_action(user_id: str, action: str, details: str = ""):
    """Log admin action untuk audit trail"""
    db.log_admin_action(user_id, action, details)
    logger.info(f"👑 Admin Action: {user_id} - {action} - {details}")

# ==================== MAIN ADMIN MENU ====================
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main admin menu yang komprehensif"""
    if not await admin_check(update, context):
        return
    
    user_id = update.effective_user.id
    
    # Get quick stats untuk dashboard
    stats = db.get_bot_statistics()
    
    keyboard = [
        [InlineKeyboardButton("🔄 Update Produk", callback_data="admin_update")],
        [InlineKeyboardButton("📋 List Produk", callback_data="admin_list_produk")],
        [InlineKeyboardButton("✏️ Edit Produk", callback_data="admin_edit_produk")],
        [InlineKeyboardButton("💳 Kelola Topup", callback_data="admin_topup")],
        [InlineKeyboardButton("🛒 Kelola Order", callback_data="admin_orders")],
        [InlineKeyboardButton("👥 Kelola User", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Statistik", callback_data="admin_stats")],
        [InlineKeyboardButton("💾 Backup Database", callback_data="admin_backup")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🏥 System Health", callback_data="admin_health")],
        [InlineKeyboardButton("🧹 Cleanup Data", callback_data="admin_cleanup")],
        [InlineKeyboardButton("❌ Tutup Menu", callback_data="admin_close")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"""
👑 **MENU ADMIN** - Dashboard

📊 **Quick Stats:**
├ 👥 Users: {stats['total_users']}
├ 🛒 Orders: {stats['successful_orders']}/{stats['total_orders']}
├ 💰 Revenue: Rp {stats['total_revenue']:,.0f}
├ 📦 Produk: {stats['active_products']}
├ ⏳ Topup Pending: {stats['pending_topups']}
└ ⏳ Order Pending: {stats['pending_orders']}

**Fitur Admin:**
• 🔄 Update Produk - Sync produk dari provider
• 📋 List Produk - Lihat daftar produk aktif  
• ✏️ Edit Produk - Ubah harga & deskripsi
• 💳 Kelola Topup - Approve permintaan saldo
• 🛒 Kelola Order - Lihat & manage order
• 👥 Kelola User - Kelola user bot
• 📊 Statistik - Lihat statistik bot
• 💾 Backup - Backup database
• 📢 Broadcast - Kirim pesan ke semua user
• 🏥 Health - Cek status system
• 🧹 Cleanup - Bersihkan data lama
"""
    
    if update.message:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Menu admin edit failed: {e}")

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin callback queries dengan comprehensive routing"""
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return
    
    data = query.data
    user_id = query.from_user.id
    
    logger.info(f"Admin callback: {data} by {user_id}")
    
    # Routing berdasarkan callback data
    handlers = {
        "admin_update": update_produk,
        "admin_list_produk": list_produk,
        "admin_edit_produk": edit_produk_start,
        "admin_topup": topup_list,
        "admin_orders": orders_list,
        "admin_users": show_users_menu,
        "admin_stats": show_stats_menu,
        "admin_backup": backup_database,
        "admin_broadcast": broadcast_start,
        "admin_health": system_health,
        "admin_cleanup": cleanup_data,
        "admin_back": admin_menu,
        "admin_close": lambda u, c: query.edit_message_text("✅ Menu admin ditutup")
    }
    
    handler = handlers.get(data)
    if handler:
        await handler(update, context)
    else:
        await query.edit_message_text("❌ Perintah tidak dikenali")

# ==================== PRODUCT MANAGEMENT ====================
async def update_produk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Update products from provider dengan comprehensive error handling"""
    if update.callback_query:
        msg_func = update.callback_query.edit_message_text
        user_id = update.callback_query.from_user.id
    else:
        msg_func = update.message.reply_text
        user_id = update.message.from_user.id

    await msg_func("🔄 Memperbarui Produk dari Provider...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                config.PRODUCT_API_URL, 
                params={"api_key": config.API_KEY_PROVIDER}, 
                timeout=config.REQUEST_TIMEOUT
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}: {await resp.text()}")
                data = await resp.json()
        
        if not data.get("ok", False):
            error_msg = data.get("message", "Unknown error from provider")
            await msg_func(f"❌ Error dari provider: {error_msg}")
            return

        produk_list = data.get("data", [])
        if not produk_list:
            await msg_func("⚠️ Tidak ada data produk dari provider.")
            return

        # Process products
        processed_products = []
        for prod in produk_list:
            try:
                code = str(prod.get("kode_produk", "")).strip()
                name = str(prod.get("nama_produk", "")).strip()
                price = float(prod.get("harga_final", 0))
                gangguan = int(prod.get("gangguan", 0))
                kosong = int(prod.get("kosong", 0))
                
                if not code or not name or price <= 0 or gangguan == 1 or kosong == 1:
                    continue
                
                # Determine category
                name_lower = name.lower()
                if "pulsa" in name_lower:
                    category = "Pulsa"
                elif any(x in name_lower for x in ["data", "internet", "kuota"]):
                    category = "Internet"
                elif any(x in name_lower for x in ["listrik", "pln"]):
                    category = "Listrik"
                elif "game" in name_lower:
                    category = "Game"
                elif any(x in name_lower for x in ["emoney", "gopay", "dana"]):
                    category = "E-Money"
                elif any(x in name_lower for x in ["akrab", "bonus"]):
                    category = "Paket Bonus"
                else:
                    category = "Umum"
                
                processed_products.append({
                    'code': code,
                    'name': name,
                    'price': price,
                    'description': prod.get("deskripsi", f"Produk {name}"),
                    'category': category,
                    'provider': prod.get("kode_provider", ""),
                    'gangguan': gangguan,
                    'kosong': kosong,
                    'stock': prod.get("stock", 0)
                })
                
            except Exception as e:
                logger.error(f"Error processing product {prod}: {e}")
                continue
        
        # Bulk update ke database
        count = db.bulk_update_products(processed_products)
        
        await log_admin_action(user_id, "UPDATE_PRODUCTS", f"Updated: {count} produk")
        
        keyboard = [
            [InlineKeyboardButton("📋 Lihat Produk", callback_data="admin_list_produk")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_update")],
            [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg_func(
            f"✅ **Update Produk Berhasil**\n\n"
            f"📊 **Statistik:**\n"
            f"├ Berhasil diupdate: {count} produk\n"
            f"├ Gagal diproses: {len(produk_list) - count} produk\n"
            f"⏰ **Update Terakhir:** {datetime.now().strftime('%d-%m-%Y %H:%M')}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except aiohttp.ClientError as e:
        await msg_func(f"❌ **Network Error:** Gagal terhubung ke provider\n\nDetail: {str(e)}")
    except Exception as e:
        logger.error(f"Error updating products: {e}")
        await msg_func(f"❌ **System Error:** Gagal memperbarui produk\n\nDetail: {str(e)}")

async def list_produk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all active products dengan pagination dan filtering"""
    if update.callback_query:
        msg_func = update.callback_query.edit_message_text
    else:
        msg_func = update.message.reply_text

    # Get category filter dari context jika ada
    category = context.user_data.get('list_category', None)
    
    products = db.get_active_products(category)
    
    if not products:
        await msg_func("📭 Tidak ada produk aktif.")
        return
    
    # Group by category
    products_by_category = {}
    for product in products:
        cat = product['category'] or 'Umum'
        if cat not in products_by_category:
            products_by_category[cat] = []
        products_by_category[cat].append(product)
    
    # Build message
    msg = "📋 **DAFTAR PRODUK AKTIF**\n\n"
    total_products = 0
    
    for category_name, products_list in products_by_category.items():
        msg += f"**{category_name}** ({len(products_list)} produk):\n"
        total_products += len(products_list)
        
        for product in products_list[:6]:  # Limit per category
            status_icon = "✅" if product.get('stock', 0) > 0 else "⚠️"
            msg += f"├ {status_icon} `{product['code']}` | {product['name'][:25]} | Rp {product['price']:,.0f}\n"
        
        if len(products_list) > 6:
            msg += f"└ ... dan {len(products_list) - 6} produk lainnya\n"
        msg += "\n"
    
    msg += f"📊 **Total:** {total_products} produk aktif"
    
    # Keyboard dengan category filter
    keyboard = [
        [InlineKeyboardButton("📱 Pulsa", callback_data="filter_category:Pulsa"),
         InlineKeyboardButton("🌐 Internet", callback_data="filter_category:Internet")],
        [InlineKeyboardButton("⚡ Listrik", callback_data="filter_category:Listrik"),
         InlineKeyboardButton("🎮 Game", callback_data="filter_category:Game")],
        [InlineKeyboardButton("💳 E-Money", callback_data="filter_category:E-Money"),
         InlineKeyboardButton("🎁 Paket Bonus", callback_data="filter_category:Paket Bonus")],
        [InlineKeyboardButton("🔄 Update Produk", callback_data="admin_update"),
         InlineKeyboardButton("📋 Semua Kategori", callback_data="filter_category:all")],
        [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await msg_func(msg, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        if "Message is too long" in str(e):
            # Split long message
            chunks = [msg[i:i+config.MAX_MESSAGE_LENGTH] for i in range(0, len(msg), config.MAX_MESSAGE_LENGTH)]
            for chunk in chunks:
                await msg_func(chunk, parse_mode='Markdown')
            await msg_func("📋 **Daftar produk selesai**", reply_markup=reply_markup)

async def handle_category_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle category filter untuk list produk"""
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return
    
    data = query.data
    category = data.split(":")[1] if ":" in data else None
    
    if category == 'all':
        category = None
    
    context.user_data['list_category'] = category
    await list_produk(update, context)

# ==================== PRODUCT EDITING SYSTEM ====================
async def edit_produk_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start product editing process"""
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Harga Produk", callback_data="edit_harga")],
        [InlineKeyboardButton("📝 Edit Deskripsi Produk", callback_data="edit_deskripsi")],
        [InlineKeyboardButton("⚡ Edit Status Produk", callback_data="edit_status")],
        [InlineKeyboardButton("⬅️ Kembali ke Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = "🛠️ **MENU EDIT PRODUK**\n\nPilih jenis edit yang ingin dilakukan:"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    return EDIT_MENU

async def edit_produk_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product editing menu selection"""
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return ConversationHandler.END
    
    data = query.data
    context.user_data['edit_type'] = data
    
    if data in ['edit_harga', 'edit_deskripsi', 'edit_status']:
        products = db.get_active_products()
        
        if not products:
            await query.edit_message_text("❌ Tidak ada produk yang tersedia untuk diedit.")
            return EDIT_MENU
        
        # Create product selection keyboard
        keyboard = []
        for product in products[:30]:  # Limit to 30 products
            btn_text = f"{product['name'][:20]} - Rp {product['price']:,.0f}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"select_product:{product['code']}")])
        
        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_edit_menu")])
        
        edit_type_text = {
            'edit_harga': 'HARGA',
            'edit_deskripsi': 'DESKRIPSI', 
            'edit_status': 'STATUS'
        }.get(data, 'PRODUK')
        
        await query.edit_message_text(
            f"📦 **PILIH PRODUK UNTUK EDIT {edit_type_text}**\n\n"
            f"Total {len(products)} produk aktif. Pilih produk dari daftar di bawah:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return CHOOSE_PRODUCT
    
    elif data == "admin_back":
        await admin_menu(update, context)
        return ConversationHandler.END
    
    elif data == "back_to_edit_menu":
        return await edit_produk_start(update, context)

async def select_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product selection untuk editing"""
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return ConversationHandler.END
    
    data = query.data
    
    if data.startswith('select_product:'):
        product_code = data.split(':')[1]
        product = db.get_product_by_code(product_code)
        
        if product:
            context.user_data['selected_product'] = product
            
            edit_type = context.user_data.get('edit_type')
            user_id = query.from_user.id
            
            if edit_type == 'edit_harga':
                await log_admin_action(user_id, "EDIT_HARGA_START", f"Product: {product_code}")
                await query.edit_message_text(
                    f"💰 **EDIT HARGA PRODUK**\n\n"
                    f"📦 **Produk:** {product['name']}\n"
                    f"📌 **Kode:** `{product['code']}`\n"
                    f"💰 **Harga Saat Ini:** Rp {product['price']:,.0f}\n\n"
                    f"Silakan kirim harga baru (hanya angka):",
                    parse_mode='Markdown'
                )
                return EDIT_HARGA
            
            elif edit_type == 'edit_deskripsi':
                await log_admin_action(user_id, "EDIT_DESKRIPSI_START", f"Product: {product_code}")
                current_desc = product['description'] if product['description'] else "Belum ada deskripsi"
                await query.edit_message_text(
                    f"📝 **EDIT DESKRIPSI PRODUK**\n\n"
                    f"📦 **Produk:** {product['name']}\n"
                    f"📌 **Kode:** `{product['code']}`\n"
                    f"📄 **Deskripsi Saat Ini:**\n{current_desc}\n\n"
                    f"Silakan kirim deskripsi baru:",
                    parse_mode='Markdown'
                )
                return EDIT_DESKRIPSI
            
            elif edit_type == 'edit_status':
                await log_admin_action(user_id, "EDIT_STATUS_START", f"Product: {product_code}")
                current_status = product['status']
                keyboard = [
                    [InlineKeyboardButton("✅ Aktif", callback_data=f"set_status:{product_code}:active")],
                    [InlineKeyboardButton("❌ Nonaktif", callback_data=f"set_status:{product_code}:inactive")],
                    [InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_edit_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"⚡ **EDIT STATUS PRODUK**\n\n"
                    f"📦 **Produk:** {product['name']}\n"
                    f"📌 **Kode:** `{product['code']}`\n"
                    f"📊 **Status Saat Ini:** {current_status}\n\n"
                    f"Pilih status baru:",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return ConversationHandler.END
    
    await query.edit_message_text("❌ Terjadi kesalahan. Silakan coba lagi.")
    return EDIT_MENU

async def edit_harga_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle harga editing dengan validation"""
    if not await admin_check(update, context):
        return ConversationHandler.END
    
    try:
        new_price = float(update.message.text.replace(',', '').replace('.', '').strip())
        if new_price <= 0:
            await update.message.reply_text("❌ Harga harus lebih dari 0. Silakan coba lagi:")
            return EDIT_HARGA
    except ValueError:
        await update.message.reply_text("❌ Format harga tidak valid. Kirim hanya angka. Silakan coba lagi:")
        return EDIT_HARGA
    
    product = context.user_data.get('selected_product')
    if not product:
        await update.message.reply_text("❌ Data produk tidak ditemukan. Silakan mulai ulang.")
        return ConversationHandler.END
    
    product_code = product['code']
    old_price = product['price']
    
    # Update product price
    db.update_product(product_code, price=new_price)
    await log_admin_action(
        update.message.from_user.id, 
        "EDIT_HARGA_SUCCESS", 
        f"Product: {product_code}, Old: {old_price}, New: {new_price}"
    )
    
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Produk Lain", callback_data="back_to_edit_menu")],
        [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ **Harga Berhasil Diupdate!**\n\n"
        f"📦 **Produk:** {product['name']}\n"
        f"📌 **Kode:** `{product_code}`\n"
        f"💰 **Harga Lama:** Rp {old_price:,.0f}\n"
        f"💰 **Harga Baru:** Rp {new_price:,.0f}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def edit_deskripsi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deskripsi editing"""
    if not await admin_check(update, context):
        return ConversationHandler.END
    
    new_description = update.message.text.strip()
    if not new_description:
        await update.message.reply_text("❌ Deskripsi tidak boleh kosong. Silakan coba lagi:")
        return EDIT_DESKRIPSI
    
    product = context.user_data.get('selected_product')
    if not product:
        await update.message.reply_text("❌ Data produk tidak ditemukan. Silakan mulai ulang.")
        return ConversationHandler.END
    
    product_code = product['code']
    old_description = product['description'] or "Tidak ada"
    
    # Update product description
    db.update_product(product_code, description=new_description)
    await log_admin_action(
        update.message.from_user.id, 
        "EDIT_DESKRIPSI_SUCCESS", 
        f"Product: {product_code}"
    )
    
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Produk Lain", callback_data="back_to_edit_menu")],
        [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ **Deskripsi Berhasil Diupdate!**\n\n"
        f"📦 **Produk:** {product['name']}\n"
        f"📌 **Kode:** `{product_code}`\n"
        f"📄 **Deskripsi Baru:**\n{new_description}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def handle_status_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product status change"""
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return
    
    data = query.data
    if data.startswith('set_status:'):
        _, product_code, new_status = data.split(':')
        
        product = db.get_product_by_code(product_code)
        if not product:
            await query.edit_message_text("❌ Produk tidak ditemukan.")
            return
        
        old_status = product['status']
        db.update_product(product_code, status=new_status)
        
        await log_admin_action(
            query.from_user.id,
            "EDIT_STATUS_SUCCESS",
            f"Product: {product_code}, {old_status} -> {new_status}"
        )
        
        keyboard = [
            [InlineKeyboardButton("✏️ Edit Produk Lain", callback_data="back_to_edit_menu")],
            [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        status_icon = "✅" if new_status == 'active' else "❌"
        await query.edit_message_text(
            f"{status_icon} **Status Produk Berhasil Diupdate!**\n\n"
            f"📦 **Produk:** {product['name']}\n"
            f"📌 **Kode:** `{product_code}`\n"
            f"📊 **Status Lama:** {old_status}\n"
            f"📊 **Status Baru:** {new_status}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

# ==================== TOPUP MANAGEMENT ====================
async def topup_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List pending topup requests dengan comprehensive info"""
    if update.callback_query:
        msg_func = update.callback_query.edit_message_text
        user_id = update.callback_query.from_user.id
    else:
        msg_func = update.message.reply_text
        user_id = update.message.from_user.id

    pending_transactions = db.get_pending_transactions('topup')
    
    if not pending_transactions:
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_topup")],
            [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await msg_func("✅ Tidak ada permintaan topup yang pending.", reply_markup=reply_markup)
        return

    # Kirim summary dulu
    total_pending = len(pending_transactions)
    total_amount = sum(trans['amount'] for trans in pending_transactions)
    
    summary_msg = (
        f"💳 **PERMINTAAN TOPUP PENDING**\n\n"
        f"📊 **Summary:**\n"
        f"├ Total Pending: {total_pending} transaksi\n"
        f"├ Total Amount: Rp {total_amount:,.0f}\n"
        f"└ Berikut detailnya:\n\n"
    )
    
    await msg_func(summary_msg, parse_mode='Markdown')
    
    # Kirim detail setiap transaksi
    for trans in pending_transactions:
        message = (
            f"🆔 **ID Transaksi:** `{trans['id']}`\n"
            f"👤 **User:** {trans['full_name']} (@{trans['username']})\n"
            f"🆔 **User ID:** `{trans['user_id']}`\n"
            f"💵 **Jumlah:** Rp {trans['amount']:,.0f}\n"
            f"🔢 **Kode Unik:** {trans['unique_code']}\n"
            f"💰 **Saldo User:** Rp {trans['user_balance']:,.0f}\n"
            f"⏰ **Waktu:** {trans['created_at']}\n"
            f"📝 **Detail:** {trans['details'] or 'Tidak ada'}"
        )
        
        # Action buttons untuk setiap transaksi
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_topup:{trans['id']}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_topup:{trans['id']}")
            ],
            [InlineKeyboardButton("📋 Lihat Semua", callback_data="admin_topup")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg_func(message, reply_markup=reply_markup, parse_mode='Markdown')

    # Kirim menu navigasi
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_topup")],
        [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await msg_func(f"📋 **Total {total_pending} permintaan topup pending**", reply_markup=reply_markup)

async def approve_topup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approve topup request dengan comprehensive processing"""
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return
    
    data = query.data
    transaction_id = int(data.split(':')[1])
    admin_id = query.from_user.id
    
    try:
        # Get transaction details
        pending_transactions = db.get_pending_transactions('topup')
        trans = next((t for t in pending_transactions if t['id'] == transaction_id), None)
        
        if not trans:
            await query.edit_message_text("❌ Transaksi tidak ditemukan atau sudah diproses.")
            return
        
        if trans['status'] != 'pending':
            await query.edit_message_text("❌ Transaksi sudah diproses.")
            return
        
        # Update transaction status
        db.update_transaction_status(
            transaction_id, 
            'completed', 
            'Topup approved by admin',
            f'Approved by admin {admin_id}'
        )
        
        # Log admin action
        await log_admin_action(
            admin_id, 
            "APPROVE_TOPUP", 
            f"Transaction: {transaction_id}, Amount: {trans['amount']}, User: {trans['user_id']}"
        )
        
        # Notify user
        try:
            from main import application
            await application.bot.send_message(
                chat_id=trans['user_id'],
                text=(
                    f"✅ **Topup Disetujui!**\n\n"
                    f"💵 **Jumlah:** Rp {trans['amount']:,.0f}\n"
                    f"🔢 **Kode Unik:** {trans['unique_code']}\n"
                    f"💰 **Saldo ditambahkan ke akun Anda.**\n"
                    f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}\n\n"
                    f"Terima kasih telah topup! 🎉"
                )
            )
        except Exception as e:
            logger.error(f"Failed to notify user {trans['user_id']}: {e}")
        
        # Update admin message
        keyboard = [
            [InlineKeyboardButton("📋 Lihat Topup Lain", callback_data="admin_topup")],
            [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ **Topup Approved!**\n\n"
            f"👤 **User:** {trans['full_name']} (@{trans['username']})\n"
            f"💵 **Jumlah:** Rp {trans['amount']:,.0f}\n"
            f"🆔 **Transaction ID:** {transaction_id}\n"
            f"⏰ **Waktu:** {datetime.now().strftime('%H:%M')}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error approving topup {transaction_id}: {e}")
        await query.edit_message_text(f"❌ Gagal approve topup: {str(e)}")

async def reject_topup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reject topup request dengan comprehensive processing"""
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return
    
    data = query.data
    transaction_id = int(data.split(':')[1])
    admin_id = query.from_user.id
    
    try:
        # Get transaction details
        pending_transactions = db.get_pending_transactions('topup')
        trans = next((t for t in pending_transactions if t['id'] == transaction_id), None)
        
        if not trans:
            await query.edit_message_text("❌ Transaksi tidak ditemukan atau sudah diproses.")
            return
        
        if trans['status'] != 'pending':
            await query.edit_message_text("❌ Transaksi sudah diproses.")
            return
        
        # Update transaction status
        db.update_transaction_status(
            transaction_id, 
            'rejected', 
            'Topup rejected by admin',
            f'Rejected by admin {admin_id}'
        )
        
        # Log admin action
        await log_admin_action(
            admin_id, 
            "REJECT_TOPUP", 
            f"Transaction: {transaction_id}, Amount: {trans['amount']}, User: {trans['user_id']}"
        )
        
        # Notify user
        try:
            from main import application
            await application.bot.send_message(
                chat_id=trans['user_id'],
                text=(
                    f"❌ **Topup Ditolak!**\n\n"
                    f"💵 **Jumlah:** Rp {trans['amount']:,.0f}\n"
                    f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M')}\n\n"
                    f"📞 **Silakan hubungi admin untuk informasi lebih lanjut.**\n"
                    f"Alasan: Topup tidak valid atau bukti transfer tidak jelas."
                )
            )
        except Exception as e:
            logger.error(f"Failed to notify user {trans['user_id']}: {e}")
        
        # Update admin message
        keyboard = [
            [InlineKeyboardButton("📋 Lihat Topup Lain", callback_data="admin_topup")],
            [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"❌ **Topup Rejected!**\n\n"
            f"👤 **User:** {trans['full_name']} (@{trans['username']})\n"
            f"💵 **Jumlah:** Rp {trans['amount']:,.0f}\n"
            f"🆔 **Transaction ID:** {transaction_id}\n"
            f"⏰ **Waktu:** {datetime.now().strftime('%H:%M')}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error rejecting topup {transaction_id}: {e}")
        await query.edit_message_text(f"❌ Gagal reject topup: {str(e)}")

# ==================== ORDER MANAGEMENT ====================
async def orders_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List orders dengan status filtering"""
    if update.callback_query:
        msg_func = update.callback_query.edit_message_text
    else:
        msg_func = update.message.reply_text

    # Get status filter
    status_filter = context.user_data.get('order_status', 'pending')
    
    if status_filter == 'pending':
        orders = db.get_pending_orders()
        status_text = "PENDING"
    else:
        # Untuk simplicity, kita ambil semua orders dulu
        orders = []  # Ini akan diimplementasi lengkap nanti
        status_text = "ALL"
    
    if not orders:
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_orders")],
            [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await msg_func(f"✅ Tidak ada order dengan status {status_text}.", reply_markup=reply_markup)
        return

    message = f"🛒 **ORDER {status_text.upper()}**\n\n"
    
    for order in orders[:10]:  # Limit to 10 orders
        message += (
            f"🆔 **ID:** `{order['id']}`\n"
            f"👤 **User:** {order['full_name']}\n"
            f"📦 **Produk:** {order['product_name']}\n"
            f"💰 **Harga:** Rp {order['price']:,.0f}\n"
            f"📥 **Input:** {order['customer_input']}\n"
            f"⏰ **Waktu:** {order['created_at']}\n"
            f"────────────────────\n"
        )
    
    if len(orders) > 10:
        message += f"\n... dan {len(orders) - 10} order lainnya"
    
    # Status filter buttons
    keyboard = [
        [
            InlineKeyboardButton("⏳ Pending", callback_data="filter_orders:pending"),
            InlineKeyboardButton("✅ Completed", callback_data="filter_orders:completed")
        ],
        [
            InlineKeyboardButton("❌ Failed", callback_data="filter_orders:failed"),
            InlineKeyboardButton("📋 All", callback_data="filter_orders:all")
        ],
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_orders")],
        [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await msg_func(message, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_order_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle order status filter"""
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return
    
    data = query.data
    status = data.split(":")[1] if ":" in data else 'pending'
    
    context.user_data['order_status'] = status
    await orders_list(update, context)

# ==================== USER MANAGEMENT ====================
async def show_users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user management menu dengan statistics"""
    if update.callback_query:
        msg_func = update.callback_query.edit_message_text
    else:
        msg_func = update.message.reply_text

    stats = db.get_bot_statistics()
    daily_stats = db.get_daily_stats(7)

    # Calculate active users (last 7 days)
    active_users = 0  # Ini akan diimplementasi lengkap nanti

    message = (
        f"👥 **MANAJEMEN USER**\n\n"
        f"📊 **Statistik User:**\n"
        f"├ Total User: {stats['total_users']}\n"
        f"├ User Aktif (7h): {active_users}\n"
        f"├ User Baru (H ini): {stats['today_users']}\n"
        f"├ Total Saldo: Rp {stats['total_revenue']:,.0f}\n"
        f"└ Total Spending: Rp {stats['total_spending']:,.0f}\n\n"
        f"📈 **Activity (7 hari):**\n"
    )
    
    # Add daily stats
    for day in daily_stats[-3:]:  # Last 3 days
        message += f"├ {day['date']}: {day['order_count']} orders\n"
    
    message += f"\n⚡ **Fitur user management dalam pengembangan...**"

    keyboard = [
        [InlineKeyboardButton("📊 User Statistics", callback_data="user_stats")],
        [InlineKeyboardButton("👤 Top Users", callback_data="top_users")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_users")],
        [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await msg_func(message, reply_markup=reply_markup, parse_mode='Markdown')

# ==================== STATISTICS & REPORTING ====================
async def show_stats_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show comprehensive bot statistics"""
    if update.callback_query:
        msg_func = update.callback_query.edit_message_text
    else:
        msg_func = update.message.reply_text

    stats = db.get_bot_statistics()
    daily_stats = db.get_daily_stats(7)

    # Calculate averages
    avg_order_value = stats['total_spending'] / stats['successful_orders'] if stats['successful_orders'] > 0 else 0
    avg_topup_value = stats['total_revenue'] / stats['total_transactions'] if stats['total_transactions'] > 0 else 0

    message = (
        f"📊 **STATISTIK BOT LENGKAP**\n\n"
        f"👥 **Users:**\n"
        f"├ Total: {stats['total_users']} users\n"
        f"├ Baru (H ini): {stats['today_users']} users\n"
        f"└ Growth: {((stats['today_users'] / stats['total_users']) * 100) if stats['total_users'] > 0 else 0:.1f}%\n\n"
        
        f"🛒 **Orders:**\n"
        f"├ Total: {stats['total_orders']} orders\n"
        f"├ Berhasil: {stats['successful_orders']} orders\n"
        f"├ Success Rate: {((stats['successful_orders'] / stats['total_orders']) * 100) if stats['total_orders'] > 0 else 0:.1f}%\n"
        f"├ Rata-rata: Rp {avg_order_value:,.0f}\n"
        f"└ Pending: {stats['pending_orders']} orders\n\n"
        
        f"💳 **Financial:**\n"
        f"├ Revenue: Rp {stats['total_revenue']:,.0f}\n"
        f"├ Spending: Rp {stats['total_spending']:,.0f}\n"
        f"├ Profit: Rp {stats['net_profit']:,.0f}\n"
        f"├ Rata-rata Topup: Rp {avg_topup_value:,.0f}\n"
        f"└ Topup Pending: {stats['pending_topups']}\n\n"
        
        f"📦 **Products:**\n"
        f"└ Aktif: {stats['active_products']} produk\n\n"
        
        f"⏰ **Update:** {datetime.now().strftime('%d-%m-%Y %H:%M')}"
    )

    keyboard = [
        [InlineKeyboardButton("📈 Daily Report", callback_data="daily_report")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_stats")],
        [InlineKeyboardButton("💾 Export", callback_data="export_stats")],
        [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await msg_func(message, reply_markup=reply_markup, parse_mode='Markdown')

# ==================== SYSTEM MAINTENANCE ====================
async def backup_database(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Backup database dengan comprehensive reporting"""
    if update.callback_query:
        msg_func = update.callback_query.edit_message_text
        user_id = update.callback_query.from_user.id
    else:
        msg_func = update.message.reply_text
        user_id = update.message.from_user.id

    try:
        import shutil
        import os
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"backup_{timestamp}.db"
        
        # Create backup
        shutil.copy2(config.DB_PATH, backup_filename)
        
        # Get backup info
        backup_size = os.path.getsize(backup_filename)
        original_size = os.path.getsize(config.DB_PATH)
        
        await log_admin_action(user_id, "BACKUP_DATABASE", f"File: {backup_filename}, Size: {backup_size} bytes")
        
        keyboard = [
            [InlineKeyboardButton("💾 Download Backup", callback_data=f"download_backup:{backup_filename}")],
            [InlineKeyboardButton("🔄 New Backup", callback_data="admin_backup")],
            [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg_func(
            f"✅ **Backup Berhasil!**\n\n"
            f"📁 **File:** `{backup_filename}`\n"
            f"💾 **Size:** {backup_size / 1024:.2f} KB\n"
            f"📊 **Original:** {original_size / 1024:.2f} KB\n"
            f"⏰ **Waktu:** {datetime.now().strftime('%H:%M:%S')}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Backup error: {e}")
        await msg_func(f"❌ **Gagal backup:** {str(e)}")

async def system_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show comprehensive system health information"""
    if update.callback_query:
        msg_func = update.callback_query.edit_message_text
    else:
        msg_func = update.message.reply_text

    try:
        import psutil
        import platform
        
        # System info
        system = platform.system()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Database info
        import os
        db_size = os.path.getsize(config.DB_PATH) if os.path.exists(config.DB_PATH) else 0
        
        # Bot stats
        stats = db.get_bot_statistics()
        
        # Process info
        process = psutil.Process()
        memory_usage = process.memory_info().rss / 1024 / 1024  # MB
        
        message = (
            f"🏥 **SYSTEM HEALTH**\n\n"
            f"🖥️ **System:** {system}\n"
            f"💾 **Memory:** {memory.percent}% used ({memory.used//1024//1024}MB/{memory.total//1024//1024}MB)\n"
            f"🖥️ **CPU:** {cpu_percent}% used\n"
            f"💿 **Disk:** {disk.percent}% used\n"
            f"📊 **Database:** {db_size / 1024 / 1024:.2f} MB\n"
            f"🤖 **Bot Memory:** {memory_usage:.2f} MB\n\n"
            
            f"📈 **Bot Performance:**\n"
            f"├ Uptime: {datetime.now().strftime('%d days %H:%M')}\n"
            f"├ Active Users: {stats['total_users']}\n"
            f"├ Successful Orders: {stats['successful_orders']}\n"
            f"└ Pending Tasks: {stats['pending_orders'] + stats['pending_topups']}\n\n"
            
            f"⏰ **Last Update:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
        )

        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_health")],
            [InlineKeyboardButton("🐛 Debug Info", callback_data="debug_info")],
            [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg_func(message, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"System health error: {e}")
        await msg_func(f"❌ **Gagal mengambil system health:** {str(e)}")

async def cleanup_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cleanup old data dengan comprehensive reporting"""
    if update.callback_query:
        msg_func = update.callback_query.edit_message_text
        user_id = update.callback_query.from_user.id
    else:
        msg_func = update.message.reply_text
        user_id = update.message.from_user.id

    try:
        # Cleanup data older than 30 days
        cleanup_stats = db.cleanup_old_data(30)
        
        await log_admin_action(user_id, "CLEANUP_DATA", f"Stats: {cleanup_stats}")
        
        keyboard = [
            [InlineKeyboardButton("🔄 Cleanup Again", callback_data="admin_cleanup")],
            [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg_func(
            f"🧹 **Data Cleanup Berhasil!**\n\n"
            f"🗑️ **Data yang dihapus:**\n"
            f"├ Transaksi: {cleanup_stats['transactions']}\n"
            f"├ Orders: {cleanup_stats['orders']}\n"
            f"├ Admin Logs: {cleanup_stats['admin_logs']}\n"
            f"└ System Logs: {cleanup_stats['system_logs']}\n\n"
            f"💾 **Database dioptimalkan.**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        await msg_func(f"❌ **Gagal cleanup:** {str(e)}")

# ==================== BROADCAST SYSTEM ====================
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start broadcast process"""
    if not await admin_check(update, context):
        return ConversationHandler.END
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "📢 **BROADCAST MESSAGE**\n\n"
            "Silakan kirim pesan yang ingin di-broadcast ke semua user.\n\n"
            "**Formatting:**\n"
            "• Gunakan Markdown untuk formatting\n"
            "• **Bold**, *italic*, `code`\n"
            "• Support links dan emoji\n\n"
            "❌ **Ketik /cancel untuk membatalkan**",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "📢 **BROADCAST MESSAGE**\n\n"
            "Silakan kirim pesan yang ingin di-broadcast ke semua user.\n\n"
            "**Formatting:**\n"
            "• Gunakan Markdown untuk formatting\n"
            "• **Bold**, *italic*, `code`\n"
            "• Support links dan emoji\n\n"
            "❌ **Ketik /cancel untuk membatalkan**",
            parse_mode='Markdown'
        )
    return BROADCAST_MESSAGE

async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast message dengan progress tracking"""
    if not await admin_check(update, context):
        return ConversationHandler.END
    
    broadcast_text = update.message.text
    user_id = update.message.from_user.id
    
    # Get all active users
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE is_banned = 0')
            users = [row['user_id'] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error getting users for broadcast: {e}")
        await update.message.reply_text("❌ Gagal mengambil daftar user.")
        return ConversationHandler.END
    
    total_users = len(users)
    
    if total_users == 0:
        await update.message.reply_text("❌ Tidak ada user yang aktif.")
        return ConversationHandler.END
    
    # Confirm broadcast
    keyboard = [
        [InlineKeyboardButton("✅ Ya, Broadcast Sekarang", callback_data=f"confirm_broadcast:{user_id}")],
        [InlineKeyboardButton("❌ Batalkan", callback_data="cancel_broadcast")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    preview_text = broadcast_text[:200] + "..." if len(broadcast_text) > 200 else broadcast_text
    
    await update.message.reply_text(
        f"📢 **KONFIRMASI BROADCAST**\n\n"
        f"**Pesan:**\n{preview_text}\n\n"
        f"**Target:** {total_users} users\n\n"
        f"⚠️ **Yakin ingin melanjutkan?**",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    # Store broadcast data in context
    context.user_data['broadcast_data'] = {
        'text': broadcast_text,
        'total_users': total_users,
        'admin_id': user_id
    }
    
    return ConversationHandler.END

async def confirm_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast confirmation dan eksekusi"""
    query = update.callback_query
    await query.answer()
    
    if not await admin_check(update, context):
        return
    
    broadcast_data = context.user_data.get('broadcast_data')
    if not broadcast_data:
        await query.edit_message_text("❌ Data broadcast tidak ditemukan.")
        return
    
    broadcast_text = broadcast_data['text']
    total_users = broadcast_data['total_users']
    admin_id = broadcast_data['admin_id']
    
    # Get users list again to ensure freshness
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE is_banned = 0')
            users = [row['user_id'] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error getting users for broadcast: {e}")
        await query.edit_message_text("❌ Gagal mengambil daftar user.")
        return
    
    # Start broadcast process
    success_count = 0
    fail_count = 0
    failed_users = []
    
    progress_msg = await query.edit_message_text(
        f"📢 **Mengirim Broadcast...**\n\n"
        f"📝 **Pesan:** {broadcast_text[:100]}...\n"
        f"👥 **Target:** {total_users} users\n"
        f"✅ **Terkirim:** 0\n"
        f"❌ **Gagal:** 0\n"
        f"📊 **Progress:** 0%"
    )
    
    # Send to all users
    for index, user_id in enumerate(users):
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=broadcast_text,
                parse_mode='Markdown'
            )
            success_count += 1
        except Exception as e:
            fail_count += 1
            failed_users.append(user_id)
            logger.error(f"Failed to send broadcast to {user_id}: {e}")
        
        # Update progress every 10 sends or 10%
        if (index + 1) % 10 == 0 or (index + 1) == len(users):
            progress = ((index + 1) / len(users)) * 100
            try:
                await progress_msg.edit_text(
                    f"📢 **Mengirim Broadcast...**\n\n"
                    f"📝 **Pesan:** {broadcast_text[:100]}...\n"
                    f"👥 **Target:** {total_users} users\n"
                    f"✅ **Terkirim:** {success_count}\n"
                    f"❌ **Gagal:** {fail_count}\n"
                    f"📊 **Progress:** {progress:.1f}%"
                )
            except Exception as e:
                logger.error(f"Error updating progress: {e}")
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.1)
    
    # Log broadcast result
    await log_admin_action(
        admin_id, 
        "BROADCAST", 
        f"Success: {success_count}, Failed: {fail_count}, Total: {total_users}"
    )
    
    # Send final report
    keyboard = [
        [InlineKeyboardButton("📊 Lihat Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("⬅️ Menu Admin", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    success_rate = (success_count / total_users) * 100 if total_users > 0 else 0
    
    await progress_msg.edit_text(
        f"✅ **Broadcast Selesai!**\n\n"
        f"📝 **Pesan:** {broadcast_text[:100]}...\n"
        f"👥 **Total Target:** {total_users} users\n"
        f"✅ **Berhasil:** {success_count} users\n"
        f"❌ **Gagal:** {fail_count} users\n"
        f"📊 **Success Rate:** {success_rate:.1f}%\n\n"
        f"⏰ **Waktu:** {datetime.now().strftime('%H:%M:%S')}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel broadcast process"""
    await update.message.reply_text("❌ Broadcast dibatalkan.")
    return ConversationHandler.END

# ==================== CONVERSATION HANDLERS ====================
async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel editing process"""
    await update.message.reply_text("❌ Editing dibatalkan.")
    return ConversationHandler.END

def get_admin_conv_handler():
    """Return admin conversation handlers"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_produk_start, pattern="^admin_edit_produk$"),
            CallbackQueryHandler(broadcast_start, pattern="^admin_broadcast$")
        ],
        states={
            EDIT_MENU: [
                CallbackQueryHandler(edit_produk_menu_handler, pattern="^(edit_harga|edit_deskripsi|edit_status|admin_back|back_to_edit_menu)$")
            ],
            CHOOSE_PRODUCT: [
                CallbackQueryHandler(select_product_handler, pattern="^select_product:"),
                CallbackQueryHandler(edit_produk_start, pattern="^back_to_edit_menu$")
            ],
            EDIT_HARGA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_harga_handler)
            ],
            EDIT_DESKRIPSI: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_deskripsi_handler)
            ],
            BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler),
                CommandHandler('cancel', cancel_broadcast)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel_edit),
            CallbackQueryHandler(admin_menu, pattern="^admin_back$")
        ],
        allow_reentry=True
    )

def get_admin_handlers():
    """Return all admin handlers untuk registration"""
    return [
        CallbackQueryHandler(admin_callback_handler, pattern="^admin_"),
        CallbackQueryHandler(approve_topup_handler, pattern="^approve_topup:"),
        CallbackQueryHandler(reject_topup_handler, pattern="^reject_topup:"),
        CallbackQueryHandler(handle_status_change, pattern="^set_status:"),
        CallbackQueryHandler(handle_category_filter, pattern="^filter_category:"),
        CallbackQueryHandler(handle_order_filter, pattern="^filter_orders:"),
        CallbackQueryHandler(confirm_broadcast_handler, pattern="^confirm_broadcast:"),
        CallbackQueryHandler(cancel_broadcast, pattern="^cancel_broadcast$"),
        get_admin_conv_handler()
    ]
