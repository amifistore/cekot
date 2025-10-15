import logging
import uuid
import requests
import aiohttp
import asyncio
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
import database
import config
import telegram

logger = logging.getLogger(__name__)

# States
MENU, CHOOSING_GROUP, CHOOSING_PRODUCT, ENTER_TUJUAN, CONFIRM_ORDER = range(5)
PRODUCTS_PER_PAGE = 8

# PATCH: Helper agar edit_message_text tidak error jika "Message is not modified"
async def safe_edit_message_text(callback_query, *args, **kwargs):
    """Safely edit message text with error handling"""
    try:
        await callback_query.edit_message_text(*args, **kwargs)
        return True
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e):
            # Ignore this specific error
            return True
        elif "Message can't be deleted" in str(e):
            # Try sending new message instead
            try:
                await callback_query.message.reply_text(*args, **kwargs)
                return True
            except Exception as send_error:
                logger.error(f"Failed to send new message: {send_error}")
                return False
        logger.error(f"Error editing message: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in safe_edit_message_text: {e}")
        return False

async def safe_reply_message(update, *args, **kwargs):
    """Safely reply to message with error handling"""
    try:
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(*args, **kwargs)
            return True
        elif hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.reply_text(*args, **kwargs)
            return True
        return False
    except Exception as e:
        logger.error(f"Error replying to message: {e}")
        return False

def get_grouped_products():
    """Get products grouped by category with error handling"""
    try:
        conn = sqlite3.connect(database.DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT code, name, price, category, description, status, gangguan, kosong
            FROM products
            WHERE status='active' AND gangguan=0 AND kosong=0
            ORDER BY code ASC
        """)
        products = c.fetchall()
        conn.close()

        groups = {}
        for code, name, price, category, description, status, gangguan, kosong in products:
            if code.startswith("BPAL"):
                group = "BPAL (Bonus Akrab L)"
            elif code.startswith("BPAXXL"):
                group = "BPAXXL (Bonus Akrab XXL)"
            elif code.startswith("XLA"):
                group = "XLA (Umum)"
            else:
                group = category or "Lainnya"
            
            if group not in groups:
                groups[group] = []
            
            groups[group].append({
                'code': code,
                'name': name,
                'price': price,
                'category': category,
                'description': description
            })
        return groups
    except Exception as e:
        logger.error(f"Error getting grouped products: {e}")
        return {}

async def menu_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show main menu"""
    try:
        user = getattr(update, 'effective_user', None)
        if user is None and hasattr(update, "callback_query"):
            user = getattr(update.callback_query, "from_user", None)
        
        if not user:
            await safe_reply_message(update, "❌ Error: Tidak dapat mengidentifikasi pengguna.")
            return MENU
        
        saldo = 0
        try:
            user_id = str(user.id)
            database.get_or_create_user(user_id, user.username or "", user.full_name or "")
            saldo = database.get_user_saldo(user_id)
        except Exception as e:
            logger.error(f"Error getting user saldo: {e}")
            saldo = 0
        
        keyboard = [
            [InlineKeyboardButton("🛒 Beli Produk", callback_data="menu_order")],
            [InlineKeyboardButton("💳 Cek Saldo", callback_data="menu_saldo")],
            [InlineKeyboardButton("💸 Top Up Saldo", callback_data="menu_topup")],
            [InlineKeyboardButton("📊 Cek Stok", callback_data="menu_stock")],
            [InlineKeyboardButton("📞 Bantuan", callback_data="menu_help")]
        ]
        
        # Check if user is admin
        admin_ids = getattr(config, 'ADMIN_TELEGRAM_IDS', [])
        if user and str(user.id) in admin_ids:
            keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="menu_admin")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = (
            f"🤖 *Selamat Datang!*\n\n"
            f"Halo, *{user.full_name or user.username or 'User'}*!\n"
            f"💰 Saldo Anda: *Rp {saldo:,.0f}*\n\n"
            f"Pilih menu di bawah:"
        )
        
        if hasattr(update, "callback_query") and update.callback_query:
            await safe_edit_message_text(update.callback_query, text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await safe_reply_message(update, text, reply_markup=reply_markup, parse_mode="Markdown")
            
        return MENU
        
    except Exception as e:
        logger.error(f"Error in menu_main: {e}")
        await safe_reply_message(update, "❌ Terjadi error. Silakan coba lagi.")
        return MENU

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main menu handler"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    logger.info(f"Menu callback received: {data}")
    
    try:
        if data == "menu_order":
            return await show_group_menu(update, context)
        elif data == "menu_saldo":
            user_id = str(query.from_user.id)
            saldo = database.get_user_saldo(user_id)
            await safe_edit_message_text(
                query,
                f"💳 *SALDO ANDA*\n\nSaldo: *Rp {saldo:,.0f}*\n\nGunakan menu Top Up untuk menambah saldo.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💸 Top Up Saldo", callback_data="menu_topup")], [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
                parse_mode="Markdown"
            )
            return MENU
        elif data == "menu_help":
            await safe_edit_message_text(
                query,
                "📞 *BANTUAN*\n\n"
                "Jika mengalami masalah, hubungi admin.\n\n"
                "**Cara Order:**\n"
                "1. Pilih *Beli Produk*\n"
                "2. Pilih grup produk\n" 
                "3. Pilih produk yang diinginkan\n"
                "4. Masukkan nomor tujuan\n"
                "5. Konfirmasi order\n\n"
                "**Fitur Lain:**\n"
                "• Top Up Saldo\n"
                "• Cek Stok Produk\n"
                "• Riwayat Transaksi",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
                parse_mode="Markdown"
            )
            return MENU
        elif data == "menu_topup":
            # Langsung arahkan ke topup_handler
            try:
                from topup_handler import show_topup_menu
                await show_topup_menu(update, context)
                return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error loading topup menu: {e}")
                await safe_edit_message_text(
                    query,
                    "❌ Error memuat menu topup. Silakan gunakan command /topup",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
                )
                return MENU
        elif data == "menu_stock":
            await show_stock_menu(update, context)
            return MENU
        elif data == "menu_admin":
            admin_ids = getattr(config, 'ADMIN_TELEGRAM_IDS', [])
            if str(query.from_user.id) in admin_ids:
                try:
                    from admin_handler import admin_menu
                    await admin_menu(update, context)
                    return ConversationHandler.END
                except Exception as e:
                    logger.error(f"Error loading admin panel: {e}")
                    await safe_edit_message_text(
                        query,
                        "❌ Error memuat panel admin. Silakan gunakan command /admin",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
                    )
                    return MENU
            else:
                await query.answer("❌ Anda bukan admin!", show_alert=True)
                return MENU
        elif data == "menu_main":
            return await menu_main(update, context)
        else:
            await query.answer("❌ Menu tidak dikenal!")
            return MENU
            
    except Exception as e:
        logger.error(f"Error in menu_handler: {e}")
        await safe_edit_message_text(
            query,
            "❌ Terjadi error. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return MENU

async def show_stock_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show stock menu with fallback"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Try to use stok_handler if available
        try:
            import stok_handler
            if hasattr(stok_handler, 'stock_akrab_callback'):
                await stok_handler.stock_akrab_callback(update, context)
                return
        except ImportError:
            pass
        
        # Fallback to direct API call
        await get_stock_fallback(update, context)
        
    except Exception as e:
        logger.error(f"Error showing stock menu: {e}")
        await safe_edit_message_text(
            query,
            "❌ Gagal mengambil data stok. Silakan coba lagi nanti.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh Stok", callback_data="menu_stock")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
            ])
        )

async def get_stock_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback stock check using aiohttp"""
    query = update.callback_query
    
    try:
        api_key = getattr(config, 'API_KEY_PROVIDER', '')
        url = "https://panel.khfy-store.com/api_v3/cek_stock_akrab"
        
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params={'api_key': api_key} if api_key else {}) as response:
                if response.status == 200:
                    data = await response.json()
                else:
                    data = None
        
        if data and data.get("ok", False):
            stocks = data.get("data", {})
            if stocks:
                msg = "📊 **STOK PRODUK AKRAB**\n\n"
                for product_name, stock_info in stocks.items():
                    stock = stock_info.get("stock", 0)
                    status = "✅ TERSEDIA" if stock > 0 else "❌ HABIS"
                    msg += f"• **{product_name}**: {stock} pcs - {status}\n"
                msg += f"\n⏰ **Update**: {data.get('timestamp', 'N/A')}"
            else:
                msg = "📭 Tidak ada data stok yang tersedia."
        else:
            msg = "❌ Gagal mengambil data stok dari provider."
            
    except asyncio.TimeoutError:
        msg = "⏰ Timeout: Gagal mengambil data stok. Silakan coba lagi."
    except Exception as e:
        logger.error(f"Error getting stock: {e}")
        msg = f"❌ **Gagal mengambil data stok:**\n{str(e)}"

    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Stok", callback_data="menu_stock")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await safe_edit_message_text(query, msg, parse_mode='Markdown', reply_markup=reply_markup)

async def show_group_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show product groups menu"""
    try:
        groups = get_grouped_products()
        
        if not groups:
            await safe_edit_message_text(
                update.callback_query,
                "❌ Tidak ada produk yang tersedia saat ini.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
            return MENU
        
        keyboard = [
            [InlineKeyboardButton(group, callback_data=f"group_{group}")]
            for group in sorted(groups.keys())
        ]
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await safe_edit_message_text(
            update.callback_query,
            "📦 *PILIH GRUP PRODUK*\n\nSilakan pilih grup kuota/produk yang diinginkan:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        context.user_data["groups"] = groups
        return CHOOSING_GROUP
        
    except Exception as e:
        logger.error(f"Error in show_group_menu: {e}")
        await safe_edit_message_text(
            update.callback_query,
            "❌ Error memuat daftar produk. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return MENU

def get_products_keyboard_group(products, page=0):
    """Create paginated products keyboard"""
    total_pages = (len(products) - 1) // PRODUCTS_PER_PAGE + 1
    start = page * PRODUCTS_PER_PAGE
    end = start + PRODUCTS_PER_PAGE
    page_products = products[start:end]
    
    keyboard = [
        [InlineKeyboardButton(
            f"{prod['name']} ({prod['code']}) - Rp {prod['price']:,.0f}",
            callback_data=f"prod_{prod['code']}")
        ] for prod in page_products
    ]
    
    # Navigation buttons
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{page-1}"))
    if page < total_pages - 1:
        navigation.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{page+1}"))
    
    if navigation:
        keyboard.append(navigation)
    
    keyboard.append([InlineKeyboardButton("⬅️ Kembali ke Grup", callback_data="menu_order")])
    keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")])
    
    return InlineKeyboardMarkup(keyboard), total_pages

async def choose_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle group selection"""
    query = update.callback_query
    await query.answer()
    
    try:
        group_name = query.data.replace("group_", "")
        groups = context.user_data.get("groups", {})
        products = groups.get(group_name, [])
        
        if not products:
            await safe_edit_message_text(
                query,
                f"❌ Tidak ada produk di grup {group_name}.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali ke Grup", callback_data="menu_order")]])
            )
            return CHOOSING_GROUP
        
        context.user_data["current_group"] = group_name
        context.user_data["product_list"] = products
        context.user_data["product_page"] = 0
        
        return await show_product_in_group(query, context, page=0)
        
    except Exception as e:
        logger.error(f"Error in choose_group: {e}")
        await safe_edit_message_text(
            query,
            "❌ Error memuat produk. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return MENU

async def show_product_in_group(query, context, page=0):
    """Show products in selected group"""
    try:
        products = context.user_data.get("product_list", [])
        group_name = context.user_data.get("current_group", "")
        
        if not products:
            await safe_edit_message_text(
                query,
                f"❌ Tidak ada produk di grup {group_name}.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali ke Grup", callback_data="menu_order")]])
            )
            return CHOOSING_GROUP
        
        reply_markup, total_pages = get_products_keyboard_group(products, page)
        
        await safe_edit_message_text(
            query,
            f"🛒 *PILIH PRODUK - {group_name}*\n\nHalaman {page+1} dari {total_pages}\nSilakan pilih produk:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        context.user_data["product_page"] = page
        return CHOOSING_PRODUCT
        
    except Exception as e:
        logger.error(f"Error in show_product_in_group: {e}")
        await safe_edit_message_text(
            query,
            "❌ Error menampilkan produk. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return MENU

async def choose_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product selection"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    try:
        if data == "menu_main":
            return await menu_main(update, context)
        elif data == "menu_order":
            return await show_group_menu(update, context)
        elif data.startswith("page_"):
            page = int(data.split("_")[1])
            return await show_product_in_group(query, context, page)
        elif not data.startswith("prod_"):
            await safe_edit_message_text(
                query, 
                "❌ Produk tidak valid.", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
            return CHOOSING_PRODUCT
        
        # Handle product selection
        kode_produk = data.replace("prod_", "")
        products = context.user_data.get("product_list", [])
        found = next((p for p in products if p['code'] == kode_produk), None)
        
        if not found:
            await safe_edit_message_text(
                query, 
                "❌ Produk tidak ditemukan atau tidak tersedia.", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
            return CHOOSING_PRODUCT
        
        context.user_data['selected_product'] = found
        desc = found['description'] or "(Deskripsi produk tidak tersedia)"
        
        await safe_edit_message_text(
            query,
            f"🛒 *PRODUK DIPILIH*\n\n"
            f"*Nama*: {found['name']}\n"
            f"*Kode*: {found['code']}\n"
            f"*Kategori*: {found['category']}\n"
            f"*Harga*: Rp {found['price']:,.0f}\n\n"
            f"*Deskripsi:*\n{desc}\n\n"
            f"Masukkan nomor tujuan (contoh: 081234567890):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]),
            parse_mode="Markdown"
        )
        return ENTER_TUJUAN
   
