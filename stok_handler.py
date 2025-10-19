import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database

logger = logging.getLogger(__name__)

async def stock_akrab_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk cek stok produk"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Get active products count
        active_products = database.get_active_products_count()
        
        # Get products from database
        conn = database.db_manager.conn if hasattr(database.db_manager, 'conn') else None
        if not conn:
            import sqlite3
            conn = sqlite3.connect(database.db_manager.db_path)
        
        c = conn.cursor()
        c.execute("""
            SELECT name, category, price, stock 
            FROM products 
            WHERE status = 'active' 
            ORDER BY category, name 
            LIMIT 50
        """)
        products = c.fetchall()
        conn.close()
        
        if not products:
            message = "📊 **STOK PRODUK**\n\n" \
                     "📭 Tidak ada produk aktif saat ini.\n\n" \
                     "ℹ️ Admin dapat mengupdate produk melalui menu admin."
        else:
            message = "📊 **STOK PRODUK**\n\n"
            current_category = ""
            
            for name, category, price, stock in products:
                if category != current_category:
                    message += f"\n**{category.upper()}:**\n"
                    current_category = category
                
                stock_emoji = "✅" if stock > 0 else "❌"
                message += f"{stock_emoji} {name} - Rp {price:,.0f}\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="menu_stock")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in stock_akrab_callback: {e}")
        await query.message.reply_text("❌ Gagal memuat data stok.")

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /stock"""
    try:
        active_products = database.get_active_products_count()
        
        message = f"📊 **STOK PRODUK**\n\n" \
                 f"Total produk aktif: **{active_products}**\n\n" \
                 f"Klik tombol di bawah untuk melihat detail stok:"
        
        keyboard = [
            [InlineKeyboardButton("📋 Lihat Detail Stok", callback_data="menu_stock")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in stock_command: {e}")
        await update.message.reply_text("❌ Gagal memuat data stok.")
