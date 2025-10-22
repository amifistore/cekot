#!/usr/bin/env python3
"""
History Handler - Untuk menangani riwayat order dan transaksi
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
import database
from datetime import datetime

logger = logging.getLogger(__name__)

async def show_order_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user order history"""
    query = update.callback_query
    await query.answer()
    
    try:
        user_id = str(query.from_user.id)
        
        # Get user orders
        orders = database.get_user_orders(user_id, limit=10)
        
        if not orders:
            await query.edit_message_text(
                "📋 *RIWAYAT ORDER*\n\n"
                "Anda belum memiliki riwayat order.\n"
                "Silakan melakukan order terlebih dahulu.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛒 Belanja Sekarang", callback_data="main_menu_order")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
                ])
            )
            return
        
        # Format orders for display
        orders_text = "📋 *RIWAYAT ORDER TERAKHIR*\n\n"
        
        for i, order in enumerate(orders[:5], 1):  # Show last 5 orders
            status_emoji = {
                'completed': '✅',
                'pending': '⏳', 
                'processing': '🔄',
                'failed': '❌',
                'refunded': '💰',
                'cancelled': '🚫'
            }.get(order['status'], '📦')
            
            # Handle date format
            try:
                if 'T' in order['created_at']:
                    order_date = datetime.fromisoformat(order['created_at'].replace('Z', '+00:00')).strftime('%d/%m/%Y %H:%M')
                else:
                    order_date = datetime.strptime(order['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M')
            except:
                order_date = order['created_at']
            
            orders_text += (
                f"{status_emoji} *Order #{order['id']}*\n"
                f"📦 {order['product_name']}\n"
                f"💰 Rp {order['price']:,}\n"
                f"📮 {order['customer_input']}\n"
                f"🕒 {order_date}\n"
                f"📊 Status: {order['status'].upper()}\n"
            )
            
            if order.get('sn'):
                orders_text += f"🔢 SN: `{order['sn']}`\n"
            
            if order.get('note'):
                orders_text += f"📝 Note: {order['note']}\n"
            
            orders_text += "\n"
        
        if len(orders) > 5:
            orders_text += f"📖 *Dan {len(orders) - 5} order lainnya...*\n\n"
        
        orders_text += f"📊 Total Order: {len(orders)} order"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="main_menu_history")],
            [InlineKeyboardButton("🛒 Order Lagi", callback_data="main_menu_order")],
            [InlineKeyboardButton("💰 Cek Saldo", callback_data="main_menu_balance")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
        ]
        
        await query.edit_message_text(
            orders_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error showing order history: {e}")
        await query.edit_message_text(
            "❌ Error memuat riwayat order. Silakan coba lagi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Coba Lagi", callback_data="main_menu_history")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu_main")]
            ])
        )

def get_history_handlers():
    """Return handlers for history features"""
    return [
        CallbackQueryHandler(show_order_history, pattern="^main_menu_history$")
    ]
