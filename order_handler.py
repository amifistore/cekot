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
    ContextTypes,
    CommandHandler
)
import database
import config
import telegram
import os

logger = logging.getLogger(__name__)

# States
MENU, CHOOSING_GROUP, CHOOSING_PRODUCT, ENTER_TUJUAN, CONFIRM_ORDER = range(5)
PRODUCTS_PER_PAGE = 8

# Database path - FIX: Use consistent database path
DB_PATH = getattr(database, 'DB_PATH', 'bot_database.db')

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
    """Get products grouped by category from database"""
    try:
        # FIX: Use consistent database path
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT code, name, price, category, description, status, gangguan, kosong
            FROM products 
            WHERE status='active' AND gangguan=0 AND kosong=0
            ORDER BY category, name ASC
        """)
        products = c.fetchall()
        conn.close()

        logger.info(f"Found {len(products)} active products in database")
        
        groups = {}
        for code, name, price, category, description, status, gangguan, kosong in products:
            # Use category from database, fallback to code-based grouping
            group = category or "Lainnya"
            
            # Additional grouping for specific product codes if needed
            if code.startswith("BPAL"):
                group = "BPAL (Bonus Akrab L)"
            elif code.startswith("BPAXXL"):
                group = "BPAXXL (Bonus Akrab XXL)"
            elif code.startswith("XLA"):
                group = "XLA (Umum)"
            elif "pulsa" in name.lower():
                group = "Pulsa"
            elif "data" in name.lower() or "internet" in name.lower() or "kuota" in name.lower():
                group = "Internet"
            elif "listrik" in name.lower() or "pln" in name.lower():
                group = "Listrik"
            elif "game" in name.lower():
                group = "Game"
            elif "emoney" in name.lower() or "gopay" in name.lower() or "dana" in name.lower():
                group = "E-Money"
            
            if group not in groups:
                groups[group] = []
            
            groups[group].append({
                'code': code,
                'name': name,
                'price': price,
                'category': category,
                'description': description
            })
        
        # Sort groups alphabetically
        sorted_groups = {}
        for group in sorted(groups.keys()):
            sorted_groups[group] = groups[group]
            
        return sorted_groups
        
    except Exception as e:
        logger.error(f"Error getting grouped products from database: {e}")
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
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💸 Top Up Saldo", callback_data="menu_topup")], 
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ]),
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
        
        # Fallback to direct database check
        await get_stock_from_database(update, context)
        
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

async def get_stock_from_database(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get stock information from database"""
    query = update.callback_query
    
    try:
        # FIX: Use consistent database path
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT code, name, price, category, stock 
            FROM products 
            WHERE status='active' 
            ORDER BY category, name ASC
            LIMIT 50
        """)
        products = c.fetchall()
        conn.close()

        if not products:
            msg = "📭 Tidak ada produk aktif di database.\n\nℹ️ Admin dapat mengupdate produk melalui menu admin."
        else:
            msg = "📊 **STOK PRODUK DARI DATABASE**\n\n"
            current_category = ""
            
            for code, name, price, category, stock in products:
                if category != current_category:
                    msg += f"\n**{category.upper()}:**\n"
                    current_category = category
                
                stock_emoji = "✅" if stock > 0 else "❌"
                msg += f"{stock_emoji} {name} - Rp {price:,.0f} (Stok: {stock})\n"
            
            msg += f"\n📊 Total {len(products)} produk aktif"

    except Exception as e:
        logger.error(f"Error getting stock from database: {e}")
        msg = f"❌ Gagal mengambil data stok dari database: {str(e)}"

    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Stok", callback_data="menu_stock")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await safe_edit_message_text(query, msg, parse_mode='Markdown', reply_markup=reply_markup)

async def show_group_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show product groups menu from database"""
    try:
        groups = get_grouped_products()
        
        if not groups:
            await safe_edit_message_text(
                update.callback_query,
                "❌ Tidak ada produk yang tersedia saat ini.\n\n"
                "ℹ️ Silakan hubungi admin untuk mengupdate produk atau gunakan menu admin untuk sync produk dari provider.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Coba Lagi", callback_data="menu_order")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ])
            )
            return MENU
        
        keyboard = [
            [InlineKeyboardButton(f"{group} ({len(products)} produk)", callback_data=f"group_{group}")]
            for group in groups.keys()
        ]
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        total_products = sum(len(products) for products in groups.values())
        
        await safe_edit_message_text(
            update.callback_query,
            f"📦 *PILIH KATEGORI PRODUK*\n\n"
            f"📊 **Total {total_products} produk aktif**\n\n"
            f"Silakan pilih kategori produk yang diinginkan:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        context.user_data["groups"] = groups
        return CHOOSING_GROUP
        
    except Exception as e:
        logger.error(f"Error in show_group_menu: {e}")
        await safe_edit_message_text(
            update.callback_query,
            "❌ Error memuat daftar produk dari database. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return MENU

def get_products_keyboard_group(products, page=0):
    """Create paginated products keyboard"""
    total_pages = (len(products) - 1) // PRODUCTS_PER_PAGE + 1
    start = page * PRODUCTS_PER_PAGE
    end = start + PRODUCTS_PER_PAGE
    page_products = products[start:end]
    
    keyboard = []
    for prod in page_products:
        # Truncate long product names
        display_name = prod['name']
        if len(display_name) > 30:
            display_name = display_name[:27] + "..."
            
        btn_text = f"{display_name} - Rp {prod['price']:,.0f}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"prod_{prod['code']}")])
    
    # Navigation buttons
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data=f"page_{page-1}"))
    if page < total_pages - 1:
        navigation.append(InlineKeyboardButton("Selanjutnya ➡️", callback_data=f"page_{page+1}"))
    
    if navigation:
        keyboard.append(navigation)
    
    keyboard.append([InlineKeyboardButton("⬅️ Kembali ke Kategori", callback_data="back_to_categories")])
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
                f"❌ Tidak ada produk di kategori {group_name}.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali ke Kategori", callback_data="back_to_categories")]])
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
                f"❌ Tidak ada produk di kategori {group_name}.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali ke Kategori", callback_data="back_to_categories")]])
            )
            return CHOOSING_GROUP
        
        reply_markup, total_pages = get_products_keyboard_group(products, page)
        
        await safe_edit_message_text(
            query,
            f"🛒 *PILIH PRODUK - {group_name}*\n\n"
            f"📄 Halaman {page+1} dari {total_pages}\n"
            f"📦 Total {len(products)} produk\n\n"
            f"Silakan pilih produk:",
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
        elif data == "back_to_categories":
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
            f"📦 *Nama*: {found['name']}\n"
            f"🏷️ *Kode*: {found['code']}\n"
            f"📂 *Kategori*: {found['category']}\n"
            f"💰 *Harga*: Rp {found['price']:,.0f}\n\n"
            f"📄 *Deskripsi:*\n{desc}\n\n"
            f"Silakan masukkan nomor tujuan:\n"
            f"Contoh: 081234567890",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Kembali ke Produk", callback_data=f"group_{context.user_data.get('current_group', '')}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
            ]),
            parse_mode="Markdown"
        )
        return ENTER_TUJUAN
        
    except Exception as e:
        logger.error(f"Error in choose_product: {e}")
        await safe_edit_message_text(
            query,
            "❌ Error memilih produk. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return CHOOSING_PRODUCT

async def enter_tujuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle destination number input"""
    try:
        tujuan = update.message.text.strip()
        
        # Basic phone number validation
        if not tujuan.isdigit() or len(tujuan) < 10 or len(tujuan) > 15:
            await update.message.reply_text(
                "❌ Format nomor tidak valid.\n\n"
                "Silakan masukkan nomor tujuan yang valid (10-15 digit):\n"
                "Contoh: 081234567890",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Kembali ke Produk", callback_data=f"group_{context.user_data.get('current_group', '')}")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ])
            )
            return ENTER_TUJUAN
        
        context.user_data['tujuan'] = tujuan
        product = context.user_data.get('selected_product', {})
        
        # Check user balance
        user_id = str(update.message.from_user.id)
        saldo = database.get_user_saldo(user_id)
        
        if saldo < product.get('price', 0):
            await update.message.reply_text(
                f"❌ Saldo tidak mencukupi!\n\n"
                f"💰 Saldo Anda: Rp {saldo:,.0f}\n"
                f"💳 Harga produk: Rp {product.get('price', 0):,.0f}\n"
                f"📊 Kekurangan: Rp {product.get('price', 0) - saldo:,.0f}\n\n"
                f"Silakan top up saldo terlebih dahulu.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💸 Top Up Saldo", callback_data="menu_topup")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
                ]),
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
        # Show confirmation
        keyboard = [
            [
                InlineKeyboardButton("✅ Konfirmasi Order", callback_data="confirm_order"),
                InlineKeyboardButton("❌ Batalkan", callback_data="cancel_order")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📋 *KONFIRMASI ORDER*\n\n"
            f"📦 *Produk*: {product.get('name', 'N/A')}\n"
            f"🏷️ *Kode*: {product.get('code', 'N/A')}\n"
            f"💰 *Harga*: Rp {product.get('price', 0):,.0f}\n"
            f"📱 *Tujuan*: {tujuan}\n\n"
            f"💳 *Saldo Anda*: Rp {saldo:,.0f}\n"
            f"💰 *Saldo Setelah*: Rp {saldo - product.get('price', 0):,.0f}\n\n"
            f"Apakah Anda yakin ingin memesan?",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        return CONFIRM_ORDER
        
    except Exception as e:
        logger.error(f"Error in enter_tujuan: {e}")
        await update.message.reply_text(
            "❌ Error memproses nomor tujuan. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return ENTER_TUJUAN

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle order confirmation"""
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        
        if data == "cancel_order":
            await safe_edit_message_text(
                query,
                "❌ Order dibatalkan.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
            )
            return ConversationHandler.END
        
        # Process the order
        product = context.user_data.get('selected_product', {})
        tujuan = context.user_data.get('tujuan', '')
        user_id = str(query.from_user.id)
        
        # Here you would typically call the provider API to process the order
        # For now, we'll simulate a successful order
        
        # Deduct balance
        price = product.get('price', 0)
        current_saldo = database.get_user_saldo(user_id)
        new_saldo = current_saldo - price
        
        # Update user balance in database
        # FIX: Use consistent database path
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET saldo = ? WHERE telegram_id = ?", (new_saldo, user_id))
        conn.commit()
        conn.close()
        
        # Create order record (you might want to create an orders table)
        order_id = str(uuid.uuid4())[:8].upper()
        
        await safe_edit_message_text(
            query,
            f"✅ *ORDER BERHASIL!*\n\n"
            f"📦 *Produk*: {product.get('name', 'N/A')}\n"
            f"🏷️ *Kode*: {product.get('code', 'N/A')}\n"
            f"💰 *Harga*: Rp {price:,.0f}\n"
            f"📱 *Tujuan*: {tujuan}\n"
            f"🆔 *Order ID*: {order_id}\n\n"
            f"💳 *Saldo Awal*: Rp {current_saldo:,.0f}\n"
            f"💳 *Saldo Akhir*: Rp {new_saldo:,.0f}\n\n"
            f"⏰ *Waktu*: {database.get_current_timestamp()}\n\n"
            f"Terima kasih telah berbelanja!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Beli Lagi", callback_data="menu_order")]]),
            parse_mode="Markdown"
        )
        
        # Clear user data
        context.user_data.clear()
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in confirm_order: {e}")
        await safe_edit_message_text(
            query,
            "❌ Error memproses order. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
        )
        return CONFIRM_ORDER

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel order process"""
    query = update.callback_query
    await query.answer()
    
    await safe_edit_message_text(
        query,
        "❌ Order dibatalkan.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
    )
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the entire conversation"""
    await update.message.reply_text(
        "❌ Proses order dibatalkan.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]])
    )
    return ConversationHandler.END

# Conversation handler
order_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(menu_handler, pattern="^menu_order$")],
    states={
        MENU: [CallbackQueryHandler(menu_handler, pattern="^menu_")],
        CHOOSING_GROUP: [
            CallbackQueryHandler(choose_group, pattern="^group_"),
            CallbackQueryHandler(menu_handler, pattern="^menu_")
        ],
        CHOOSING_PRODUCT: [
            CallbackQueryHandler(choose_product, pattern="^(prod_|page_|back_to_categories|menu_)"),
        ],
        ENTER_TUJUAN: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, enter_tujuan),
        ],
        CONFIRM_ORDER: [
            CallbackQueryHandler(confirm_order, pattern="^(confirm_order|cancel_order)$"),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_conversation),
        CallbackQueryHandler(cancel_conversation, pattern="^cancel$"),
    ],
    allow_reentry=True
)

# Command handler for /order
async def order_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /order command"""
    return await show_group_menu(update, context)
